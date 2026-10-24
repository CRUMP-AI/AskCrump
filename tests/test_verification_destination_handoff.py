from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from backend.routes import auth as auth_routes
from backend.schemas import RegisterRequest, ResendVerificationRequest
from backend.verification_handoff import (
    creation_intent,
    paid_plan_intent,
    verification_email_url,
    verified_workspace_url,
)


def test_verification_handoff_urls_carry_only_allowlisted_content_free_destinations() -> None:
    email_url = verification_email_url(
        "https://www.askcrump.com/",
        "token with spaces",
        intent="Presentation",
        plan="professional",
    )
    email_query = parse_qs(urlparse(email_url).query)

    assert urlparse(email_url).path == "/api/auth/verify-email"
    assert email_query == {
        "token": ["token with spaces"],
        "intent": ["presentation"],
        "plan": ["professional"],
    }
    assert verified_workspace_url(
        "https://www.askcrump.com",
        intent="video",
        plan="enterprise",
    ) == (
        "https://www.askcrump.com/app?verification=success"
        "&intent=video&plan=enterprise"
    )
    assert verified_workspace_url(
        "https://www.askcrump.com",
        intent="IMAGE",
        plan="professional",
    ) == (
        "https://www.askcrump.com/app?verification=success"
        "&intent=image&plan=professional"
    )
    assert verified_workspace_url(
        "https://www.askcrump.com",
        intent="video",
        result="already_verified",
    ) == (
        "https://www.askcrump.com/app?verification=already_verified"
        "&intent=video"
    )
    assert verified_workspace_url(
        "https://www.askcrump.com",
        result="untrusted-result",
    ) == "https://www.askcrump.com/app?verification=success"

    invalid = verification_email_url(
        "https://www.askcrump.com",
        "token",
        intent="private prompt content",
        plan="free",
    )
    assert parse_qs(urlparse(invalid).query) == {"token": ["token"]}
    assert creation_intent("race") is None
    assert paid_plan_intent("admin") is None
    with pytest.raises(ValidationError):
        ResendVerificationRequest(
            email="new-user@example.com",
            intent="private-prompt",
        )
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="new-user@example.com",
            password="StrongPass1",
            intent="private-prompt",
        )


class _RegistrationDB:
    def __init__(self, user: dict | None = None) -> None:
        self.user = dict(user) if user else None
        self.inserted: dict | None = None
        self.updated: list[dict] = []

    async def select_one(self, table, **_kwargs):
        assert table == "users"
        return dict(self.user) if self.user else None

    async def insert(self, table, payload):
        assert table == "users"
        self.inserted = dict(payload)
        self.user = dict(payload)
        return [dict(payload)]

    async def update(self, table, payload, *, filters):
        assert table == "users"
        assert filters["id"].startswith("eq.")
        self.updated.append(dict(payload))
        if self.user:
            self.user.update(payload)
        return [dict(self.user or payload)]

    async def upsert(self, table, payload, *, on_conflict):
        assert table == "user_settings"
        assert on_conflict == "user_id"
        return [dict(payload)]


class _VerificationQueueCapture:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def enqueue_resend(self, **kwargs):
        self.calls.append(dict(kwargs))


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", ["presentation", "image"])
async def test_registration_and_resend_preserve_the_promised_destination(
    monkeypatch,
    intent: str,
) -> None:
    database = _RegistrationDB()
    queue = _VerificationQueueCapture()

    async def allow_rate_limit(*_args, **_kwargs):
        return None

    async def ignore_event(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "db", database)
    monkeypatch.setattr(auth_routes, "verification_emails", queue)
    monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", allow_rate_limit)
    monkeypatch.setattr(auth_routes, "record_account_created_event", ignore_event)
    monkeypatch.setattr(auth_routes, "record_product_event", ignore_event)
    monkeypatch.setattr(auth_routes, "hash_password", lambda _password: "hashed")

    request = Request({
        "type": "http", "method": "POST", "path": "/api/auth/register",
        "scheme": "https", "server": ("www.askcrump.com", 443),
        "client": ("127.0.0.1", 12345), "headers": [],
    })
    result = await auth_routes.register(
        RegisterRequest(
            email="new-user@example.com",
            password="StrongPass1",
            intent=intent,
            plan="professional",
        ),
        request,
    )

    assert result["success"] is True
    assert result["emailQueued"] is True
    assert result["emailSent"] is False
    assert queue.calls == [{
        "email": "new-user@example.com",
        "intent": intent,
        "plan": "professional",
    }]

    await auth_routes.resend_verification(
        ResendVerificationRequest(
            email="new-user@example.com",
            intent=intent,
            plan="professional",
        ),
        request,
    )
    assert queue.calls == [
        {
            "email": "new-user@example.com",
            "intent": intent,
            "plan": "professional",
        },
        {
            "email": "new-user@example.com",
            "intent": intent,
            "plan": "professional",
        },
    ]


def test_registration_uses_only_the_durable_verification_queue() -> None:
    source = Path(auth_routes.__file__).read_text(encoding="utf-8")
    registration = source[
        source.index("@router.post('/register')") :
        source.index("@router.post('/guest')")
    ]

    assert "await verification_emails.enqueue_resend(" in registration
    assert "email_service.send_verification" not in registration
    assert "_prepare_resend_verification_alias" not in registration
    assert "'emailSent': False" in registration
    assert "'emailQueued': True" in registration


def test_browser_contract_sends_destination_context_without_customer_content() -> None:
    controller = (Path(auth_routes.__file__).resolve().parents[2] / "public" / "auth-controller.js").read_text(
        encoding="utf-8"
    )
    register_start = controller.index("const creationIntent = pendingCreationIntent();")
    register_flow = controller[
        register_start : controller.index("termsVersion: TERMS_VERSION", register_start)
    ]
    resend_flow = controller[
        controller.index("async function resendVerificationEmail") :
        controller.index("function showVerificationResult")
    ]
    register = register_flow[register_flow.index("body: JSON.stringify") :]
    resend = resend_flow[
        resend_flow.index("body: JSON.stringify") :
        resend_flow.index("}, 'Submitting the verification email request")
    ]

    assert "const creationIntent = pendingCreationIntent();" in register_flow
    assert "intent: creationIntent?.kind || attribution.intent" in register
    assert "plan: planIntent?.plan || null" in register
    assert "intent: pendingCreationIntent()?.kind || null" in resend
    assert "plan: pendingPlanIntent()?.plan || null" in resend
    for forbidden in ("prompt", "message", "response", "filename", "chatId"):
        assert forbidden not in register
        assert forbidden not in resend
