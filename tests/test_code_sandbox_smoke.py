from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import time

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest

from backend import code_runner
from backend.code_identity import CodeIdentityVerifier, JWKS_URL, verify_code_identity


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_crump_code_sandbox_smoke.py"
SPEC = importlib.util.spec_from_file_location("crump_code_sandbox_smoke", SCRIPT_PATH)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def _valid_environment() -> dict[str, str]:
    return {
        "VERCEL_OIDC_TOKEN": "opaque-token", "CRUMP_ENABLE_CODE_WORKSPACE": "false",
        "CODE_OIDC_ISSUER": "https://oidc.vercel.com/offline-team",
        "CODE_OIDC_AUDIENCE": "https://vercel.com/offline-team",
        "CODE_OIDC_ENVIRONMENT": "production",
    }


def test_dry_run_is_content_free_and_cannot_authorize_live_compute(capsys, monkeypatch):
    def unexpected(*_args, **_kwargs):
        raise AssertionError("Dry run must not initialize a loop, verify identity or provision")

    monkeypatch.setattr(smoke, "decode_sandbox_identity", unexpected)
    monkeypatch.setattr(smoke, "provision_code_sandbox", unexpected)
    monkeypatch.setattr(smoke.asyncio, "run", unexpected)
    assert smoke.main(["--dry-run"]) == 0
    receipt = json.loads(capsys.readouterr().out)

    assert receipt == smoke.smoke_plan()
    assert receipt["wouldProvisionSandboxes"] == 1
    assert receipt["modelCalls"] == 0
    assert receipt["databaseWrites"] == 0
    assert receipt["customerData"] is False
    assert receipt["liveRunAuthorized"] is False
    assert receipt["injectedEnvironmentVariables"] == 3
    assert receipt["privilegedEnvironmentVariables"] == 0
    assert smoke.FIXTURE_REPOSITORY not in json.dumps(receipt)


