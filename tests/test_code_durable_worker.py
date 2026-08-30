from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.code_runner import CodeRunnerError
from backend.code_service import CodeTaskService
from backend.code_worker import CodeWorker


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-4000-8000-000000000081"
PROJECT_ID = "00000000-0000-4000-8000-000000000082"
TASK_ID = "00000000-0000-4000-8000-000000000083"
LEASE_ID = "00000000-0000-4000-8000-000000000084"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def task(**changes):
    row = {
        "id": TASK_ID,
        "user_id": USER_ID,
        "project_id": PROJECT_ID,
        "status": "provisioning",
        "lease_token": LEASE_ID,
        "attempt_count": 1,
        "max_attempts": 3,
        "max_duration_seconds": 30,
        "usage_receipt": {"eventId": "usage-1", "paymentSource": "included"},
        "payment_source": "included",
    }
    row.update(changes)
    return row


class WorkerService:
    def __init__(self, claimed=None, refund_pending=None):
        self.claimed = claimed
        self.current = dict(claimed) if claimed else None
        self.refund_pending = refund_pending
        self.claim_calls = []
        self.requeues = []
        self.transitions = []
        self.refunded = []

    async def next_refund_pending(self):
        return self.refund_pending

    async def mark_refunded(self, item):
        self.refunded.append(dict(item))
        return {**item, "usage_receipt": None, "payment_source": "refunded"}

    async def claim_next(self, **kwargs):
        self.claim_calls.append(kwargs)
        return dict(self.claimed) if self.claimed else None

    async def get(self, **_kwargs):
        return dict(self.current)

    async def requeue_after_failure(self, item, **kwargs):
        self.requeues.append((dict(item), kwargs))
        return {**item, "status": "provisioning", "lease_token": None}

    async def transition(self, item, target, **kwargs):
        self.transitions.append((dict(item), target, kwargs))
        updated = {**item, **kwargs.get("changes", {}), "status": target}
        self.current = updated
        return updated


class WorkerFeatures:
    def __init__(self):
        self.refunds = []

    async def refund(self, user_id, receipt):
        self.refunds.append((user_id, dict(receipt)))


class FailingRefundLookupService(WorkerService):
    async def next_refund_pending(self):
        raise RuntimeError("private database detail must not reach operations logs")


class CompletingRunner:
    async def run(self, item, *, oidc_token):
        assert oidc_token == "oidc"
        return {**item, "status": "completed"}


class TimeoutRunner:
    async def run(self, _item, *, oidc_token):
        assert oidc_token == "oidc"
        raise CodeRunnerError("temporary", "CODE_MODEL_TIMEOUT")


class NeverRunner:
    async def run(self, _item, *, oidc_token):
        raise AssertionError(f"Runner should not be called with {oidc_token}.")


class UnexpectedRunner:
    async def run(self, _item, *, oidc_token):
        assert oidc_token == "oidc"
        raise RuntimeError("private failure detail must not reach operations logs")


def worker(service, runner, features=None, *, enabled=True):
    return CodeWorker(
        SimpleNamespace(
            code_workspace_enabled=enabled,
            anthropic_api_key="configured" if enabled else None,
            code_max_duration_seconds=30,
        ),
        SimpleNamespace(),
        service,
        runner,
        features or WorkerFeatures(),
    )


def test_durable_code_schema_is_private_replay_safe_and_leased():
    migration = read("migrations/20260830093000_crump_code_durable_worker.sql").lower()
    assert "create or replace function public.dispatch_code_task" in migration
    assert "create or replace function public.claim_code_task" in migration
    assert "for update skip locked" in migration
    assert "security invoker" in migration
    assert "lease_token = p_claim_token" in migration
    assert "dispatch_token = p_dispatch_token" in migration
    assert "usage_receipt is not null" in migration
    for signature in (
        "public.dispatch_code_task(uuid, uuid, uuid, jsonb, text, integer)",
        "public.claim_code_task(integer, uuid)",
    ):
        assert f"revoke all on function {signature} from public, anon, authenticated" in migration.replace(
            "\n  ", " "
        )
        assert f"grant execute on function {signature}" in migration


def test_worker_reuses_existing_cron_slot_and_browser_only_dispatches():
    vercel = json.loads(read("vercel.json"))
    assert len(vercel["crons"]) == 2
    assert any(item["path"] == "/api/cron/manuscripts" for item in vercel["crons"])
    cron_route = read("backend/routes/manuscripts.py")
    assert cron_route.index("code_worker.process_next(") < cron_route.index(
        "manuscripts.process_next_run()"
    )
    run_route = read("backend/routes/code.py")
    assert "run_with_deadline" not in run_route
    assert "code_tasks.dispatch(" in run_route
    assert "status_code=202" in run_route


def test_private_lease_and_dispatch_tokens_never_reach_the_browser():
    public = CodeTaskService.public_task(
        task(dispatch_token="dispatch-secret", lease_expires_at="2999-01-01T00:00:00Z")
    )
    assert "dispatch_token" not in public
    assert "lease_token" not in public
    assert "lease_expires_at" not in public


@pytest.mark.asyncio
async def test_disabled_worker_never_claims_or_runs(caplog):
    service = WorkerService(claimed=task())
    caplog.set_level(logging.INFO, logger="askcrump.code_worker")
    result = await worker(service, CompletingRunner(), enabled=False).process_next(
        oidc_token="oidc"
    )
    assert result == {"handled": False, "claimed": False, "disabled": True}
    assert service.claim_calls == []
    assert not caplog.records


