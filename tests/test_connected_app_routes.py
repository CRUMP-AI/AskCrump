from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace
from urllib.parse import urlencode

import httpx
import pytest
from fastapi import FastAPI

from backend.auth_service import AuthenticationError
from backend.connected_app_contracts import (
    ConnectionAuthorizationState,
    ConnectorAccountKind,
    MailDraftSpec,
    MailSendRequest,
)
from backend.connected_app_policy import (
    ConnectedActionPolicy,
    ConnectorActionKind,
    ConnectorProvider,
    ConnectorResource,
)
from backend.connected_app_scopes import delegated_scope_plan
from backend.connected_app_service import (
    ConnectedAppServiceError,
    ConnectedApprovalReviewPreview,
    ConnectedApprovalStatus,
    ConnectedApprovalView,
    ConnectedConnectionView,
    ConnectedMailReviewPayload,
    DisconnectView,
    OAuthStartView,
    ConnectedScheduleStatus,
    ConnectedScheduleView,
    approval_execution_parameters_sha256,
    approval_review_preview_sha256,
)
from backend.http import register_exception_handlers
from backend.routes import connected_apps


NOW = datetime(2026, 11, 7, 20, 0, tzinfo=timezone.utc)
OWNER = "00000000-0000-4000-8000-000000000001"
SESSION = "00000000-0000-4000-8000-000000000002"
REQUEST = "00000000-0000-4000-8000-000000000003"
CONNECTION = "00000000-0000-4000-8000-000000000004"
TASK = "00000000-0000-4000-8000-000000000006"
TEMPLATE = "00000000-0000-4000-8000-000000000007"
SCHEDULE = "00000000-0000-4000-8000-000000000008"
ACTION = "00000000-0000-4000-8000-000000000009"
TURN = "00000000-0000-4000-8000-00000000000a"
APPROVAL = "00000000-0000-4000-8000-00000000000b"
DECISION = "00000000-0000-4000-8000-00000000000c"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64
GOOGLE_CLIENT_ID = "ask-crump-google-client.apps.googleusercontent.com"
MICROSOFT_CLIENT_ID = "ask-crump-microsoft-client"
OAUTH_STATE = "s" * 43
PKCE_CHALLENGE = "p" * 43
HEADERS = {"X-Ask-Crump-Expected-Owner": OWNER}


@pytest.fixture(autouse=True)
def complete_release_source_lockset(monkeypatch):
    from backend import config

    monkeypatch.setattr(config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)


def connection() -> ConnectedConnectionView:
    return ConnectedConnectionView(
        connection_id=CONNECTION,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        account_kind=ConnectorAccountKind.PERSONAL,
        granted_actions=(ConnectorActionKind.MAIL_GET, ConnectorActionKind.MAIL_SEND),
        authorization_state=ConnectionAuthorizationState.ACTIVE,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA_A,
        expires_at=NOW + timedelta(hours=1),
        updated_at=NOW,
    )


def schedule() -> ConnectedScheduleView:
    return ConnectedScheduleView(
        schedule_id=SCHEDULE,
        connection_id=CONNECTION,
        task_id=TASK,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.CALENDAR,
        action=ConnectorActionKind.CALENDAR_CREATE,
        action_template_ref=TEMPLATE,
        parameters_sha256=SHA_B,
        task_state_revision=1,
        time_zone="America/New_York",
        cadence_seconds=3600,
        quiet_start_minute=1320,
        quiet_end_minute=420,
        requires_approval_every_run=True,
        status=ConnectedScheduleStatus.ACTIVE,
        next_run_at=NOW + timedelta(hours=1),
        updated_at=NOW,
    )


def disconnected() -> DisconnectView:
    return DisconnectView(
        connection=ConnectedConnectionView(
            connection_id=CONNECTION,
            provider=ConnectorProvider.GOOGLE,
            resource=ConnectorResource.MAIL,
            account_kind=ConnectorAccountKind.PERSONAL,
            granted_actions=(ConnectorActionKind.MAIL_GET, ConnectorActionKind.MAIL_SEND),
            authorization_state=ConnectionAuthorizationState.REVOKED,
            authorization_revision=1,
            authorization_snapshot_sha256=None,
            expires_at=None,
            updated_at=NOW,
        ),
        grants_invalidated=True,
        schedules_invalidated=True,
        broker_cleanup_enqueued=True,
        updated_at=NOW,
    )


