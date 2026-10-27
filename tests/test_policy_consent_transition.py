from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.requests import Request

from backend.policy_consent import (
    CURRENT_POLICY_BUNDLE_HASH,
    CURRENT_POLICY_BUNDLE_ID,
    UNTRUSTED_CLIENT_PLATFORM,
)
from backend.routes import account as account_routes
from backend.routes import auth as auth_routes
from backend.schemas import RegisterRequest, TermsAcceptanceRequest


ROOT = Path(__file__).resolve().parents[1]
LEGACY_VERSION = "2026-08-01"
USER_ID = "11111111-1111-4111-8111-111111111111"


def exact_registration(**overrides) -> RegisterRequest:
    values = {
        "email": "exact@example.com",
        "password": "StrongPass1",
        "termsAccepted": True,
        "privacyNoticeAcknowledged": True,
        "age17PlusAttested": True,
        "aiProviderTransmissionAuthorized": True,
        "termsVersion": CURRENT_POLICY_BUNDLE_ID,
    }
    values.update(overrides)
    return RegisterRequest(**values)


def exact_reacceptance(**overrides) -> TermsAcceptanceRequest:
    values = {
        "version": CURRENT_POLICY_BUNDLE_ID,
        "termsAccepted": True,
        "privacyNoticeAcknowledged": True,
        "age17PlusAttested": True,
        "aiProviderTransmissionAuthorized": True,
    }
    values.update(overrides)
    return TermsAcceptanceRequest(**values)


@pytest.mark.parametrize(
    "field",
    [
        "termsAccepted",
        "privacyNoticeAcknowledged",
        "age17PlusAttested",
        "aiProviderTransmissionAuthorized",
    ],
)
@pytest.mark.parametrize("value", [None, False, 1, 1.0, "true"])
def test_exact_contract_requires_four_literal_boolean_true_attestations(field, value):
    with pytest.raises(ValidationError):
        exact_registration(**{field: value})
    with pytest.raises(ValidationError):
        exact_reacceptance(**{field: value})


def test_legacy_contract_remains_functional_but_cannot_upgrade_itself():
    omitted = RegisterRequest(email="legacy@example.com", password="StrongPass1")
    legacy = RegisterRequest(
        email="legacy-explicit@example.com",
        password="StrongPass1",
        termsAccepted=True,
        privacyNoticeAcknowledged=True,
        age17PlusAttested=True,
        aiProviderTransmissionAuthorized=True,
        termsVersion=LEGACY_VERSION,
    )
    reacceptance = TermsAcceptanceRequest(
        version=LEGACY_VERSION,
        termsAccepted=True,
        privacyNoticeAcknowledged=True,
        age17PlusAttested=True,
        aiProviderTransmissionAuthorized=True,
    )

    assert omitted.accepts_current_policy_bundle is False
    assert legacy.accepts_current_policy_bundle is False
    assert reacceptance.accepts_current_policy_bundle is False


def test_exact_new_client_payload_is_rejected_by_the_old_server_contract():
    class OldRegisterRequest(BaseModel):
        model_config = ConfigDict(extra="ignore")
        email: str
        password: str
        termsAccepted: bool = False
        termsVersion: Literal["2026-08-01"] | None = None

    class OldTermsAcceptanceRequest(BaseModel):
        model_config = ConfigDict(extra="ignore")
        version: Literal["2026-08-01"] = LEGACY_VERSION

    with pytest.raises(ValidationError):
        OldRegisterRequest.model_validate(exact_registration().model_dump())
    with pytest.raises(ValidationError):
        OldTermsAcceptanceRequest.model_validate(exact_reacceptance().model_dump())


class TransitionRegistrationDB:
    def __init__(self) -> None:
        self.inserted_user: dict | None = None
        self.receipt_calls: list[tuple[str, dict]] = []

    async def select_one(self, table, **_kwargs):
        assert table == "users"
        return None

    async def insert(self, table, payload):
        assert table == "users"
        self.inserted_user = dict(payload)
        return [dict(payload)]

    async def upsert(self, table, payload, *, on_conflict):
        assert table == "user_settings"
        assert on_conflict == "user_id"
        return [dict(payload)]

    async def rpc(self, name, payload, **_kwargs):
        self.receipt_calls.append((name, dict(payload)))
        return [{
            "receipt_id": "22222222-2222-4222-8222-222222222222",
            "accepted_at": "2026-10-27T10:00:00+00:00",
            "bundle_id": CURRENT_POLICY_BUNDLE_ID,
            "bundle_hash": CURRENT_POLICY_BUNDLE_HASH,
        }]


class VerificationQueue:
    async def enqueue_resend(self, **_kwargs):
        return None


def registration_request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/register",
        "scheme": "https",
        "server": ("www.askcrump.com", 443),
        "client": ("127.0.0.1", 12345),
        # This intentionally spoofable value must not affect provenance.
        "headers": [(b"x-crump-client", b"native")],
    })


async def configure_registration(monkeypatch, database):
    async def no_op(*_args, **_kwargs):
        return None

    async def no_event(*_args, **_kwargs):
        return False

    monkeypatch.setattr(auth_routes, "db", database)
    monkeypatch.setattr(auth_routes, "verification_emails", VerificationQueue())
    monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", no_op)
    monkeypatch.setattr(auth_routes, "record_account_created_event", no_event)
    monkeypatch.setattr(auth_routes, "record_product_event", no_event)


