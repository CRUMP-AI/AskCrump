from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from backend.connected_app_read_surface import ConnectedOwnerReadResultError
from backend.http import register_exception_handlers
from backend.routes import connected_apps


OWNER = "10000000-0000-4000-8000-000000000001"
SESSION = "10000000-0000-4000-8000-000000000002"
ACTION = "10000000-0000-4000-8000-000000000003"
RESULT = "10000000-0000-4000-8000-000000000004"
HEADERS = {"X-Ask-Crump-Expected-Owner": OWNER}


def app() -> FastAPI:
    application = FastAPI()
    application.include_router(connected_apps.router)
    register_exception_handlers(application)
    return application


async def authenticated(_request, _db, _settings, **kwargs):
    assert kwargs == {
        "require_account": True,
        "require_expected_owner_header": True,
    }
    return SimpleNamespace(user={"id": OWNER}, session={"id": SESSION}, token="redacted")


class ReadyService:
    def __init__(self):
        self.calls = 0

    def require_ready(self):
        self.calls += 1


class Results:
    def __init__(self, error=None):
        self.calls = []
        self.error = error

    async def get(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return {
            "version": 1,
            "resultReferenceId": RESULT,
            "actionId": ACTION,
            "provider": "google",
            "resource": "mail",
            "action": "mail.get",
            "observedAt": "2026-11-08T06:20:00+00:00",
            "expiresAt": "2026-11-14T06:20:00+00:00",
            "items": [
                {
                    "kind": "mail_message",
                    "subject": "<img src=x onerror=alert(1)>",
                    "bodyText": "<script>alert(1)</script>",
                    "trustBoundary": "untrusted_external_data",
                }
            ],
            "itemCount": 1,
            "trustBoundary": "untrusted_external_data",
        }


@pytest.mark.asyncio
async def test_read_result_route_requires_release_and_injected_surface(monkeypatch):
    auth_calls = []

    async def forbidden(*_args, **_kwargs):
        auth_calls.append(True)
        raise AssertionError("auth must remain behind release lock")

    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=False))
    monkeypatch.setattr(connected_apps, "connected_app_service", ReadyService())
    monkeypatch.setattr(connected_apps, "connected_read_result_service", Results())
    monkeypatch.setattr(connected_apps, "authenticate_request", forbidden)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(f"/api/connected-apps/results/{RESULT}", headers=HEADERS)
    assert response.status_code == 404
    assert response.json()["code"] == "CONNECTED_APPS_NOT_RELEASED"
    assert response.headers["cache-control"] == "private, no-store"
    assert auth_calls == []


@pytest.mark.asyncio
async def test_read_result_route_is_owner_scoped_no_store_and_preserves_data_as_json(monkeypatch):
    ready = ReadyService()
    results = Results()
    monkeypatch.setattr(
        connected_apps.config,
        "connected_apps_release_candidate_source_released",
        lambda: True,
    )
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", ready)
    monkeypatch.setattr(connected_apps, "connected_read_result_service", results)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(f"/api/connected-apps/results/{RESULT}", headers=HEADERS)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["result"]["items"][0]["bodyText"] == (
        "<script>alert(1)</script>"
    )
    assert results.calls == [{"owner_id": OWNER, "result_reference_id": RESULT}]
    assert ready.calls == 1


@pytest.mark.asyncio
async def test_read_result_route_returns_fixed_expiry_without_content(monkeypatch):
    results = Results(
        ConnectedOwnerReadResultError("CONNECTED_READ_RESULT_EXPIRED", 410)
    )
    monkeypatch.setattr(
        connected_apps.config,
        "connected_apps_release_candidate_source_released",
        lambda: True,
    )
    monkeypatch.setattr(connected_apps, "settings", SimpleNamespace(connected_apps_enabled=True))
    monkeypatch.setattr(connected_apps, "connected_app_service", ReadyService())
    monkeypatch.setattr(connected_apps, "connected_read_result_service", results)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(f"/api/connected-apps/results/{RESULT}", headers=HEADERS)
    assert response.status_code == 410
    assert response.json() == {
        "success": False,
        "code": "CONNECTED_READ_RESULT_EXPIRED",
        "retryable": False,
    }
    assert "script" not in response.text