def review_payload() -> ConnectedMailReviewPayload:
    return ConnectedMailReviewPayload(
        account=CONNECTION,
        to=("recipient@example.com",),
        cc=(),
        bcc=(),
        subject="Exact approval subject",
        body_text="Confidential exact approval body",
        reply_context=None,
    )


def provider_request() -> MailSendRequest:
    return MailSendRequest.build(
        MailDraftSpec(
            to=("recipient@example.com",),
            cc=(),
            bcc=(),
            subject="Exact approval subject",
            body_text="Confidential exact approval body",
        )
    )


def parameters_sha256() -> str:
    return approval_execution_parameters_sha256(
        action=ConnectorActionKind.MAIL_SEND,
        provider_request=provider_request(),
        payload_commitment_sha256=SHA_B,
    )


def preview_sha256() -> str:
    return approval_review_preview_sha256(
        approval_id=APPROVAL,
        action_id=ACTION,
        action=ConnectorActionKind.MAIL_SEND,
        approval_binding_sha256=SHA_A,
        parameters_sha256=parameters_sha256(),
        resource_version_sha256=None,
        payload=review_payload(),
        preview_commitment_sha256=SHA_C,
    )


def approval() -> ConnectedApprovalView:
    preview = preview_sha256()
    return ConnectedApprovalView(
        approval_id=APPROVAL,
        action_id=ACTION,
        connection_id=CONNECTION,
        task_id=TASK,
        turn_id=TURN,
        provider=ConnectorProvider.GOOGLE,
        resource=ConnectorResource.MAIL,
        action=ConnectorActionKind.MAIL_SEND,
        authorization_revision=1,
        authorization_snapshot_sha256=SHA_A,
        granted_scopes_sha256=SHA_D,
        policy_version=ConnectedActionPolicy.version,
        action_revision=1,
        status=ConnectedApprovalStatus.APPROVED,
        approval_binding_sha256=SHA_A,
        parameters_sha256=parameters_sha256(),
        resource_version_sha256=None,
        preview_sha256=preview,
        review_preview=ConnectedApprovalReviewPreview(
            approval_binding_sha256=SHA_A,
            parameters_sha256=parameters_sha256(),
            preview_sha256=preview,
            payload=review_payload(),
            connection_id=CONNECTION,
            action=ConnectorActionKind.MAIL_SEND,
            resource_version_sha256=None,
            provider_request=provider_request(),
        ),
        decision_id=DECISION,
        decision_session_binding_sha256=(
            "6f3bf40e3362dd37a6ae3292c910c40e8a0990f8a8029ee32dbcb7b533f9f03d"
        ),
        expires_at=NOW + timedelta(minutes=5),
        decided_at=NOW,
    )


