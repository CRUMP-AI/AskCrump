"""Offline integration of Code identity, durable provider admission, and completion.

Only generated signing keys, MockTransport, and in-memory control-plane doubles
are used. No paid Sandbox, model endpoint, database, or environment secrets.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest

from backend import code_runner, code_worker
from backend.code_budget import CodeBudgetPolicy
from backend.code_identity import CodeIdentityVerifier, JWKS_URL, verify_code_identity
from backend.code_runner import CodeRunnerError, CrumpCodeRunner, SandboxWorkspace
from backend.code_worker import CodeWorker


MODEL = "offline-approved-model-20261015"
TASK = {"id": "offline-task", "user_id": "offline-user", "lease_token": "offline-lease",
        "status": "provisioning", "mode": "implement", "objective": "Repair a local fixture",
        "attempt_count": 1, "max_attempts": 3, "max_duration_seconds": 30,
        "source_repo_url": "https://github.com/octocat/Hello-World", "source_ref": "main"}


def settings(**changes):
    return SimpleNamespace(**{
        "anthropic_api_key": "offline-not-a-provider-credential", "anthropic_model": MODEL,
        "code_workspace_enabled": True, "code_max_duration_seconds": 30, "code_max_agent_steps": 2,
        "code_oidc_issuer": "https://oidc.vercel.com/offline-team",
        "code_oidc_audience": "https://vercel.com/offline-team",
        "code_oidc_project_id": "prj_offline", "code_oidc_team_id": "team_offline",
        "code_oidc_environment": "production", **changes,
    })


@pytest.fixture
def provider_policy(monkeypatch):
    values = {"MODEL": MODEL, "INPUT_USD_MICROS_PER_MILLION": "3000000",
              "OUTPUT_USD_MICROS_PER_MILLION": "15000000", "MAX_INPUT_BYTES": "100000",
              "MAX_OUTPUT_TOKENS": "6000", "CALL_USD_MICROS": "500000",
              "RUN_USD_MICROS": "2000000", "ACCOUNT_DAILY_USD_MICROS": "10000000",
              "GLOBAL_DAILY_USD_MICROS": "20000000"}
    for suffix, value in values.items():
        monkeypatch.setenv("CODE_PROVIDER_" + suffix, value)
    return CodeBudgetPolicy.from_env()


@pytest.fixture
def provider_http(monkeypatch):
    requests = []
    reply = {"status": 200, "payload": {"content": [{"type": "text", "text": "Offline fixture"}],
                                        "usage": {"input_tokens": 100, "output_tokens": 20}}}

    def respond(request):
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.method == "POST"
        requests.append(request)
        if "error" in reply:
            raise reply["error"]
        return httpx.Response(reply["status"], json=reply["payload"])

    original_client = httpx.AsyncClient

    def offline_client(*args, **kwargs):
        # Explicit transports used by the signed JWKS fixture remain intact.
        kwargs.setdefault("transport", httpx.MockTransport(respond))
        return original_client(*args, **kwargs)

    monkeypatch.setattr(code_runner.httpx, "AsyncClient", offline_client)
    return requests, reply


class ProviderDB:
    def __init__(self, **responses):
        self.responses = responses
        self.calls = []
        self.reservation = None

    async def rpc(self, function, payload, **options):
        self.calls.append((function, deepcopy(payload), options))
        if function == "reserve_code_provider_call":
            self.reservation = {"id": "offline-reservation", "status": "reserved",
                                "policy": payload["p_policy"],
                                "input_ceiling": payload["p_input_ceiling"],
                                "output_ceiling": payload["p_output_ceiling"],
                                "reserved_micros": payload["p_reserved_micros"]}
        default = {
            "reserve_code_provider_call": {"outcome": "reserved", "reservation": self.reservation},
            "begin_code_provider_call": {"outcome": "started", "reservation": self.reservation},
            "settle_code_provider_call": {"outcome": "settled", "reservation": {"status": "settled"}},
            "release_code_provider_call": {"outcome": "released"},
        }
        response = self.responses.get(function, default[function])
        if isinstance(response, BaseException):
            raise response
        return deepcopy(response)


class Service:
    def __init__(self, task=None, db=None):
        self.current = deepcopy(TASK if task is None else task)
        self.db = db or ProviderDB()
        self.transitions = []
        self.events = []
        self.claims = []
        self.requeues = []
        self.refunds = []

    async def get(self, **_kwargs):
        return deepcopy(self.current)

    async def transition(self, _task, status, **kwargs):
        self.current.update(kwargs.get("changes", {}))
        self.current["status"] = status
        self.transitions.append(status)
        return deepcopy(self.current)

    async def append_event(self, _task, kind, payload):
        self.events.append((kind, deepcopy(payload)))

    async def next_refund_pending(self):
        return None

    async def claim_next(self, **kwargs):
        self.claims.append(kwargs)
        return deepcopy(self.current)

    async def requeue_after_failure(self, task, **kwargs):
        self.requeues.append((deepcopy(task), kwargs))
        return deepcopy(task)

    async def refund_if_unstarted(self, task):
        self.refunds.append(deepcopy(task))
        return deepcopy(task)


async def turn(db):
    runner = CrumpCodeRunner(settings(), Service(db=db))
    return await runner._anthropic_turn(task=deepcopy(TASK), call_key="step:0",
                                        messages=[{"role": "user", "content": "Offline source"}], tools=[])


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["missing", "model-mismatch", "request-too-large"])
async def test_invalid_provider_policy_reaches_no_provider_http_or_reservation(
    monkeypatch, provider_policy, provider_http, invalid,
):
    if invalid == "missing":
        monkeypatch.delenv("CODE_PROVIDER_INPUT_USD_MICROS_PER_MILLION")
    elif invalid == "model-mismatch":
        monkeypatch.setenv("CODE_PROVIDER_MODEL", "different-approved-model")
    else:
        monkeypatch.setenv("CODE_PROVIDER_MAX_INPUT_BYTES", "1")
    db = ProviderDB()
    with pytest.raises(CodeRunnerError):
        await turn(db)
    assert provider_http[0] == []
    assert db.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("admission", [None, {}, {"outcome": "denied"},
    {"outcome": "reserved"}, {"outcome": "reserved", "reservation": None}])
async def test_unconfirmed_reservation_cannot_dispatch_http(provider_policy, provider_http, admission):
    db = ProviderDB(reserve_code_provider_call=admission)
    with pytest.raises(CodeRunnerError):
        await turn(db)
    assert provider_http[0] == []
    assert [call[0] for call in db.calls] == ["reserve_code_provider_call"]


@pytest.mark.asyncio
@pytest.mark.parametrize("admission", [None, {}, {"outcome": "already_started"},
    {"outcome": "started"}, {"outcome": "uncertain"}, RuntimeError("offline ambiguous begin")])
async def test_unconfirmed_durable_begin_cannot_dispatch_http(provider_policy, provider_http, admission):
    db = ProviderDB(begin_code_provider_call=admission)
    with pytest.raises((CodeRunnerError, RuntimeError)):
        await turn(db)
    assert provider_http[0] == []
    assert [call[0] for call in db.calls] == ["reserve_code_provider_call",
        "begin_code_provider_call", "release_code_provider_call"]


@pytest.mark.asyncio
@pytest.mark.parametrize("settlement", [None, {}, {"outcome": "uncertain"},
    {"outcome": "settled_replay", "reservation": {"status": "uncertain"}},
    {"outcome": "settled_replay"}, RuntimeError("offline lost settlement response")])
async def test_unconfirmed_settlement_never_returns_a_success(provider_policy, provider_http, settlement):
    db = ProviderDB(settle_code_provider_call=settlement)
    with pytest.raises(CodeRunnerError) as caught:
        await turn(db)
    assert caught.value.code == "CODE_PROVIDER_OUTCOME_UNCERTAIN"
    assert len(provider_http[0]) == 1
    assert [call[0] for call in db.calls] == ["reserve_code_provider_call",
        "begin_code_provider_call", "settle_code_provider_call"]


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["settled", "settled_replay"])
async def test_canonical_settlement_accepts_exactly_one_provider_response(provider_policy, provider_http, outcome):
    db = ProviderDB(settle_code_provider_call={"outcome": outcome, "reservation": {"status": "settled"}})
    assert (await turn(db))["content"][0]["text"] == "Offline fixture"
    assert len(provider_http[0]) == 1
    begin = next(call for call in db.calls if call[0] == "begin_code_provider_call")
    settle = db.calls[-1]
    assert begin[1]["p_lease_token"] == TASK["lease_token"]
    assert settle[1]["p_uncertain"] is False
    assert settle[1]["p_actual_micros"] == provider_policy.price(100, 20)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, {}, {"content": "invalid"},
    {"content": [], "usage": None}, {"content": [], "usage": {"input_tokens": True, "output_tokens": 2}}])
async def test_invalid_provider_payload_or_usage_is_never_success(provider_policy, provider_http, payload):
    requests, reply = provider_http
    reply["payload"] = payload
    db = ProviderDB(settle_code_provider_call={"outcome": "uncertain", "reservation": {"status": "uncertain"}})
    with pytest.raises(CodeRunnerError):
        await turn(db)
    assert len(requests) == 1
    assert db.calls[-1][0] == "settle_code_provider_call"
    assert db.calls[-1][1]["p_uncertain"] is True


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["forged", "expired", "wrong-project", "wrong-team", "wrong-audience"])
async def test_bad_signed_identity_stops_worker_claim_and_sandbox_runtime(
    monkeypatch, provider_http, signing_key, fault,
):
    now = int(time.time())
    claims = {"iss": settings().code_oidc_issuer, "aud": settings().code_oidc_audience,
              "sub": "owner:offline-team:project:fixture:environment:production",
              "iat": now - 10, "nbf": now - 10, "exp": now + 600,
              "project_id": "prj_offline", "owner_id": "team_offline", "environment": "production"}
    if fault == "expired": claims["exp"] = now - 100
    if fault == "wrong-project": claims["project_id"] = "prj_attacker"
    if fault == "wrong-team": claims["owner_id"] = "team_attacker"
    if fault == "wrong-audience": claims["aud"] = "api://attacker"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048) if fault == "forged" else signing_key
    signed = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "offline"})
    jwk = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key())),
           "kid": "offline", "alg": "RS256", "use": "sig"}

    def jwks(request):
        assert str(request.url) == JWKS_URL and request.method == "GET"
        return httpx.Response(200, json={"keys": [jwk]})

    verifier = CodeIdentityVerifier(transport=httpx.MockTransport(jwks))

    async def verify(value, config):
        return await verify_code_identity(value, config, verifier=verifier)

    monkeypatch.setattr(code_runner, "verify_code_identity", verify)
    monkeypatch.setattr(code_worker, "verify_code_identity", verify)
    runtime = []

    def reject_runtime():
        runtime.append(True)
        raise AssertionError("Unverified identity loaded a Sandbox runtime")

    monkeypatch.setattr(code_runner, "_load_sandbox_runtime", reject_runtime)
    runner = SimpleNamespace(run=AsyncMock(side_effect=AssertionError("Unverified identity ran")))
    service = Service()
    worker = CodeWorker(settings(), service.db, service, runner, SimpleNamespace())
    assert await worker.process_next(oidc_token=signed) == {"handled": False, "claimed": False, "misconfigured": True}
    with pytest.raises(CodeRunnerError) as caught:
        async with code_runner.provision_code_sandbox(deepcopy(TASK), oidc_token=signed, settings=settings()):
            pytest.fail("Invalid identity provisioned a Sandbox")
    assert caught.value.code == "SANDBOX_AUTH_INVALID"
    assert service.claims == [] and service.db.calls == []
    assert provider_http[0] == [] and runtime == []
    runner.run.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [CodeRunnerError("offline timeout", "CODE_MODEL_TIMEOUT"),
                                      RuntimeError("offline unexpected post-provider failure")])
async def test_started_provider_work_cannot_retry_even_for_transient_or_unexpected_failure(monkeypatch, provider_policy, failure):
    monkeypatch.setattr(code_worker, "verify_code_identity", AsyncMock(return_value=SimpleNamespace()))
    service = Service({**TASK, "provider_started_at": "2026-10-15T12:00:00Z"})
    runner = SimpleNamespace(run=AsyncMock(side_effect=failure))
    worker = CodeWorker(settings(), service.db, service, runner, SimpleNamespace())
    assert await worker.process_next(oidc_token="verified-at-helper-seam") == {
        "handled": True, "claimed": True, "status": "failed"}
    assert service.requeues == []
    assert service.transitions == ["failed"]
    assert runner.run.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing", "mismatch", "invalid"])
async def test_invalid_budget_stops_worker_before_claim_and_sandbox(monkeypatch, provider_policy, provider_http, fault):
    verified = AsyncMock(return_value=SimpleNamespace())
    monkeypatch.setattr(code_worker, "verify_code_identity", verified)
    if fault == "missing": monkeypatch.delenv("CODE_PROVIDER_CALL_USD_MICROS")
    if fault == "mismatch": monkeypatch.setenv("CODE_PROVIDER_MODEL", "different-approved-model")
    if fault == "invalid": monkeypatch.setenv("CODE_PROVIDER_RUN_USD_MICROS", "1")
    service = Service()
    runner = SimpleNamespace(run=AsyncMock(side_effect=AssertionError("Invalid budget reached runner")))
    worker = CodeWorker(settings(), service.db, service, runner, SimpleNamespace())
    assert await worker.process_next(oidc_token="verified-at-helper-seam") == {
        "handled": False, "claimed": False, "misconfigured": True}
    verified.assert_awaited_once()
    assert service.claims == [] and service.db.calls == [] and provider_http[0] == []
    runner.run.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing", "mismatch", "drift", "unpinned"])
async def test_runner_budget_drift_cannot_provision_or_send_model_http(monkeypatch, provider_policy, provider_http, fault):
    task = {**TASK, "provider_budget_policy": provider_policy.as_dict()}
    if fault == "missing": monkeypatch.delenv("CODE_PROVIDER_CALL_USD_MICROS")
    if fault == "mismatch": monkeypatch.setenv("CODE_PROVIDER_MODEL", "different-approved-model")
    if fault == "drift": monkeypatch.setenv("CODE_PROVIDER_CALL_USD_MICROS", "500001")
    if fault == "unpinned": task.pop("provider_budget_policy")
    provisions = []

    @asynccontextmanager
    async def no_provision(*_args, **_kwargs):
        provisions.append(True)
        raise AssertionError("Invalid budget reached Sandbox provisioning")
        yield  # pragma: no cover - gives the tripwire the real context-manager contract.

    monkeypatch.setattr(code_runner, "provision_code_sandbox", no_provision)
    service = Service(task)
    with pytest.raises(CodeRunnerError) as caught:
        await CrumpCodeRunner(settings(), service).run(task, oidc_token="not-consumed")
    assert caught.value.code == ("CODE_BUDGET_NOT_CONFIGURED" if fault == "missing"
                                  else "CODE_BUDGET_POLICY_CONFLICT")
    assert provisions == [] and provider_http[0] == [] and service.db.calls == []
    assert service.transitions == []


@pytest.mark.asyncio
async def test_exact_pinned_budget_reaches_only_the_mocked_provision_boundary(monkeypatch, provider_policy, provider_http):
    task = {**TASK, "provider_budget_policy": provider_policy.as_dict()}
    provisions = []

    @asynccontextmanager
    async def admitted(*args, **kwargs):
        provisions.append((args, kwargs))
        raise RuntimeError("offline admitted boundary")
        yield  # pragma: no cover

    monkeypatch.setattr(code_runner, "provision_code_sandbox", admitted)
    service = Service(task)
    with pytest.raises(RuntimeError, match="offline admitted boundary"):
        await CrumpCodeRunner(settings(), service).run(task, oidc_token="helper-boundary-only")
    assert len(provisions) == 1
    assert provisions[0][1]["settings"].anthropic_model == MODEL
    assert provider_http[0] == [] and service.transitions == []


class Workspace:
    def __init__(self, verification, *, incomplete_patch=False):
        self.verification = verification
        self.incomplete_patch = incomplete_patch

    async def base_revision(self): return "offline-base"
    async def list_files(self, _prefix): return "notes.txt"
    async def changed_paths(self): return ["notes.txt"]
    async def syntax_verify(self, _paths): pass

    async def patch(self):
        if self.incomplete_patch:
            raise CodeRunnerError("Offline incomplete artifact", "CODE_RESULT_INCOMPLETE")
        return "diff --git a/notes.txt b/notes.txt\n+fixed\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("verification,code", [
    ([], "CODE_VERIFICATION_REQUIRED"),
    ([{"command": "test", "returnCode": 1}], "CODE_VERIFICATION_FAILED"),
    ([{"command": "test", "returnCode": None}], "CODE_VERIFICATION_FAILED"),
    ([{"command": "test"}], "CODE_VERIFICATION_FAILED"),
    ([{"command": "test", "returnCode": False}], "CODE_VERIFICATION_FAILED"),
    ([{"command": "test", "returnCode": 0.0}], "CODE_VERIFICATION_FAILED"),
])
async def test_failed_null_or_missing_verification_cannot_complete(verification, code):
    service = Service()
    runner = CrumpCodeRunner(settings(), service)
    runner._agent_loop = AsyncMock(return_value="The model claims everything passed")
    result = await runner._run_in_workspace(deepcopy(TASK), Workspace(verification))
    assert result["status"] == "failed" and result["failure_code"] == code
    assert "completed" not in service.transitions
    assert "claims everything passed" not in result["result_summary"]


@pytest.mark.asyncio
async def test_incomplete_patch_never_gets_a_completed_transition():
    service = Service()
    runner = CrumpCodeRunner(settings(), service)
    runner._agent_loop = AsyncMock(return_value="Offline fixture")
    with pytest.raises(CodeRunnerError) as caught:
        await runner._run_in_workspace(deepcopy(TASK), Workspace([{"returnCode": 0}], incomplete_patch=True))
    assert caught.value.code == "CODE_RESULT_INCOMPLETE"
    assert service.transitions == ["running", "verifying"]
    assert "task.completed" not in [kind for kind, _ in service.events]


@pytest.mark.asyncio
@pytest.mark.parametrize("output", [" M .env\0", " M notes.txt\0" * 2000,
    "".join(f" M file{i}.txt\0" for i in range(81))])
async def test_unsafe_or_truncated_changed_file_artifacts_are_rejected(output):
    sandbox = SimpleNamespace(run_process=AsyncMock(return_value=SimpleNamespace(returncode=0, stdout=output)))
    with pytest.raises(CodeRunnerError) as caught:
        await SandboxWorkspace(sandbox).changed_paths()
    assert caught.value.code == "CODE_RESULT_INCOMPLETE"


@pytest.mark.asyncio
async def test_patch_read_failure_rejects_instead_of_returning_a_partial_artifact():
    responses = [SimpleNamespace(returncode=0, stdout=""), SimpleNamespace(returncode=0, stdout=""),
                 SimpleNamespace(returncode=1, stdout="incomplete bytes")]
    sandbox = SimpleNamespace(run_process=AsyncMock(side_effect=responses))
    with pytest.raises(CodeRunnerError) as caught:
        await SandboxWorkspace(sandbox).patch()
    assert caught.value.code == "CODE_RESULT_INCOMPLETE"
    assert sandbox.run_process.await_count == 3
