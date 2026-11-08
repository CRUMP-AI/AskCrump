from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from backend import config
from backend.auth_service import AuthenticationError
from backend.http import register_exception_handlers
from backend.routes import connected_apps


def test_environment_cannot_bypass_connected_app_source_release_lock(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CRUMP_ENABLE_CONNECTED_APPS", "true")
    config.get_settings.cache_clear()
    try:
        settings = config.get_settings()
        assert config.CONNECTED_APPS_PUBLIC_RELEASED is False
        assert settings.connected_apps_enabled is False
    finally:
        config.get_settings.cache_clear()


@pytest.mark.parametrize(
    "missing",
    ("preview", "public", "multi_step"),
)
def test_complete_operator_release_requires_all_three_source_pins(
    monkeypatch, missing
):
    monkeypatch.setattr(config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)
    mapping = {
        "preview": "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED",
        "public": "CONNECTED_APPS_PUBLIC_RELEASED",
        "multi_step": "CONNECTED_MULTI_STEP_SOURCE_RELEASED",
    }
    monkeypatch.setattr(config, mapping[missing], False)
    monkeypatch.setenv("CRUMP_ENABLE_CONNECTED_APPS", "true")
    assert config.connected_apps_release_candidate_source_released() is False
    assert config.connected_apps_environment_released() is False


def test_complete_operator_release_enables_only_the_exact_lockset(monkeypatch):
    monkeypatch.setattr(config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)
    monkeypatch.setenv("CRUMP_ENABLE_CONNECTED_APPS", "true")
    assert config.connected_apps_release_candidate_source_released() is True
    assert config.connected_apps_environment_released() is True


def test_connected_app_route_is_registered_behind_authoritative_settings_lock():
    application = open("backend/application.py", encoding="utf-8").read()
    route = open("backend/routes/connected_apps.py", encoding="utf-8").read()
    config_source = open("backend/config.py", encoding="utf-8").read()

    assert "application.include_router(connected_apps.router)" in application
    assert "application.include_router(connected_apps.cron_router)" in application
    assert "CONNECTED_APPS_PUBLIC_RELEASED = False" in config_source
    assert "CONNECTED_MULTI_STEP_SOURCE_RELEASED = False" in config_source
    assert "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED = False" in config_source
    assert "connected_apps_enabled=connected_apps_environment_released()" in config_source
    assert "return connected_apps_release_candidate_source_released() and _bool(" in config_source
    assert '"enabled": False' in route
    assert '"status": "not_released"' in route
    assert '"status": "available"' not in route
    assert "CRUMP_ENABLE_CONNECTED_APPS" not in route
    assert "config.connected_apps_release_candidate_source_released() is not True" in route
    assert "hmac.compare_digest" in route
    assert "require_account=True" in route
    assert "require_expected_owner_header=True" in route


def _status_app() -> FastAPI:
    application = FastAPI()
    application.include_router(connected_apps.router)
    register_exception_handlers(application)
    return application


@pytest.mark.asyncio
async def test_status_requires_an_account_and_exact_owner_header(monkeypatch):
    seen: dict[str, object] = {}

    async def reject(_request, _db, _settings, **kwargs):
        seen.update(kwargs)
        raise AuthenticationError(
            "The account precondition did not match.",
            status_code=409,
            code="AUTH_OWNER_MISMATCH",
        )

    monkeypatch.setattr(connected_apps, "authenticate_request", reject)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_status_app()),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/connected-apps/status")

    assert response.status_code == 409
    assert response.json()["code"] == "AUTH_OWNER_MISMATCH"
    assert seen == {
        "require_account": True,
        "require_expected_owner_header": True,
    }


@pytest.mark.asyncio
async def test_status_is_content_free_disabled_and_has_no_side_effects(monkeypatch):
    calls: list[str] = []

    async def authenticate(_request, _db, _settings, **kwargs):
        calls.append("authenticate")
        assert kwargs == {
            "require_account": True,
            "require_expected_owner_header": True,
        }
        return SimpleNamespace(user={"id": "00000000-0000-4000-8000-000000000001"})

    monkeypatch.setattr(connected_apps, "authenticate_request", authenticate)
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(connected_apps_enabled=False),
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_status_app()),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/connected-apps/status",
            headers={"X-Ask-Crump-Expected-Owner": "00000000-0000-4000-8000-000000000001"},
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {
        "success": True,
        "enabled": False,
        "status": "not_released",
        "providers": [],
        "capabilities": [],
    }
    serialized = response.text.casefold()
    for forbidden in (
        "token",
        "secret",
        "credential",
        "scope",
        "email",
        "calendar",
        "oauth",
    ):
        assert forbidden not in serialized
    assert calls == ["authenticate"]
