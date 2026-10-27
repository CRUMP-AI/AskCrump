from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from backend.auth_service import AuthenticationError, authenticate_request, public_user
from backend.policy_consent import (
    CURRENT_POLICY_BUNDLE_HASH,
    CURRENT_POLICY_BUNDLE_ID,
    record_current_policy_acceptance,
)
from backend.manuscript_service import ManuscriptService
from backend.schemas import RegisterRequest, TermsAcceptanceRequest
from backend.security import token_hash
from backend.routes import chat as chat_routes


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "11111111-1111-4111-8111-111111111111"
RAW_TOKEN = "policy-test-session-token"
SETTINGS = SimpleNamespace(session_cookie_name="crump_session", session_days=30)


def request_for(kind: str) -> Request:
    header = (
        (b"authorization", f"Bearer {RAW_TOKEN}".encode())
        if kind == "bearer"
        else (b"cookie", f"crump_session={RAW_TOKEN}".encode())
    )
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/chat",
        "headers": [header],
        "client": ("127.0.0.1", 12345),
    })


class PolicyAuthDB:
    def __init__(self, *, guest: bool, receipt: str) -> None:
        self.receipt = receipt
        self.updates: list[tuple] = []
        self.rpcs: list[tuple[str, dict]] = []
        self.user = {
            "id": USER_ID,
            "email": "guest@example.test" if guest else "registered@example.test",
            "is_guest": guest,
            "is_verified": not guest,
            "deleted_at": None,
        }

    async def select_one(self, table, *, columns="*", filters=None):
        if table == "sessions":
            if (filters or {}).get("token_hash") != f"eq.{token_hash(RAW_TOKEN)}":
                return None
            return {
                "id": "22222222-2222-4222-8222-222222222222",
                "user_id": USER_ID,
                "token_hash": token_hash(RAW_TOKEN),
                "last_activity": None,
                "expires_at": "2099-01-01T00:00:00+00:00",
            }
        if table == "users":
            return dict(self.user)
        return None

    async def rpc(self, name, payload, **_kwargs):
        self.rpcs.append((name, dict(payload)))
        if name == "get_guest_mode_control_v1":
            return True
        if name == "read_current_policy_acceptance_v1":
            if self.receipt == "error":
                raise RuntimeError("private receipt-check failure")
            if self.receipt == "missing":
                return []
            if self.receipt == "stale":
                return [{
                    "receipt_id": "33333333-3333-4333-8333-333333333333",
                    "accepted_at": "2026-10-27T00:00:00+00:00",
                    "bundle_id": "ask-crump-legal-stale",
                    "bundle_hash": "0" * 64,
                }]
            return [{
                "receipt_id": "33333333-3333-4333-8333-333333333333",
                "accepted_at": "2026-10-27T00:00:00+00:00",
                "bundle_id": CURRENT_POLICY_BUNDLE_ID,
                "bundle_hash": CURRENT_POLICY_BUNDLE_HASH,
                "acceptance_source": "guest_gate" if self.user["is_guest"] else "account_gate",
            }]
        raise AssertionError(f"unexpected RPC {name}")

    async def update(self, table, payload, *, filters):
        self.updates.append((table, dict(payload), dict(filters)))
        return []


@pytest.mark.parametrize("credential_kind", ["cookie", "bearer"])
@pytest.mark.parametrize("guest", [False, True])
@pytest.mark.parametrize("receipt", ["missing", "stale"])
@pytest.mark.asyncio
async def test_missing_or_stale_policy_receipt_is_a_specific_403_before_mutation(
    credential_kind: str,
    guest: bool,
    receipt: str,
) -> None:
    database = PolicyAuthDB(guest=guest, receipt=receipt)

    with pytest.raises(AuthenticationError) as captured:
        await authenticate_request(
            request_for(credential_kind),
            database,
            SETTINGS,
            require_account=True,
        )

    assert captured.value.status_code == 403
    assert captured.value.code == "POLICY_ACCEPTANCE_REQUIRED"
    assert captured.value.details == {
        "policyAcceptanceRequired": True,
        "requiredPolicyBundle": CURRENT_POLICY_BUNDLE_ID,
        "requiredPolicyBundleHash": CURRENT_POLICY_BUNDLE_HASH,
    }
    assert database.updates == []
    assert database.rpcs[-1] == (
        "read_current_policy_acceptance_v1",
        {"p_user_id": USER_ID},
    )


