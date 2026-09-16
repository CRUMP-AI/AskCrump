from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from backend.routes import auth as auth_routes
from backend.schemas import LoginRequest, ResetPasswordRequest
from backend.security import hash_password, token_hash


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_FLOOR = 20260916160711
RESET_TOKEN = "inbox-owned-reset-token"


def auth_request(path: str) -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (b"host", b"www.askcrump.com"),
            (b"user-agent", b"atomic-auth-generation-test"),
        ],
        "client": ("127.0.0.1", 12345),
    })


async def allow_rate_limit(*_args, **_kwargs) -> None:
    return None


class AtomicAuthDB:
    """Deterministic model of the two user-row-serialized database RPCs."""

    def __init__(self, *, ordering: str) -> None:
        self.ordering = ordering
        self.user = {
            "id": "user-1",
            "email": "owner@example.com",
            "password_hash": hash_password("OldPassword1"),
            "is_verified": True,
            "auth_generation": 0,
            "password_reset_token_hash": token_hash(RESET_TOKEN),
            "password_reset_expires": "2099-01-01T00:00:00+00:00",
            "subscription_tier": "free",
            "subscription_status": "inactive",
        }
        self.sessions: list[dict] = []
        self._user_lock = asyncio.Lock()
        self.persist_entered = asyncio.Event()
        self.session_persisted = asyncio.Event()
        self.reset_entered = asyncio.Event()
        self.allow_persist_return = asyncio.Event()

    @staticmethod
    def _eq_value(raw_filter):
        if isinstance(raw_filter, str) and raw_filter.startswith("eq."):
            return raw_filter[3:]
        return raw_filter

    async def select_one(self, table, *, filters=None, **_kwargs):
        if table == "user_settings":
            return {}
        assert table == "users"
        filters = filters or {}
        if "email" in filters and self._eq_value(filters["email"]) != self.user["email"]:
            return None
        if "id" in filters and self._eq_value(filters["id"]) != self.user["id"]:
            return None
        return deepcopy(self.user)

    async def update(self, table, payload, *, filters, **_kwargs):
        assert table == "users"
        if self._eq_value(filters.get("id")) != self.user["id"]:
            return []
        if "auth_generation" in filters and int(
            self._eq_value(filters["auth_generation"])
        ) != self.user["auth_generation"]:
            return []
        self.user.update(deepcopy(payload))
        return [deepcopy(self.user)]

    async def rpc(self, function_name, payload):
        if function_name == "persist_auth_session":
            self.persist_entered.set()
            if self.ordering == "reset-first":
                await asyncio.wait_for(self.allow_persist_return.wait(), timeout=5)
            async with self._user_lock:
                if (
                    payload["p_user_id"] != self.user["id"]
                    or payload["p_expected_auth_generation"]
                    != self.user["auth_generation"]
                ):
                    return None
                session = {
                    "id": payload["p_session_id"],
                    "user_id": payload["p_user_id"],
                    "token_hash": payload["p_token_hash"],
                    "auth_generation": self.user["auth_generation"],
                    "expires_at": payload["p_expires_at"],
                    "revoked_at": None,
                }
                self.sessions.append(session)
                self.session_persisted.set()
                if self.ordering == "login-first":
                    await asyncio.wait_for(self.allow_persist_return.wait(), timeout=5)
                return deepcopy(session)

        assert function_name == "consume_password_reset"
        self.reset_entered.set()
        async with self._user_lock:
            if (
                payload["p_presented_token_hash"]
                != self.user["password_reset_token_hash"]
                or self.user["password_reset_expires"] <= payload["p_now"]
            ):
                return None
            self.user.update({
                "password_hash": payload["p_new_password_hash"],
                "auth_generation": self.user["auth_generation"] + 1,
                "password_reset_token_hash": None,
                "password_reset_expires": None,
                "verification_token_hash": None,
                "verification_token_expires": None,
            })
            for session in self.sessions:
                if session["revoked_at"] is None:
                    session["revoked_at"] = payload["p_now"]
            return {
                "id": self.user["id"],
                "auth_generation": self.user["auth_generation"],
            }


def install_route_fakes(monkeypatch, database: AtomicAuthDB) -> list[str]:
    cookies: list[str] = []
    monkeypatch.setattr(auth_routes, "db", database)
    monkeypatch.setattr(auth_routes, "enforce_auth_rate_limit", allow_rate_limit)
    monkeypatch.setattr(
        auth_routes,
        "set_session_cookie",
        lambda _response, raw_token, _request: cookies.append(raw_token),
    )
    return cookies


