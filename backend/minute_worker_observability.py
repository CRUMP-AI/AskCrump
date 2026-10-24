"""Content-free structured logs for the shared minute worker."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from typing import Any


MINUTE_WORKER_LANES = (
    "account-storage-deletion",
    "verification-email",
    "password-reset-email",
    "code",
    "manuscripts",
)
EMAIL_QUEUE_LANES = frozenset({"verification-email", "password-reset-email"})

_LANE_OUTCOMES = frozenset(
    {
        "claim_database_error",
        "handled",
        "idle",
        "unexpected_exception",
    }
)
_TURN_RESULTS = frozenset(
    {
        "handled",
        "idle",
        "retryable_database_503",
        "unexpected_exception",
    }
)
_STATUSES = frozenset(
    {
        "awaiting_credits",
        "claim_invalid",
        "completed",
        "failed",
        "failed_permanent",
        "idle",
        "invalid_claim",
        "lease_expiry_recovery",
        "lease_lost",
        "lease_recovery_pending",
        "none",
        "paused",
        "provider_accepted",
        "queued",
        "released",
        "retry_scheduled",
        "retrying",
        "superseded",
        "suppressed",
        "unknown",
    }
)


def _emit(target: logging.Logger, level: int, record: Mapping[str, Any]) -> None:
    """Keep an unavailable logging sink from changing worker behavior."""

    try:
        target.log(level, json.dumps(record, sort_keys=True, separators=(",", ":")))
    except Exception:
        # Observability is best effort. Do not recurse into the failed logger.
        pass


def _normalized_status(value: Any) -> str:
    if value is None:
        return "none"
    if not isinstance(value, str):
        return "unknown"
    status = value.strip()
    return status if status in _STATUSES else "unknown"


def _bounded_ordinal(value: Any, *, maximum: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if not 1 <= value <= maximum:
        return None
    return value


def log_email_queue_outcome(
    target: logging.Logger,
    *,
    lane: str,
    handled: bool,
    status: Any,
    attempt: Any = None,
    provider_attempts: Any = None,
) -> dict[str, Any]:
    """Emit one allowlisted queue outcome without identifiers or delivery content."""

    safe_lane = (
        lane if isinstance(lane, str) and lane in EMAIL_QUEUE_LANES else "unknown"
    )
    record: dict[str, Any] = {
        "component": "minute_worker",
        "event": "email_queue_outcome",
        "lane": safe_lane,
        "handled": bool(handled),
        "status": _normalized_status(status),
    }
    safe_attempt = _bounded_ordinal(attempt, maximum=6)
    if safe_attempt is not None:
        record["attempt"] = safe_attempt
    safe_provider_attempts = _bounded_ordinal(provider_attempts, maximum=3)
    if safe_provider_attempts is not None:
        record["provider_attempts"] = safe_provider_attempts
    _emit(target, logging.INFO, record)
    return record


def log_minute_worker_turn(
    target: logging.Logger,
    level: int,
    *,
    result: str,
    worker: str,
    handled: bool,
    status: Any,
    lane_outcomes: Mapping[str, str],
    degraded_lanes: Sequence[str] = (),
) -> dict[str, Any]:
    """Emit one allowlisted cron-turn record without copying worker summaries."""

    safe_result = (
        result
        if isinstance(result, str) and result in _TURN_RESULTS
        else "unexpected_exception"
    )
    safe_worker = (
        worker
        if isinstance(worker, str) and worker in MINUTE_WORKER_LANES
        else "idle"
    )
    safe_lane_outcomes = {
        lane: lane_outcomes[lane]
        for lane in MINUTE_WORKER_LANES
        if (
            lane in lane_outcomes
            and isinstance(lane_outcomes[lane], str)
            and lane_outcomes[lane] in _LANE_OUTCOMES
        )
    }
    safe_degraded_lanes = [
        lane for lane in MINUTE_WORKER_LANES if lane in degraded_lanes
    ]
    record: dict[str, Any] = {
        "component": "minute_worker",
        "event": "turn_outcome",
        "result": safe_result,
        "worker": safe_worker,
        "handled": bool(handled),
        "status": _normalized_status(status),
        "lane_outcomes": safe_lane_outcomes,
        "degraded_lanes": safe_degraded_lanes,
        "degraded_lane_count": len(safe_degraded_lanes),
    }
    _emit(target, level, record)
    return record