@pytest.mark.parametrize("credential_kind", ["cookie", "bearer"])
@pytest.mark.parametrize("guest", [False, True])
@pytest.mark.asyncio
async def test_exact_current_receipt_allows_only_the_matching_account_kind(
    credential_kind: str,
    guest: bool,
) -> None:
    database = PolicyAuthDB(guest=guest, receipt="current")
    if guest:
        with pytest.raises(AuthenticationError) as captured:
            await authenticate_request(
                request_for(credential_kind),
                database,
                SETTINGS,
                touch=False,
                require_account=True,
            )
        assert captured.value.code == "AUTH_REQUIRED"
        assert "Create your free account" in captured.value.message
    else:
        auth = await authenticate_request(
            request_for(credential_kind),
            database,
            SETTINGS,
            touch=False,
            require_account=True,
        )
        assert auth.user["id"] == USER_ID
    assert database.updates == []


@pytest.mark.parametrize(
    ("receipt", "expected_current"),
    [("missing", False), ("stale", False), ("current", True)],
)
@pytest.mark.asyncio
async def test_allowlisted_session_bootstrap_never_promotes_legacy_timestamp_without_receipt(
    receipt: str,
    expected_current: bool,
) -> None:
    database = PolicyAuthDB(guest=False, receipt=receipt)
    database.user.update({
        "terms_version": CURRENT_POLICY_BUNDLE_ID,
        "terms_accepted_at": "2026-10-27T00:00:00+00:00",
    })

    auth = await authenticate_request(
        request_for("cookie"),
        database,
        SETTINGS,
        touch=False,
        require_current_policy_acceptance=False,
        include_policy_acceptance_state=True,
    )

    assert public_user(auth.user)["policyAcceptedCurrent"] is expected_current
    assert auth.user["terms_version"] == CURRENT_POLICY_BUNDLE_ID
    assert auth.user["terms_accepted_at"]


def test_registration_requires_explicit_exact_current_bundle() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="missing@example.com", password="StrongPass1")
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="false@example.com",
            password="StrongPass1",
            termsAccepted=False,
            privacyNoticeAcknowledged=True,
            age17PlusAttested=True,
            aiProviderTransmissionAuthorized=True,
            termsVersion=CURRENT_POLICY_BUNDLE_ID,
        )
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="stale@example.com",
            password="StrongPass1",
            termsAccepted=True,
            privacyNoticeAcknowledged=True,
            age17PlusAttested=True,
            aiProviderTransmissionAuthorized=True,
            termsVersion="2026-08-01",
        )
    accepted = RegisterRequest(
        email="current@example.com",
        password="StrongPass1",
        termsAccepted=True,
        privacyNoticeAcknowledged=True,
        age17PlusAttested=True,
        aiProviderTransmissionAuthorized=True,
        termsVersion=CURRENT_POLICY_BUNDLE_ID,
    )
    assert accepted.termsAccepted is True


@pytest.mark.parametrize(
    "field",
    [
        "termsAccepted",
        "privacyNoticeAcknowledged",
        "age17PlusAttested",
        "aiProviderTransmissionAuthorized",
    ],
)
@pytest.mark.parametrize(
    ("mode", "invalid_value"),
    [
        ("omitted", None),
        ("false", False),
        ("integer", 1),
        ("float", 1.0),
        ("string", "true"),
        ("null", None),
    ],
)
def test_registration_rejects_each_missing_or_false_bundle_attestation(
    field: str,
    mode: str,
    invalid_value,
) -> None:
    payload = {
        "email": "explicit@example.com",
        "password": "StrongPass1",
        "termsAccepted": True,
        "privacyNoticeAcknowledged": True,
        "age17PlusAttested": True,
        "aiProviderTransmissionAuthorized": True,
        "termsVersion": CURRENT_POLICY_BUNDLE_ID,
    }
    if mode == "omitted":
        payload.pop(field)
    else:
        payload[field] = invalid_value
    with pytest.raises(ValidationError):
        RegisterRequest(**payload)


@pytest.mark.parametrize(
    "field",
    [
        "termsAccepted",
        "privacyNoticeAcknowledged",
        "age17PlusAttested",
        "aiProviderTransmissionAuthorized",
    ],
)
@pytest.mark.parametrize(
    ("mode", "invalid_value"),
    [
        ("omitted", None),
        ("false", False),
        ("integer", 1),
        ("float", 1.0),
        ("string", "true"),
        ("null", None),
    ],
)
def test_reacceptance_rejects_each_missing_or_false_bundle_attestation(
    field: str,
    mode: str,
    invalid_value,
) -> None:
    payload = {
        "version": CURRENT_POLICY_BUNDLE_ID,
        "termsAccepted": True,
        "privacyNoticeAcknowledged": True,
        "age17PlusAttested": True,
        "aiProviderTransmissionAuthorized": True,
    }
    if mode == "omitted":
        payload.pop(field)
    else:
        payload[field] = invalid_value
    with pytest.raises(ValidationError):
        TermsAcceptanceRequest(**payload)


