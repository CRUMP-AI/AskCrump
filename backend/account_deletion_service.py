"""Durable account deletion and private Storage cleanup.

Account deletion is deliberately a small durable workflow rather than one
request-sized transaction. Supabase signed and resumable upload credentials can
outlive the browser session that requested deletion, so a service-role-only job
keeps sweeping the exact owner prefix after the account row is gone.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import logging
from typing import Any, Callable
from urllib.parse import quote
from uuid import uuid4

import httpx

from .db import SupabaseDB, eq, lte
from .file_service import FileService, FileServiceError


logger = logging.getLogger("askcrump.account_deletion")


@dataclass(frozen=True, slots=True)
class DeletionProgress:
    account_deleted: bool
    cleanup_complete: bool
    retry_scheduled: bool
    code: str | None = None


class RevenueCatCleanupState(str, Enum):
    NOT_REQUIRED = "not_required"
    UNCONFIRMED = "unconfirmed"
    QUEUED = "queued"
    ABSENT = "absent"


class AccountDeletionService:
    """Fence an account, delete it, then sweep late owner-prefixed uploads."""

    # Signed upload tokens can remain usable for two hours and an upload started
    # with one can keep a resumable URL for up to 24 hours. Thirty hours leaves a
    # safety margin and the hourly worker performs the final confirmed sweep.
    LATE_UPLOAD_SAFETY_HOURS = 30
    RETRY_MINUTES = 15
    SWEEP_INTERVAL_HOURS = 1
    FENCE_RECONCILE_MINUTES = 15
    PROCESS_LEASE_MINUTES = 30

    def __init__(
        self,
        db: SupabaseDB,
        files: FileService,
        *,
        now: Callable[[], datetime] | None = None,
        revenuecat_secret_api_key: str | None = None,
        revenuecat_required: bool = False,
    ) -> None:
        self.db = db
        self.files = files
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._revenuecat_secret_api_key = revenuecat_secret_api_key
        self._revenuecat_required = revenuecat_required

    @staticmethod
    def _rows(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            return [value]
        return []

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    async def _job(self, user_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "account_deletion_jobs",
            columns="*",
            filters={"user_id": eq(user_id)},
        )

    async def _user(self, user_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "users",
            columns=(
                "id,deleted_at,account_deletion_token,subscription_provider,"
                "native_billing_identity_possible_at"
            ),
            filters={"id": eq(user_id)},
        )

    def _native_cleanup_required(
        self,
        user: dict[str, Any] | None,
        job: dict[str, Any],
    ) -> bool:
        return bool(
            self._revenuecat_required
            or job.get("native_billing_identity_possible")
            or job.get("last_error_code") in {
                "REVENUECAT_CLEANUP_UNCONFIRMED",
                "REVENUECAT_CLEANUP_QUEUED",
                "REVENUECAT_IDENTITY_MARK_UNCONFIRMED",
            }
            or (
                user
                and (
                    user.get("native_billing_identity_possible_at")
                    or user.get("subscription_provider") == "revenuecat"
                )
            )
        )

    async def _persist_native_cleanup_requirement(
        self,
        user: dict[str, Any] | None,
        job: dict[str, Any],
        *,
        provider_customer_possible: bool = False,
    ) -> bool:
        """Snapshot native identity evidence before the users row can vanish."""
        if job.get("native_billing_identity_possible"):
            return True
        if not provider_customer_possible and not self._native_cleanup_required(user, job):
            return True
        try:
            if await self._update_job(
                job, {"native_billing_identity_possible": True}
            ):
                job["native_billing_identity_possible"] = True
                return True
        except Exception:
            logger.exception("Native identity deletion-job write was ambiguous")
        try:
            current = await self._job(str(job.get("user_id") or ""))
        except Exception:
            logger.exception("Native identity deletion-job readback failed")
            return False
        confirmed = bool(
            current
            and str(current.get("operation_token") or "")
            == str(job.get("operation_token") or "")
            and (
                not job.get("_processing_claim")
                or int(current.get("attempts") or 0) == int(job.get("attempts") or 0)
            )
            and current.get("native_billing_identity_possible")
            and not current.get("completed_at")
        )
        if confirmed:
            job["native_billing_identity_possible"] = True
        return confirmed

    async def _ensure_revenuecat_deleted(
        self,
        owner_id: str,
        user: dict[str, Any] | None,
        job: dict[str, Any],
    ) -> RevenueCatCleanupState:
        """Distinguish a queued deletion from confirmed provider absence."""
        key = self._revenuecat_secret_api_key
        if not key:
            # A native customer must remain fenced and retryable if the server
            # key is unavailable. The durable marker remains authoritative even
            # if the native-billing release flag is switched off later.
            return (
                RevenueCatCleanupState.UNCONFIRMED
                if self._native_cleanup_required(user, job)
                else RevenueCatCleanupState.NOT_REQUIRED
            )
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.delete(
                    f"https://api.revenuecat.com/v1/subscribers/{quote(owner_id, safe='')}",
                    headers={"Authorization": f"Bearer {key}"},
                )
        except httpx.HTTPError:
            logger.exception("RevenueCat customer cleanup request failed")
            return RevenueCatCleanupState.UNCONFIRMED
        if response.status_code == 200:
            # RevenueCat queues v1 customer deletion asynchronously. A later
            # 404, not this accepted request, permits final tombstone purge.
            return RevenueCatCleanupState.QUEUED
        if response.status_code == 404:
            return RevenueCatCleanupState.ABSENT
        logger.error(
            "RevenueCat customer cleanup was not accepted status=%s",
            response.status_code,
        )
        return RevenueCatCleanupState.UNCONFIRMED

    @staticmethod
    def _job_identity(job: dict[str, Any]) -> tuple[str, str]:
        return (
            str(job.get("user_id") or "").strip(),
            str(job.get("operation_token") or "").strip(),
        )

    async def _update_job(self, job: dict[str, Any], values: dict[str, Any]) -> bool:
        user_id, token = self._job_identity(job)
        if not user_id or not token:
            return False
        filters = {
            "user_id": eq(user_id),
            "operation_token": eq(token),
            "completed_at": "is.null",
        }
        if "attempts" in job:
            # A later request or cron worker may already own a newer attempt.
            # Never let an older snapshot overwrite its provider state.
            filters["attempts"] = eq(int(job.get("attempts") or 0))
        updated = await self.db.update(
            "account_deletion_jobs",
            {**values, "updated_at": self._iso(self._now())},
            filters=filters,
            retry_transient=True,
        )
        return any(
            str(row.get("user_id") or "") == user_id
            and str(row.get("operation_token") or "") == token
            for row in self._rows(updated)
        )

    async def _claim_due_job(self, job: dict[str, Any]) -> bool:
        """Lease one processing generation across request and cron workers."""
        user_id, token = self._job_identity(job)
        now = self._now()
        due_at = self._parse_time(job.get("next_attempt_at"))
        if not user_id or not token or not due_at or due_at > now:
            return False
        previous_attempts = max(0, int(job.get("attempts") or 0))
        claimed_attempts = previous_attempts + 1
        lease_until = self._iso(now + timedelta(minutes=self.PROCESS_LEASE_MINUTES))
        try:
            updated = await self.db.update(
                "account_deletion_jobs",
                {
                    "attempts": claimed_attempts,
                    "next_attempt_at": lease_until,
                    "updated_at": self._iso(now),
                },
                filters={
                    "user_id": eq(user_id),
                    "operation_token": eq(token),
                    "completed_at": "is.null",
                    "attempts": eq(previous_attempts),
                    "next_attempt_at": lte(self._iso(now)),
                },
                retry_transient=True,
            )
        except Exception:
            # A write may have committed before its response was lost. Waiting
            # for the lease is safe; guessing ownership could purge a newer job.
            logger.exception("Account deletion processing claim was unconfirmed")
            return False
        claimed = any(
            str(row.get("user_id") or "") == user_id
            and str(row.get("operation_token") or "") == token
            and int(row.get("attempts") or 0) == claimed_attempts
            for row in self._rows(updated)
        )
        if claimed:
            job["attempts"] = claimed_attempts
            job["next_attempt_at"] = lease_until
            job["_processing_claim"] = True
        return claimed

    async def _best_effort_job_update(
        self,
        job: dict[str, Any],
        values: dict[str, Any],
    ) -> bool:
        try:
            return await self._update_job(job, values)
        except Exception:
            logger.exception("Account deletion job state update was not confirmed")
            return False

    async def _delete_completed_job(self, job: dict[str, Any]) -> bool:
        """Purge the content-free tombstone after its final confirmed sweep."""
        user_id, token = self._job_identity(job)
        if not user_id or not token:
            return False
        try:
            deleted = await self.db.delete(
                "account_deletion_jobs",
                filters={
                    "user_id": eq(user_id),
                    "operation_token": eq(token),
                    "attempts": eq(int(job.get("attempts") or 0)),
                    "next_attempt_at": eq(str(job.get("next_attempt_at") or "")),
                },
            )
            if any(
                str(row.get("user_id") or "") == user_id
                and str(row.get("operation_token") or "") == token
                for row in self._rows(deleted)
            ):
                return True
        except Exception:
            logger.exception("Completed account deletion tombstone purge was ambiguous")
        try:
            current = await self._job(user_id)
        except Exception:
            return False
        return current is None

    async def _schedule_retry(self, job: dict[str, Any], code: str) -> None:
        now = self._now()
        attempts = max(0, int(job.get("attempts") or 0))
        if not job.get("_processing_claim"):
            attempts += 1
        updated = await self._best_effort_job_update(
            job,
            {
                "state": "retry_pending",
                "attempts": attempts,
                "last_error_code": code[:80],
                "next_attempt_at": self._iso(now + timedelta(minutes=self.RETRY_MINUTES)),
            },
        )
        if updated:
            job["attempts"] = attempts

    async def begin(self, *, user_id: str) -> dict[str, Any]:
        """Persist an operation token, then establish and reconcile its fence."""
        owner_id = str(user_id or "").strip()
        if not owner_id:
            raise RuntimeError("Account deletion owner is missing.")
        now = self._now()
        started_at = self._iso(now)
        job_payload: dict[str, Any] = {
            "user_id": owner_id,
            "operation_token": str(uuid4()),
            "state": "fencing",
            "fenced_at": started_at,
            "finalize_after": self._iso(
                now + timedelta(hours=self.LATE_UPLOAD_SAFETY_HOURS)
            ),
            "next_attempt_at": self._iso(now + timedelta(minutes=self.RETRY_MINUTES)),
            "attempts": 0,
            "last_error_code": None,
            "native_billing_identity_possible": self._revenuecat_required,
            "updated_at": started_at,
        }
        try:
            inserted = self._rows(
                await self.db.insert("account_deletion_jobs", job_payload)
            )
            job = inserted[0] if inserted else await self._job(owner_id)
            if not job:
                raise RuntimeError("Account deletion job persistence was not confirmed.")
        except Exception:
            # A transport failure can occur after Postgres committed the insert.
            # Read back by the unique owner key before deciding it failed.
            existing = await self._job(owner_id)
            if not existing:
                raise
            current_user = await self._user(owner_id)
            existing_token = str(existing.get("operation_token") or "")
            existing_fence_matches = bool(
                current_user
                and current_user.get("deleted_at")
                and str(current_user.get("account_deletion_token") or "")
                == existing_token
            )
            active_without_fence = bool(
                current_user
                and not current_user.get("deleted_at")
                and not current_user.get("account_deletion_token")
            )
            existing_started = self._parse_time(
                existing.get("created_at") or existing.get("fenced_at")
            )
            existing_is_recent = bool(
                existing_started
                and self._now() - existing_started
                < timedelta(minutes=self.FENCE_RECONCILE_MINUTES)
                and not existing.get("completed_at")
            )
            if active_without_fence and existing_is_recent:
                # Concurrent callers converge on the first durable token. This
                # prevents one request from replacing the job while another is
                # committing that token to users.account_deletion_token.
                job = existing
            elif active_without_fence:
                # A stale or abandoned operation must not shorten the late-upload
                # window for a new request. Reset the durable row in place because
                # user_id is intentionally its stable primary key.
                reset_payload = {
                    **job_payload,
                    "created_at": started_at,
                    "account_deleted_at": None,
                    "completed_at": None,
                }
                try:
                    reset = self._rows(
                        await self.db.update(
                            "account_deletion_jobs",
                            reset_payload,
                            filters={
                                "user_id": eq(owner_id),
                                "operation_token": eq(existing_token),
                            },
                            retry_transient=True,
                        )
                    )
                    job = reset[0] if reset else await self._job(owner_id)
                except Exception:
                    job = await self._job(owner_id)
                if not job or str(job.get("operation_token") or "") != str(
                    job_payload["operation_token"]
                ):
                    raise RuntimeError(
                        "Account deletion job reset was not confirmed."
                    )
            elif existing_fence_matches and not existing.get("completed_at"):
                job = existing
            elif current_user is None and not existing.get("completed_at"):
                job = existing
            else:
                raise RuntimeError("Account deletion operation could not be resumed.")

        job_owner, token = self._job_identity(job)
        if job_owner != owner_id or not token or job.get("completed_at"):
            raise RuntimeError("Account deletion operation could not be verified.")
        fenced_at = str(job.get("fenced_at") or started_at)
        fence_values = {
            "deleted_at": fenced_at,
            "account_deletion_token": token,
            # Revocation is part of the same users-row write as the deletion
            # fence. Background workers can therefore fail closed on either
            # deleted_at or the authoritative consent predicate without a gap.
            "ai_data_sharing_consent_revoked_at": fenced_at,
            "ai_data_sharing_consent_updated_at": fenced_at,
            "updated_at": started_at,
        }
        fence_confirmed = False
        try:
            updated = await self.db.update(
                "users",
                fence_values,
                filters={
                    "id": eq(owner_id),
                    "deleted_at": "is.null",
                    "account_deletion_token": "is.null",
                },
                retry_transient=True,
            )
            fence_confirmed = any(
                str(row.get("id") or "") == owner_id
                and str(row.get("account_deletion_token") or "") == token
                and bool(row.get("deleted_at"))
                for row in self._rows(updated)
            )
        except Exception:
            logger.exception("Account deletion fence write response was ambiguous")

        if not fence_confirmed:
            # Reconcile commit-then-transport-error and empty representation cases.
            current = await self._user(owner_id)
            fence_confirmed = bool(
                current
                and current.get("deleted_at")
                and str(current.get("account_deletion_token") or "") == token
            )
        if not fence_confirmed:
            # The job remains harmless: the worker will never delete storage for
            # an active account whose token does not match this operation.
            raise RuntimeError("Account deletion fence was not confirmed.")

        # Marker writes and the fence both update the users row. Once the fence
        # is visible no further marker write is permitted; a fresh read here
        # captures any marker that won the race before the fence. Never proceed
        # to local deletion unless the job carries that obligation durably.
        current_user = await self._user(owner_id)
        if not await self._persist_native_cleanup_requirement(current_user, job):
            raise RuntimeError("Native customer cleanup evidence was not persisted.")

        if job.get("state") == "fencing" and int(job.get("attempts") or 0) == 0:
            # Only the first successful fence promotes the job to immediately
            # due. A re-entrant request must not shorten an active worker's
            # lease or erase a queued provider-cleanup retry.
            if await self._best_effort_job_update(
                job,
                {
                    "state": "fenced",
                    "last_error_code": None,
                    "next_attempt_at": self._iso(now),
                },
            ):
                job["state"] = "fenced"
                job["next_attempt_at"] = self._iso(now)
        return {**job, "fenced_at": fenced_at}

    async def process(self, job: dict[str, Any]) -> DeletionProgress:
        """Advance one deletion and retain its late-upload tombstone."""
        owner_id, token = self._job_identity(job)
        if not owner_id or not token:
            return DeletionProgress(False, False, False, "INVALID_DELETION_JOB")

        # Always prefer the current durable record over a stale request copy.
        current_job = await self._job(owner_id)
        if not current_job:
            # No durable record remains to own retries or a provider response.
            return DeletionProgress(False, False, False, "DELETION_JOB_MISSING")
        current_token = str(current_job.get("operation_token") or "")
        if current_token != token or current_job.get("completed_at"):
            return DeletionProgress(
                account_deleted=not bool(await self._user(owner_id)),
                cleanup_complete=bool(current_job.get("completed_at")),
                retry_scheduled=False,
                code="DELETION_JOB_REPLACED",
            )
        job = current_job

        user = await self._user(owner_id)
        if user:
            fence_matches = bool(
                user.get("deleted_at")
                and str(user.get("account_deletion_token") or "") == token
            )
            if not fence_matches:
                created_at = self._parse_time(job.get("created_at") or job.get("fenced_at"))
                still_reconciling = bool(
                    created_at
                    and self._now() - created_at
                    < timedelta(minutes=self.FENCE_RECONCILE_MINUTES)
                )
                if still_reconciling:
                    await self._schedule_retry(job, "DELETION_FENCE_NOT_VISIBLE")
                    return DeletionProgress(
                        False,
                        False,
                        True,
                        "DELETION_FENCE_NOT_VISIBLE",
                    )
                await self._best_effort_job_update(
                    job,
                    {
                        "state": "abandoned",
                        "completed_at": self._iso(self._now()),
                        "last_error_code": "DELETION_FENCE_NOT_ESTABLISHED",
                        "next_attempt_at": None,
                    },
                )
                return DeletionProgress(
                    False,
                    False,
                    False,
                    "DELETION_FENCE_NOT_ESTABLISHED",
                )

        if not await self._claim_due_job(job):
            return DeletionProgress(
                not bool(user), False, True, "DELETION_JOB_IN_PROGRESS"
            )

        # A server key can reach a historical free native customer even if its
        # local marker predates the marker migration. Snapshot that possible
        # obligation before any provider DELETE, so a lost response cannot
        # leave an unmarked job that later skips cleanup if the key disappears.
        if not await self._persist_native_cleanup_requirement(
            user,
            job,
            provider_customer_possible=bool(self._revenuecat_secret_api_key),
        ):
            await self._schedule_retry(job, "REVENUECAT_IDENTITY_MARK_UNCONFIRMED")
            return DeletionProgress(
                False, False, True, "REVENUECAT_IDENTITY_MARK_UNCONFIRMED"
            )

        revenuecat_state = await self._ensure_revenuecat_deleted(owner_id, user, job)
        if revenuecat_state is RevenueCatCleanupState.UNCONFIRMED and user:
            await self._schedule_retry(job, "REVENUECAT_CLEANUP_UNCONFIRMED")
            return DeletionProgress(
                False, False, True, "REVENUECAT_CLEANUP_UNCONFIRMED"
            )

        try:
            await self.files.hard_delete_all_owned(user_id=owner_id)
        except Exception as exc:
            code = (
                exc.code
                if isinstance(exc, FileServiceError)
                else "ACCOUNT_STORAGE_CLEANUP_FAILED"
            )
            logger.exception("Durable private Storage cleanup will be retried")
            await self._schedule_retry(job, code)
            return DeletionProgress(not bool(user), False, True, code)

        if user:
            try:
                await self.db.rpc(
                    "delete_user_account",
                    {"p_user_id": owner_id},
                    retry_transient=True,
                )
            except Exception:
                logger.exception("Final account deletion RPC response was ambiguous")
                try:
                    user = await self._user(owner_id)
                except Exception:
                    user = {"id": owner_id}
                if user:
                    await self._schedule_retry(
                        job,
                        "ACCOUNT_DELETION_RPC_UNCONFIRMED",
                    )
                    return DeletionProgress(
                        False,
                        False,
                        True,
                        "ACCOUNT_DELETION_RPC_UNCONFIRMED",
                    )

        # After local account removal, continue sweeping late Storage uploads
        # even when the provider is unavailable. Its durable cleanup obligation
        # remains retryable and cannot be purged on an uncertain response.
        if revenuecat_state is RevenueCatCleanupState.UNCONFIRMED:
            await self._schedule_retry(job, "REVENUECAT_CLEANUP_UNCONFIRMED")
            return DeletionProgress(
                True, False, True, "REVENUECAT_CLEANUP_UNCONFIRMED"
            )

        now = self._now()
        finalize_after = self._parse_time(job.get("finalize_after"))
        if finalize_after and now >= finalize_after:
            if revenuecat_state is RevenueCatCleanupState.QUEUED:
                await self._schedule_retry(job, "REVENUECAT_CLEANUP_QUEUED")
                return DeletionProgress(
                    True, False, True, "REVENUECAT_CLEANUP_QUEUED"
                )
            purged = await self._delete_completed_job(job)
            if not purged:
                await self._schedule_retry(job, "DELETION_TOMBSTONE_PURGE_UNCONFIRMED")
            return DeletionProgress(
                True,
                purged,
                not purged,
                None if purged else "DELETION_TOMBSTONE_PURGE_UNCONFIRMED",
            )

        next_sweep = now + timedelta(hours=self.SWEEP_INTERVAL_HOURS)
        if finalize_after and next_sweep > finalize_after:
            next_sweep = finalize_after
        updated = await self._best_effort_job_update(
            job,
            {
                "state": "late_upload_sweep",
                "account_deleted_at": job.get("account_deleted_at") or self._iso(now),
                "last_error_code": None,
                "next_attempt_at": self._iso(next_sweep),
            },
        )
        return DeletionProgress(True, False, True, None if updated else "JOB_UPDATE_UNCONFIRMED")

    async def process_due(self, *, limit: int = 10) -> dict[str, int]:
        """Advance bounded due jobs for the authenticated cron endpoint."""
        rows = await self.db.select(
            "account_deletion_jobs",
            columns="*",
            filters={
                "completed_at": "is.null",
                "next_attempt_at": lte(self._iso(self._now())),
            },
            order="next_attempt_at.asc",
            limit=max(1, min(25, int(limit or 10))),
        )
        summary = {"processed": 0, "deleted": 0, "completed": 0, "retrying": 0}
        for job in rows:
            summary["processed"] += 1
            try:
                progress = await self.process(job)
            except Exception:
                logger.exception("Account deletion worker failed before progress was recorded")
                await self._schedule_retry(job, "ACCOUNT_DELETION_WORKER_FAILED")
                summary["retrying"] += 1
                continue
            if progress.account_deleted:
                summary["deleted"] += 1
            if progress.cleanup_complete:
                summary["completed"] += 1
            elif progress.retry_scheduled:
                summary["retrying"] += 1
        return summary
