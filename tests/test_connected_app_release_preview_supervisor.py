from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json

import pytest

from backend import config
from backend.connected_app_kms import ConnectedVercelOIDCAssertion
from backend.connected_app_release_preview_supervisor import (
    ConnectedReleasePreviewSupervisorError,
    claim_connected_release_preview_ceremony,
    run_connected_release_preview_child,
)


NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
INVOCATION = "11111111-1111-4111-8111-111111111111"
TOKEN = "a" * 80 + "." + "b" * 80 + "." + "c" * 80
CONFIRMATION = "RUN_CONNECTED_RELEASE_PREVIEW_WITH_DEDICATED_NON_CUSTOMER_ACCOUNTS"
SHA = hashlib.sha256(b"receipt").hexdigest()


def release_candidate(monkeypatch) -> None:
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED",
        True,
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)


class Input:
    def __init__(self) -> None:
        self.value = bytearray()
        self.closed = False

    def write(self, value: bytes) -> None:
        self.value.extend(value)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class Process:
    def __init__(self, output: bytes, *, returncode: int = 0) -> None:
        self.stdin = Input()
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(output)
        self.stdout.feed_eof()
        self.returncode: int | None = None
        self._final = returncode
        self.terminated = False
        self.killed = False

    async def wait(self) -> int:
        self.returncode = self._final
        return self._final

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def receipt() -> bytes:
    return json.dumps(
        {
            "version": "askcrump-release-preview-child-result-v1",
            "ok": True,
            "invocation_id": INVOCATION,
            "composition_manifest_sha256": SHA,
            "database_target_fingerprint": "1" * 32,
            "release_preview_contract_sha256": SHA,
            "deployment_id": "dpl_12345678abcd",
            "commit_sha": "a" * 40,
            "host_configuration_ciphertext_sha256": SHA,
            "provider_smoke_attestation_sha256": SHA,
            "checked_at": NOW.isoformat(),
            "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
            "process_exit_required": True,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def environment(monkeypatch) -> None:
    values = {
        "APP_ENV": "production",
        "VERCEL": "1",
        "VERCEL_ENV": "production",
        "VERCEL_DEPLOYMENT_ID": "dpl_12345678abcd",
        "VERCEL_GIT_COMMIT_SHA": "a" * 40,
        "VERCEL_PROJECT_ID": "prj_12345678",
        "SUPABASE_URL": config.PRODUCTION_SUPABASE_ORIGIN,
        "SUPABASE_SERVICE_KEY": "service-role-key-" + "s" * 40,
        "CRUMP_CONNECTED_KMS_ENCRYPTED_ROOT_B64": "Y2lwaGVydGV4dA==",
        "CRUMP_CONNECTED_HOST_CONFIGURATION_CIPHERTEXT": "v1:key:nonce:cipher",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "must-not-be-forwarded")


class ClaimDatabase:
    calls: list[tuple[str, dict[str, object]]] = []
    lose_claim = False
    recovery = False

    async def rpc(self, name, payload, *, retry_transient=False):
        del retry_transient
        type(self).calls.append((name, payload))
        if name == "connected_app_claim_release_preview_ceremony_v1":
            if type(self).lose_claim:
                raise TimeoutError
            return {"claimed": True}
        if name == "connected_app_read_release_preview_ceremony_v1":
            reference = datetime.now(UTC)
            return [
                {
                    "invocation_id": INVOCATION,
                    "issued_at": reference.isoformat(),
                    "expires_at": (reference + timedelta(minutes=10)).isoformat(),
                    "recovery": type(self).recovery,
                    "deployment_id": "dpl_12345678abcd",
                    "commit_sha": "a" * 40,
                    "host_configuration_ciphertext_sha256": hashlib.sha256(
                        b"v1:key:nonce:cipher"
                    ).hexdigest(),
                }
            ]
        raise AssertionError(name)


@pytest.mark.asyncio
async def test_supervisor_passes_assertion_only_on_stdin_and_waits_for_exit(
    monkeypatch,
) -> None:
    environment(monkeypatch)
    release_candidate(monkeypatch)
    process = Process(receipt())
    observed: dict[str, object] = {}

    async def create(*args, **kwargs):
        observed["args"] = args
        observed["env"] = kwargs["env"]
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    value = await run_connected_release_preview_child(
        assertion=ConnectedVercelOIDCAssertion(TOKEN),
        invocation_id=INVOCATION,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=10),
        confirmation=CONFIRMATION,
    )
    assert value.invocation_id == INVOCATION
    assert process.returncode == 0
    assert process.stdin.closed is True
    assert TOKEN.encode() in process.stdin.value
    assert TOKEN not in repr(observed["args"])
    assert "VERCEL_OIDC_TOKEN" not in observed["env"]
    assert TOKEN not in repr(observed["env"])


@pytest.mark.asyncio
async def test_lock_false_fails_before_environment_or_process(monkeypatch) -> None:
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED",
        False,
    )
    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("lock-false spawned child")
        ),
    )
    with pytest.raises(ConnectedReleasePreviewSupervisorError):
        await run_connected_release_preview_child(
            assertion=ConnectedVercelOIDCAssertion(TOKEN),
            invocation_id=INVOCATION,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=10),
            confirmation=CONFIRMATION,
        )


