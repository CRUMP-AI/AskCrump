from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import Request, Response

from backend.routes import auth as auth_routes
from backend.schemas import LoginRequest


class LoginDB:
    def __init__(self, user: dict | None) -> None:
        self.user = user

    async def select_one(self, *_args, **_kwargs):
        return self.user


async def allow_rate_limit(*_args, **_kwargs) -> None:
    return None


def login_request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "headers": [(b"host", b"www.askcrump.com")],
        "client": ("127.0.0.1", 12345),
    })


@pytest.mark.asyncio
async def test_login_rejections_return_stable_content_free_codes(monkeypatch) -> None:
    monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", allow_rate_limit)
    payload = LoginRequest(email="person@example.com", password="wrong-password")

    monkeypatch.setattr(auth_routes, "db", LoginDB(None))
    invalid = await auth_routes.login(payload, login_request(), Response())
    assert invalid.status_code == 401
    assert json.loads(invalid.body) == {
        "success": False,
        "error": "Invalid email or password.",
        "code": "INVALID_CREDENTIALS",
    }

    monkeypatch.setattr(
        auth_routes,
        "db",
        LoginDB({"password_hash": "safe-hash", "is_verified": False}),
    )
    monkeypatch.setattr(auth_routes, "verify_password", lambda *_args: True)
    unverified = await auth_routes.login(payload, login_request(), Response())
    assert unverified.status_code == 403
    body = json.loads(unverified.body)
    assert body["code"] == "EMAIL_VERIFICATION_REQUIRED"
    assert body["needsVerification"] is True


def test_login_failure_measurement_has_bounded_runtime_coverage() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "public" / "auth-controller.js").read_text(encoding="utf-8")
    verifier = (root / "scripts" / "verify-login-failure-classification.cjs").read_text(
        encoding="utf-8"
    )

    assert "function loginFailureReason(error)" in source
    for reason in (
        "credentials_rejected",
        "verification_required",
        "rate_limited",
        "session_establishment",
        "timeout",
        "offline",
        "request_failed",
    ):
        assert f"'{reason}'" in source
    assert "event.result?.error" not in source
    assert "login-measurement@example.test" in verifier
    assert "UNSTRUCTURED_PRIVATE_DETAIL" in verifier
