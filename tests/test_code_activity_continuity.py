from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from backend.code_service import (
    ACTIVE_STATUSES,
    ACTIVITY_LIMIT,
    TERMINAL_STATUSES,
    CodeTaskService,
)


OWNER_ID = "00000000-0000-4000-8000-000000000091"
OTHER_OWNER_ID = "00000000-0000-4000-8000-000000000092"
PROJECT_ID = "00000000-0000-4000-8000-000000000093"
PUBLIC_ACTIVITY_KEYS = {
    "id",
    "projectId",
    "status",
    "createdAt",
    "updatedAt",
    "completedAt",
}


def _statuses(expression: str) -> set[str]:
    assert expression.startswith("in.(") and expression.endswith(")")
    return set(json.loads(f"[{expression[4:-1]}]"))


class ActivityDB:
    def __init__(self, rows: list[dict]):
        self.rows = [dict(row) for row in rows]
        self.calls: list[dict] = []

    async def select(self, table: str, **kwargs):
        assert table == "code_tasks"
        self.calls.append(dict(kwargs))
        filters = kwargs["filters"]
        owner = str(filters["user_id"]).removeprefix("eq.")
        status_filter = filters["status"]
        statuses = (
            {status_filter.removeprefix("eq.")}
            if status_filter.startswith("eq.")
            else _statuses(status_filter)
        )
        matching = [
            dict(row)
            for row in self.rows
            if row.get("user_id") == owner and row.get("status") in statuses
        ]
        if filters.get("payment_source") == "not.is.null":
            matching = [row for row in matching if row.get("payment_source") is not None]
        sort_column = str(kwargs["order"]).split(".", 1)[0]
        matching.sort(key=lambda row: str(row.get(sort_column) or ""), reverse=True)
        return matching[: int(kwargs["limit"])]


def _task(task_id: str, *, owner: str = OWNER_ID, status: str = "running", minute: int = 0):
    timestamp = f"2026-10-14T12:{minute:02d}:00+00:00"
    return {
        "id": task_id,
        "user_id": owner,
        "project_id": PROJECT_ID,
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "completed_at": timestamp if status in TERMINAL_STATUSES else None,
        "objective": "PRIVATE CUSTOMER OBJECTIVE",
        "source_repo_url": "https://github.com/private/repository.git",
        "result_summary": "PRIVATE RESULT",
        "patch": "PRIVATE PATCH",
        "usage_receipt": {"token": "PRIVATE RECEIPT"},
        "payment_source": "included",
        "lease_token": "PRIVATE LEASE",
        "dispatch_token": "PRIVATE DISPATCH",
    }


@pytest.mark.asyncio
async def test_activity_is_owner_scoped_bounded_and_content_free():
    rows = [
        _task("active-owner", status="running", minute=3),
        _task("prepared-only", status="queued", minute=6) | {"payment_source": None},
        _task("dispatched-queued", status="queued", minute=4),
        _task("terminal-owner", status="completed", minute=2),
        _task("active-other", owner=OTHER_OWNER_ID, status="running", minute=4),
        _task("terminal-other", owner=OTHER_OWNER_ID, status="failed", minute=5),
    ]
    database = ActivityDB(rows)
    service = CodeTaskService(database, SimpleNamespace())

    activity = await service.list_activity(user_id=OWNER_ID)

    assert [item["id"] for item in activity] == [
        "dispatched-queued",
        "active-owner",
        "terminal-owner",
    ]
    assert all(set(item) == PUBLIC_ACTIVITY_KEYS for item in activity)
    assert activity == [
        {
            "id": "dispatched-queued",
            "projectId": PROJECT_ID,
            "status": "queued",
            "createdAt": "2026-10-14T12:04:00+00:00",
            "updatedAt": "2026-10-14T12:04:00+00:00",
            "completedAt": None,
        },
        {
            "id": "active-owner",
            "projectId": PROJECT_ID,
            "status": "running",
            "createdAt": "2026-10-14T12:03:00+00:00",
            "updatedAt": "2026-10-14T12:03:00+00:00",
            "completedAt": None,
        },
        {
            "id": "terminal-owner",
            "projectId": PROJECT_ID,
            "status": "completed",
            "createdAt": "2026-10-14T12:02:00+00:00",
            "updatedAt": "2026-10-14T12:02:00+00:00",
            "completedAt": "2026-10-14T12:02:00+00:00",
        },
    ]
    serialized = repr(activity)
    for private in (
        "PRIVATE CUSTOMER OBJECTIVE",
        "github.com",
        "PRIVATE RESULT",
        "PRIVATE PATCH",
        "PRIVATE RECEIPT",
        "PRIVATE LEASE",
        "PRIVATE DISPATCH",
        OWNER_ID,
    ):
        assert private not in serialized

    assert len(database.calls) == 3
    for call in database.calls:
        assert call["columns"] == (
            "id,project_id,status,created_at,updated_at,completed_at,payment_source"
        )
        assert call["filters"]["user_id"] == f"eq.{OWNER_ID}"
        assert call["limit"] == ACTIVITY_LIMIT
    assert _statuses(database.calls[0]["filters"]["status"]) == ACTIVE_STATUSES - {"queued"}
    assert database.calls[1]["filters"]["status"] == "eq.queued"
    assert database.calls[1]["filters"]["payment_source"] == "not.is.null"
    assert _statuses(database.calls[2]["filters"]["status"]) == TERMINAL_STATUSES


