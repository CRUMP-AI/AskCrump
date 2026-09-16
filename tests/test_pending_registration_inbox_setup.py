from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from backend.email_service import EmailDeliveryError
from backend.db import DatabaseError
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
PRIOR_RESET_TOKEN = "prior-reset-token-owner-link"


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


def response_contract(response) -> tuple[int, dict]:
    if isinstance(response, JSONResponse):
        return response.status_code, response_body(response)
    return 200, response


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
        self.rpc_calls: list[dict] = []
        self._reset_lock = asyncio.Lock()

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

    async def rpc(self, function_name, payload, **_kwargs):
        assert function_name == "consume_password_reset"
        self.rpc_calls.append(deepcopy(payload))
        async with self._reset_lock:
            if (
                self.user.get("password_reset_token_hash")
                != payload["p_presented_token_hash"]
                or not self.user.get("password_reset_expires")
                or self.user["password_reset_expires"] <= payload["p_now"]
            ):
                return None
            was_verified = bool(self.user.get("is_verified"))
            self.user.update({
                "password_hash": payload["p_new_password_hash"],
                "auth_generation": int(self.user.get("auth_generation") or 0) + 1,
                "is_verified": True,
                "verification_token_hash": None,
                "verification_token_expires": None,
                "password_reset_token_hash": None,
                "password_reset_expires": None,
                "updated_at": payload["p_now"],
            })
            if not was_verified:
                self.user.update({
                    "full_name": None,
                    "terms_accepted_at": None,
                    "terms_version": None,
                })
            self.session_updates.append({
                "payload": {"revoked_at": payload["p_now"]},
                "filters": {"user_id": f"eq.{self.user['id']}", "revoked_at": "is.null"},
            })
            return {
                "id": self.user["id"],
                "auth_generation": self.user["auth_generation"],
            }


class RegistrationParityDB:
    def __init__(self, user: dict | None) -> None:
        self.user = deepcopy(user) if user is not None else None
        self.inserted_user: dict | None = None
        self.user_updates: list[dict] = []
        self.settings_created = False

    async def select_one(self, table, *, filters=None, **_kwargs):
        if table == "user_settings":
            return {}
        assert table == "users"
        if self.user is None or not PendingAccountDB._matches(self.user, filters or {}):
            return None
        return deepcopy(self.user)

    async def update(self, table, payload, *, filters, **_kwargs):
        assert table == "users"
        self.user_updates.append(deepcopy(payload))
        if self.user is None or not PendingAccountDB._matches(self.user, filters):
            return []
        self.user.update(deepcopy(payload))
        return [deepcopy(self.user)]

    async def insert(self, table, payload, **_kwargs):
        assert table == "users"
        assert self.user is None
        self.user = deepcopy(payload)
        self.inserted_user = deepcopy(payload)
        return [deepcopy(payload)]

    async def upsert(self, table, payload, **_kwargs):
        assert table == "user_settings"
        self.settings_created = True
        return [deepcopy(payload)]


class FirstRegistrationConflictDB(RegistrationParityDB):
    def __init__(self) -> None:
        super().__init__(None)
        self.insert_attempts = 0

    async def insert(self, table, payload, **_kwargs):
        assert table == "users"
        self.insert_attempts += 1
        # Model the other transaction winning the normalized-email unique key
        # between this request's initial SELECT and INSERT.
        self.user = deepcopy(payload)
        raise DatabaseError(
            "Database operation failed",
            status_code=409,
            details={"code": "23505", "constraint": "users_email_lower_unique"},
        )


