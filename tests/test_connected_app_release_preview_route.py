from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from types import SimpleNamespace

from fastapi import FastAPI
import httpx
import pytest

from backend import config
from backend.connected_app_release_preview_supervisor import (
    ConnectedReleasePreviewCeremonyClaim,
    ConnectedReleasePreviewChildResult,
    ConnectedReleasePreviewSupervisorError,
)
from backend.http import register_exception_handlers
from backend.routes import connected_apps
import backend.connected_app_release_preview_supervisor as supervisor


NOW = datetime(2026, 11, 8, 20, 0, tzinfo=UTC)
OWNER = "00000000-0000-4000-8000-000000000001"
SESSION = "00000000-0000-4000-8000-000000000002"
INVOCATION = "00000000-0000-4000-8000-000000000003"
CONFIRMATION = "RUN_CONNECTED_RELEASE_PREVIEW_WITH_DEDICATED_NON_CUSTOMER_ACCOUNTS"
OIDC = "a" * 80 + "." + "b" * 80 + "." + "c" * 80
SHA = "a" * 64
HEADERS = {
    "X-Ask-Crump-Expected-Owner": OWNER,
    "Origin": "https://www.askcrump.com",
    "Sec-Fetch-Site": "same-origin",
    "X-Ask-Crump-Release-Preview-CSRF": "connected-release-preview-v1",
    "X-Vercel-OIDC-Token": OIDC,
}


def app() -> FastAPI:
    application = FastAPI()
    application.include_router(connected_apps.router)
    register_exception_handlers(application)
    return application


async def authenticated(_request, _db, _settings, **kwargs):
    assert kwargs == {
        "require_account": True,
        "require_expected_owner_header": True,
    }
    return SimpleNamespace(
        user={"id": OWNER},
        session={"id": SESSION},
        token="redacted",
    )


def release_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED",
        True,
    )
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(is_production=True, connected_apps_enabled=True),
    )


@pytest.mark.asyncio
async def test_source_lock_refuses_before_origin_auth_body_or_release_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def forbidden_auth(*_args, **_kwargs):
        calls.append("auth")
        raise AssertionError

    monkeypatch.setattr(
        config,
        "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED",
        False,
    )
    monkeypatch.setattr(connected_apps, "authenticate_request", forbidden_auth)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()),
        base_url="https://www.askcrump.com",
    ) as client:
        response = await client.post(
            "/api/connected-apps/internal/release-preview",
            content=b"not-json",
        )
    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "code": "CONNECTED_RELEASE_PREVIEW_NOT_RELEASED",
        "retryable": False,
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing",
    ("preview", "public", "multi_step", "environment", "production"),
)
async def test_same_deployment_ceremony_requires_complete_release_lockset(
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    release_on(monkeypatch)
    if missing == "preview":
        monkeypatch.setattr(
            config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", False
        )
    elif missing == "public":
        monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", False)
    elif missing == "multi_step":
        monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", False)
    elif missing == "environment":
        monkeypatch.setattr(
            connected_apps,
            "settings",
            SimpleNamespace(is_production=True, connected_apps_enabled=False),
        )
    else:
        monkeypatch.setattr(
            connected_apps,
            "settings",
            SimpleNamespace(is_production=False, connected_apps_enabled=True),
        )

    async def forbidden_auth(*_args, **_kwargs):
        raise AssertionError("incomplete release tuple reached authentication")

    monkeypatch.setattr(connected_apps, "authenticate_request", forbidden_auth)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()),
        base_url="https://www.askcrump.com",
    ) as client:
        response = await client.post(
            "/api/connected-apps/internal/release-preview",
            headers=HEADERS,
            json={"confirmation": CONFIRMATION},
        )
    assert response.status_code == 404
    assert response.json()["code"] == "CONNECTED_RELEASE_PREVIEW_NOT_RELEASED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {key: value for key, value in HEADERS.items() if key != "Origin"},
        {**HEADERS, "Origin": "https://evil.example"},
        {**HEADERS, "Sec-Fetch-Site": "cross-site"},
        {
            key: value
            for key, value in HEADERS.items()
            if key != "X-Ask-Crump-Release-Preview-CSRF"
        },
        {**HEADERS, "X-Ask-Crump-Release-Preview-CSRF": "wrong"},
        {**HEADERS, "Host": "preview.example"},
    ],
)
async def test_release_preview_requires_exact_browser_same_origin_before_auth(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
) -> None:
    release_on(monkeypatch)
    calls: list[str] = []

    async def forbidden_auth(*_args, **_kwargs):
        calls.append("auth")
        raise AssertionError

    monkeypatch.setattr(connected_apps, "authenticate_request", forbidden_auth)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()),
        base_url="https://www.askcrump.com",
    ) as client:
        response = await client.post(
            "/api/connected-apps/internal/release-preview",
            headers=headers,
            json={"confirmation": CONFIRMATION},
        )
    assert response.status_code == 403
    assert response.json()["code"] == "CONNECTED_RELEASE_PREVIEW_ORIGIN_REJECTED"
    assert calls == []