@pytest.mark.asyncio
async def test_old_client_to_transition_server_works_without_current_receipt(monkeypatch):
    database = TransitionRegistrationDB()
    await configure_registration(monkeypatch, database)

    response = await auth_routes.register(
        RegisterRequest(
            email="legacy@example.com",
            password="StrongPass1",
            termsAccepted=True,
            termsVersion=LEGACY_VERSION,
        ),
        registration_request(),
    )

    assert response["success"] is True
    assert database.receipt_calls == []
    assert database.inserted_user["terms_version"] == LEGACY_VERSION
    assert database.inserted_user["terms_accepted_at"]


@pytest.mark.asyncio
async def test_exact_client_to_transition_server_writes_only_exact_receipt(monkeypatch):
    database = TransitionRegistrationDB()
    await configure_registration(monkeypatch, database)

    response = await auth_routes.register(exact_registration(), registration_request())

    assert response["success"] is True
    assert "terms_version" not in database.inserted_user
    assert "terms_accepted_at" not in database.inserted_user
    assert database.receipt_calls == [(
        "record_policy_acceptance_v1",
        {
            "p_user_id": database.inserted_user["id"],
            "p_bundle_id": CURRENT_POLICY_BUNDLE_ID,
            "p_acceptance_source": "registration",
            "p_client_platform": UNTRUSTED_CLIENT_PLATFORM,
            "p_age_17_plus_attested": True,
            "p_terms_accepted": True,
            "p_privacy_notice_acknowledged": True,
            "p_ai_provider_transmission_authorized": True,
        },
    )]


class ReacceptanceDB:
    def __init__(self) -> None:
        self.updates: list[tuple] = []
        self.receipt_calls: list[tuple[str, dict]] = []

    async def update(self, table, payload, *, filters):
        self.updates.append((table, dict(payload), dict(filters)))
        return [dict(payload)]

    async def rpc(self, name, payload, **_kwargs):
        self.receipt_calls.append((name, dict(payload)))
        return [{
            "receipt_id": "33333333-3333-4333-8333-333333333333",
            "accepted_at": "2026-10-27T10:05:00+00:00",
            "bundle_id": CURRENT_POLICY_BUNDLE_ID,
            "bundle_hash": CURRENT_POLICY_BUNDLE_HASH,
        }]


@pytest.mark.asyncio
async def test_exact_reacceptance_is_idempotent_and_legacy_never_calls_receipt_rpc(monkeypatch):
    database = ReacceptanceDB()

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={"id": USER_ID, "is_guest": False})

    monkeypatch.setattr(account_routes, "db", database)
    monkeypatch.setattr(account_routes, "authenticate_request", authenticate)
    request = Request({"type": "http", "method": "POST", "path": "/api/account/accept-terms", "headers": []})

    first = await account_routes.accept_terms(exact_reacceptance(), request)
    second = await account_routes.accept_terms(exact_reacceptance(), request)
    assert first["user"]["termsAcceptedAt"] == second["user"]["termsAcceptedAt"]
    assert len(database.receipt_calls) == 2
    assert database.receipt_calls[0] == database.receipt_calls[1]
    assert database.updates == []

    await account_routes.accept_terms(
        TermsAcceptanceRequest(
            version=LEGACY_VERSION,
            termsAccepted=True,
            privacyNoticeAcknowledged=True,
            age17PlusAttested=True,
            aiProviderTransmissionAuthorized=True,
        ),
        request,
    )
    assert len(database.receipt_calls) == 2
    assert len(database.updates) == 1
    assert database.updates[0][1]["terms_version"] == LEGACY_VERSION


def test_transition_does_not_enable_route_worker_or_provider_usage_enforcement():
    backend_sources = {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8")
        for path in (ROOT / "backend").rglob("*.py")
        if path.name != "policy_consent.py"
    }
    combined = "\n".join(backend_sources.values())
    frontend = (ROOT / "public/auth-controller.js").read_text(encoding="utf-8")

    assert "read_current_policy_acceptance" not in combined
    assert "require_current_policy_acceptance" not in combined
    assert "POLICY_ACCEPTANCE_REQUIRED" not in combined
    route_gate = frontend[
        frontend.index("function routeAuthenticatedUser"):
        frontend.index("// ---- Free text access")
    ]
    assert "if (!user.termsAcceptedAt)" in route_gate
    assert "policyAcceptedCurrent" not in route_gate


def test_reviewed_client_source_emits_exact_web_and_native_payload():
    source = (ROOT / "public/auth-controller.js").read_text(encoding="utf-8")
    assert CURRENT_POLICY_BUNDLE_ID in source
    assert CURRENT_POLICY_BUNDLE_HASH in source
    for field in (
        "termsAccepted",
        "privacyNoticeAcknowledged",
        "age17PlusAttested",
        "aiProviderTransmissionAuthorized",
    ):
        assert source.count(field) >= 2
    assert "x-crump-client" not in source.lower()


def test_deletion_cascade_p3_is_explicit_and_documented():
    migration = (ROOT / "migrations/20261027075649_server_policy_consent_receipts.sql").read_text(
        encoding="utf-8"
    )
    rollout = (ROOT / "docs/policy-consent-transition-20261027.md").read_text(
        encoding="utf-8"
    )
    assert "references public.users(id) on delete cascade" in migration.lower()
    assert "unresolved deletion-cascade decision (P3)" in rollout
