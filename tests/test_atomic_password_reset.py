from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from backend.routes import auth as auth_routes
from backend.schemas import ResetPasswordRequest
from backend.security import token_hash, verify_password


RAW_TOKEN = "reset-token-with-enough-entropy"
NEW_PASSWORD = "NewPassword123"


def request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/reset-password",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 50000),
    })


class ResetRpcDb:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple[str, dict, dict]] = []

    async def rpc(self, name, payload, **options):
        self.calls.append((name, dict(payload), dict(options)))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    async def select_one(self, *_args, **_kwargs):
        raise AssertionError("password reset must not pre-read mutable account state")

    async def update(self, *_args, **_kwargs):
        raise AssertionError("password reset must not split its database writes")


def run_reset(monkeypatch, database):
    monkeypatch.setattr(auth_routes, "db", database)
    monkeypatch.setattr(
        auth_routes,
        "enforce_auth_rate_limit",
        AsyncMock(return_value=None),
    )
    return asyncio.run(auth_routes.reset_password(
        ResetPasswordRequest(token=RAW_TOKEN, newPassword=NEW_PASSWORD),
        request(),
    ))


def test_reset_route_uses_one_non_retrying_atomic_rpc(monkeypatch):
    database = ResetRpcDb([{"reset_applied": True}])

    result = run_reset(monkeypatch, database)

    assert result == {
        "success": True,
        "message": "Password updated. Sign in with your new password.",
    }
    assert len(database.calls) == 1
    name, payload, options = database.calls[0]
    assert name == "consume_password_reset_v1"
    assert payload["p_token_hash"] == token_hash(RAW_TOKEN)
    assert payload["p_password_hash"] != NEW_PASSWORD
    assert verify_password(NEW_PASSWORD, payload["p_password_hash"])
    assert options == {}


@pytest.mark.parametrize("result", [[], {}, [{"reset_applied": False}], True])
def test_reset_route_keeps_invalid_or_replayed_tokens_generic(monkeypatch, result):
    database = ResetRpcDb(result)

    response = run_reset(monkeypatch, database)

    assert response.status_code == 400
    assert json.loads(response.body) == {
        "success": False,
        "error": "This reset link is invalid or expired.",
    }
    assert len(database.calls) == 1


def test_reset_route_does_not_fallback_after_database_failure(monkeypatch):
    database = ResetRpcDb(RuntimeError("database unavailable"))

    with pytest.raises(RuntimeError, match="database unavailable"):
        run_reset(monkeypatch, database)

    assert len(database.calls) == 1