class RouteService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def require_ready(self) -> None:
        self.calls.append(("ready", None))

    def public_readiness_manifest(self):
        self.calls.append(("public-manifest", None))
        actions = [
            "calendar.cancel",
            "calendar.create",
            "calendar.free_busy",
            "calendar.get",
            "calendar.list",
            "calendar.update",
            "mail.create_draft",
            "mail.get",
            "mail.reply",
            "mail.search",
            "mail.send",
        ]
        return {
            "providers": ["google", "microsoft"],
            "capabilities": {"google": list(actions), "microsoft": list(actions)},
            "oauthClientIds": {
                "google": GOOGLE_CLIENT_ID,
                "microsoft": MICROSOFT_CLIENT_ID,
            },
        }

    async def list_connections(self, **kwargs):
        self.calls.append(("list-connections", kwargs))
        return (connection(),)

    async def start_oauth(self, **kwargs):
        self.calls.append(("start-oauth", kwargs))
        parameters = {
            "client_id": GOOGLE_CLIENT_ID,
            "redirect_uri": kwargs["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(
                delegated_scope_plan(
                    kwargs["provider"],
                    kwargs["actions"],
                    account_kind=kwargs["account_kind"],
                ).delegated_scopes
            ),
            "state": OAUTH_STATE,
            "code_challenge": PKCE_CHALLENGE,
            "code_challenge_method": "S256",
        }
        return OAuthStartView(
            request_id=kwargs["request_id"],
            flow_id="00000000-0000-4000-8000-000000000005",
            connection_id=CONNECTION,
            provider=kwargs["provider"],
            authorization_url=(
                f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(parameters)}"
            ),
            state_sha256=hashlib.sha256(OAUTH_STATE.encode()).hexdigest(),
            pkce_challenge=PKCE_CHALLENGE,
            command_binding_sha256=SHA_A,
            expires_at=NOW + timedelta(minutes=5),
        )

    async def complete_oauth_callback(self, **kwargs):
        self.calls.append(("callback", kwargs))
        return connection()

    async def deny_oauth_callback(self, **kwargs):
        self.calls.append(("deny-callback", kwargs))

    async def disconnect(self, **kwargs):
        self.calls.append(("disconnect", kwargs))
        return disconnected()

    async def list_schedules(self, **kwargs):
        self.calls.append(("list-schedules", kwargs))
        return (schedule(),)

    async def create_schedule(self, **kwargs):
        self.calls.append(("create-schedule", kwargs))
        return schedule()

    async def transition_schedule(self, **kwargs):
        self.calls.append(("transition-schedule", kwargs))
        return schedule()

    async def list_actions(self, **kwargs):
        self.calls.append(("list-actions", kwargs))
        return ()

    async def get_action(self, **kwargs):
        self.calls.append(("get-action", kwargs))
        raise AssertionError("not expected in this test")

    async def list_approvals(self, **kwargs):
        self.calls.append(("list-approvals", kwargs))
        return (approval(),)

    async def decide_approval(self, **kwargs):
        self.calls.append(("decide-approval", kwargs))
        return approval()


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
    return SimpleNamespace(user={"id": OWNER}, session={"id": SESSION}, token="redacted")


async def callback_authenticated(_request, _db, _settings, **kwargs):
    assert kwargs == {
        "require_account": True,
        "require_expected_owner_header": False,
    }
    return SimpleNamespace(user={"id": OWNER}, session={"id": SESSION}, token="redacted")


@pytest.mark.parametrize(
    ("method", "path"),
    (
        ("POST", "/api/connected-apps/oauth/start"),
        ("GET", "/api/connected-apps/oauth/callback/google?code=raw&state=raw"),
        ("POST", f"/api/connected-apps/connections/{CONNECTION}/disconnect"),
        ("POST", f"/api/connected-apps/schedules/{SCHEDULE}/pause"),
        ("POST", f"/api/connected-apps/approvals/{APPROVAL}"),
    ),
)
@pytest.mark.asyncio
async def test_source_lock_fails_before_body_auth_or_dependency(
    monkeypatch, method: str, path: str
):
    service = RouteService()
    auth_calls: list[str] = []

    async def forbidden_auth(*_args, **_kwargs):
        auth_calls.append("auth")
        raise AssertionError("authentication must not run behind source lock")

    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=False))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", forbidden_auth)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.request(method, path, content=b"not-even-json")
    if "/oauth/callback/" in path:
        assert response.status_code == 303
        assert response.headers["location"] == "/app?connected-app=failed"
    else:
        assert response.status_code == 404
        assert response.json() == {
            "success": False,
            "code": "CONNECTED_APPS_NOT_RELEASED",
            "retryable": False,
        }
    assert response.headers["cache-control"] == "private, no-store"
    assert auth_calls == []
    assert service.calls == []