class ResetRaceDB(PendingAccountDB):
    def __init__(
        self,
        user: dict,
        *,
        replace_token_after_select: bool = False,
        synchronize_reset_selects: bool = False,
    ) -> None:
        super().__init__(user)
        self.replace_token_after_select = replace_token_after_select
        self.synchronize_reset_selects = synchronize_reset_selects
        self.reset_select_count = 0
        self.both_reset_selects = asyncio.Event()

    async def rpc(self, function_name, payload, **kwargs):
        if self.replace_token_after_select:
            self.replace_token_after_select = False
            self.user["password_reset_token_hash"] = token_hash("newer-reset-token")
            self.user["password_reset_expires"] = "2099-04-01T00:00:00+00:00"

        if self.synchronize_reset_selects:
            self.reset_select_count += 1
            if self.reset_select_count == 2:
                self.both_reset_selects.set()
            await asyncio.wait_for(self.both_reset_selects.wait(), timeout=2)
        return await super().rpc(function_name, payload, **kwargs)


class SetupEmail:
    def __init__(self, outcome: str = "success") -> None:
        self.outcome = outcome
        self.reset_calls: list[dict] = []
        self.verification_calls: list[dict] = []

    async def _deliver(self):
        if self.outcome == "false":
            return False
        if self.outcome == "error":
            raise EmailDeliveryError(status_code=503, retryable=True)
        if self.outcome == "unexpected":
            raise RuntimeError("synthetic delivery failure")
        return True

    async def send_password_reset(self, email, name, token):
        self.reset_calls.append({"email": email, "name": name, "token": token})
        return await self._deliver()

    async def send_verification(self, email, name, token, **kwargs):
        self.verification_calls.append(
            {"email": email, "name": name, "token": token, **kwargs}
        )
        return await self._deliver()


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
        "password_reset_token_hash": token_hash(PRIOR_RESET_TOKEN),
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
@pytest.mark.parametrize("outcome", ["success", "false", "error", "unexpected"])
async def test_new_and_pending_registration_have_indistinguishable_contract_and_hash_work(
    monkeypatch,
    outcome: str,
) -> None:
    original_pending = pending_user()
    real_hash_password = auth_routes.hash_password
    payload = RegisterRequest(
        email=original_pending["email"],
        password="SubmittedPassword2",
        fullName="Submitted Name",
        source="facebook",
        placement="submitted-placement",
        campaign="submitted-campaign",
        creative="submitted-creative",
        intent="projects",
        plan="enterprise",
        termsAccepted=True,
        termsVersion=CURRENT_TERMS_VERSION,
    )
    observations: list[dict] = []

    async def ignore_event(*_args, **_kwargs):
        return True

    for kind, existing in (("new", None), ("pending", original_pending)):
        database = RegistrationParityDB(existing)
        email = SetupEmail(outcome)
        hash_calls: list[str] = []

        def measured_hash(password: str) -> str:
            hash_calls.append(password)
            return real_hash_password(password)

        monkeypatch.setattr(auth_routes, "db", database)
        monkeypatch.setattr(auth_routes, "email_service", email)
        monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", allow_rate_limit)
        monkeypatch.setattr(auth_routes, "hash_password", measured_hash)
        monkeypatch.setattr(auth_routes, "record_account_created_event", ignore_event)
        monkeypatch.setattr(auth_routes, "record_product_event", ignore_event)

        result = await auth_routes.register(
            payload,
            auth_request("POST", "/api/auth/register"),
        )
        observations.append(
            {
                "kind": kind,
                "response": result,
                "contract": response_contract(result),
                "hash_calls": hash_calls,
                "database": database,
                "email": email,
            }
        )

    new, pending = observations
    assert new["contract"] == pending["contract"] == (
        200,
        {
            "success": True,
            "message": GENERIC_SETUP_MESSAGE,
        },
    )
    assert isinstance(new["response"], dict)
    assert isinstance(pending["response"], dict)
    assert new["hash_calls"] == pending["hash_calls"] == [payload.password]
    assert len(new["email"].verification_calls) == 1
    assert new["email"].reset_calls == []
    assert len(pending["email"].reset_calls) == 1
    assert pending["email"].verification_calls == []
    assert verify_password(
        payload.password,
        new["database"].inserted_user["password_hash"],
    )
    assert pending["database"].user["password_hash"] == original_pending["password_hash"]
    assert pending["database"].user["verification_token_hash"] == (
        original_pending["verification_token_hash"]
    )
    if outcome != "success":
        assert pending["database"].user["password_reset_token_hash"] is None
        assert pending["database"].user["password_reset_expires"] is None
        for key, value in original_pending.items():
            if key not in {
                "password_reset_token_hash",
                "password_reset_expires",
                "updated_at",
            }:
                assert pending["database"].user[key] == value


