"""Code-only admission policy and control-plane contracts; no provider requests."""
from dataclasses import replace
from types import SimpleNamespace

import pytest

from backend.code_budget import CodeBudgetError, CodeBudgetPolicy, CodeProviderBudgetService
from backend.code_service import CodeTaskService, CodeTaskNotFoundError
from backend.feature_service import CreditAuthorization, FeatureAccessError


USER = {"id": "00000000-0000-4000-8000-000000000091", "internal_tier": "professional"}
TASK = {"id": "00000000-0000-4000-8000-000000000092", "user_id": USER["id"],
        "mode": "plan", "status": "queued", "expires_at": "2099-01-01T00:00:00Z", "lease_token": "lease"}


def policy(**changes):
    return CodeBudgetPolicy(**{"model": "explicit-model-20260101", "input_rate": 3_000_000,
        "output_rate": 15_000_000, "max_input_bytes": 100_000, "max_output_tokens": 6000,
        "call_limit": 500_000, "run_limit": 2_000_000, "account_daily_limit": 10_000_000,
        "global_daily_limit": 20_000_000, **changes})


def body(**changes):
    return {"model": policy().model, "max_tokens": 1000, "system": "bounded system",
            "messages": [{"role": "user", "content": "Explain this code."}], **changes}


def test_policy_requires_explicit_exact_model_prices_and_integer_caps():
    with pytest.raises(CodeBudgetError, match="explicit"):
        CodeBudgetPolicy.from_env({})
    for field, value in [("input_rate", 0), ("output_rate", True), ("call_limit", "500000"),
                         ("max_input_bytes", 2_000_001), ("max_output_tokens", 16_385),
                         ("run_limit", 1), ("model", "invalid model alias")]:
        with pytest.raises(CodeBudgetError):
            policy(**{field: value})
    with pytest.raises(CodeBudgetError):
        policy().request_details(body(model="another-model"))
    env = {"CODE_PROVIDER_MODEL": "exact-approved-model", "CODE_PROVIDER_INPUT_USD_MICROS_PER_MILLION": "3",
           "CODE_PROVIDER_OUTPUT_USD_MICROS_PER_MILLION": "5", "CODE_PROVIDER_MAX_INPUT_BYTES": "1000",
           "CODE_PROVIDER_MAX_OUTPUT_TOKENS": "100", "CODE_PROVIDER_CALL_USD_MICROS": "10",
           "CODE_PROVIDER_RUN_USD_MICROS": "20", "CODE_PROVIDER_ACCOUNT_DAILY_USD_MICROS": "30",
           "CODE_PROVIDER_GLOBAL_DAILY_USD_MICROS": "40"}
    configured = CodeBudgetPolicy.from_env(env)
    assert configured.model == "exact-approved-model" and configured.price(1, 1) == 1
    assert configured.price(1_000_000, 1_000_000) == 8


def test_request_digest_and_reservation_cover_system_tools_bytes_and_output():
    p = policy()
    digest, cost, ceiling, output = p.request_details(body())
    assert len(digest) == 64 and output == 1000 and ceiling > 4096
    assert cost == p.price(ceiling, output)
    reordered = dict(reversed(list(body().items())))
    assert p.request_details(reordered) == (digest, cost, ceiling, output)
    assert p.request_details(body(tools=[{"name": "inspect", "description": "a" * 1000}]))[1] > cost
    assert p.request_details(body(system="Secret different system"))[0] != digest
    for request in [body(max_tokens=True), body(max_tokens=6001), body(system="a" * 100_001), body(x=float("nan"))]:
        with pytest.raises(CodeBudgetError):
            p.request_details(request)
    with pytest.raises(CodeBudgetError):
        replace(p, call_limit=1).request_details(body())


class RPCDB:
    def __init__(self, responses=None, task=None):
        self.responses = dict(responses or {})
        self.task = dict(TASK if task is None else task)
        self.calls = []

    async def rpc(self, function, payload, **options):
        self.calls.append((function, payload, options))
        return self.responses[function]

    async def select_one(self, table, **_options):
        assert table == "code_tasks"
        return dict(self.task)


@pytest.mark.asyncio
async def test_provider_requires_fresh_durable_begin_and_never_replays_started_call():
    p = policy()
    digest, cost, ceiling, output = p.request_details(body())
    reservation = {"id": "reservation", "policy": p.as_dict(), "reserved_micros": cost,
                   "input_ceiling": ceiling, "output_ceiling": output}
    db = RPCDB({"reserve_code_provider_call": {"outcome": "reserved_replay", "reservation": reservation},
                "begin_code_provider_call": {"outcome": "already_started", "reservation": reservation}})
    service = CodeProviderBudgetService(db)
    assert await service.reserve_call(TASK, call_key="turn:0", request_body=body(), policy=p) == reservation
    sent = db.calls[0][1]
    assert sent["p_request_sha256"] == digest and sent["p_reserved_micros"] == cost
    assert "messages" not in str(sent) and "bounded system" not in str(sent)
    assert db.calls[0][2] == {"retry_transient": True}
    with pytest.raises(CodeBudgetError) as caught:
        await service.begin_call(TASK, reservation)
    assert caught.value.code == "CODE_PROVIDER_OUTCOME_UNCERTAIN"
    db.responses["begin_code_provider_call"] = {"outcome": "started", "reservation": reservation}
    assert await service.begin_call(TASK, reservation) == reservation