@pytest.mark.asyncio
async def test_status_is_ready_only_for_an_injected_attested_service(monkeypatch):
    service = RouteService()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/connected-apps/status", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "enabled": True,
        "status": "ready",
        "providers": ["google", "microsoft"],
        "capabilities": {
            "google": [
                "calendar.cancel",
                "calendar.create",
                "calendar.free_busy",
                "calendar.get",
                "calendar.list",
                "calendar.update",
                "mail.create_draft",
                "mail.get",
                "mail.reply",
                "mail.search",
                "mail.send",
            ],
            "microsoft": [
                "calendar.cancel",
                "calendar.create",
                "calendar.free_busy",
                "calendar.get",
                "calendar.list",
                "calendar.update",
                "mail.create_draft",
                "mail.get",
                "mail.reply",
                "mail.search",
                "mail.send",
            ],
        },
        "oauthClientIds": {
            "google": GOOGLE_CLIENT_ID,
            "microsoft": MICROSOFT_CLIENT_ID,
        },
    }
    assert service.calls == [("public-manifest", None)]


@pytest.mark.asyncio
async def test_status_fails_closed_when_composition_attestation_is_not_ready(monkeypatch):
    class NotReady(RouteService):
        def public_readiness_manifest(self):
            self.calls.append(("public-manifest", None))
            raise ConnectedAppServiceError("CONNECTED_APPS_NOT_READY", 503)

    service = NotReady()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/connected-apps/status", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "enabled": False,
        "status": "not_ready",
        "providers": [],
        "capabilities": [],
    }
    assert service.calls == [("public-manifest", None)]


@pytest.mark.asyncio
async def test_status_independently_rejects_legacy_missing_or_wrong_owner_header(monkeypatch):
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        missing = await client.get("/api/connected-apps/status")
        wrong = await client.get(
            "/api/connected-apps/status",
            headers={"X-Ask-Crump-Expected-Owner": SESSION},
        )
    assert missing.status_code == wrong.status_code == 409
    assert missing.json()["code"] == wrong.json()["code"] == "AUTH_OWNER_MISMATCH"
    assert missing.headers["cache-control"] == "private, no-store"
    assert wrong.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_status_authentication_failure_is_explicitly_no_store(monkeypatch):
    async def rejected(*_args, **_kwargs):
        raise AuthenticationError("Expired.", code="AUTH_EXPIRED")

    monkeypatch.setattr(connected_apps, "authenticate_request", rejected)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/connected-apps/status", headers=HEADERS)
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_EXPIRED"
    assert response.headers["cache-control"] == "private, no-store"


@pytest.mark.asyncio
async def test_account_route_requires_exact_expected_owner(monkeypatch):
    service = RouteService()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/connected-apps/connections",
            headers={"X-Ask-Crump-Expected-Owner": SESSION},
        )
    assert response.status_code == 403
    assert response.json()["code"] == "CONNECTED_OWNER_MISMATCH"
    # Authentication and the owner precondition must fail before the
    # secret-bound request graph or service readiness dependency is touched.
    assert service.calls == []


@pytest.mark.asyncio
async def test_authenticated_owner_acquires_one_graph_lease_after_auth_and_releases_it(
    monkeypatch,
):
    service = RouteService()
    events: list[str] = []

    async def ordered_auth(*args, **kwargs):
        events.append("auth")
        return await authenticated(*args, **kwargs)

    class Lease:
        async def release(self):
            events.append("release")

    async def acquire(assertion_source):
        events.append("activation")
        assert assertion_source() == "request-oidc-assertion"
        return Lease()

    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", ordered_auth)
    monkeypatch.setattr(connected_apps, "_acquire_request_activation", acquire)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/connected-apps/connections",
            headers={**HEADERS, "x-vercel-oidc-token": "request-oidc-assertion"},
        )
    assert response.status_code == 200
    assert events == ["auth", "activation", "release"]
    assert service.calls[0] == ("ready", None)