@pytest.mark.asyncio
async def test_release_preview_claims_and_runs_exact_child_without_normal_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_on(monkeypatch)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    events: list[tuple[str, object]] = []

    async def forbidden_activation(*_args, **_kwargs):
        raise AssertionError("normal request activation must not run")

    async def claim(**kwargs):
        events.append(("claim", kwargs))
        return ConnectedReleasePreviewCeremonyClaim(
            invocation_id=INVOCATION,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=10),
            recovery=True,
        )

    async def run(**kwargs):
        events.append(("run", kwargs))
        assert kwargs["assertion"].reveal_for_exchange() == OIDC
        return ConnectedReleasePreviewChildResult(
            invocation_id=INVOCATION,
            composition_manifest_sha256=SHA,
            database_target_fingerprint="1" * 32,
            release_preview_contract_sha256=SHA,
            deployment_id="dpl_12345678abcd",
            commit_sha="b" * 40,
            host_configuration_ciphertext_sha256=SHA,
            provider_smoke_attestation_sha256=SHA,
            checked_at=NOW + timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=11),
        )

    monkeypatch.setattr(connected_apps, "_acquire_request_activation", forbidden_activation)
    monkeypatch.setattr(supervisor, "claim_connected_release_preview_ceremony", claim)
    monkeypatch.setattr(supervisor, "run_connected_release_preview_child", run)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()),
        base_url="https://www.askcrump.com",
    ) as client:
        response = await client.post(
            "/api/connected-apps/internal/release-preview",
            headers=HEADERS,
            json={"confirmation": CONFIRMATION},
        )
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "status": "completed",
        "invocationId": INVOCATION,
        "checkedAt": "2026-11-08T20:01:00Z",
        "expiresAt": "2026-11-08T20:11:00Z",
    }
    assert response.headers["cache-control"] == "private, no-store"
    expected_session = hashlib.sha256(
        b"askcrump.connected-release-session/v1\0" + SESSION.encode("ascii")
    ).hexdigest()
    assert events[0] == (
        "claim",
        {
            "owner_id": OWNER,
            "session_binding_sha256": expected_session,
            "confirmation": CONFIRMATION,
        },
    )
    assert events[1][0] == "run"
    run_args = events[1][1]
    assert run_args["invocation_id"] == INVOCATION
    assert run_args["issued_at"] == NOW
    assert run_args["expires_at"] == NOW + timedelta(minutes=10)
    assert run_args["confirmation"] == CONFIRMATION
    assert run_args["recovery"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "payload", "expected_status"),
    [
        (
            {key: value for key, value in HEADERS.items() if key != "X-Vercel-OIDC-Token"},
            {"confirmation": CONFIRMATION},
            503,
        ),
        (HEADERS, {"confirmation": "wrong"}, 400),
        (HEADERS, {"confirmation": CONFIRMATION, "extra": True}, 400),
    ],
)
async def test_release_preview_rejects_missing_identity_or_inexact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
    payload: dict[str, object],
    expected_status: int,
) -> None:
    release_on(monkeypatch)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()),
        base_url="https://www.askcrump.com",
    ) as client:
        response = await client.post(
            "/api/connected-apps/internal/release-preview",
            headers=headers,
            json=payload,
        )
    assert response.status_code == expected_status
    assert response.json()["success"] is False
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_release_preview_failures_are_content_free_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release_on(monkeypatch)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)

    async def failed_claim(**_kwargs):
        raise ConnectedReleasePreviewSupervisorError()

    monkeypatch.setattr(
        supervisor,
        "claim_connected_release_preview_ceremony",
        failed_claim,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()),
        base_url="https://www.askcrump.com",
    ) as client:
        response = await client.post(
            "/api/connected-apps/internal/release-preview",
            headers=HEADERS,
            json={"confirmation": CONFIRMATION},
        )
    assert response.status_code == 503
    assert response.json() == {
        "success": False,
        "code": "CONNECTED_RELEASE_PREVIEW_FAILED",
        "retryable": True,
    }
    assert OIDC not in response.text