@pytest.mark.asyncio
async def test_settlement_accounts_cached_usage_and_preserves_uncertain_overruns():
    p = policy()
    _, cost, ceiling, output = p.request_details(body())
    reservation = {"id": "r", "policy": p.as_dict(), "reserved_micros": cost,
                   "input_ceiling": ceiling, "output_ceiling": output}
    db = RPCDB({"settle_code_provider_call": {"outcome": "settled"}})
    service = CodeProviderBudgetService(db)
    await service.settle_call(TASK, reservation, usage={"input_tokens": 10, "output_tokens": 20,
                             "cache_creation_input_tokens": 30, "cache_read_input_tokens": 40})
    assert db.calls[-1][1]["p_actual_micros"] == p.price(80, 20)
    assert db.calls[-1][1]["p_uncertain"] is False
    await service.settle_call(TASK, reservation, usage={"input_tokens": ceiling + 1, "output_tokens": 1})
    assert db.calls[-1][1]["p_uncertain"] is True
    assert db.calls[-1][1]["p_actual_micros"] == p.price(ceiling + 1, 1)
    for usage in [None, {}, {"input_tokens": True, "output_tokens": 1}, {"input_tokens": -1, "output_tokens": 2}]:
        await service.settle_call(TASK, reservation, usage=usage)
        assert db.calls[-1][1]["p_uncertain"] is True


class Features:
    def __init__(self, *, error=None):
        self.calls = []
        self.error = error

    async def require_tier(self, user, code):
        assert user == USER and code == "code_workspace"
        return SimpleNamespace(credit_cost=12, included_daily={"professional": 3})

    async def authorize(self, user, components, confirmation, **options):
        self.calls.append((user, components, confirmation, options))
        if self.error:
            raise self.error
        return CreditAuthorization(user["id"], "signed-action", {"code_workspace": 12}, {"code_workspace": 1}, 12)

    async def quote(self, *args, **kwargs):
        return {"creditBalance": 50}


@pytest.mark.asyncio
async def test_dispatch_passes_only_server_authorized_amount_and_policy_in_one_rpc():
    accepted = {**TASK, "status": "provisioning", "dispatch_token": "committed"}
    db = RPCDB({"reserve_and_dispatch_code_task": {"outcome": "dispatched", "task": accepted}})
    features = Features()
    service = CodeTaskService(db, None)
    returned = await service.dispatch_authorized(TASK, user=USER, features=features, dispatch_token="request",
                                                budget_policy=policy(), confirmation={"quoteToken": "signed"})
    assert returned == accepted
    function, sent, options = db.calls[0]
    assert function == "reserve_and_dispatch_code_task" and options == {"retry_transient": True}
    assert sent["p_credit_cost"] == 12 and sent["p_confirmed_max"] == 12
    assert sent["p_bypass_source"] == "internal" and sent["p_budget_policy"] == policy().as_dict()
    assert "p_usage_receipt" not in sent
    assert features.calls[0][3]["scope"] == {"route": "code_task", "taskId": TASK["id"], "mode": "plan"}


@pytest.mark.asyncio
async def test_replay_reconciles_without_new_quote_charge_or_refund_and_checks_owner():
    accepted = {**TASK, "status": "completed", "dispatch_token": "first-request"}
    db = RPCDB(task=accepted)
    service = CodeTaskService(db, None)
    features = Features(error=FeatureAccessError("expired"))
    assert await service.dispatch_authorized(TASK, user=USER, features=features, dispatch_token="another-request",
                                            budget_policy=policy(), confirmation={"expired": True}) == accepted
    assert not db.calls and not features.calls
    with pytest.raises(CodeTaskNotFoundError):
        await service.dispatch_authorized(TASK, user={"id": "other"}, features=features,
                                          dispatch_token="request", budget_policy=policy())


@pytest.mark.asyncio
async def test_refund_uses_atomic_eligibility_rpc_and_public_response_excludes_new_private_fields():
    retained = {**TASK, "status": "failed", "provider_started_at": "2026-10-15T12:00:00Z",
                "provider_budget_policy": policy().as_dict(), "provider_execution_lease_token": "private",
                "payment_source": "credits", "usage_receipt": {"private": True}, "future_private_key": "secret"}
    db = RPCDB({"refund_code_task_if_unstarted": {"outcome": "provider_started", "task": retained}})
    service = CodeTaskService(db, None)
    assert await service.refund_if_unstarted(TASK) == retained
    assert db.calls[0] == ("refund_code_task_if_unstarted", {"p_task_id": TASK["id"], "p_user_id": USER["id"]}, {"retry_transient": True})
    public = service.public_task(retained)
    assert public["status"] == "failed" and public["payment_source"] == "credits"
    assert not {"user_id", "usage_receipt", "lease_token", "provider_started_at", "provider_budget_policy",
                "provider_execution_lease_token", "future_private_key"}.intersection(public)