@pytest.mark.asyncio
async def test_receipt_writer_sends_only_bounded_content_free_attestations() -> None:
    class ReceiptDB:
        def __init__(self) -> None:
            self.call = None

        async def rpc(self, name, payload, **_kwargs):
            self.call = (name, dict(payload))
            return [{
                "receipt_id": "33333333-3333-4333-8333-333333333333",
                "accepted_at": "2026-10-27T00:00:00+00:00",
                "bundle_id": CURRENT_POLICY_BUNDLE_ID,
                "bundle_hash": CURRENT_POLICY_BUNDLE_HASH,
            }]

    database = ReceiptDB()
    receipt = await record_current_policy_acceptance(
        database,
        user_id=USER_ID,
        source="guest_gate",
        platform="web",
        age_17_plus_attested=True,
        terms_accepted=True,
        privacy_notice_acknowledged=True,
        ai_provider_transmission_authorized=True,
    )
    assert receipt["bundle_id"] == CURRENT_POLICY_BUNDLE_ID
    assert database.call == (
        "record_policy_acceptance_v1",
        {
            "p_user_id": USER_ID,
            "p_bundle_id": CURRENT_POLICY_BUNDLE_ID,
            "p_acceptance_source": "guest_gate",
            "p_client_platform": "web",
            "p_age_17_plus_attested": True,
            "p_terms_accepted": True,
            "p_privacy_notice_acknowledged": True,
            "p_ai_provider_transmission_authorized": True,
        },
    )
    assert "ip" not in repr(database.call).lower()
    assert "content" not in repr(database.call).lower()


def test_only_the_narrow_recovery_and_session_allowlist_can_bypass_policy() -> None:
    account = (ROOT / "backend/routes/account.py").read_text(encoding="utf-8")
    auth = (ROOT / "backend/routes/auth.py").read_text(encoding="utf-8")
    all_backend = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "backend").rglob("*.py")
    )
    assert all_backend.count("require_current_policy_acceptance=False") == 10
    assert account.count("require_current_policy_acceptance=False") == 2
    assert auth.count("require_current_policy_acceptance=False") == 8


def test_frontend_treats_timestamp_only_or_stale_version_as_unaccepted() -> None:
    source = (ROOT / "public/auth-controller.js").read_text(encoding="utf-8")
    gate = source[source.index("function routeAuthenticatedUser"):source.index("// ---- Free text access")]
    assert "!user.policyAcceptedCurrent" in gate
    assert "user.termsVersion !== TERMS_VERSION" in gate
    assert "user.policyBundleHash !== TERMS_BUNDLE_HASH" in gate
    assert CURRENT_POLICY_BUNDLE_ID in source
    assert CURRENT_POLICY_BUNDLE_HASH in source


@pytest.mark.asyncio
async def test_chat_denial_precedes_payload_usage_claim_and_provider_work(monkeypatch) -> None:
    calls = {"json": 0}

    async def deny_policy(*_args, **_kwargs):
        raise AuthenticationError(
            "Accept the current policy bundle.",
            status_code=403,
            code="POLICY_ACCEPTANCE_REQUIRED",
        )

    class UnreadRequest:
        headers: dict[str, str] = {}
        state = SimpleNamespace()

        async def json(self):
            calls["json"] += 1
            raise AssertionError("denied chat must not read customer content")

    monkeypatch.setattr(chat_routes, "authenticate_request", deny_policy)
    with pytest.raises(AuthenticationError) as captured:
        await chat_routes.chat(UnreadRequest())

    assert captured.value.code == "POLICY_ACCEPTANCE_REQUIRED"
    assert calls == {"json": 0}
    assert not hasattr(UnreadRequest.state, "chat_job_claim")


