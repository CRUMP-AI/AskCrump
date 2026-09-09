from __future__ import annotations

from contextlib import asynccontextmanager
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend import code_runner


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_crump_code_sandbox_smoke.py"
SPEC = importlib.util.spec_from_file_location("crump_code_sandbox_smoke", SCRIPT_PATH)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def _valid_environment() -> dict[str, str]:
    return {"VERCEL_OIDC_TOKEN": "opaque-token", "CRUMP_ENABLE_CODE_WORKSPACE": "false"}


def test_dry_run_is_content_free_and_cannot_authorize_live_compute(capsys):
    assert smoke.main(["--dry-run"]) == 0
    receipt = json.loads(capsys.readouterr().out)

    assert receipt == smoke.smoke_plan()
    assert receipt["wouldProvisionSandboxes"] == 1
    assert receipt["modelCalls"] == 0
    assert receipt["databaseWrites"] == 0
    assert receipt["customerData"] is False
    assert receipt["liveRunAuthorized"] is False
    assert smoke.FIXTURE_REPOSITORY not in json.dumps(receipt)


@pytest.mark.parametrize(
    "cost,source,environment,code",
    [
        (None, smoke.SOURCE_ACKNOWLEDGEMENT, _valid_environment(), "CODE_SMOKE_COST_ACK_REQUIRED"),
        (2, smoke.SOURCE_ACKNOWLEDGEMENT, _valid_environment(), "CODE_SMOKE_COST_ACK_REQUIRED"),
        (1, None, _valid_environment(), "CODE_SMOKE_SOURCE_ACK_REQUIRED"),
        (1, "different-source", _valid_environment(), "CODE_SMOKE_SOURCE_ACK_REQUIRED"),
        (
            1,
            smoke.SOURCE_ACKNOWLEDGEMENT,
            {"VERCEL_OIDC_TOKEN": "opaque-token", "CRUMP_ENABLE_CODE_WORKSPACE": "true"},
            "CODE_SMOKE_PUBLIC_FEATURE_MUST_BE_DISABLED",
        ),
        (1, smoke.SOURCE_ACKNOWLEDGEMENT, {}, "CODE_SMOKE_OIDC_REQUIRED"),
    ],
)
def test_live_gate_fails_closed_before_identity_or_compute(
    monkeypatch, cost, source, environment, code
):
    called = False

    def unexpected_decode(_token):
        nonlocal called
        called = True
        raise AssertionError("identity decoding should not run")

    monkeypatch.setattr(smoke, "decode_sandbox_identity", unexpected_decode)
    with pytest.raises(smoke.SmokeGateError) as exc:
        smoke.validate_live_gate(
            confirmed_cost_cents=cost,
            confirmed_source=source,
            environment=environment,
        )
    assert exc.value.code == code
    assert called is False


def test_live_gate_requires_exact_ask_crump_oidc_scope(monkeypatch):
    monkeypatch.setattr(
        smoke,
        "decode_sandbox_identity",
        lambda _token: ("different-project", smoke.EXPECTED_TEAM_ID),
    )
    with pytest.raises(smoke.SmokeGateError) as exc:
        smoke.validate_live_gate(
            confirmed_cost_cents=1,
            confirmed_source=smoke.SOURCE_ACKNOWLEDGEMENT,
            environment=_valid_environment(),
        )
    assert exc.value.code == "CODE_SMOKE_OIDC_SCOPE_MISMATCH"


def test_live_gate_returns_token_without_including_it_in_any_receipt(monkeypatch):
    monkeypatch.setattr(
        smoke,
        "decode_sandbox_identity",
        lambda _token: (smoke.EXPECTED_PROJECT_ID, smoke.EXPECTED_TEAM_ID),
    )
    token = smoke.validate_live_gate(
        confirmed_cost_cents=1,
        confirmed_source=smoke.SOURCE_ACKNOWLEDGEMENT,
        environment=_valid_environment(),
    )
    assert token == "opaque-token"
    assert token not in json.dumps(smoke.smoke_plan())


