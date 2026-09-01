from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

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

    invalid = verification_email_url(
        "https://www.askcrump.com",
        "token",
        intent="private prompt content",
        plan="free",
    )
    assert parse_qs(urlparse(invalid).query) == {"token": ["token"]}
    assert creation_intent("race") is None
    assert paid_plan_intent("admin") is None


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


class _VerificationEmailCapture:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send_verification(self, email, name, token, **kwargs):
        self.calls.append({"email": email, "name": name, "token": token, **kwargs})
        return True


@pytest.mark.asyncio
async def test_registration_and_resend_preserve_the_promised_destination(monkeypatch) -> None:
    database = _RegistrationDB()
    email = _VerificationEmailCapture()

    async def allow_rate_limit(*_args, **_kwargs):
        return None

    async def ignore_event(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes, "db", database)
    monkeypatch.setattr(auth_routes, "email_service", email)
    monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", allow_rate_limit)
    monkeypatch.setattr(auth_routes, "record_account_created_event", ignore_event)
    monkeypatch.setattr(auth_routes, "record_product_event", ignore_event)
    monkeypatch.setattr(auth_routes, "hash_password", lambda _password: "hashed")

    request = SimpleNamespace(
        headers={},
        client=SimpleNamespace(host="127.0.0.1"),
        url=SimpleNamespace(hostname="www.askcrump.com"),
    )
    result = await auth_routes.register(
        RegisterRequest(
            email="new-user@example.com",
            password="StrongPass1",
            intent="presentation",
            plan="professional",
        ),
        request,
    )

    assert result["success"] is True
    assert email.calls[0]["intent"] == "presentation"
    assert email.calls[0]["plan"] == "professional"

    await auth_routes.resend_verification(
        ResendVerificationRequest(
            email="new-user@example.com",
            intent="presentation",
            plan="professional",
        ),
        request,
    )
    assert len(email.calls) == 2
    assert email.calls[1]["intent"] == "presentation"
    assert email.calls[1]["plan"] == "professional"


def test_browser_contract_sends_destination_context_without_customer_content() -> None:
    controller = (Path(auth_routes.__file__).resolve().parents[2] / "public" / "auth-controller.js").read_text(
        encoding="utf-8"
    )
    register_start = controller.index("const planIntent = pendingPlanIntent();")
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
        resend_flow.index("}, 'Sending the verification email")
    ]

    assert "intent: attribution.intent" in register
    assert "plan: planIntent?.plan || null" in register
    assert "intent: pendingCreationIntent()?.kind || null" in resend
    assert "plan: pendingPlanIntent()?.plan || null" in resend
    for forbidden in ("prompt", "message", "response", "filename", "chatId"):
        assert forbidden not in register
        assert forbidden not in resend