class ManuscriptPolicyDB:
    def __init__(self, receipt: str) -> None:
        self.receipt = receipt
        self.updates: list[tuple] = []

    async def rpc(self, name, payload, *, retry_transient=False):
        if name == "claim_manuscript_run":
            return [{
                "id": "44444444-4444-4444-8444-444444444444",
                "user_id": USER_ID,
                "manuscript_id": "55555555-5555-4555-8555-555555555555",
                "project_id": "66666666-6666-4666-8666-666666666666",
                "status": "running",
                "stage": "blueprint",
                "mode": "outline",
                "lease_token": payload["p_claim_token"],
                "attempt_count": 3,
                "brief": "private manuscript brief",
                "target_words": 20_000,
                "chapter_count": 10,
            }]
        if name == "read_current_policy_acceptance_v1":
            if self.receipt == "error":
                raise RuntimeError("private receipt-check failure")
            if self.receipt == "missing":
                return []
            if self.receipt == "stale":
                return [{
                    "bundle_id": "ask-crump-legal-stale",
                    "bundle_hash": "0" * 64,
                }]
            return [{
                "bundle_id": CURRENT_POLICY_BUNDLE_ID,
                "bundle_hash": CURRENT_POLICY_BUNDLE_HASH,
            }]
        raise AssertionError(f"unexpected RPC {name}")

    async def select_one(self, table, **_kwargs):
        assert table == "users"
        return {"id": USER_ID}

    async def update(self, table, payload, *, filters):
        self.updates.append((table, dict(payload), dict(filters)))
        return [{**payload, "id": "44444444-4444-4444-8444-444444444444"}]


@pytest.mark.parametrize("receipt", ["missing", "stale"])
@pytest.mark.asyncio
async def test_manuscript_worker_policy_hold_precedes_provider_and_usage_mutation(
    receipt: str,
) -> None:
    database = ManuscriptPolicyDB(receipt)
    service = ManuscriptService(
        database,
        SimpleNamespace(),
        SimpleNamespace(),
        features=SimpleNamespace(),
        files=SimpleNamespace(),
    )
    service.plan_blueprint = AsyncMock(side_effect=AssertionError("provider must not run"))

    result = await service.process_next_run()

    assert result["status"] == "policy_required"
    service.plan_blueprint.assert_not_awaited()
    assert len(database.updates) == 1
    table, changes, _filters = database.updates[0]
    assert table == "manuscript_runs"
    assert changes["status"] == "paused"
    assert changes["attempt_count"] == 2
    assert changes["last_error_code"] == "POLICY_ACCEPTANCE_REQUIRED"
    assert changes["lease_token"] is None
    assert "provider_usage" not in changes
    assert "credits_spent" not in changes


@pytest.mark.asyncio
async def test_manuscript_policy_check_outage_restores_attempt_and_queues_without_provider_work(
) -> None:
    database = ManuscriptPolicyDB("error")
    service = ManuscriptService(
        database,
        SimpleNamespace(),
        SimpleNamespace(),
        features=SimpleNamespace(),
        files=SimpleNamespace(),
    )
    service.plan_blueprint = AsyncMock(side_effect=AssertionError("provider must not run"))

    result = await service.process_next_run()

    assert result["status"] == "policy_check_unavailable"
    service.plan_blueprint.assert_not_awaited()
    assert len(database.updates) == 1
    table, changes, filters = database.updates[0]
    assert table == "manuscript_runs"
    assert changes["status"] == "queued"
    assert changes["attempt_count"] == 2
    assert changes["not_before"]
    assert changes["last_error_code"] == "POLICY_ACCEPTANCE_CHECK_UNAVAILABLE"
    assert changes["lease_token"] is None
    assert changes["lease_expires_at"] is None
    assert "provider_usage" not in changes
    assert "credits_spent" not in changes
    assert filters["id"] == "eq.44444444-4444-4444-8444-444444444444"
    assert filters["status"] == "eq.running"
    assert filters["lease_token"].startswith("eq.")


@pytest.mark.asyncio
async def test_manuscript_worker_current_policy_reaches_provider_boundary() -> None:
    database = ManuscriptPolicyDB("current")
    service = ManuscriptService(
        database,
        SimpleNamespace(),
        SimpleNamespace(),
        features=SimpleNamespace(),
        files=SimpleNamespace(),
    )
    service.get = AsyncMock(return_value={
        "id": "55555555-5555-4555-8555-555555555555",
        "title": "Test manuscript",
    })
    service.list_sections = AsyncMock(return_value=[])
    service.plan_blueprint = AsyncMock(side_effect=RuntimeError("provider boundary reached"))

    result = await service.process_next_run()

    service.plan_blueprint.assert_awaited_once()
    assert result["claimed"] is True
    assert result["status"] in {"queued", "failed"}
