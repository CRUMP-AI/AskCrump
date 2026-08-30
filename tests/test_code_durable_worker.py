from __future__ import annotations

import json
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
async def test_disabled_worker_never_claims_or_runs():
    service = WorkerService(claimed=task())
    result = await worker(service, CompletingRunner(), enabled=False).process_next(
        oidc_token="oidc"
    )
    assert result == {"handled": False, "claimed": False, "disabled": True}
    assert service.claim_calls == []


@pytest.mark.asyncio
async def test_worker_claim_token_is_unique_and_success_is_content_free():
    service = WorkerService(claimed=task())
    result = await worker(service, CompletingRunner()).process_next(oidc_token="oidc")
    assert result == {"handled": True, "claimed": True, "status": "completed"}
    assert len(service.claim_calls) == 1
    claim = service.claim_calls[0]
    assert claim["lease_seconds"] == 75
    assert str(UUID(claim["claim_token"])) == claim["claim_token"]


@pytest.mark.asyncio
async def test_transient_worker_failure_requeues_without_refunding_or_recharging():
    service = WorkerService(claimed=task())
    features = WorkerFeatures()
    result = await worker(service, TimeoutRunner(), features).process_next(oidc_token="oidc")
    assert result == {"handled": True, "claimed": True, "status": "retrying"}
    assert len(service.requeues) == 1
    assert service.requeues[0][1]["failure_code"] == "CODE_MODEL_TIMEOUT"
    assert features.refunds == []


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
