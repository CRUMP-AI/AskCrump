"""Content-free structured operational logs for the Crump Code control plane."""
from __future__ import annotations

import json
import logging
import re
from typing import Any


LOG_EVENTS = frozenset(
    {
        "cancellation_recorded",
        "dispatch_accepted",
        "dispatch_recovered",
        "dispatch_rejected",
        "refund_reconciliation_failed",
        "refund_reconciled",
        "worker_claimed",
        "worker_completed",
        "worker_lease_superseded",
        "worker_misconfigured",
        "worker_retry_scheduled",
        "worker_terminal_failure",
        "worker_terminal_observed",
        "worker_unexpected_failure",
    }
)
_STRING_FIELDS = frozenset(
    {
        "error_type",
        "failure_code",
        "mode",
        "outcome",
        "payment_source",
        "status",
    }
)
_INTEGER_FIELDS = frozenset(
    {
        "attempt",
        "credits_spent",
        "duration_ms",
        "lease_seconds",
        "max_attempts",
        "retry_delay_seconds",
    }
)
_BOOLEAN_FIELDS = frozenset({"refund_pending"})
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def code_log(
    target: logging.Logger,
    level: int,
    event: str,
    **fields: Any,
) -> dict[str, Any]:
    """Emit one allowlisted JSON record without account, task, source, or content data."""
    if event not in LOG_EVENTS:
        raise ValueError("Unknown Crump Code operational event.")
    record: dict[str, Any] = {
        "component": "crump_code",
        "event": event,
    }
    for key, value in fields.items():
        if key in _BOOLEAN_FIELDS and isinstance(value, bool):
            record[key] = value
        elif key in _INTEGER_FIELDS and isinstance(value, int) and not isinstance(value, bool):
            record[key] = max(0, min(10_000_000, value))
        elif key in _STRING_FIELDS:
            normalized = str(value or "").strip()
            if _SAFE_VALUE.fullmatch(normalized):
                record[key] = normalized
    target.log(level, json.dumps(record, sort_keys=True, separators=(",", ":")))
    return record
