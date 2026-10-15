"""Bounded maintenance for abandoned Code tasks, independent of paid execution."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any

from .code_service import ACTIVE_STATUSES, TERMINAL_STATUSES
from .db import eq, in_, lte

logger = logging.getLogger("askcrump.code_reconciliation")


async def reconcile_code_tasks(
    db: Any,
    service: Any,
    *,
    limit: int = 20,
    refund_limit: int = 10,
    timeout_seconds: float = 8.0,
) -> dict[str, int | bool]:
    """Run before shared-cron early returns, including while Code is disabled.

    Only the service's owner-scoped, optimistic expiry transitions and atomic
    refund settlement may write. This path cannot claim tasks or call a model.
    A timeout or partial failure is observable and safe to retry next minute.
    """
    limit = max(1, min(40, int(limit)))
    refund_limit = max(0, min(20, int(refund_limit)))
    timeout_seconds = max(.01, min(15.0, float(timeout_seconds)))
    summary: dict[str, int | bool] = {
        "scanned": 0, "cancelled": 0, "refundsScanned": 0,
        "refunded": 0, "costRetained": 0, "leasesScanned": 0,
        "leasesRetired": 0, "errors": 0, "timedOut": False,
    }

    async def run() -> None:
        now = datetime.now(timezone.utc).isoformat()
        expired = await db.select(
            "code_tasks", columns="id,user_id,status",
            filters={"status": in_(sorted(ACTIVE_STATUSES)), "expires_at": lte(now)},
            order="expires_at.asc", limit=limit,
        )
        # Waiting tasks are ordered oldest first. Their actual pending approval
        # expiry is resolved by the same service path used by an owner detail read.
        waiting = await db.select(
            "code_tasks", columns="id,user_id,status",
            filters={"status": eq("awaiting_approval")},
            order="updated_at.asc", limit=limit,
        )
        candidates = {
            (str(row["user_id"]), str(row["id"])): row
            for row in [*expired, *waiting]
        }
        for (user_id, task_id), original in candidates.items():
            summary["scanned"] += 1
            try:
                current = await service.get(user_id=user_id, task_id=task_id, include_history=True)
                if current.get("status") == "cancelled" and original.get("status") != "cancelled":
                    summary["cancelled"] += 1
            except Exception as exc:
                summary["errors"] += 1
                logger.warning("Code expiry deferred error_type=%s", type(exc).__name__)
        # The database rechecks the live lease under the same locks as begin and
        # refund. A stale cron read must never retire a lease just extended by a
        # worker, nor reclaim and replay a request the provider may have accepted.
        started = await db.select(
            "code_tasks", columns="id,user_id,status,provider_started_at,lease_expires_at",
            filters={"status": in_(["provisioning", "running", "verifying"]),
                     "provider_started_at": "not.is.null",
                     "lease_expires_at": lte(now)},
            order="lease_expires_at.asc", limit=limit,
        )
        for task in started:
            if not task.get("provider_started_at"):
                continue
            summary["leasesScanned"] += 1
            try:
                current = await service.reconcile_provider_lease(task)
                if current.get("failure_code") == "CODE_PROVIDER_OUTCOME_UNCERTAIN":
                    summary["leasesRetired"] += 1
            except Exception as exc:
                summary["errors"] += 1
                logger.warning("Code lease settlement deferred error_type=%s", type(exc).__name__)
        if not refund_limit:
            return
        pending = await db.select(
            "code_tasks",
            filters={"status": in_(sorted(TERMINAL_STATUSES)), "payment_source": eq("refund_pending")},
            order="updated_at.asc", limit=refund_limit,
        )
        for task in pending:
            summary["refundsScanned"] += 1
            try:
                current = await service.refund_if_unstarted(task)
                if current.get("payment_source") == "refunded":
                    summary["refunded"] += 1
                elif current.get("provider_started_at"):
                    summary["costRetained"] += 1
            except Exception as exc:
                summary["errors"] += 1
                logger.warning("Code settlement deferred error_type=%s", type(exc).__name__)

    try:
        async with asyncio.timeout(timeout_seconds):
            await run()
    except TimeoutError:
        summary["timedOut"] = True
    except Exception as exc:
        summary["errors"] += 1
        logger.warning("Code maintenance deferred error_type=%s", type(exc).__name__)
    return summary