class _FakeSandbox:
    def __init__(self, *, network_denied: bool = True, secret_count: int = 0) -> None:
        self.network_denied = network_denied
        self.secret_count = secret_count
        self.network_policy = SimpleNamespace(mode="deny-all")
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    async def run_process(self, command, args, **kwargs):
        self.calls.append((command, tuple(args)))
        assert kwargs["capture_output"] is True
        if command == "git" and args == ["rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout=smoke.FIXTURE_REVISION + "\n", stderr="")
        if command == "git" and args == ["status", "--porcelain"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "socket.create_connection" in " ".join(args):
            return SimpleNamespace(
                returncode=1 if self.network_denied else 0,
                stdout="",
                stderr="network output is deliberately ignored",
            )
        if "names={'ANTHROPIC_API_KEY'" in " ".join(args):
            return SimpleNamespace(returncode=0, stdout=f"{self.secret_count}\n", stderr="")
        if ".crump-code-smoke" in " ".join(args):
            return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")
        raise AssertionError((command, args))


@pytest.mark.asyncio
async def test_live_smoke_uses_fixed_non_model_non_database_checks(monkeypatch):
    sandbox = _FakeSandbox()
    captured: dict[str, object] = {}

    @asynccontextmanager
    async def fake_provision(task, *, oidc_token):
        captured["task"] = dict(task)
        captured["token"] = oidc_token
        try:
            yield sandbox
        finally:
            captured["cleanup"] = True

    monkeypatch.setattr(smoke, "provision_code_sandbox", fake_provision)
    receipt = await smoke.run_live_smoke("opaque-token")

    assert captured == {
        "task": {
            "id": "operator-smoke",
            "source_repo_url": smoke.FIXTURE_REPOSITORY,
            "source_ref": smoke.FIXTURE_REVISION,
            "max_duration_seconds": 30,
        },
        "token": "opaque-token",
        "cleanup": True,
    }
    assert receipt["success"] is True
    assert receipt["fixture"] == smoke.FIXTURE_NAME
    assert receipt["modelCalls"] == 0
    assert receipt["databaseWrites"] == 0
    assert receipt["customerData"] is False
    assert receipt["checks"] == {
        "revisionPinned": True,
        "workspaceWritable": True,
        "repositoryCleanAfterProbe": True,
        "sensitiveEnvironmentNames": 0,
        "networkDenied": True,
        "reportedNetworkPolicy": "deny-all",
        "cleanupCompleted": True,
    }
    assert len(sandbox.calls) == 5
    assert "opaque-token" not in json.dumps(receipt)
    assert smoke.FIXTURE_REPOSITORY not in json.dumps(receipt)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sandbox,code",
    [
        (_FakeSandbox(network_denied=False), "CODE_SMOKE_NETWORK_NOT_DENIED"),
        (_FakeSandbox(secret_count=1), "CODE_SMOKE_ENVIRONMENT_EXPOSED"),
    ],
)
async def test_live_smoke_rejects_unsafe_runtime_evidence(monkeypatch, sandbox, code):
    @asynccontextmanager
    async def fake_provision(_task, *, oidc_token):
        assert oidc_token == "opaque-token"
        yield sandbox

    monkeypatch.setattr(smoke, "provision_code_sandbox", fake_provision)
    with pytest.raises(smoke.SmokeGateError) as exc:
        await smoke.run_live_smoke("opaque-token")
    assert exc.value.code == code


@pytest.mark.asyncio
async def test_production_runner_and_smoke_share_exact_sandbox_provisioning(monkeypatch):
    captured: dict[str, object] = {}

    class Value:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class NetworkPolicy:
        @staticmethod
        def deny_all():
            return Value(mode="deny-all")

    class Session:
        async def __aenter__(self):
            captured["session_entered"] = True

        async def __aexit__(self, *_args):
            captured["session_exited"] = True

    class SandboxContext:
        async def __aenter__(self):
            captured["sandbox_entered"] = True
            return "sandbox-handle"

        async def __aexit__(self, *_args):
            captured["sandbox_destroyed"] = True

    def create_sandbox(**kwargs):
        captured["create"] = kwargs
        return SandboxContext()

    runtime = SimpleNamespace(
        GitSource=Value,
        NetworkPolicy=NetworkPolicy,
        SandboxCredentials=Value,
        SandboxResources=Value,
        SandboxServiceOptions=Value,
        create_sandbox=create_sandbox,
        session=lambda **kwargs: (captured.update(session=kwargs) or Session()),
    )
    monkeypatch.setattr(
        code_runner,
        "decode_sandbox_identity",
        lambda _token: (smoke.EXPECTED_PROJECT_ID, smoke.EXPECTED_TEAM_ID),
    )
    task = {
        "id": "operator-smoke",
        "source_repo_url": smoke.FIXTURE_REPOSITORY,
        "source_ref": smoke.FIXTURE_REVISION,
        "max_duration_seconds": 30,
    }

    async with code_runner.provision_code_sandbox(
        task, oidc_token="opaque-token", runtime=runtime
    ) as sandbox:
        assert sandbox == "sandbox-handle"

    create = captured["create"]
    assert create["project_id"] == smoke.EXPECTED_PROJECT_ID
    assert create["source"].url == smoke.FIXTURE_REPOSITORY
    assert create["source"].revision == smoke.FIXTURE_REVISION
    assert create["source"].depth == 1
    assert create["execution_time_limit"] == 30
    assert create["resources"].vcpus == 2
    assert create["resources"].memory == 4096
    assert create["persistent"] is False
    assert create["network_policy"].mode == "deny-all"
    assert create["env"] == {}
    assert create["tags"] == {"feature": "crump-code", "task": "operator-smoke"}
    assert create["destroy"] is True
    credentials_factory = captured["session"]["service_options"][0].credentials_factory
    credentials = await credentials_factory()
    assert credentials.token == "opaque-token"
    assert credentials.project_id == smoke.EXPECTED_PROJECT_ID
    assert credentials.team_id == smoke.EXPECTED_TEAM_ID
    assert captured["sandbox_destroyed"] is True
    assert captured["session_exited"] is True
