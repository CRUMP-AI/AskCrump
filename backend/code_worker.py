"""Lease-owned, replay-safe worker for accepted Crump Code tasks."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

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
        if not self.configured():
            return {"handled": False, "claimed": False, "disabled": True}

        if await self._reconcile_one_refund():
            return {"handled": True, "claimed": False, "refundReconciled": True}

        if not oidc_token:
            return {"handled": False, "claimed": False, "misconfigured": True}

        lease_seconds = min(300, max(60, int(self.settings.code_max_duration_seconds) + 45))
        task = await self.service.claim_next(
            lease_seconds=lease_seconds,
            claim_token=str(uuid4()),
        )
        if not task:
            return {"handled": False, "claimed": False}

        attempt = int(task.get("attempt_count") or 0)
        maximum = max(1, int(task.get("max_attempts") or 3))
        if attempt > maximum:
            await self._fail(task, "CODE_RETRY_LIMIT")
            return {"handled": True, "claimed": True, "status": "failed"}

        try:
            completed = await run_with_deadline(self.runner, task, oidc_token=oidc_token)
            return {
                "handled": True,
                "claimed": True,
                "status": str(completed.get("status") or "completed"),
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
                return {
                    "handled": True,
                    "claimed": True,
                    "status": str(current.get("status")),
                }
            if str(current.get("lease_token") or "") != str(task.get("lease_token") or ""):
                return {"handled": True, "claimed": True, "status": "superseded"}
            if failure_code in RETRYABLE_FAILURES and attempt < maximum:
                delay = min(120, 15 * (2 ** max(0, attempt - 1)))
                await self.service.requeue_after_failure(
                    current,
                    failure_code=failure_code,
                    delay_seconds=delay,
                )
                return {"handled": True, "claimed": True, "status": "retrying"}
            await self._fail(current, failure_code)
            return {"handled": True, "claimed": True, "status": "failed"}
        except Exception:
            logger.exception("Crump Code worker failed without task content")
            current = await self.service.get(
                user_id=str(task["user_id"]),
                task_id=str(task["id"]),
            )
            if current.get("status") not in TERMINAL_STATUSES and str(
                current.get("lease_token") or ""
            ) == str(task.get("lease_token") or ""):
                if attempt < maximum:
                    await self.service.requeue_after_failure(
                        current,
                        failure_code="CODE_RUN_FAILED",
                        delay_seconds=min(120, 15 * (2 ** max(0, attempt - 1))),
                    )
                    return {"handled": True, "claimed": True, "status": "retrying"}
                await self._fail(current, "CODE_RUN_FAILED")
            return {"handled": True, "claimed": True, "status": "failed"}