@pytest.mark.asyncio
async def test_verified_registration_conflict_contract_is_unchanged(monkeypatch) -> None:
    verified = pending_user()
    verified["is_verified"] = True
    database = RegistrationParityDB(verified)
    email = SetupEmail()
    install_auth_fakes(monkeypatch, database, email)

    result = await auth_routes.register(
        RegisterRequest(email=verified["email"], password="SubmittedPassword2"),
        auth_request("POST", "/api/auth/register"),
    )

    assert result.status_code == 409
    assert response_body(result) == {
        "success": False,
        "error": "An account with that email already exists.",
    }
    assert email.reset_calls == []
    assert email.verification_calls == []


@pytest.mark.asyncio
async def test_simultaneous_first_registration_unique_loser_gets_generic_success(
    monkeypatch,
) -> None:
    database = FirstRegistrationConflictDB()
    email = SetupEmail()
    hash_calls: list[str] = []
    real_hash_password = auth_routes.hash_password

    def measured_hash(password: str) -> str:
        hash_calls.append(password)
        return real_hash_password(password)

    monkeypatch.setattr(auth_routes, "db", database)
    monkeypatch.setattr(auth_routes, "email_service", email)
    monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", allow_rate_limit)
    monkeypatch.setattr(auth_routes, "hash_password", measured_hash)

    result = await auth_routes.register(
        RegisterRequest(email="new@example.com", password="FirstPassword2"),
        auth_request("POST", "/api/auth/register"),
    )

    assert result == {"success": True, "message": GENERIC_SETUP_MESSAGE}
    assert hash_calls == ["FirstPassword2"]
    assert database.insert_attempts == 1
    assert len(email.reset_calls) == 1
    assert email.verification_calls == []


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
    assert database.user["full_name"] is None
    assert database.user["terms_accepted_at"] is None
    assert database.user["terms_version"] is None
    owner_view = auth_routes.public_user(database.user)
    assert owner_view["fullName"] is None
    assert owner_view["termsAcceptedAt"] is None
    assert owner_view["termsVersion"] is None
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
async def test_verified_account_recovery_preserves_owner_profile_and_terms(monkeypatch) -> None:
    original = pending_user()
    original["is_verified"] = True
    database = PendingAccountDB(original)
    email = SetupEmail()
    install_auth_fakes(monkeypatch, database, email)
    captured_now = "2026-09-16T15:00:00+00:00"
    now_calls: list[str] = []

    def fixed_now() -> str:
        now_calls.append(captured_now)
        return captured_now

    monkeypatch.setattr(auth_routes, "iso_now", fixed_now)
    reset = await auth_routes.reset_password(
        ResetPasswordRequest(token=PRIOR_RESET_TOKEN, newPassword="OwnerRecovery2"),
        auth_request("POST", "/api/auth/reset-password"),
    )

    assert reset == {
        "success": True,
        "message": "Password updated. Sign in with your new password.",
    }
    assert now_calls == [captured_now]
    assert database.user["full_name"] == original["full_name"]
    assert database.user["terms_accepted_at"] == original["terms_accepted_at"]
    assert database.user["terms_version"] == original["terms_version"]
    assert verify_password("OwnerRecovery2", database.user["password_hash"])
    assert database.rpc_calls[0] == {
        "p_presented_token_hash": token_hash(PRIOR_RESET_TOKEN),
        "p_new_password_hash": database.user["password_hash"],
        "p_now": captured_now,
    }
    assert database.session_updates[0]["payload"] == {"revoked_at": captured_now}