@pytest.mark.asyncio
async def test_nonzero_or_oversized_child_output_never_returns_partial_result(
    monkeypatch,
) -> None:
    environment(monkeypatch)
    release_candidate(monkeypatch)
    processes = [Process(b"{}", returncode=1), Process(b"x" * 4097)]

    async def create(*_args, **_kwargs):
        return processes.pop(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create)
    for _ in range(2):
        with pytest.raises(ConnectedReleasePreviewSupervisorError):
            await run_connected_release_preview_child(
                assertion=ConnectedVercelOIDCAssertion(TOKEN),
                invocation_id=INVOCATION,
                issued_at=NOW,
                expires_at=NOW + timedelta(minutes=10),
                confirmation=CONFIRMATION,
            )


@pytest.mark.asyncio
async def test_claim_is_owner_pinned_and_response_loss_uses_readback(
    monkeypatch,
) -> None:
    environment(monkeypatch)
    release_candidate(monkeypatch)
    owner_id = "22222222-2222-4222-8222-222222222222"
    owner_sha256 = hashlib.sha256(
        b"askcrump.connected-release-operator/v1\0" + owner_id.encode("ascii")
    ).hexdigest()
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_OPERATOR_OWNER_SHA256",
        owner_sha256,
    )
    monkeypatch.setattr(
        "backend.connected_app_release_preview_supervisor.ConnectedReleasePreviewProductionDatabase",
        ClaimDatabase,
    )
    ClaimDatabase.calls.clear()
    ClaimDatabase.lose_claim = True
    ClaimDatabase.recovery = False
    value = await claim_connected_release_preview_ceremony(
        owner_id=owner_id,
        session_binding_sha256=SHA,
        confirmation=CONFIRMATION,
    )
    assert value.invocation_id == INVOCATION
    assert [name for name, _payload in ClaimDatabase.calls] == [
        "connected_app_claim_release_preview_ceremony_v1",
        "connected_app_read_release_preview_ceremony_v1",
    ]
    payload = ClaimDatabase.calls[0][1]
    assert payload["p_deployment_id"] == "dpl_12345678abcd"
    assert payload["p_commit_sha"] == "a" * 40
    assert payload["p_host_configuration_ciphertext_sha256"] == hashlib.sha256(
        b"v1:key:nonce:cipher"
    ).hexdigest()
    with pytest.raises(ConnectedReleasePreviewSupervisorError):
        await claim_connected_release_preview_ceremony(
            owner_id="33333333-3333-4333-8333-333333333333",
            session_binding_sha256=SHA,
            confirmation=CONFIRMATION,
        )


@pytest.mark.asyncio
async def test_recovery_claim_is_same_invocation_with_a_fresh_bounded_lease(
    monkeypatch,
) -> None:
    environment(monkeypatch)
    release_candidate(monkeypatch)
    owner_id = "22222222-2222-4222-8222-222222222222"
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_OPERATOR_OWNER_SHA256",
        hashlib.sha256(
            b"askcrump.connected-release-operator/v1\0"
            + owner_id.encode("ascii")
        ).hexdigest(),
    )
    monkeypatch.setattr(
        "backend.connected_app_release_preview_supervisor.ConnectedReleasePreviewProductionDatabase",
        ClaimDatabase,
    )
    ClaimDatabase.calls.clear()
    ClaimDatabase.lose_claim = False
    ClaimDatabase.recovery = True
    claim = await claim_connected_release_preview_ceremony(
        owner_id=owner_id,
        session_binding_sha256=SHA,
        confirmation=CONFIRMATION,
    )
    assert claim.invocation_id == INVOCATION
    assert claim.recovery is True
    assert datetime.now(UTC) < claim.expires_at
    assert claim.expires_at - claim.issued_at <= timedelta(minutes=15)
