from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from backend.code_observability import code_log


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_code_operational_log_is_json_and_drops_content_and_identifiers(caplog):
    logger = logging.getLogger("test.code_observability")
    caplog.set_level(logging.INFO, logger=logger.name)
    record = code_log(
        logger,
        logging.INFO,
        "worker_completed",
        status="completed",
        mode="implement",
        attempt=1,
        duration_ms=321,
        objective="private customer objective",
        task_id="task-secret",
        user_id="user-secret",
        repository_url="https://github.com/private/value",
    )
    assert record == {
        "component": "crump_code",
        "event": "worker_completed",
        "status": "completed",
        "mode": "implement",
        "attempt": 1,
        "duration_ms": 321,
    }
    emitted = json.loads(caplog.records[-1].message)
    assert emitted == record
    for private in (
        "private customer objective",
        "task-secret",
        "user-secret",
        "github.com",
    ):
        assert private not in caplog.text


def test_code_operational_log_rejects_unknown_events_and_unsafe_values(caplog):
    logger = logging.getLogger("test.code_observability")
    caplog.set_level(logging.ERROR, logger=logger.name)
    with pytest.raises(ValueError):
        code_log(logger, logging.INFO, "arbitrary_event")
    record = code_log(
        logger,
        logging.ERROR,
        "worker_unexpected_failure",
        error_type="Exception with private details",
        outcome="recovery_failed",
        duration_ms=-4,
    )
    assert "error_type" not in record
    assert record["duration_ms"] == 0
    assert json.loads(caplog.records[-1].message) == record


def test_dispatch_and_worker_instrument_only_the_allowlisted_boundary():
    observability = read("backend/code_observability.py")
    worker = read("backend/code_worker.py")
    routes = read("backend/routes/code.py")
    for forbidden in ("objective", "repository_url", "task_id", "user_id", "lease_token"):
        assert f'"{forbidden}"' not in observability
    for event in (
        "dispatch_accepted",
        "dispatch_recovered",
        "dispatch_rejected",
        "cancellation_recorded",
    ):
        assert f'"{event}"' in routes
    for event in (
        "refund_reconciled",
        "refund_reconciliation_failed",
        "worker_claimed",
        "worker_completed",
        "worker_retry_scheduled",
        "worker_terminal_failure",
        "worker_lease_superseded",
        "worker_misconfigured",
        "worker_unexpected_failure",
    ):
        assert f'"{event}"' in worker
