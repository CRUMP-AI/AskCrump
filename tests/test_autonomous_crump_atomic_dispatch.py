from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.code_service import CodeTaskConflictError, CodeTaskService


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "20260916231500_autonomous_crump_atomic_dispatch.sql"
USER_ID = "00000000-0000-4000-8000-000000000091"
TASK_ID = "00000000-0000-4000-8000-000000000092"
DISPATCH_TOKEN = "00000000-0000-4000-8000-000000000093"
REVISION = "a" * 40


class AtomicDispatchDB:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, dict(payload), retry_transient))
        return self.result


def queued_task() -> dict:
    return {
        "id": TASK_ID,
        "user_id": USER_ID,
        "status": "queued",
        "source_ref": REVISION,
        "base_revision": REVISION,
        "expires_at": "2999-01-01T00:00:00+00:00",
    }


def test_atomic_dispatch_migration_owns_charge_and_claim_in_one_transaction() -> None:
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert sql.startswith("-- autonomous crump atomic acceptance boundary")
    assert "begin;" in sql and sql.rstrip().endswith("commit;")
    assert "create or replace function public.accept_code_task_run" in sql
    assert "returns jsonb" in sql
    assert "security invoker" in sql
    assert "set search_path = ''" in sql
    assert "for update;" in sql
    assert "from public.consume_usage_event(" in sql
    assert "from public.spend_credits_confirmed(" in sql
    assert "update public.code_tasks" in sql
    assert "insert into public.code_task_events" in sql
    assert "candidate.source_ref" in sql and "candidate.base_revision" in sql
    assert "account.internal_tier" in sql
    assert "p_included_limit not in (3, 10)" in sql
    assert "p_credit_cost <> 12" in sql
    assert "candidate.dispatch_token = p_dispatch_token" in sql
    assert "candidate.usage_receipt is null" in sql
    assert "revoke all on function public.accept_code_task_run" in sql
    assert "to service_role" in sql
    assert "revoke all on function public.dispatch_code_task" in sql

    charge = sql.index("from public.consume_usage_event(")
    dispatch = sql.index("update public.code_tasks")
    event = sql.index("insert into public.code_task_events")
    assert charge < dispatch < event


def test_atomic_dispatch_has_bounded_content_free_receipts() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for forbidden in ("objective", "source_repo_url", "result_patch", "result_summary"):
        receipt_segment = sql[sql.index("usage_metadata :=") : sql.index("update public.code_tasks")]
        assert forbidden not in receipt_segment
    for required in ("'feature', 'code_workspace'", "'route', 'code_task'", "'taskId'"):
        assert required in sql


@pytest.mark.asyncio
async def test_service_sends_exact_atomic_acceptance_terms_and_returns_task() -> None:
    accepted_task = {**queued_task(), "status": "provisioning", "credits_spent": 12}
    database = AtomicDispatchDB(
        {"accepted": True, "replayed": False, "task": accepted_task}
    )
    service = CodeTaskService(database, SimpleNamespace())

    result = await service.accept_run(
        queued_task(),
        dispatch_token=DISPATCH_TOKEN,
        source_revision=REVISION,
        included_limit=3,
        credit_cost=12,
        credit_action_key="quote-action",
        confirmed_max=12,
    )

    assert result["accepted"] is True
    assert result["task"]["status"] == "provisioning"
    assert database.calls == [
        (
            "accept_code_task_run",
            {
                "p_task_id": TASK_ID,
                "p_user_id": USER_ID,
                "p_dispatch_token": DISPATCH_TOKEN,
                "p_source_revision": REVISION,
                "p_included_limit": 3,
                "p_credit_cost": 12,
                "p_credit_action_key": "quote-action",
                "p_confirmed_max": 12,
            },
            True,
        )
    ]


@pytest.mark.asyncio
async def test_service_fails_closed_on_incomplete_atomic_receipt() -> None:
    service = CodeTaskService(
        AtomicDispatchDB({"accepted": True, "replayed": False}),
        SimpleNamespace(),
    )

    with pytest.raises(CodeTaskConflictError, match="incomplete acceptance receipt"):
        await service.accept_run(
            queued_task(),
            dispatch_token=DISPATCH_TOKEN,
            source_revision=REVISION,
            included_limit=3,
            credit_cost=12,
            credit_action_key="internal-action",
            confirmed_max=0,
        )
