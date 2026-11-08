from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from backend import config
from backend.auth_service import AuthenticationError
from backend.http import register_exception_handlers
from backend.routes import browser


def _app() -> FastAPI:
    application = FastAPI()
    application.include_router(browser.router)
    register_exception_handlers(application)
    return application


def test_environment_cannot_bypass_browser_source_release_lock(monkeypatch):
    monkeypatch.setenv("CRUMP_ENABLE_BROWSER_WORKSPACE", "true")
    assert config.AUTONOMOUS_CRUMP_BROWSER_PUBLIC_RELEASED is False
    assert config.browser_workspace_environment_released() is False


def test_browser_release_requires_source_and_operator_switch(monkeypatch):
    monkeypatch.setattr(config, "AUTONOMOUS_CRUMP_BROWSER_PUBLIC_RELEASED", True)
    monkeypatch.delenv("CRUMP_ENABLE_BROWSER_WORKSPACE", raising=False)
    assert config.browser_workspace_environment_released() is False
    monkeypatch.setenv("CRUMP_ENABLE_BROWSER_WORKSPACE", "true")
    assert config.browser_workspace_environment_released() is True


def test_browser_boundary_is_registered_and_fail_closed():
    application = open("backend/application.py", encoding="utf-8").read()
    route = open("backend/routes/browser.py", encoding="utf-8").read()
    source = open("backend/config.py", encoding="utf-8").read()

    assert "application.include_router(browser.router)" in application
    assert "AUTONOMOUS_CRUMP_BROWSER_PUBLIC_RELEASED = False" in source
    assert "require_account=True" in route
    assert "require_expected_owner_header=True" in route
    assert '"code": "BROWSER_NOT_RELEASED"' in route
    assert "browser_workspace_environment_released()" in route
    assert "and _runtime_ready()" in route


@pytest.mark.asyncio
async def test_status_requires_account_and_exact_owner(monkeypatch):
    seen: dict[str, object] = {}

    async def reject(_request, _db, _settings, **kwargs):
        seen.update(kwargs)
        raise AuthenticationError(
            "The account precondition did not match.",
            status_code=409,
            code="AUTH_OWNER_MISMATCH",
        )

    monkeypatch.setattr(browser, "authenticate_request", reject)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/browser/status")

    assert response.status_code == 409
    assert response.json()["code"] == "AUTH_OWNER_MISMATCH"
    assert seen == {
        "require_account": True,
        "require_expected_owner_header": True,
    }


@pytest.mark.asyncio
async def test_status_is_content_free_unreleased_and_no_store(monkeypatch):
    calls: list[str] = []

    async def authenticate(_request, _db, _settings, **kwargs):
        calls.append("authenticate")
        assert kwargs == {
            "require_account": True,
            "require_expected_owner_header": True,
        }
        return SimpleNamespace(user={"id": "00000000-0000-4000-8000-000000000001"})

    monkeypatch.setattr(browser, "authenticate_request", authenticate)
    monkeypatch.setattr(browser, "browser_workspace_environment_released", lambda: False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/browser/status",
            headers={
                "X-Ask-Crump-Expected-Owner": "00000000-0000-4000-8000-000000000001",
            },
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"success": True, "released": False}
    assert calls == ["authenticate"]


@pytest.mark.asyncio
async def test_task_routes_refuse_without_reading_request_body(monkeypatch):
    async def authenticate(_request, _db, _settings, **_kwargs):
        return SimpleNamespace(user={"id": "00000000-0000-4000-8000-000000000001"})

    monkeypatch.setattr(browser, "authenticate_request", authenticate)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/browser/tasks",
            headers={
                "X-Ask-Crump-Expected-Owner": "00000000-0000-4000-8000-000000000001",
                "Content-Type": "application/json",
            },
            content=b'{"private":"content must stay unread"}',
        )

    assert response.status_code == 404
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["code"] == "BROWSER_NOT_RELEASED"
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_request_receipt_route_is_authenticated_content_free_and_no_store(monkeypatch):
    async def authenticate(_request, _db, _settings, **_kwargs):
        return SimpleNamespace(user={"id": "00000000-0000-4000-8000-000000000001"})

    monkeypatch.setattr(browser, "authenticate_request", authenticate)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/browser/requests/00000000-0000-4000-8000-000000000099",
            headers={
                "X-Ask-Crump-Expected-Owner": "00000000-0000-4000-8000-000000000001",
            },
        )

    assert response.status_code == 404
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "success": False,
        "error": "Browser workspace is not released.",
        "code": "BROWSER_NOT_RELEASED",
    }