@pytest.mark.asyncio
async def test_authentication_failure_never_acquires_a_graph_lease(monkeypatch):
    service = RouteService()
    activation_calls: list[str] = []

    async def rejected(*_args, **_kwargs):
        raise AuthenticationError("Expired.", code="AUTH_EXPIRED")

    async def forbidden_activation(_assertion_source):
        activation_calls.append("activation")
        raise AssertionError("activation must follow authentication")

    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", rejected)
    monkeypatch.setattr(
        connected_apps,
        "_acquire_request_activation",
        forbidden_activation,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/connected-apps/connections", headers=HEADERS)
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_EXPIRED"
    assert activation_calls == []
    assert service.calls == []


@pytest.mark.asyncio
async def test_strict_json_rejects_unknown_fields_and_controls(monkeypatch):
    service = RouteService()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        unknown = await client.post(
            f"/api/connected-apps/connections/{CONNECTION}/disconnect",
            headers=HEADERS,
            json={"requestId": REQUEST, "confirmed": True, "surprise": "field"},
        )
        control = await client.post(
            f"/api/connected-apps/connections/{CONNECTION}/disconnect",
            headers=HEADERS,
            json={"requestId": REQUEST + "\u0000", "confirmed": True},
        )
    assert unknown.status_code == 400
    assert control.status_code == 400
    assert unknown.json()["code"] == control.json()["code"] == "CONNECTED_INPUT_INVALID"
    assert all(name == "ready" for name, _ in service.calls)


@pytest.mark.asyncio
async def test_route_rejects_resume_from_cancelled_before_service_mutation(monkeypatch):
    service = RouteService()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.post(
            f"/api/connected-apps/schedules/{SCHEDULE}/resume",
            headers=HEADERS,
            json={
                "requestId": REQUEST,
                "expectedTaskStateRevision": 3,
                "expectedStatus": "cancelled",
                "confirmed": True,
            },
        )
    assert response.status_code == 409
    assert response.json()["code"] == "CONNECTED_SCHEDULE_TRANSITION_INVALID"
    assert not any(name == "transition-schedule" for name, _ in service.calls)


@pytest.mark.asyncio
async def test_callback_rejects_malicious_shape_without_leaking_or_calling_service(monkeypatch):
    service = RouteService()
    auth_calls: list[str] = []
    activation_calls: list[str] = []

    async def forbidden_auth(*_args, **_kwargs):
        auth_calls.append("auth")
        raise AssertionError("malformed callback must fail before authentication")

    async def forbidden_activation(_assertion_source):
        activation_calls.append("activation")
        raise AssertionError("malformed callback must fail before activation")

    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", forbidden_auth)
    monkeypatch.setattr(
        connected_apps,
        "_acquire_request_activation",
        forbidden_activation,
    )
    raw_code = "raw-secret-code-123456"
    raw_state = "s" * 43
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/connected-apps/oauth/callback/google",
            params={"code": raw_code, "state": raw_state, "unexpected": "mail.read"},
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/app?connected-app=failed"
    assert response.headers["cache-control"] == "private, no-store"
    assert raw_code not in response.text
    assert raw_state not in response.text
    # Malformed OAuth redirects are rejected before authentication, activation,
    # or any provider/control-plane dependency.
    assert auth_calls == []
    assert activation_calls == []
    assert service.calls == []


@pytest.mark.asyncio
async def test_oauth_start_requires_exact_explicit_user_request(monkeypatch):
    service = RouteService()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    body = {
        "requestId": REQUEST,
        "provider": "google",
        "resource": "mail",
        "accountKind": "personal",
        "actions": ["mail.get", "mail.send"],
        "redirectUri": "https://www.askcrump.com/api/connected-apps/oauth/callback/google",
        "confirmed": True,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.post("/api/connected-apps/oauth/start", headers=HEADERS, json=body)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    public = response.json()["authorization"]
    assert public["provider"] == "google"
    assert "verifier" not in response.text.casefold()
    assert "token" not in response.text.casefold()
    call = next(item for item in service.calls if item[0] == "start-oauth")
    assert call[1]["owner_id"] == OWNER
    assert call[1]["session_id"] == SESSION
    assert call[1]["actions"] == frozenset(
        {ConnectorActionKind.MAIL_GET, ConnectorActionKind.MAIL_SEND}
    )
    assert call[1]["confirmed"] is True


@pytest.mark.asyncio
async def test_callback_delegates_only_code_and_state_and_returns_content_free_redirect(
    monkeypatch,
):
    service = RouteService()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", callback_authenticated)
    raw_code = "raw-secret-code-123456"
    raw_state = "s" * 43
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/connected-apps/oauth/callback/google",
            params={"code": raw_code, "state": raw_state},
        )
    assert response.status_code == 303
    assert raw_code not in response.text
    assert raw_state not in response.text
    assert response.headers["location"] == "/app?connected-app=connected"
    assert response.headers["cache-control"] == "private, no-store"
    assert CONNECTION not in response.headers["location"]
    assert service.calls[1] == (
        "callback",
        {
            "owner_id": OWNER,
            "session_id": SESSION,
            "provider": ConnectorProvider.GOOGLE,
            "code": raw_code,
            "state": raw_state,
        },
    )


@pytest.mark.asyncio
async def test_google_callback_accepts_bounded_documented_extension_parameters(monkeypatch):
    service = RouteService()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", callback_authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/connected-apps/oauth/callback/google",
            params={
                "code": "raw-secret-code-123456",
                "state": "s" * 43,
                "scope": "openid email",
                "authuser": "0",
                "prompt": "consent",
                "hd": "example.com",
            },
        )
    assert response.status_code == 303
    assert response.headers["location"] == "/app?connected-app=connected"
    callback = next(item for item in service.calls if item[0] == "callback")
    assert set(callback[1]) == {"owner_id", "session_id", "provider", "code", "state"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    (
        "code=one&code=two&state=" + "s" * 43,
        "code=one&state=" + "s" * 43 + "&unknown=value",
        "code=one&error=access_denied&state=" + "s" * 43,
        "error=server_error&state=" + "s" * 43,
    ),
)
async def test_callback_duplicate_unknown_and_malformed_error_shapes_never_exchange(
    monkeypatch, query
):
    service = RouteService()
    auth_calls = []

    async def forbidden_auth(*_args, **_kwargs):
        auth_calls.append("auth")
        raise AssertionError("malformed and denied callbacks stop before authentication")

    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", forbidden_auth)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(f"/api/connected-apps/oauth/callback/google?{query}")
    assert response.status_code == 303
    assert response.headers["location"] == "/app?connected-app=failed"
    assert auth_calls == []
    assert not any(name == "callback" for name, _ in service.calls)
    assert not any(name == "deny-callback" for name, _ in service.calls)


