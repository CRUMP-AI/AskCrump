"""Lease-owned, replay-safe worker for accepted Crump Code tasks."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import monotonic
from typing import Any
from uuid import uuid4

from .code_observability import code_log
from .code_runner import CodeRunnerError, run_with_deadline
from .code_service import CodeTaskConflictError, CodeTaskService, TERMINAL_STATUSES
from .config import Settings
from .db import SupabaseDB
from .feature_service import FeatureService


logger = logging.getLogger("askcrump.code_worker")

RETRYABLE_FAILURES = frozenset(
    {
        "CODE_MODEL_NETWORK",
        "CODE_MODEL_RATE_LIMIT",
        "CODE_MODEL_TIMEOUT",
        "PATCH_FAILED",
        "WORKSPACE_LIST_FAILED",
    }
)


class CodeWorker:
    def __init__(
        self,
        settings: Settings,
        db: SupabaseDB,
        service: CodeTaskService,
        runner: Any,
        features: FeatureService,
    ) -> None:
        self.settings = settings
        self.db = db
        self.service = service
        self.runner = runner
        self.features = features

    def configured(self) -> bool:
        return bool(self.settings.code_workspace_enabled and self.settings.anthropic_api_key)

    async def _refund(self, task: dict[str, Any]) -> None:
        receipt = task.get("usage_receipt")
        if not receipt:
            return
        await self.features.refund(str(task["user_id"]), receipt)
        await self.service.mark_refunded(task)

    async def _reconcile_one_refund(self) -> bool:
        task = await self.service.next_refund_pending()
        if not task:
            return False
        await self._refund(task)
        code_log(
            logger,
            logging.INFO,
            "refund_reconciled",
            status=str(task.get("status") or ""),
            payment_source="refunded",
        )
        return True

    async def _fail(self, task: dict[str, Any], failure_code: str) -> dict[str, Any]:
        failed = await self.service.transition(
            task,
            "failed",
            changes={
                "failure_code": failure_code,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "payment_source": "refund_pending" if task.get("usage_receipt") else None,
            },
            event_type="task.failed",
            event_payload={"failureCode": failure_code, "status": "failed"},
        )
        if failed.get("usage_receipt"):
            await self._refund(failed)
        return failed

    async def process_next(self, *, oidc_token: str) -> dict[str, Any]:
        try:
            if await self._reconcile_one_refund():
                return {"handled": True, "claimed": False, "refundReconciled": True}
        except Exception as exc:
            code_log(
                logger,
                logging.ERROR,
                "refund_reconciliation_failed",
                error_type=type(exc).__name__,
                outcome="deferred",
            )
            return {
                "handled": False,
                "claimed": False,
                "refundReconciliationFailed": True,
            }

        if not self.configured():
            return {"handled": False, "claimed": False, "disabled": True}

        if not oidc_token:
            code_log(
                logger,
                logging.WARNING,
                "worker_misconfigured",
                outcome="missing_oidc",
            )
            return {"handled": False, "claimed": False, "misconfigured": True}

        lease_seconds = min(300, max(60, int(self.settings.code_max_duration_seconds) + 45))
        task = await self.service.claim_next(
            lease_seconds=lease_seconds,
            claim_token=str(uuid4()),
        )
        if not task:
            return {"handled": False, "claimed": False}

        started = monotonic()
        attempt = int(task.get("attempt_count") or 0)
        maximum = max(1, int(task.get("max_attempts") or 3))
        code_log(
            logger,
            logging.INFO,
            "worker_claimed",
            attempt=attempt,
            max_attempts=maximum,
            lease_seconds=lease_seconds,
            mode=str(task.get("mode") or ""),
        )
        if attempt > maximum:
            await self._fail(task, "CODE_RETRY_LIMIT")
            code_log(
                logger,
                logging.ERROR,
                "worker_terminal_failure",
                attempt=attempt,
                max_attempts=maximum,
                failure_code="CODE_RETRY_LIMIT",
                status="failed",
                duration_ms=int((monotonic() - started) * 1000),
            )
            return {"handled": True, "claimed": True, "status": "failed"}

        try:
            completed = await run_with_deadline(self.runner, task, oidc_token=oidc_token)
            completed_status = str(completed.get("status") or "completed")
            code_log(
                logger,
                logging.INFO,
                "worker_completed",
                attempt=attempt,
                max_attempts=maximum,
                status=completed_status,
                duration_ms=int((monotonic() - started) * 1000),
            )
            return {
                "handled": True,
                "claimed": True,
                "status": completed_status,
            }
        except (CodeRunnerError, CodeTaskConflictError) as exc:
            failure_code = str(getattr(exc, "code", "CODE_RUN_FAILED"))[:80]
            current = await self.service.get(
                user_id=str(task["user_id"]),
                task_id=str(task["id"]),
            )
            if current.get("status") in TERMINAL_STATUSES:
                if current.get("payment_source") == "refund_pending":
                    await self._refund(current)
                current_status = str(current.get("status") or "")
                code_log(
                    logger,
                    logging.INFO,
                    "worker_terminal_observed",
                    attempt=attempt,
                    max_attempts=maximum,
                    status=current_status,
                    failure_code=str(current.get("failure_code") or failure_code),
                    refund_pending=False,
                    duration_ms=int((monotonic() - started) * 1000),
                )
                return {
                    "handled": True,
                    "claimed": True,
                    "status": current_status,
                }
            if str(current.get("lease_token") or "") != str(task.get("lease_token") or ""):
                code_log(
                    logger,
                    logging.WARNING,
                    "worker_lease_superseded",
                    attempt=attempt,
                    max_attempts=maximum,
                    outcome="stopped",
                    duration_ms=int((monotonic() - started) * 1000),
                )
                return {"handled": True, "claimed": True, "status": "superseded"}
            if failure_code in RETRYABLE_FAILURES and attempt < maximum:
                delay = min(120, 15 * (2 ** max(0, attempt - 1)))
                await self.service.requeue_after_failure(
                    current,
                    failure_code=failure_code,
                    delay_seconds=delay,
                )
                code_log(
                    logger,
                    logging.WARNING,
                    "worker_retry_scheduled",
                    attempt=attempt,
                    max_attempts=maximum,
                    failure_code=failure_code,
                    retry_delay_seconds=delay,
                    status="provisioning",
                    duration_ms=int((monotonic() - started) * 1000),
                )
                return {"handled": True, "claimed": True, "status": "retrying"}
            await self._fail(current, failure_code)
            code_log(
                logger,
                logging.ERROR,
                "worker_terminal_failure",
                attempt=attempt,
                max_attempts=maximum,
                failure_code=failure_code,
                status="failed",
                duration_ms=int((monotonic() - started) * 1000),
            )
            return {"handled": True, "claimed": True, "status": "failed"}
        except Exception as exc:
            try:
                current = await self.service.get(
                    user_id=str(task["user_id"]),
                    task_id=str(task["id"]),
                )
            except Exception:
                code_log(
                    logger,
                    logging.ERROR,
                    "worker_unexpected_failure",
                    attempt=attempt,
                    max_attempts=maximum,
                    error_type=type(exc).__name__,
                    outcome="recovery_failed",
                    duration_ms=int((monotonic() - started) * 1000),
                )
                raise
            outcome = "failed"
            result_status = "failed"
            if current.get("status") in TERMINAL_STATUSES:
                if current.get("payment_source") == "refund_pending":
                    await self._refund(current)
                result_status = str(current.get("status") or "failed")
                outcome = result_status
            elif str(current.get("lease_token") or "") == str(task.get("lease_token") or ""):
                if attempt < maximum:
                    await self.service.requeue_after_failure(
                        current,
                        failure_code="CODE_RUN_FAILED",
                        delay_seconds=min(120, 15 * (2 ** max(0, attempt - 1))),
                    )
                    outcome = "retrying"
                    code_log(
                        logger,
                        logging.ERROR,
                        "worker_unexpected_failure",
                        attempt=attempt,
                        max_attempts=maximum,
                        error_type=type(exc).__name__,
                        outcome=outcome,
                        duration_ms=int((monotonic() - started) * 1000),
                    )
                    return {"handled": True, "claimed": True, "status": "retrying"}
                await self._fail(current, "CODE_RUN_FAILED")
            else:
                outcome = "superseded"
                result_status = "superseded"
            code_log(
                logger,
                logging.ERROR,
                "worker_unexpected_failure",
                attempt=attempt,
                max_attempts=maximum,
                error_type=type(exc).__name__,
                outcome=outcome,
                duration_ms=int((monotonic() - started) * 1000),
            )
            return {"handled": True, "claimed": True, "status": result_status}