@pytest.mark.asyncio
async def test_activity_keeps_freshest_status_deduplicates_and_never_exceeds_eighteen():
    active = [
        _task(f"active-{index:02d}", status="running", minute=index)
        for index in range(2)
    ]
    terminal = [
        _task(f"terminal-{index:02d}", status="completed", minute=index)
        for index in range(20)
    ]
    # Simulate a status transition racing the two reads. The newer terminal snapshot wins.
    terminal.append(_task("active-01", status="completed", minute=59))
    service = CodeTaskService(ActivityDB([*active, *terminal]), SimpleNamespace())

    activity = await service.list_activity(user_id=OWNER_ID)

    assert len(activity) == ACTIVITY_LIMIT == 18
    assert activity[0]["id"] == "active-00"
    transitioned = next(item for item in activity if item["id"] == "active-01")
    assert transitioned["status"] == "completed"
    assert len({item["id"] for item in activity}) == ACTIVITY_LIMIT
    assert sum(item["status"] == "completed" for item in activity) == 17


@pytest.mark.asyncio
async def test_prepared_drafts_cannot_hide_older_running_work():
    prepared = [
        _task(f"draft-{index:02d}", status="queued", minute=index)
        | {"payment_source": None}
        for index in range(18)
    ]
    running = _task("older-running", status="running", minute=0)
    service = CodeTaskService(ActivityDB([*prepared, running]), SimpleNamespace())

    activity = await service.list_activity(user_id=OWNER_ID)

    assert [item["id"] for item in activity] == ["older-running"]


@pytest.mark.asyncio
async def test_activity_endpoint_authenticates_and_returns_only_service_projection(
    monkeypatch,
):
    from backend.routes import code as code_routes

    calls: list[tuple] = []

    async def authenticate(request, database, settings):
        calls.append((request, database, settings))
        return SimpleNamespace(user={"id": OWNER_ID})

    class ActivityService:
        async def list_activity(self, *, user_id: str):
            assert user_id == OWNER_ID
            return [
                {
                    "id": "task-1",
                    "projectId": PROJECT_ID,
                    "status": "queued",
                    "createdAt": "2026-10-14T12:00:00+00:00",
                    "updatedAt": "2026-10-14T12:00:00+00:00",
                    "completedAt": None,
                }
            ]

    monkeypatch.setattr(code_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(code_routes, "code_tasks", ActivityService())

    response = await code_routes.list_code_activity(object())

    assert response == {
        "success": True,
        "activity": [
            {
                "id": "task-1",
                "projectId": PROJECT_ID,
                "status": "queued",
                "createdAt": "2026-10-14T12:00:00+00:00",
                "updatedAt": "2026-10-14T12:00:00+00:00",
                "completedAt": None,
            }
        ],
    }
    assert len(calls) == 1
    assert calls[0][1:] == (code_routes.db, code_routes.settings)
    endpoint = next(
        route for route in code_routes.router.routes if route.path == "/api/code/activity"
    )
    assert endpoint.methods == {"GET"}
