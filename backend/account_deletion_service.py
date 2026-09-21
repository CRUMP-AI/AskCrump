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


class VideoFenceRecoveryState(str, Enum):
    ABANDONED = "abandoned"
    RELEASED = "released"
    ALREADY_RELEASED = "already_released"
    STILL_RECONCILING = "still_reconciling"
    ACCOUNT_DELETING = "account_deleting"
    USER_DELETED = "user_deleted"
    NOT_OWNER = "not_owner"
    JOB_CONFLICT = "job_conflict"
    UNCONFIRMED = "unconfirmed"


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

    async def _video_fence(self, user_id: str) -> dict[str, Any] | None:
        return await self.db.select_one(
            "video_account_deletion_fences",
            columns="user_id,operation_token,requested_at,deleted_at",
            filters={"user_id": eq(user_id)},
        )

    async def confirm_video_fence(self, *, user_id: str, operation_token: str) -> bool:
        """Confirm this exact active provider fence, including a lost RPC response."""
        owner_id = str(user_id or "").strip()
        token = str(operation_token or "").strip()
        if not owner_id or not token:
            return False
        rpc_failed = False
        try:
            if await self.db.rpc(
                "begin_video_account_deletion",
                {"p_user_id": owner_id, "p_operation_token": token},
                retry_transient=True,
            ):
                return True
        except Exception:
            rpc_failed = True
            logger.exception("Video provider deletion fence response was ambiguous")
        try:
            fence = await self._video_fence(owner_id)
        except Exception as exc:
            if rpc_failed:
                raise RuntimeError(
                    "Video provider account-deletion fence was not confirmed."
                ) from exc
            return False
        return bool(
            fence
            and str(fence.get("operation_token") or "") == token
            and not fence.get("deleted_at")
        )

    async def recover_video_fence(
        self,
        *,
        user_id: str,
        operation_token: str,
        require_stale: bool = False,
    ) -> VideoFenceRecoveryState:
        """Run the atomic token-safe recovery and reconcile a lost response."""
        owner_id = str(user_id or "").strip()
        token = str(operation_token or "").strip()
        if not owner_id or not token:
            return VideoFenceRecoveryState.UNCONFIRMED
        raw_result: Any = None
        try:
            raw_result = await self.db.rpc(
                "recover_video_account_deletion_fence",
                {
                    "p_user_id": owner_id,
                    "p_operation_token": token,
                    "p_require_stale": require_stale,
                },
                retry_transient=True,
            )
        except Exception:
            logger.exception("Video provider deletion fence recovery was ambiguous")

        result = str(raw_result or "").strip().lower()
        direct_states = {
            state.value: state
            for state in VideoFenceRecoveryState
            if state not in {
                # SQL reports this whenever either users-row fence column is
                # present. Re-read below proves that this exact token won;
                # a foreign users fence must normalize to NOT_OWNER.
                VideoFenceRecoveryState.ACCOUNT_DELETING,
                VideoFenceRecoveryState.NOT_OWNER,
                VideoFenceRecoveryState.UNCONFIRMED,
            }
        }
        if result in direct_states:
            return direct_states[result]

        # `not_owner` is also returned when a retry follows a committed release.
        # A service-role read distinguishes that harmless replay from a different
        # token. It never authorizes a second, non-atomic delete.
        try:
            fence = await self._video_fence(owner_id)
            user = await self._user(owner_id)
            job = await self._job(owner_id)
        except Exception:
            logger.exception("Video provider deletion fence recovery readback failed")
            return VideoFenceRecoveryState.UNCONFIRMED

        if user is None:
            return VideoFenceRecoveryState.USER_DELETED
        if user.get("deleted_at") or user.get("account_deletion_token"):
            if (
                user.get("deleted_at")
                and str(user.get("account_deletion_token") or "") == token
            ):
                return VideoFenceRecoveryState.ACCOUNT_DELETING
            return VideoFenceRecoveryState.NOT_OWNER
        if fence is None:
            if (
                job
                and str(job.get("operation_token") or "") == token
                and job.get("completed_at")
            ):
                return VideoFenceRecoveryState.ABANDONED
            if job is None:
                return VideoFenceRecoveryState.ALREADY_RELEASED
            return VideoFenceRecoveryState.UNCONFIRMED
        if fence.get("deleted_at"):
            return VideoFenceRecoveryState.NOT_OWNER
        if str(fence.get("operation_token") or "") != token:
            return VideoFenceRecoveryState.NOT_OWNER
        return VideoFenceRecoveryState.UNCONFIRMED

    async def recover_stale_orphan_video_fence(
        self,
        *,
        user_id: str,
    ) -> VideoFenceRecoveryState:
        """Recover an old active-user fence through the atomic token RPC.

        A no-job fence is given the same reconciliation grace as a durable job,
        so a concurrent request still between provider fencing and persistence
        is never mistaken for an orphan.
        """
        owner_id = str(user_id or "").strip()
        if not owner_id:
            return VideoFenceRecoveryState.UNCONFIRMED
        try:
            user = await self._user(owner_id)
            job = await self._job(owner_id)
            fence = await self._video_fence(owner_id)
        except Exception:
            logger.exception("Stale video deletion fence discovery failed")
            return VideoFenceRecoveryState.UNCONFIRMED
        if (
            not user
            or user.get("deleted_at")
            or user.get("account_deletion_token")
            or not fence
            or fence.get("deleted_at")
        ):
            return VideoFenceRecoveryState.NOT_OWNER
        fence_token = str(fence.get("operation_token") or "")
        if not fence_token:
            return VideoFenceRecoveryState.UNCONFIRMED
        if job:
            if str(job.get("operation_token") or "") != fence_token:
                return VideoFenceRecoveryState.JOB_CONFLICT
        return await self.recover_video_fence(
            user_id=owner_id,
            operation_token=fence_token,
            require_stale=True,
        )

    async def _establish_user_fence(
        self,
        *,
        user_id: str,
        operation_token: str,
        fenced_at: str,
    ) -> str:
        """Atomically bind users, durable-job, and video-fence ownership."""
        result: Any = None
        try:
            result = await self.db.rpc(
                "establish_account_deletion_fence",
                {
                    "p_user_id": user_id,
                    "p_operation_token": operation_token,
                    "p_fenced_at": fenced_at,
                },
                retry_transient=True,
            )
        except Exception:
            logger.exception("Account deletion fence RPC response was ambiguous")
        normalized = str(result or "").strip().lower()
        if normalized == "fenced":
            return normalized
        try:
            current = await self._user(user_id)
        except Exception:
            return normalized or "unconfirmed"
        if current is None:
            return "user_deleted"
        if (
            current.get("deleted_at")
            and str(current.get("account_deletion_token") or "") == operation_token
        ):
            return "fenced"
        return normalized or "unconfirmed"

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

    async def begin(
        self,
        *,
        user_id: str,
        operation_token: str | None = None,
    ) -> dict[str, Any]:
        """Confirm the provider fence, persist its token, then fence the user."""
        owner_id = str(user_id or "").strip()
        if not owner_id:
            raise RuntimeError("Account deletion owner is missing.")
        now = self._now()
        started_at = self._iso(now)
        explicit_token = operation_token is not None
        requested_token = str(operation_token if explicit_token else uuid4()).strip()
        if not requested_token:
            raise RuntimeError("Account deletion operation token is missing.")

        # An implicit re-entrant caller may converge on a recent durable token.
        # An explicit route token remains authoritative once it owns the video
        # fence, even when an older unfenced job is still inside this window.
        existing_hint: dict[str, Any] | None = None
        current_user_hint: dict[str, Any] | None = None
        hint_read_confirmed = False
        try:
            existing_hint = await self._job(owner_id)
            current_user_hint = await self._user(owner_id)
            hint_read_confirmed = True
        except Exception:
            logger.exception("Account deletion pre-fence read was unavailable")
        if not explicit_token and existing_hint and not existing_hint.get("completed_at"):
            existing_hint_token = str(existing_hint.get("operation_token") or "")
            existing_started = self._parse_time(
                existing_hint.get("created_at") or existing_hint.get("fenced_at")
            )
            existing_is_recent = bool(
                existing_started
                and self._now() - existing_started
                < timedelta(minutes=self.FENCE_RECONCILE_MINUTES)
            )
            existing_user_fence_matches = bool(
                current_user_hint
                and current_user_hint.get("deleted_at")
                and str(current_user_hint.get("account_deletion_token") or "")
                == existing_hint_token
            )
            active_without_user_fence = bool(
                current_user_hint
                and not current_user_hint.get("deleted_at")
                and not current_user_hint.get("account_deletion_token")
            )
            if existing_hint_token and (
                existing_user_fence_matches
                or (active_without_user_fence and existing_is_recent)
                or (hint_read_confirmed and current_user_hint is None)
            ):
                requested_token = existing_hint_token

        video_fence_confirmed = await self.confirm_video_fence(
            user_id=owner_id,
            operation_token=requested_token,
        )
        if (
            not video_fence_confirmed
            and existing_hint
            and current_user_hint
            and not current_user_hint.get("deleted_at")
            and not current_user_hint.get("account_deletion_token")
        ):
            prior_token = str(existing_hint.get("operation_token") or "")
            if prior_token and prior_token != requested_token:
                prior_recovery = await self.recover_video_fence(
                    user_id=owner_id,
                    operation_token=prior_token,
                )
                if prior_recovery in {
                    VideoFenceRecoveryState.ABANDONED,
                    VideoFenceRecoveryState.RELEASED,
                    VideoFenceRecoveryState.ALREADY_RELEASED,
                }:
                    video_fence_confirmed = await self.confirm_video_fence(
                        user_id=owner_id,
                        operation_token=requested_token,
                    )
        if not video_fence_confirmed:
            orphan_recovery = await self.recover_stale_orphan_video_fence(
                user_id=owner_id,
            )
            if orphan_recovery in {
                VideoFenceRecoveryState.ABANDONED,
                VideoFenceRecoveryState.RELEASED,
                VideoFenceRecoveryState.ALREADY_RELEASED,
            }:
                video_fence_confirmed = await self.confirm_video_fence(
                    user_id=owner_id,
                    operation_token=requested_token,
                )
        if not video_fence_confirmed:
            raise RuntimeError("A video provider start is still settling.")

        job_payload: dict[str, Any] = {
            "user_id": owner_id,
            "operation_token": requested_token,
            "state": "fencing",
            "fenced_at": started_at,
            "finalize_after": self._iso(
                now + timedelta(hours=self.LATE_UPLOAD_SAFETY_HOURS)
            ),
            "next_attempt_at": self._iso(now + timedelta(minutes=self.RETRY_MINUTES)),
            "attempts": 0,
            "last_error_code": None,
            "native_billing_identity_possible": self._native_cleanup_required(
                current_user_hint,
                existing_hint or {},
            ),
            "updated_at": started_at,
        }
        persistence_error: Exception | None = None
        try:
            inserted = self._rows(
                await self.db.insert("account_deletion_jobs", job_payload)
            )
            job = inserted[0] if inserted else await self._job(owner_id)
        except Exception as exc:
            persistence_error = exc
            # A transport failure can occur after Postgres committed the insert.
            # Read back by the unique owner key before deciding it failed.
            try:
                job = await self._job(owner_id)
            except Exception:
                await self.recover_video_fence(
                    user_id=owner_id,
                    operation_token=requested_token,
                )
                raise RuntimeError(
                    "Account deletion job persistence was not confirmed."
                ) from exc

        if not job:
            await self.recover_video_fence(
                user_id=owner_id,
                operation_token=requested_token,
            )
            raise RuntimeError(
                "Account deletion job persistence was not confirmed."
            ) from persistence_error

        current_user = await self._user(owner_id)
        existing_token = str(job.get("operation_token") or "")
        active_without_user_fence = bool(
            current_user
            and not current_user.get("deleted_at")
            and not current_user.get("account_deletion_token")
        )
        requested_user_fence_matches = bool(
            current_user
            and current_user.get("deleted_at")
            and str(current_user.get("account_deletion_token") or "")
            == requested_token
        )
        if existing_token == requested_token and not job.get("completed_at"):
            if not (
                active_without_user_fence
                or requested_user_fence_matches
                or current_user is None
            ):
                raise RuntimeError("Account deletion operation could not be resumed.")
        elif active_without_user_fence:
            # `confirm_video_fence` proved that the caller token, not this older
            # row, owns the provider fence. Reset by the old token as a CAS even
            # when that unfenced row is recent.
            reset_payload = {
                **job_payload,
                "created_at": started_at,
                "account_deleted_at": None,
                "completed_at": None,
                # Provider-customer evidence is monotonic. Replacing an
                # unfenced operation must never turn a durable true back into
                # false when this worker has no runtime RevenueCat key.
                "native_billing_identity_possible": self._native_cleanup_required(
                    current_user,
                    job,
                ),
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
            if not job or str(job.get("operation_token") or "") != requested_token:
                raise RuntimeError("Account deletion job reset was not confirmed.")
        else:
            raise RuntimeError("Account deletion operation could not be resumed.")

        job_owner, token = self._job_identity(job)
        if job_owner != owner_id or not token or job.get("completed_at"):
            raise RuntimeError("Account deletion operation could not be verified.")

        fenced_at = str(job.get("fenced_at") or started_at)
        fence_result = await self._establish_user_fence(
            user_id=owner_id,
            operation_token=token,
            fenced_at=fenced_at,
        )
        if fence_result not in {"fenced", "user_deleted"}:
            # Atomic recovery owns any later abandonment. A recent same-token job
            # remains fenced and retryable if this caller loses its response.
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
                recovery = await self.recover_video_fence(
                    user_id=owner_id,
                    operation_token=token,
                )
                if recovery is VideoFenceRecoveryState.ACCOUNT_DELETING:
                    try:
                        user = await self._user(owner_id)
                    except Exception:
                        await self._schedule_retry(
                            job, "DELETION_FENCE_RECOVERY_UNCONFIRMED"
                        )
                        return DeletionProgress(
                            False,
                            False,
                            True,
                            "DELETION_FENCE_RECOVERY_UNCONFIRMED",
                        )
                    if user is not None and not (
                        user.get("deleted_at")
                        and str(user.get("account_deletion_token") or "") == token
                    ):
                        latest_job = await self._job(owner_id)
                        if latest_job and str(
                            latest_job.get("operation_token") or ""
                        ) != token:
                            return DeletionProgress(
                                False, False, False, "DELETION_JOB_REPLACED"
                            )
                        await self._schedule_retry(
                            job, "VIDEO_DELETION_FENCE_OWNERSHIP_CONFLICT"
                        )
                        return DeletionProgress(
                            False,
                            False,
                            True,
                            "VIDEO_DELETION_FENCE_OWNERSHIP_CONFLICT",
                        )
                elif recovery is VideoFenceRecoveryState.USER_DELETED:
                    # The release RPC never removes a post-delete tombstone.
                    # Continue the durable storage/provider cleanup as user-missing.
                    user = None
                elif recovery is VideoFenceRecoveryState.ABANDONED:
                    return DeletionProgress(
                        False,
                        False,
                        False,
                        "DELETION_FENCE_NOT_ESTABLISHED",
                    )
                else:
                    latest_job = await self._job(owner_id)
                    if (
                        not latest_job
                        or str(latest_job.get("operation_token") or "") != token
                        or latest_job.get("completed_at")
                    ):
                        return DeletionProgress(
                            not bool(await self._user(owner_id)),
                            bool(latest_job and latest_job.get("completed_at")),
                            False,
                            "DELETION_JOB_REPLACED",
                        )
                    code = (
                        "DELETION_FENCE_NOT_VISIBLE"
                        if recovery is VideoFenceRecoveryState.STILL_RECONCILING
                        else "VIDEO_DELETION_FENCE_OWNERSHIP_CONFLICT"
                        if recovery in {
                            VideoFenceRecoveryState.NOT_OWNER,
                            VideoFenceRecoveryState.JOB_CONFLICT,
                        }
                        else "DELETION_FENCE_RECOVERY_UNCONFIRMED"
                    )
                    await self._schedule_retry(job, code)
                    return DeletionProgress(False, False, True, code)

        if not await self._claim_due_job(job):
            return DeletionProgress(
                not bool(user), False, True, "DELETION_JOB_IN_PROGRESS"
            )

        if user:
            try:
                video_fence_confirmed = await self.confirm_video_fence(
                    user_id=owner_id,
                    operation_token=token,
                )
            except Exception:
                await self._schedule_retry(job, "VIDEO_DELETION_FENCE_UNAVAILABLE")
                return DeletionProgress(
                    False,
                    False,
                    True,
                    "VIDEO_DELETION_FENCE_UNAVAILABLE",
                )
            if not video_fence_confirmed:
                await self._schedule_retry(job, "VIDEO_START_SETTLING")
                return DeletionProgress(
                    False,
                    False,
                    True,
                    "VIDEO_START_SETTLING",
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