@pytest.mark.asyncio
async def test_reset_cas_rejects_old_token_replaced_after_select(monkeypatch) -> None:
    original = pending_user()
    database = ResetRaceDB(original, replace_token_after_select=True)
    email = SetupEmail()
    install_auth_fakes(monkeypatch, database, email)

    result = await auth_routes.reset_password(
        ResetPasswordRequest(token=PRIOR_RESET_TOKEN, newPassword="MustNotWin2"),
        auth_request("POST", "/api/auth/reset-password"),
    )

    assert result.status_code == 400
    assert response_body(result)["error"] == "This reset link is invalid or expired."
    assert database.user["password_hash"] == original["password_hash"]
    assert database.user["password_reset_token_hash"] == token_hash("newer-reset-token")
    assert database.user["password_reset_expires"] == "2099-04-01T00:00:00+00:00"
    assert database.user["full_name"] == original["full_name"]
    assert database.user["terms_accepted_at"] == original["terms_accepted_at"]
    assert database.user["terms_version"] == original["terms_version"]
    assert database.session_updates == []
    assert database.rpc_calls[0]["p_presented_token_hash"] == token_hash(PRIOR_RESET_TOKEN)


@pytest.mark.asyncio
async def test_simultaneous_same_token_reset_has_one_winner(monkeypatch) -> None:
    original = pending_user()
    original["is_verified"] = True
    database = ResetRaceDB(original, synchronize_reset_selects=True)
    email = SetupEmail()
    install_auth_fakes(monkeypatch, database, email)
    passwords = ["FirstConcurrent2", "SecondConcurrent3"]

    results = await asyncio.gather(
        *(
            auth_routes.reset_password(
                ResetPasswordRequest(token=PRIOR_RESET_TOKEN, newPassword=password),
                auth_request("POST", "/api/auth/reset-password"),
            )
            for password in passwords
        )
    )

    winners = [index for index, result in enumerate(results) if isinstance(result, dict)]
    losers = [index for index, result in enumerate(results) if isinstance(result, JSONResponse)]
    assert len(winners) == 1
    assert len(losers) == 1
    assert results[winners[0]]["success"] is True
    assert results[losers[0]].status_code == 400
    assert response_body(results[losers[0]])["error"] == (
        "This reset link is invalid or expired."
    )
    assert verify_password(passwords[winners[0]], database.user["password_hash"])
    assert not verify_password(passwords[losers[0]], database.user["password_hash"])
    assert database.user["password_reset_token_hash"] is None
    assert len(database.session_updates) == 1


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
async def test_setup_delivery_failure_clears_only_its_token_without_resurrecting_predecessor(
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
    assert database.user["password_reset_token_hash"] is None
    assert database.user["password_reset_expires"] is None
    for key, value in original.items():
        if key not in {
            "password_reset_token_hash",
            "password_reset_expires",
            "updated_at",
        }:
            assert database.user[key] == value
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
    register_route = route[
        route.index("@router.post('/register')") : route.index("@router.post('/login')")
    ]

    assert "If an account is awaiting verification for that email" in route
    assert "secure link to finish setup and choose a password." in route
    assert "SECURE ACCOUNT SETUP" in shell
    assert "Password changes happen only after a link sent to that inbox is opened." in shell
    assert "latest password" not in shell.lower()
    assert "latest password" not in route.lower()
    assert "pendingAccount" not in route
    assert route.count("return {'success': True, 'message': PENDING_SETUP_MESSAGE}") == 3
    assert register_route.index("submitted_password_hash = hash_password") < (
        register_route.index("existing = await db.select_one")
    )
    assert "except EmailDeliveryError as exc:" in register_route
    assert "except Exception:" in register_route
    assert "verification_delivery_failure(exc, account_created=True)" not in register_route