@pytest.mark.asyncio
async def test_worker_claim_token_is_unique_and_success_is_content_free(caplog):
    service = WorkerService(claimed=task())
    caplog.set_level(logging.INFO, logger="askcrump.code_worker")
    result = await worker(service, CompletingRunner()).process_next(oidc_token="oidc")
    assert result == {"handled": True, "claimed": True, "status": "completed"}
    assert len(service.claim_calls) == 1
    claim = service.claim_calls[0]
    assert claim["lease_seconds"] == 75
    assert str(UUID(claim["claim_token"])) == claim["claim_token"]
    events = [json.loads(record.message)["event"] for record in caplog.records]
    assert events == ["worker_claimed", "worker_completed"]
    assert TASK_ID not in caplog.text
    assert USER_ID not in caplog.text
    assert LEASE_ID not in caplog.text


@pytest.mark.asyncio
async def test_transient_worker_failure_requeues_without_refunding_or_recharging(caplog):
    service = WorkerService(claimed=task())
    features = WorkerFeatures()
    caplog.set_level(logging.INFO, logger="askcrump.code_worker")
    result = await worker(service, TimeoutRunner(), features).process_next(oidc_token="oidc")
    assert result == {"handled": True, "claimed": True, "status": "retrying"}
    assert len(service.requeues) == 1
    assert service.requeues[0][1]["failure_code"] == "CODE_MODEL_TIMEOUT"
    assert features.refunds == []
    events = [json.loads(record.message)["event"] for record in caplog.records]
    assert events == ["worker_claimed", "worker_retry_scheduled"]


@pytest.mark.asyncio
async def test_enabled_worker_reports_missing_oidc_without_claiming(caplog):
    service = WorkerService(claimed=task())
    caplog.set_level(logging.WARNING, logger="askcrump.code_worker")
    result = await worker(service, CompletingRunner()).process_next(oidc_token="")
    assert result == {"handled": False, "claimed": False, "misconfigured": True}
    assert service.claim_calls == []
    assert json.loads(caplog.records[-1].message) == {
        "component": "crump_code",
        "event": "worker_misconfigured",
        "outcome": "missing_oidc",
    }


@pytest.mark.asyncio
async def test_retry_limit_fails_and_refunds_before_starting_more_compute():
    claimed = task(attempt_count=4, max_attempts=3)
    service = WorkerService(claimed=claimed)
    features = WorkerFeatures()
    result = await worker(service, NeverRunner(), features).process_next(oidc_token="oidc")
    assert result == {"handled": True, "claimed": True, "status": "failed"}
    assert service.transitions[0][1] == "failed"
    assert service.transitions[0][2]["changes"]["failure_code"] == "CODE_RETRY_LIMIT"
    assert features.refunds == [(USER_ID, claimed["usage_receipt"])]
    assert len(service.refunded) == 1


@pytest.mark.asyncio
async def test_unexpected_failure_retries_without_logging_private_detail(caplog):
    service = WorkerService(claimed=task())
    features = WorkerFeatures()
    caplog.set_level(logging.INFO, logger="askcrump.code_worker")
    result = await worker(service, UnexpectedRunner(), features).process_next(
        oidc_token="oidc"
    )
    assert result == {"handled": True, "claimed": True, "status": "retrying"}
    assert len(service.requeues) == 1
    assert service.requeues[0][1]["failure_code"] == "CODE_RUN_FAILED"
    assert features.refunds == []
    emitted = [json.loads(record.message) for record in caplog.records]
    assert [record["event"] for record in emitted] == [
        "worker_claimed",
        "worker_unexpected_failure",
    ]
    assert emitted[-1]["error_type"] == "RuntimeError"
    assert emitted[-1]["outcome"] == "retrying"
    assert "private failure detail" not in caplog.text


@pytest.mark.asyncio
async def test_refund_reconciliation_precedes_new_provider_work():
    pending = task(status="failed", payment_source="refund_pending")
    service = WorkerService(claimed=task(), refund_pending=pending)
    features = WorkerFeatures()
    result = await worker(service, CompletingRunner(), features).process_next(
        oidc_token="oidc"
    )
    assert result == {"handled": True, "claimed": False, "refundReconciled": True}
    assert features.refunds == [(USER_ID, pending["usage_receipt"])]
    assert len(service.refunded) == 1
    assert service.claim_calls == []


@pytest.mark.asyncio
async def test_emergency_stop_keeps_refunds_moving_without_claiming_compute(caplog):
    pending = task(status="failed", payment_source="refund_pending")
    service = WorkerService(claimed=task(), refund_pending=pending)
    features = WorkerFeatures()
    caplog.set_level(logging.INFO, logger="askcrump.code_worker")
    result = await worker(
        service,
        NeverRunner(),
        features,
        enabled=False,
    ).process_next(oidc_token="")
    assert result == {"handled": True, "claimed": False, "refundReconciled": True}
    assert features.refunds == [(USER_ID, pending["usage_receipt"])]
    assert len(service.refunded) == 1
    assert service.claim_calls == []
    assert [json.loads(record.message)["event"] for record in caplog.records] == [
        "refund_reconciled"
    ]


@pytest.mark.asyncio
async def test_refund_lookup_failure_defers_code_and_releases_shared_worker(caplog):
    service = FailingRefundLookupService(claimed=task())
    caplog.set_level(logging.INFO, logger="askcrump.code_worker")
    result = await worker(service, NeverRunner(), enabled=False).process_next(
        oidc_token=""
    )
    assert result == {
        "handled": False,
        "claimed": False,
        "refundReconciliationFailed": True,
    }
    assert service.claim_calls == []
    emitted = json.loads(caplog.records[-1].message)
    assert emitted["event"] == "refund_reconciliation_failed"
    assert emitted["error_type"] == "RuntimeError"
    assert emitted["outcome"] == "deferred"
    assert "private database detail" not in caplog.text