@pytest.mark.asyncio
async def test_access_denied_callback_is_owner_bound_without_provider_exchange_or_detail_forwarding(
    monkeypatch,
):
    service = RouteService()
    events: list[str] = []

    async def ordered_auth(*args, **kwargs):
        events.append("auth")
        return await callback_authenticated(*args, **kwargs)

    class Lease:
        async def release(self):
            events.append("release")

    async def acquire(assertion_source):
        events.append("activation")
        assert assertion_source() == "request-oidc-assertion"
        return Lease()

    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", ordered_auth)
    monkeypatch.setattr(connected_apps, "_acquire_request_activation", acquire)
    raw_state = "s" * 43
    detail = "User chose not to grant access"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(
            "/api/connected-apps/oauth/callback/google",
            params={
                "error": "access_denied",
                "state": raw_state,
                "error_description": detail,
                "error_uri": "https://accounts.google.com/oauth/error",
            },
            headers={"x-vercel-oidc-token": "request-oidc-assertion"},
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/app?connected-app=denied"
    assert response.headers["cache-control"] == "private, no-store"
    assert raw_state not in response.text
    assert detail not in response.text
    assert events == ["auth", "activation", "release"]
    assert not any(name == "callback" for name, _ in service.calls)
    assert service.calls == [
        ("ready", None),
        (
            "deny-callback",
            {
                "owner_id": OWNER,
                "session_id": SESSION,
                "provider": ConnectorProvider.GOOGLE,
                "state": raw_state,
                "error": "access_denied",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_approval_route_preserves_exact_bindings(monkeypatch):
    service = RouteService()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    approval_body = {
        "decisionId": DECISION,
        "actionId": ACTION,
        "connectionId": CONNECTION,
        "taskId": TASK,
        "turnId": TURN,
        "provider": "google",
        "resource": "mail",
        "action": "mail.send",
        "authorizationRevision": 1,
        "authorizationSnapshotSha256": SHA_A,
        "grantedScopesSha256": SHA_D,
        "policyVersion": ConnectedActionPolicy.version,
        "actionRevision": 1,
        "approvalBindingSha256": SHA_A,
        "parametersSha256": parameters_sha256(),
        "resourceVersionSha256": None,
        "previewSha256": preview_sha256(),
        "decision": "approved",
        "confirmed": True,
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        decided = await client.post(
            f"/api/connected-apps/approvals/{APPROVAL}",
            headers=HEADERS,
            json=approval_body,
        )
    assert decided.status_code == 200
    assert decided.json()["approval"]["approvalBindingSha256"] == SHA_A
    assert decided.json()["approval"]["previewSha256"] == preview_sha256()
    assert decided.json()["approval"]["reviewPreview"]["payload"]["subject"] == (
        "Exact approval subject"
    )
    decision_call = next(item for item in service.calls if item[0] == "decide-approval")
    assert decision_call[1]["action_id"] == ACTION
    assert decision_call[1]["approval_binding_sha256"] == SHA_A
    assert decision_call[1]["preview_sha256"] == preview_sha256()


@pytest.mark.asyncio
async def test_scheduled_write_uses_authenticated_list_then_decision_without_hidden_ids(
    monkeypatch,
):
    pending = replace(
        approval(),
        status=ConnectedApprovalStatus.PENDING,
        decision_id=None,
        decision_session_binding_sha256=None,
        decided_at=None,
    )

    class ScheduledApprovalService(RouteService):
        async def list_approvals(self, **kwargs):
            self.calls.append(("list-approvals", kwargs))
            return (pending,)

    service = ScheduledApprovalService()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        listed_response = await client.get(
            "/api/connected-apps/approvals", headers=HEADERS
        )
        listed = listed_response.json()["approvals"][0]
        decision_body = {
            "decisionId": DECISION,
            "actionId": listed["actionId"],
            "connectionId": listed["connectionId"],
            "taskId": listed["taskId"],
            "turnId": listed["turnId"],
            "provider": listed["provider"],
            "resource": listed["resource"],
            "action": listed["action"],
            "authorizationRevision": listed["authorizationRevision"],
            "authorizationSnapshotSha256": listed[
                "authorizationSnapshotSha256"
            ],
            "grantedScopesSha256": listed["grantedScopesSha256"],
            "policyVersion": listed["policyVersion"],
            "actionRevision": listed["actionRevision"],
            "approvalBindingSha256": listed["approvalBindingSha256"],
            "parametersSha256": listed["parametersSha256"],
            "resourceVersionSha256": listed["resourceVersionSha256"],
            "previewSha256": listed["previewSha256"],
            "decision": "approved",
            "confirmed": True,
        }
        decided_response = await client.post(
            f"/api/connected-apps/approvals/{listed['approvalId']}",
            headers=HEADERS,
            json=decision_body,
        )

    assert listed_response.status_code == 200
    assert listed["status"] == "pending"
    assert listed["reviewPreview"]["payload"]["subject"] == "Exact approval subject"
    assert decided_response.status_code == 200
    assert decided_response.json()["approval"]["status"] == "approved"
    assert service.calls[1] == ("list-approvals", {"owner_id": OWNER})
    decision_call = next(call for call in service.calls if call[0] == "decide-approval")
    assert decision_call[1]["owner_id"] == OWNER
    assert decision_call[1]["session_id"] == SESSION
    assert decision_call[1]["approval_id"] == APPROVAL
    assert decision_call[1]["confirmed"] is True


@pytest.mark.asyncio
async def test_public_schedule_creation_route_is_removed(monkeypatch):
    service = RouteService()
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/connected-apps/schedules",
            headers=HEADERS,
            json={"actionTemplateRef": TEMPLATE, "payloadReference": REQUEST},
        )
    assert response.status_code == 405
    assert not any(name == "create-schedule" for name, _ in service.calls)
