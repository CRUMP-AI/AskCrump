from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi import Request, Response

from backend.email_service import EmailDeliveryError
from backend.routes import auth as auth_routes
from backend.schemas import (
    CURRENT_TERMS_VERSION,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from backend.security import hash_password, token_hash, verify_password


ROOT = Path(__file__).resolve().parents[1]
GENERIC_SETUP_MESSAGE = (
    "If an account is awaiting verification for that email, check its inbox for a "
    "secure link to finish setup and choose a password."
)


def auth_request(method: str, path: str) -> Request:
    return Request({
        "type": "http",
        "method": method,
        "path": path,
        "headers": [
            (b"host", b"www.askcrump.com"),
            (b"user-agent", b"pending-inbox-setup-test"),
        ],
        "client": ("127.0.0.1", 12345),
    })


def response_body(response) -> dict:
    return json.loads(response.body)


class PendingAccountDB:
    def __init__(
        self,
        user: dict,
        *,
        verification_wins_setup_race: bool = False,
        newer_reset_wins_rollback_race: bool = False,
    ) -> None:
        self.user = deepcopy(user)
        self.verification_wins_setup_race = verification_wins_setup_race
        self.newer_reset_wins_rollback_race = newer_reset_wins_rollback_race
        self.user_updates: list[dict] = []
        self.user_update_filters: list[dict] = []
        self.session_updates: list[dict] = []

    @staticmethod
    def _matches(row: dict, filters: dict) -> bool:
        for key, raw_filter in filters.items():
            if raw_filter == "is.null":
                if row.get(key) is not None:
                    return False
                continue
            if isinstance(raw_filter, str) and raw_filter.startswith("eq."):
                expected: object = raw_filter[3:]
                if expected == "true":
                    expected = True
                elif expected == "false":
                    expected = False
                if row.get(key) != expected:
                    return False
                continue
            if isinstance(raw_filter, str) and raw_filter.startswith("gt."):
                if not row.get(key) or str(row.get(key)) <= raw_filter[3:]:
                    return False
                continue
            if row.get(key) != raw_filter:
                return False
        return True

    async def select_one(self, table, *, filters=None, **_kwargs):
        if table == "user_settings":
            return {}
        assert table == "users"
        return deepcopy(self.user) if self._matches(self.user, filters or {}) else None

    async def update(self, table, payload, *, filters, **_kwargs):
        if table == "sessions":
            self.session_updates.append({"payload": deepcopy(payload), "filters": deepcopy(filters)})
            return []

        assert table == "users"
        values = deepcopy(payload)
        criteria = deepcopy(filters)
        self.user_updates.append(values)
        self.user_update_filters.append(criteria)

        is_setup_issue = (
            "password_reset_token_hash" in values
            and values.get("password_reset_token_hash") is not None
            and "password_reset_token_hash" not in criteria
            and criteria.get("is_verified") == "eq.false"
        )
        if is_setup_issue and self.verification_wins_setup_race:
            self.user["is_verified"] = True
            return []

        is_setup_rollback = (
            "password_reset_token_hash" in criteria
            and values.get("password_reset_token_hash")
            != criteria.get("password_reset_token_hash", "").removeprefix("eq.")
        )
        if is_setup_rollback and self.newer_reset_wins_rollback_race:
            self.user["password_reset_token_hash"] = "newer-reset-hash"
            self.user["password_reset_expires"] = "2099-03-01T00:00:00+00:00"
            return []

        if not self._matches(self.user, filters):
            return []
        self.user.update(values)
        return [deepcopy(self.user)]


class SetupEmail:
    def __init__(self, outcome: str = "success") -> None:
        self.outcome = outcome
        self.reset_calls: list[dict] = []
        self.verification_calls: list[dict] = []

    async def send_password_reset(self, email, name, token):
        self.reset_calls.append({"email": email, "name": name, "token": token})
        if self.outcome == "false":
            return False
        if self.outcome == "error":
            raise EmailDeliveryError(status_code=503, retryable=True)
        if self.outcome == "unexpected":
            raise RuntimeError("synthetic delivery failure")
        return True

    async def send_verification(self, email, name, token, **kwargs):
        self.verification_calls.append(
            {"email": email, "name": name, "token": token, **kwargs}
        )
        return True


async def allow_rate_limit(*_args, **_kwargs) -> None:
    return None


def pending_user(password: str = "OwnerPassword1") -> dict:
    return {
        "id": "pending-owner",
        "email": "owner@example.com",
        "password_hash": hash_password(password),
        "full_name": "Inbox Owner",
        "is_verified": False,
        "verification_token_hash": token_hash("original-verification-token"),
        "verification_token_expires": "2099-01-01T00:00:00+00:00",
        "password_reset_token_hash": token_hash("prior-reset-token"),
        "password_reset_expires": "2099-01-02T00:00:00+00:00",
        "terms_accepted_at": "2026-09-01T00:00:00+00:00",
        "terms_version": CURRENT_TERMS_VERSION,
        "subscription_tier": "free",
        "subscription_status": "inactive",
        "updated_at": "2026-09-01T00:00:00+00:00",
    }


def install_auth_fakes(monkeypatch, database: PendingAccountDB, email: SetupEmail) -> list[str]:
    issued_sessions: list[str] = []

    async def create_test_session(*_args, **_kwargs):
        issued_sessions.append("issued")
        return "session-token", {"expires_at": "2099-01-01T00:00:00+00:00"}

    monkeypatch.setattr(auth_routes, "db", database)
    monkeypatch.setattr(auth_routes, "email_service", email)
    monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", allow_rate_limit)
    monkeypatch.setattr(auth_routes, "create_session", create_test_session)
    monkeypatch.setattr(auth_routes, "set_session_cookie", lambda *_args: None)
    return issued_sessions


@pytest.mark.asyncio
async def test_repeat_registration_cannot_poison_password_before_inbox_proof(
    monkeypatch,
) -> None:
    owner_password = "OwnerPassword1"
    attacker_password = "AttackerPass2"
    original = pending_user(owner_password)
    database = PendingAccountDB(original)
    email = SetupEmail()
    issued_sessions = install_auth_fakes(monkeypatch, database, email)
    monkeypatch.setattr(auth_routes, "random_token", lambda _size: "inbox-setup-token")

    result = await auth_routes.register(
        RegisterRequest(
            email=original["email"],
            password=attacker_password,
            fullName="Attacker Name",
            source="facebook",
            placement="attacker-placement",
            campaign="attacker-campaign",
            creative="attacker-creative",
            intent="projects",
            plan="enterprise",
            termsAccepted=True,
            termsVersion=CURRENT_TERMS_VERSION,
        ),
        auth_request("POST", "/api/auth/register"),
    )

    assert result == {"success": True, "message": GENERIC_SETUP_MESSAGE}
    assert email.verification_calls == []
    assert email.reset_calls == [{
        "email": original["email"],
        "name": original["full_name"],
        "token": "inbox-setup-token",
    }]
    assert database.user["password_hash"] == original["password_hash"]
    assert database.user["verification_token_hash"] == original["verification_token_hash"]
    assert database.user["verification_token_expires"] == original["verification_token_expires"]
    assert database.user["full_name"] == original["full_name"]
    assert database.user["terms_accepted_at"] == original["terms_accepted_at"]
    assert database.user["terms_version"] == original["terms_version"]
    issued_values = database.user_updates[0]
    assert set(issued_values) == {
        "password_reset_token_hash",
        "password_reset_expires",
        "updated_at",
    }
    assert database.user_update_filters[0] == {
        "id": "eq.pending-owner",
        "is_verified": "eq.false",
    }

    attacker_before_verification = await auth_routes.login(
        LoginRequest(email=original["email"], password=attacker_password),
        auth_request("POST", "/api/auth/login"),
        Response(),
    )
    assert attacker_before_verification.status_code == 401

    owner_before_verification = await auth_routes.login(
        LoginRequest(email=original["email"], password=owner_password),
        auth_request("POST", "/api/auth/login"),
        Response(),
    )
    assert owner_before_verification.status_code == 403

    verification = await auth_routes.verify_email(
        "original-verification-token",
        auth_request("GET", "/api/auth/verify-email"),
    )
    assert verification.status_code == 303
    assert verification.headers["location"].endswith("/app?verification=success")
    assert database.user["is_verified"] is True
    assert issued_sessions == ["issued"]

    attacker_after_verification = await auth_routes.login(
        LoginRequest(email=original["email"], password=attacker_password),
        auth_request("POST", "/api/auth/login"),
        Response(),
    )
    assert attacker_after_verification.status_code == 401

    owner_after_verification = await auth_routes.login(
        LoginRequest(email=original["email"], password=owner_password),
        auth_request("POST", "/api/auth/login"),
        Response(),
    )
    assert owner_after_verification["success"] is True
    assert issued_sessions == ["issued", "issued"]


@pytest.mark.asyncio
async def test_inbox_setup_token_is_the_only_way_to_replace_pending_password(
    monkeypatch,
) -> None:
    original = pending_user()
    database = PendingAccountDB(original)
    email = SetupEmail()
    install_auth_fakes(monkeypatch, database, email)
    setup_token = "owner-inbox-setup-token"
    monkeypatch.setattr(auth_routes, "random_token", lambda _size: setup_token)

    await auth_routes.register(
        RegisterRequest(email=original["email"], password="AttackerPass2"),
        auth_request("POST", "/api/auth/register"),
    )
    new_owner_password = "OwnerChosenPass3"
    reset = await auth_routes.reset_password(
        ResetPasswordRequest(token=setup_token, newPassword=new_owner_password),
        auth_request("POST", "/api/auth/reset-password"),
    )

    assert reset == {
        "success": True,
        "message": "Password updated. Sign in with your new password.",
    }
    assert database.user["is_verified"] is True
    assert database.user["verification_token_hash"] is None
    assert database.user["verification_token_expires"] is None
    assert database.user["password_reset_token_hash"] is None
    assert database.user["password_reset_expires"] is None
    assert verify_password(new_owner_password, database.user["password_hash"])
    assert not verify_password("OwnerPassword1", database.user["password_hash"])
    assert not verify_password("AttackerPass2", database.user["password_hash"])
    assert database.session_updates == [{
        "payload": {"revoked_at": database.session_updates[0]["payload"]["revoked_at"]},
        "filters": {"user_id": "eq.pending-owner", "revoked_at": "is.null"},
    }]

    replay = await auth_routes.reset_password(
        ResetPasswordRequest(token=setup_token, newPassword="ReplayBlocked4"),
        auth_request("POST", "/api/auth/reset-password"),
    )
    assert replay.status_code == 400
    assert response_body(replay)["error"] == "This reset link is invalid or expired."
    assert verify_password(new_owner_password, database.user["password_hash"])


@pytest.mark.asyncio
async def test_expired_inbox_setup_token_cannot_change_password(monkeypatch) -> None:
    original = pending_user()
    database = PendingAccountDB(original)
    email = SetupEmail()
    install_auth_fakes(monkeypatch, database, email)
    setup_token = "expired-inbox-setup-token"
    monkeypatch.setattr(auth_routes, "random_token", lambda _size: setup_token)

    await auth_routes.register(
        RegisterRequest(email=original["email"], password="DiscardedPass2"),
        auth_request("POST", "/api/auth/register"),
    )
    database.user["password_reset_expires"] = "2000-01-01T00:00:00+00:00"
    expired = await auth_routes.reset_password(
        ResetPasswordRequest(token=setup_token, newPassword="BlockedPass3"),
        auth_request("POST", "/api/auth/reset-password"),
    )

    assert expired.status_code == 400
    assert response_body(expired)["error"] == "This reset link is invalid or expired."
    assert database.user["password_hash"] == original["password_hash"]
    assert database.user["is_verified"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["false", "error", "unexpected"])
async def test_setup_delivery_failure_restores_original_pending_state(
    monkeypatch,
    outcome: str,
) -> None:
    original = pending_user()
    database = PendingAccountDB(original)
    email = SetupEmail(outcome)
    install_auth_fakes(monkeypatch, database, email)
    monkeypatch.setattr(auth_routes, "random_token", lambda _size: "undelivered-setup-token")

    result = await auth_routes.register(
        RegisterRequest(
            email=original["email"],
            password="DiscardedPass2",
            fullName="Discarded Name",
            termsAccepted=True,
            termsVersion=CURRENT_TERMS_VERSION,
        ),
        auth_request("POST", "/api/auth/register"),
    )

    assert result == {"success": True, "message": GENERIC_SETUP_MESSAGE}
    assert database.user == original
    assert len(database.user_updates) == 2
    assert database.user_update_filters[1] == {
        "id": "eq.pending-owner",
        "is_verified": "eq.false",
        "password_reset_token_hash": f"eq.{token_hash('undelivered-setup-token')}",
    }
    assert email.verification_calls == []


@pytest.mark.asyncio
async def test_verification_winning_setup_race_prevents_token_and_email(monkeypatch) -> None:
    original = pending_user()
    database = PendingAccountDB(original, verification_wins_setup_race=True)
    email = SetupEmail()
    install_auth_fakes(monkeypatch, database, email)

    result = await auth_routes.register(
        RegisterRequest(email=original["email"], password="DiscardedPass2"),
        auth_request("POST", "/api/auth/register"),
    )

    assert result == {"success": True, "message": GENERIC_SETUP_MESSAGE}
    assert database.user["is_verified"] is True
    assert database.user["password_hash"] == original["password_hash"]
    assert database.user["verification_token_hash"] == original["verification_token_hash"]
    assert database.user["password_reset_token_hash"] == original["password_reset_token_hash"]
    assert email.reset_calls == []
    assert email.verification_calls == []


@pytest.mark.asyncio
async def test_failed_delivery_rollback_never_clobbers_newer_reset(monkeypatch) -> None:
    original = pending_user()
    database = PendingAccountDB(original, newer_reset_wins_rollback_race=True)
    email = SetupEmail("false")
    install_auth_fakes(monkeypatch, database, email)
    monkeypatch.setattr(auth_routes, "random_token", lambda _size: "superseded-setup-token")

    result = await auth_routes.register(
        RegisterRequest(email=original["email"], password="DiscardedPass2"),
        auth_request("POST", "/api/auth/register"),
    )

    assert result == {"success": True, "message": GENERIC_SETUP_MESSAGE}
    assert database.user["password_reset_token_hash"] == "newer-reset-hash"
    assert database.user["password_reset_expires"] == "2099-03-01T00:00:00+00:00"
    assert database.user["password_hash"] == original["password_hash"]
    assert database.user["verification_token_hash"] == original["verification_token_hash"]


def test_pending_setup_copy_is_generic_and_never_promises_an_unproven_password() -> None:
    shell = (ROOT / "public" / "app.html").read_text(encoding="utf-8")
    route = (ROOT / "backend" / "routes" / "auth.py").read_text(encoding="utf-8")

    assert "If an account is awaiting verification for that email" in route
    assert "secure link to finish setup and choose a password." in route
    assert "SECURE ACCOUNT SETUP" in shell
    assert "Password changes happen only after a link sent to that inbox is opened." in shell
    assert "latest password" not in shell.lower()
    assert "latest password" not in route.lower()
    assert "pendingAccount" not in route
    assert route.count("return {'success': True, 'message': PENDING_SETUP_MESSAGE}") == 2