@pytest.mark.parametrize(
    "cost,source,environment,code",
    [
        (None, smoke.SOURCE_ACKNOWLEDGEMENT, _valid_environment(), "CODE_SMOKE_COST_ACK_REQUIRED"),
        (2, smoke.SOURCE_ACKNOWLEDGEMENT, _valid_environment(), "CODE_SMOKE_COST_ACK_REQUIRED"),
        (True, smoke.SOURCE_ACKNOWLEDGEMENT, _valid_environment(), "CODE_SMOKE_COST_ACK_REQUIRED"),
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
@pytest.mark.asyncio
async def test_live_gate_fails_closed_before_identity_or_compute(
    monkeypatch, cost, source, environment, code
):
    called = False

    async def unexpected_decode(_token, *, settings):
        nonlocal called
        called = True
        raise AssertionError("identity decoding should not run")

    monkeypatch.setattr(smoke, "decode_sandbox_identity", unexpected_decode)
    with pytest.raises(smoke.SmokeGateError) as exc:
        await smoke.validate_live_gate(
            confirmed_cost_cents=cost,
            confirmed_source=source,
            environment=environment,
        )
    assert exc.value.code == code
    assert called is False


@pytest.mark.asyncio
async def test_live_gate_requires_exact_ask_crump_oidc_scope(monkeypatch):
    async def different_scope(_token, *, settings):
        return "different-project", smoke.EXPECTED_TEAM_ID

    monkeypatch.setattr(smoke, "decode_sandbox_identity", different_scope)
    with pytest.raises(smoke.SmokeGateError) as exc:
        await smoke.validate_live_gate(
            confirmed_cost_cents=1,
            confirmed_source=smoke.SOURCE_ACKNOWLEDGEMENT,
            environment=_valid_environment(),
        )
    assert exc.value.code == "CODE_SMOKE_OIDC_SCOPE_MISMATCH"


@pytest.mark.asyncio
async def test_live_gate_returns_token_without_including_it_in_any_receipt(monkeypatch):
    async def verified_scope(_token, *, settings):
        assert settings.code_oidc_project_id == smoke.EXPECTED_PROJECT_ID
        assert settings.code_oidc_team_id == smoke.EXPECTED_TEAM_ID
        return smoke.EXPECTED_PROJECT_ID, smoke.EXPECTED_TEAM_ID

    monkeypatch.setattr(smoke, "decode_sandbox_identity", verified_scope)
    token = await smoke.validate_live_gate(
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
    async def fake_provision(task, *, oidc_token, settings):
        captured["task"] = dict(task)
        captured["token"] = oidc_token
        try:
            yield sandbox
        finally:
            captured["cleanup"] = True

    monkeypatch.setattr(smoke, "provision_code_sandbox", fake_provision)
    receipt = await smoke.run_live_smoke("opaque-token", settings=smoke.smoke_identity_settings(_valid_environment()))

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
    async def fake_provision(_task, *, oidc_token, settings):
        assert oidc_token == "opaque-token"
        yield sandbox

    monkeypatch.setattr(smoke, "provision_code_sandbox", fake_provision)
    with pytest.raises(smoke.SmokeGateError) as exc:
        await smoke.run_live_smoke("opaque-token", settings=smoke.smoke_identity_settings(_valid_environment()))
    assert exc.value.code == code


def _capturing_runtime(captured):
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

    return SimpleNamespace(
        GitSource=Value,
        NetworkPolicy=NetworkPolicy,
        SandboxCredentials=Value,
        SandboxResources=Value,
        SandboxServiceOptions=Value,
        create_sandbox=create_sandbox,
        session=lambda **kwargs: (captured.update(session=kwargs) or Session()),
    )


@pytest.mark.asyncio
async def test_production_runner_and_smoke_share_exact_sandbox_provisioning(monkeypatch, signed_identity):
    captured: dict[str, object] = {}
    runtime = _capturing_runtime(captured)
    task = {
        "id": "operator-smoke",
        "source_repo_url": smoke.FIXTURE_REPOSITORY,
        "source_ref": smoke.FIXTURE_REVISION,
        "max_duration_seconds": 30,
    }

    async with code_runner.provision_code_sandbox(
        task, oidc_token=signed_identity.signed, runtime=runtime,
        settings=smoke.smoke_identity_settings(_valid_environment()),
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
    assert create["env"] == {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": "/tmp/crump-code-pycache",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
    }
    assert not set(create["env"]) & {
        "VERCEL_OIDC_TOKEN", "VERCEL_TOKEN", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_URL", "DATABASE_URL", "DB_PASSWORD",
    }
    assert create["tags"] == {"feature": "crump-code", "task": "operator-smoke"}
    assert create["destroy"] is True
    credentials_factory = captured["session"]["service_options"][0].credentials_factory
    credentials = await credentials_factory()
    assert credentials.token == signed_identity.signed
    assert credentials.project_id == smoke.EXPECTED_PROJECT_ID
    assert credentials.team_id == smoke.EXPECTED_TEAM_ID
    assert captured["sandbox_destroyed"] is True
    assert captured["session_exited"] is True
    assert len(signed_identity.requests) == 1


@pytest.mark.asyncio
async def test_real_python_syntax_verification_keeps_bytecode_outside_repository(tmp_path, signed_identity):
    captured = {}
    task = {"id": "offline-cache-check", "source_repo_url": smoke.FIXTURE_REPOSITORY,
            "source_ref": smoke.FIXTURE_REVISION, "max_duration_seconds": 30}
    async with code_runner.provision_code_sandbox(
        task, oidc_token=signed_identity.signed,
        settings=smoke.smoke_identity_settings(_valid_environment()),
        runtime=_capturing_runtime(captured),
    ):
        pass

    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "example.py"
    source.write_text("answer = 42\n", encoding="utf-8")
    cache = tmp_path / "outside-repository-cache"
    process_environment = {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH")
                           if name in os.environ}
    process_environment.update(captured["create"]["env"])
    # The production Linux /tmp prefix maps to a private native temp path here.
    process_environment["PYTHONPYCACHEPREFIX"] = str(cache)
    process_environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "Offline fixture", "GIT_AUTHOR_EMAIL": "offline@example.invalid",
        "GIT_COMMITTER_NAME": "Offline fixture", "GIT_COMMITTER_EMAIL": "offline@example.invalid"})
    git = shutil.which("git")
    assert git, "This source-integrity regression requires offline Git"
    for args in (["init", "--quiet"], ["add", "example.py"],
                 ["-c", "commit.gpgsign=false", "commit", "--quiet", "--no-verify", "-m", "Source fixture"]):
        subprocess.run([git, *args], cwd=repository, env=process_environment, check=True, capture_output=True)
    commands = []

    class LocalPythonProcess:
        async def run_process(self, command, args, *, kill_after, capture_output):
            assert command in {"python3", "git"} and capture_output is True
            commands.append([command, *args])
            native_args = ["pycache_prefix=" + str(cache) if value == "pycache_prefix=/tmp/crump-code-pycache" else value for value in args]
            process = await asyncio.create_subprocess_exec(
                sys.executable if command == "python3" else git, *native_args, cwd=repository, env=process_environment,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=kill_after)
            except BaseException:
                if process.returncode is None:
                    process.kill()
                    await process.communicate()
                raise
            return SimpleNamespace(returncode=process.returncode,
                                   stdout=stdout.decode("utf-8", errors="replace"),
                                   stderr=stderr.decode("utf-8", errors="replace"))

    workspace = code_runner.SandboxWorkspace(LocalPythonProcess())
    await workspace.syntax_verify(["example.py"])
    assert commands[0] == ["python3", "-I", "-c", code_runner._EXISTING_SOURCE_SCRIPT, '["example.py"]']
    assert [command for command in commands if "py_compile" in command] == [
        ["python3", "-I", "-X", "pycache_prefix=/tmp/crump-code-pycache", "-m", "py_compile", "example.py"]]
    assert sum(command[:3] == ["python3", "-I", "-c"] and command[3] == code_runner._SOURCE_STATE_SCRIPT for command in commands) == 2
    assert workspace.verification[0]["returnCode"] == 0
    assert sorted(path.relative_to(repository).as_posix() for path in repository.rglob("*")
                  if ".git" not in path.relative_to(repository).parts) == ["example.py"]
    assert source.read_text(encoding="utf-8") == "answer = 42\n"
    assert list(cache.rglob("example.*.pyc")), "py_compile must write its actual artifact outside the repository"


@pytest.fixture(scope="module")
def smoke_signing_keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


@pytest.fixture
def signed_identity(monkeypatch, smoke_signing_keys):
    key, wrong_key = smoke_signing_keys
    now = int(time.time())
    claims = {
        "iss": "https://oidc.vercel.com/offline-team",
        "aud": "https://vercel.com/offline-team",
        "sub": "owner:offline-team:project:fixture:environment:production",
        "iat": now - 10, "nbf": now - 10, "exp": now + 3600,
        "project_id": smoke.EXPECTED_PROJECT_ID,
        "owner_id": smoke.EXPECTED_TEAM_ID, "environment": "production",
    }
    jwk = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())),
           "kid": "smoke-fixture", "alg": "RS256", "use": "sig"}
    requests = []

    async def transport(request):
        requests.append(request)
        assert str(request.url) == JWKS_URL
        return httpx.Response(200, json={"keys": [jwk]})

    verifier = CodeIdentityVerifier(transport=httpx.MockTransport(transport))

    async def verified(token, settings):
        return await verify_code_identity(token, settings, verifier=verifier)

    monkeypatch.setattr(code_runner, "verify_code_identity", verified)
    signed = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "smoke-fixture"})
    return SimpleNamespace(key=key, wrong_key=wrong_key, claims=claims, signed=signed, requests=requests)


