from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from backend.connected_app_multi_step import (
    ConnectedMultiStepError,
    ConnectedMultiStepPublicRecord,
    ConnectedMultiStepStatus,
)
from backend.http import register_exception_handlers
from backend.routes import connected_apps


OWNER = "00000000-0000-4000-8000-000000000001"
SESSION = "00000000-0000-4000-8000-000000000002"
LOOP = "00000000-0000-4000-8000-000000000003"
CHAT = "00000000-0000-4000-8000-000000000004"
TURN = "00000000-0000-4000-8000-000000000005"
APPROVAL = "00000000-0000-4000-8000-000000000006"
RESULT = "00000000-0000-4000-8000-000000000007"
NOW = datetime(2026, 11, 8, 21, 0, tzinfo=UTC)
HEADERS = {"X-Ask-Crump-Expected-Owner": OWNER}


class ReadyService:
    def __init__(self) -> None:
        self.calls = 0

    def require_ready(self) -> None:
        self.calls += 1


def task(
    *,
    status: ConnectedMultiStepStatus = ConnectedMultiStepStatus.WAITING_APPROVAL,
    revision: int = 4,
) -> ConnectedMultiStepPublicRecord:
    return ConnectedMultiStepPublicRecord(
        loop_id=LOOP,
        chat_id=CHAT,
        turn_id=TURN,
        status=status,
        current_step=2,
        max_steps=8,
        task_state_revision=revision,
        pending_approval_id=(
            APPROVAL if status is ConnectedMultiStepStatus.WAITING_APPROVAL else None
        ),
        last_result_reference_id=RESULT,
        expires_at=NOW + timedelta(minutes=20),
        updated_at=NOW,
    )


class Worker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def list_status(self, **kwargs):
        self.calls.append(("list", kwargs))
        return (task(),)

    async def owner_status(self, **kwargs):
        self.calls.append(("status", kwargs))
        return task()

    async def cancel_owner(self, **kwargs):
        self.calls.append(("cancel", kwargs))
        return task(status=ConnectedMultiStepStatus.CANCELLED, revision=5)


class Lease:
    async def release(self) -> None:
        return None


async def authenticated(_request, _db, _settings, **kwargs):
    assert kwargs == {
        "require_account": True,
        "require_expected_owner_header": True,
    }
    return SimpleNamespace(user={"id": OWNER}, session={"id": SESSION}, token="redacted")


def app() -> FastAPI:
    value = FastAPI()
    value.include_router(connected_apps.router)
    register_exception_handlers(value)
    return value


@pytest.fixture(autouse=True)
def route_graph(monkeypatch):
    service, worker = ReadyService(), Worker()
    monkeypatch.setattr(
        connected_apps.config,
        "connected_apps_release_candidate_source_released",
        lambda: True,
    )
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(connected_apps_enabled=True),
    )
    monkeypatch.setattr(connected_apps, "connected_app_service", service)
    monkeypatch.setattr(connected_apps, "connected_multi_step_worker", worker)
    monkeypatch.setattr(connected_apps, "authenticate_request", authenticated)

    async def acquire(_source):
        return Lease()

    monkeypatch.setattr(connected_apps, "_acquire_request_activation", acquire)
    return service, worker


@pytest.mark.asyncio
async def test_list_tasks_returns_only_the_safe_owner_projection(route_graph):
    service, worker = route_graph
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/connected-apps/tasks", headers=HEADERS)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json() == {"success": True, "tasks": [task().public()]}
    assert worker.calls == [("list", {"owner_id": OWNER, "limit": 50})]
    assert service.calls == 1
    for forbidden in (
        "sessionId",
        "messageId",
        "claimToken",
        "requestBinding",
        "resultBinding",
        "instruction",
    ):
        assert forbidden not in response.text


@pytest.mark.asyncio
async def test_one_task_status_is_exactly_owner_scoped(route_graph):
    _service, worker = route_graph
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(f"/api/connected-apps/tasks/{LOOP}", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"success": True, "task": task().public()}
    assert worker.calls == [("status", {"owner_id": OWNER, "loop_id": LOOP})]


@pytest.mark.asyncio
async def test_cancel_is_confirmation_and_exact_revision_bound(route_graph):
    _service, worker = route_graph
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        refused = await client.post(
            f"/api/connected-apps/tasks/{LOOP}/cancel",
            headers=HEADERS,
            json={"taskStateRevision": 4, "confirmed": False},
        )
        accepted = await client.post(
            f"/api/connected-apps/tasks/{LOOP}/cancel",
            headers=HEADERS,
            json={"taskStateRevision": 4, "confirmed": True},
        )
    assert refused.status_code == 400
    assert refused.json()["code"] == "CONNECTED_USER_ACTION_REQUIRED"
    assert accepted.status_code == 200
    assert accepted.json()["task"]["status"] == "cancelled"
    assert worker.calls == [
        (
            "cancel",
            {"owner_id": OWNER, "loop_id": LOOP, "expected_revision": 4},
        )
    ]


@pytest.mark.asyncio
async def test_separate_source_lock_hides_task_routes(monkeypatch, route_graph):
    service, worker = route_graph
    monkeypatch.setattr(connected_apps, "connected_multi_step_worker", None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get("/api/connected-apps/tasks", headers=HEADERS)
    assert response.status_code == 404
    assert response.json()["code"] == "CONNECTED_MULTI_STEP_NOT_RELEASED"
    assert worker.calls == []
    assert service.calls == 1


@pytest.mark.asyncio
async def test_unknown_owner_task_is_a_content_free_404(route_graph):
    _service, worker = route_graph

    async def missing(**kwargs):
        worker.calls.append(("status", kwargs))
        raise ConnectedMultiStepError("CONNECTED_MULTI_STEP_INVALID")

    worker.owner_status = missing  # type: ignore[method-assign]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        response = await client.get(f"/api/connected-apps/tasks/{LOOP}", headers=HEADERS)
    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "code": "CONNECTED_MULTI_STEP_INVALID",
        "retryable": False,
    }


@pytest.mark.asyncio
async def test_task_routes_reject_unknown_query_and_body_fields(route_graph):
    _service, worker = route_graph
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()), base_url="http://testserver"
    ) as client:
        query = await client.get(
            "/api/connected-apps/tasks?owner=someone-else",
            headers=HEADERS,
        )
        body = await client.post(
            f"/api/connected-apps/tasks/{LOOP}/cancel",
            headers=HEADERS,
            json={"taskStateRevision": 4, "confirmed": True, "extra": "field"},
        )
    assert query.status_code == body.status_code == 400
    assert query.json()["code"] == body.json()["code"] == "CONNECTED_INPUT_INVALID"
    assert worker.calls == []
