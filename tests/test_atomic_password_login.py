from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import Request, Response

from backend import auth_service
from backend.auth_service import finalize_login_session
from backend.routes import auth as auth_routes
from backend.schemas import LoginRequest


def login_request(*, installation_id: str = "installation-atomic-login") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": [
            (b"host", b"www.askcrump.com"),
            (b"x-installation-id", installation_id.encode()),
            (b"user-agent", b"pytest"),
        ],
        "client": ("127.0.0.1", 12345),
    })


class LoginRPCDB:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, dict]] = []

    async def rpc(self, name, payload):
        self.calls.append((name, dict(payload)))
        return self.result


@pytest.mark.asyncio
async def test_finalize_login_sends_exact_verified_hash_and_no_plaintext(monkeypatch) -> None:
    current_user = {
        "id": "user-1",
        "email": "person@example.com",
        "password_hash": "$argon2id$upgraded-hash",
    }
    persisted_session = {
        "id": "session-1",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    database = LoginRPCDB([{
        "login_applied": True,
        "user_data": current_user,
        "session_data": persisted_session,
        "pruned_sessions": 0,
    }])
    monkeypatch.setattr(auth_service, "random_token", lambda _length: "raw-secret-token")
    monkeypatch.setattr(auth_service, "new_uuid", lambda: "session-id")

    finalized = await finalize_login_session(
        database,
        SimpleNamespace(session_days=365),
        {"id": "user-1"},
        login_request(),
        expected_password_hash="$2b$12$exact-hash-that-python-verified",
        upgraded_password_hash="$argon2id$new-upgraded-hash",
        device_name="Phone",
        platform="web",
    )

    assert finalized == ("raw-secret-token", current_user, persisted_session)
    assert len(database.calls) == 1
    name, payload = database.calls[0]
    assert name == "finalize_password_login_v1"
    assert payload["p_expected_password_hash"] == "$2b$12$exact-hash-that-python-verified"
    assert payload["p_upgraded_password_hash"] == "$argon2id$new-upgraded-hash"
    assert payload["p_session_id"] == "session-id"
    assert payload["p_session_token_hash"] != "raw-secret-token"
    assert "FullPlaintextSecret1" not in json.dumps(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [[], [{"login_applied": False}], {}, None])
async def test_finalize_login_fails_closed_without_fallback_writes(result) -> None:
    database = LoginRPCDB(result)
    finalized = await finalize_login_session(
        database,
        SimpleNamespace(session_days=365),
        {"id": "user-1"},
        login_request(),
        expected_password_hash="$argon2id$current-password-hash",
    )

    assert finalized is None
    assert len(database.calls) == 1


class RouteLoginDB:
    def __init__(self, user):
        self.user = user

    async def select_one(self, table, *_args, **_kwargs):
        return self.user if table == "users" else None


async def allow_rate_limit(*_args, **_kwargs) -> None:
    return None


@pytest.mark.asyncio
async def test_route_returns_generic_401_and_sets_no_cookie_when_hash_cas_loses(
    monkeypatch,
) -> None:
    user = {
        "id": "user-1",
        "email": "person@example.com",
        "password_hash": "$argon2id$current-password-hash",
        "is_verified": True,
    }
    cookie_calls = []

    async def rejected_finalize(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_routes, "db", RouteLoginDB(user))
    monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", allow_rate_limit)
    monkeypatch.setattr(auth_routes, "verify_password", lambda *_args: True)
    monkeypatch.setattr(auth_routes, "finalize_login_session", rejected_finalize)
    monkeypatch.setattr(
        auth_routes,
        "set_session_cookie",
        lambda *_args, **_kwargs: cookie_calls.append(True),
    )

    result = await auth_routes.login(
        LoginRequest(email="person@example.com", password="old-password"),
        login_request(),
        Response(),
    )

    assert result.status_code == 401
    assert json.loads(result.body) == {
        "success": False,
        "error": "Invalid email or password.",
        "code": "INVALID_CREDENTIALS",
    }
    assert cookie_calls == []