@pytest.mark.asyncio
async def test_login_rpc_wins_then_reset_rpc_revokes_that_session(monkeypatch) -> None:
    database = AtomicAuthDB(ordering="login-first")
    cookies = install_route_fakes(monkeypatch, database)

    login_task = asyncio.create_task(
        auth_routes.login(
            LoginRequest(email=database.user["email"], password="OldPassword1"),
            auth_request("/api/auth/login"),
            Response(),
        )
    )
    await asyncio.wait_for(database.session_persisted.wait(), timeout=5)
    reset_task = asyncio.create_task(
        auth_routes.reset_password(
            ResetPasswordRequest(token=RESET_TOKEN, newPassword="NewPassword2"),
            auth_request("/api/auth/reset-password"),
        )
    )
    await asyncio.wait_for(database.reset_entered.wait(), timeout=5)
    database.allow_persist_return.set()
    login_result, reset_result = await asyncio.gather(login_task, reset_task)

    assert login_result["success"] is True
    assert reset_result["success"] is True
    assert cookies
    assert database.user["auth_generation"] == 1
    assert len(database.sessions) == 1
    assert database.sessions[0]["auth_generation"] == 0
    assert database.sessions[0]["revoked_at"] is not None


@pytest.mark.asyncio
async def test_reset_rpc_wins_before_stale_login_rpc_and_no_session_or_cookie_survives(
    monkeypatch,
) -> None:
    database = AtomicAuthDB(ordering="reset-first")
    cookies = install_route_fakes(monkeypatch, database)

    login_task = asyncio.create_task(
        auth_routes.login(
            LoginRequest(email=database.user["email"], password="OldPassword1"),
            auth_request("/api/auth/login"),
            Response(),
        )
    )
    await asyncio.wait_for(database.persist_entered.wait(), timeout=5)
    reset_result = await auth_routes.reset_password(
        ResetPasswordRequest(token=RESET_TOKEN, newPassword="NewPassword2"),
        auth_request("/api/auth/reset-password"),
    )
    database.allow_persist_return.set()
    login_result = await login_task

    assert reset_result["success"] is True
    assert isinstance(login_result, JSONResponse)
    assert login_result.status_code == 401
    assert json.loads(login_result.body) == {
        "success": False,
        "error": "Invalid email or password.",
        "code": "INVALID_CREDENTIALS",
    }
    assert database.user["auth_generation"] == 1
    assert database.sessions == []
    assert cookies == []


def test_atomic_auth_migration_contract_and_private_execution_boundary() -> None:
    migrations = list((ROOT / "migrations").glob("*_atomic_auth_generation.sql"))
    assert len(migrations) == 1
    migration = migrations[0]
    assert int(migration.name.split("_", 1)[0]) > MIGRATION_FLOOR
    sql = migration.read_text(encoding="utf-8").lower()

    assert "alter table public.users" in sql
    assert "alter table public.sessions" in sql
    assert sql.count("add column if not exists auth_generation") == 2
    assert "create or replace function public.persist_auth_session(" in sql
    assert "create or replace function public.consume_password_reset(" in sql
    assert sql.count("security invoker") == 2
    assert sql.count("set search_path = ''") == 2
    assert "security definer" not in sql

    persist = sql[
        sql.index("create or replace function public.persist_auth_session(") :
        sql.index("create or replace function public.consume_password_reset(")
    ]
    reset = sql[
        sql.index("create or replace function public.consume_password_reset(") :
        sql.index("revoke all on function public.persist_auth_session(")
    ]
    assert "account.auth_generation = p_expected_auth_generation" in persist
    assert "for update;" in persist
    assert "insert into public.sessions" in persist
    assert "auth_generation" in persist
    assert "on conflict (device_id) do update" in persist
    assert "ranked_active.session_rank > 20" in persist

    assert "account.auth_generation + 1" in reset
    assert "account.password_reset_token_hash = p_presented_token_hash" in reset
    assert "account.password_reset_expires > p_now" in reset
    assert "update public.sessions as active" in reset
    assert "active.revoked_at is null" in reset
    assert "when account.is_verified then account.full_name else null" in reset

    for function_name in ("persist_auth_session", "consume_password_reset"):
        assert f"revoke all on function public.{function_name}" in sql
        assert f"grant execute on function public.{function_name}" in sql
    assert sql.count("from public, anon, authenticated") == 2
    assert sql.count("to service_role") == 2
    assert "to anon" not in sql
    assert "to authenticated" not in sql


def test_all_production_session_creation_uses_generation_rpc() -> None:
    auth_service = (ROOT / "backend" / "auth_service.py").read_text(encoding="utf-8")
    routes = (ROOT / "backend" / "routes" / "auth.py").read_text(encoding="utf-8")

    assert "'persist_auth_session'" in auth_service
    assert "'p_expected_auth_generation'" in auth_service
    assert "db.insert('sessions'" not in auth_service
    assert "db.upsert('sessions'" not in auth_service
    assert routes.count("await create_session(") == 2
    assert "'consume_password_reset'" in routes
    assert "await db.update(\n        'sessions',\n        {'revoked_at': now}," not in routes[
        routes.index("@router.post('/reset-password')") :
        routes.index("@router.post('/resend-verification')")
    ]