@pytest.mark.asyncio
async def test_both_release_stops_are_checked_before_identity(monkeypatch):
    called = []

    async def unexpected(_token, *, settings):
        called.append(True)
        raise AssertionError("No public key request is allowed")

    monkeypatch.setattr(smoke, "decode_sandbox_identity", unexpected)
    monkeypatch.setattr(smoke.code_config, "CODE_WORKSPACE_PUBLIC_RELEASED", True)
    with pytest.raises(smoke.SmokeGateError) as exc:
        await smoke.validate_live_gate(
            confirmed_cost_cents=1, confirmed_source=smoke.SOURCE_ACKNOWLEDGEMENT,
            environment=_valid_environment(),
        )
    assert exc.value.code == "CODE_SMOKE_PUBLIC_FEATURE_MUST_BE_DISABLED"
    assert called == []


@pytest.mark.asyncio
async def test_signed_live_gate_pins_ids_and_requires_explicit_trust_policy(signed_identity):
    environment = {**_valid_environment(), "VERCEL_OIDC_TOKEN": signed_identity.signed,
                   "CODE_OIDC_PROJECT_ID": "prj_attacker", "CODE_OIDC_TEAM_ID": "team_attacker"}
    returned = await smoke.validate_live_gate(
        confirmed_cost_cents=1, confirmed_source=smoke.SOURCE_ACKNOWLEDGEMENT,
        environment=environment,
    )
    assert returned == signed_identity.signed
    settings = smoke.smoke_identity_settings(environment)
    assert settings.code_oidc_project_id == smoke.EXPECTED_PROJECT_ID
    assert settings.code_oidc_team_id == smoke.EXPECTED_TEAM_ID
    assert set(vars(settings)) == {
        "code_oidc_issuer", "code_oidc_audience", "code_oidc_environment",
        "code_oidc_project_id", "code_oidc_team_id",
    }
    assert len(signed_identity.requests) == 1
    for field in ("CODE_OIDC_ISSUER", "CODE_OIDC_AUDIENCE", "CODE_OIDC_ENVIRONMENT"):
        missing = dict(environment); del missing[field]
        with pytest.raises(smoke.SmokeGateError) as exc:
            await smoke.validate_live_gate(
                confirmed_cost_cents=1, confirmed_source=smoke.SOURCE_ACKNOWLEDGEMENT,
                environment=missing,
            )
        assert exc.value.code == "CODE_SMOKE_OIDC_INVALID"
    assert len(signed_identity.requests) == 1, "missing policy must not cause even a JWKS fetch"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["forged", "expired", "not-before", "issuer", "audience", "project", "team"])
async def test_bad_signed_identity_fails_gate_and_provision_before_runtime(monkeypatch, signed_identity, invalid):
    claims = dict(signed_identity.claims)
    key = signed_identity.key
    if invalid == "forged": key = signed_identity.wrong_key
    if invalid == "expired": claims["exp"] = 1
    if invalid == "not-before": claims["nbf"] = 4_000_000_000
    if invalid == "issuer": claims["iss"] = "https://oidc.vercel.com/another-team"
    if invalid == "audience": claims["aud"] = "https://vercel.com/another-team"
    if invalid == "project": claims["project_id"] = "prj_another"
    if invalid == "team": claims["owner_id"] = "team_another"
    token = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "smoke-fixture"})
    called = []

    def unexpected_runtime():
        called.append(True)
        raise AssertionError("Invalid workload must never reach Sandbox runtime loading")

    monkeypatch.setattr(code_runner, "_load_sandbox_runtime", unexpected_runtime)
    environment = {**_valid_environment(), "VERCEL_OIDC_TOKEN": token}
    with pytest.raises(smoke.SmokeGateError) as exc:
        await smoke.validate_live_gate(
            confirmed_cost_cents=1, confirmed_source=smoke.SOURCE_ACKNOWLEDGEMENT,
            environment=environment,
        )
    assert exc.value.code == "CODE_SMOKE_OIDC_INVALID"
    with pytest.raises(code_runner.CodeRunnerError) as runner_error:
        async with code_runner.provision_code_sandbox(
            {"id": "offline-smoke"}, oidc_token=token,
            settings=smoke.smoke_identity_settings(environment),
        ):
            raise AssertionError("No Sandbox may be yielded")
    assert runner_error.value.code == "SANDBOX_AUTH_INVALID"
    assert called == []


def test_cli_uses_one_async_loop_for_verified_gate_and_fake_smoke(monkeypatch, capsys):
    loops = []
    for name, value in _valid_environment().items():
        monkeypatch.setenv(name, value)

    async def verified_scope(_token, *, settings):
        loops.append(asyncio.get_running_loop())
        return smoke.EXPECTED_PROJECT_ID, smoke.EXPECTED_TEAM_ID

    async def fake_live(token, *, settings):
        loops.append(asyncio.get_running_loop())
        assert token == "opaque-token"
        assert settings.code_oidc_project_id == smoke.EXPECTED_PROJECT_ID
        return {"success": True, "mode": "offline-fixture"}

    monkeypatch.setattr(smoke, "decode_sandbox_identity", verified_scope)
    monkeypatch.setattr(smoke, "run_live_smoke", fake_live)
    assert smoke.main(["--live", "--confirm-max-cost-cents", "1", "--confirm-source", smoke.SOURCE_ACKNOWLEDGEMENT]) == 0
    assert len(loops) == 2 and loops[0] is loops[1]
    assert json.loads(capsys.readouterr().out) == {"success": True, "mode": "offline-fixture"}
