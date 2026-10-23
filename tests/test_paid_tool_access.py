from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from backend.feature_service import POLICIES, PROJECT_LIMITS
from backend.paid_tool_access import has_paid_tool_access, paid_tool_required
from backend.routes import code as code_routes
from backend.routes import files as file_routes
from backend.routes import library as library_routes
from backend.routes import manuscripts as manuscript_routes
from backend.routes import media as media_routes
from backend.routes import projects as project_routes


OWNER_ID = "00000000-0000-0000-0000-000000000001"
RESOURCE_ID = "00000000-0000-0000-0000-000000000002"


def _user(**changes):
    user = {
        "id": OWNER_ID,
        "is_guest": False,
        "subscription_tier": "free",
        "subscription_status": "inactive",
        "internal_tier": None,
    }
    user.update(changes)
    return user


def _payload(response) -> dict:
    return json.loads(response.body.decode("utf-8"))


def _run_immediate(coroutine):
    """Drive route coroutines whose mocked awaits complete without I/O."""
    try:
        coroutine.send(None)
    except StopIteration as stopped:
        return stopped.value
    raise AssertionError("The focused route test unexpectedly attempted external I/O.")


def _authenticate_as(user):
    async def authenticate(*_args, **kwargs):
        assert kwargs.get("require_account") is True
        return SimpleNamespace(user=user, session={"id": "session-one"})

    return authenticate


class UnreadableRequest:
    headers: dict[str, str] = {}

    async def json(self):
        raise AssertionError("A denied tool must not inspect or execute its request.")


class JsonRequest:
    headers: dict[str, str] = {}

    def __init__(self, payload: dict):
        self.payload = payload

    async def json(self):
        return self.payload


@pytest.mark.parametrize(
    ("user", "allowed"),
    [
        (_user(), False),
        (_user(subscription_tier="professional", subscription_status="inactive"), False),
        (_user(subscription_tier="professional", subscription_status="active"), True),
        (_user(subscription_tier="enterprise", subscription_status="trialing"), True),
        (
            _user(
                subscription_tier="professional",
                subscription_status="canceling",
                subscription_current_period_end=(
                    datetime.now(timezone.utc) + timedelta(days=1)
                ).isoformat(),
            ),
            True,
        ),
        (_user(internal_tier="professional"), True),
        (
            _user(
                is_guest=True,
                subscription_tier="professional",
                subscription_status="active",
                internal_tier="professional",
            ),
            False,
        ),
    ],
)
def test_paid_tool_access_uses_current_server_entitlement(user, allowed):
    assert has_paid_tool_access(user) is allowed


def test_paid_tool_response_is_a_non_credit_subscription_gate():
    response = paid_tool_required(_user(), label="Project creation")

    assert response is not None
    assert response.status_code == 403
    assert _payload(response) == {
        "success": False,
        "error": "Project creation requires a verified Professional plan.",
        "message": "Project creation requires a verified Professional plan.",
        "code": "SUBSCRIPTION_REQUIRED",
        "accountRequired": False,
        "upgradeRequired": True,
        "requiredTier": "professional",
    }
    assert paid_tool_required(
        _user(subscription_tier="professional", subscription_status="active")
    ) is None


def test_all_advanced_feature_policies_and_projects_require_paid_access():
    for code in (
        "research",
        "image",
        "image_edit",
        "visual_analysis",
        "video",
        "manuscript_draft",
        "manuscript_blueprint",
        "kdp_export",
        "code_workspace",
        "premium_voice",
    ):
        assert POLICIES[code].minimum_tier in {"professional", "enterprise"}
        assert POLICIES[code].included_daily["free"] == 0
    assert PROJECT_LIMITS["free"] == 0


@pytest.mark.parametrize(
    ("route_module", "route_call", "expected_label"),
    [
        (file_routes, lambda request: file_routes.sign_upload(request), "File uploads"),
        (project_routes, lambda request: project_routes.create_project(request), "Project creation"),
        (library_routes, lambda request: library_routes.import_book(request), "Book imports"),
        (
            manuscript_routes,
            lambda request: manuscript_routes.create_manuscript(RESOURCE_ID, request),
            "Manuscript creation",
        ),
        (media_routes, lambda request: media_routes.create_video(request), "Video generation"),
        (
            code_routes,
            lambda request: code_routes.decide_code_approval(
                RESOURCE_ID, OWNER_ID, request
            ),
            "Code execution",
        ),
    ],
)
def test_free_accounts_are_stopped_before_advanced_mutation(
    monkeypatch, route_module, route_call, expected_label
):
    monkeypatch.setattr(
        route_module,
        "authenticate_request",
        _authenticate_as(_user()),
    )
    request = (
        JsonRequest({"decision": "approved"})
        if route_module is code_routes
        else JsonRequest({"name": "Free Project"})
        if route_module is project_routes
        else UnreadableRequest()
    )

    response = _run_immediate(route_call(request))
    payload = _payload(response)

    assert response.status_code == 403
    assert payload["code"] == "SUBSCRIPTION_REQUIRED"
    assert payload["requiredTier"] == "professional"
    assert expected_label in payload["error"]


def test_downgraded_accounts_keep_owned_file_delete_access(monkeypatch):
    calls: list[tuple[str, str]] = []

    class Files:
        async def soft_delete(self, *, user_id, file_id):
            calls.append((user_id, file_id))

    monkeypatch.setattr(file_routes, "authenticate_request", _authenticate_as(_user()))
    monkeypatch.setattr(file_routes, "files", Files())

    response = _run_immediate(file_routes.delete(RESOURCE_ID, object()))

    assert response == {"success": True}
    assert calls == [(OWNER_ID, RESOURCE_ID)]


def test_downgraded_accounts_keep_project_archive_and_run_cancel_access(monkeypatch):
    project_calls: list[tuple[str, str]] = []
    cancel_calls: list[tuple[str, str]] = []

    class Projects:
        async def archive(self, user_id, project_id):
            project_calls.append((user_id, project_id))

    class Manuscripts:
        async def cancel_run(self, *, user_id, run_id):
            cancel_calls.append((user_id, run_id))
            return {"id": run_id, "status": "cancelled"}

        def public_run(self, row):
            return {"id": row["id"], "status": row["status"]}

    monkeypatch.setattr(project_routes, "authenticate_request", _authenticate_as(_user()))
    monkeypatch.setattr(project_routes, "projects", Projects())
    monkeypatch.setattr(manuscript_routes, "authenticate_request", _authenticate_as(_user()))
    monkeypatch.setattr(manuscript_route := manuscript_routes, "manuscripts", Manuscripts())

    archived = _run_immediate(project_routes.archive_project(RESOURCE_ID, object()))
    cancelled = _run_immediate(
        manuscript_route.cancel_manuscript_run(RESOURCE_ID, object())
    )

    assert archived == {"success": True}
    assert cancelled == {
        "success": True,
        "run": {"id": RESOURCE_ID, "status": "cancelled"},
    }
    assert project_calls == [(OWNER_ID, RESOURCE_ID)]
    assert cancel_calls == [(OWNER_ID, RESOURCE_ID)]


def test_downgraded_account_can_reject_and_cancel_a_pending_code_approval(monkeypatch):
    calls: list[tuple[str, str]] = []

    class CodeTasks:
        async def get(self, *, user_id, task_id):
            assert (user_id, task_id) == (OWNER_ID, RESOURCE_ID)
            return {"id": task_id, "status": "awaiting_approval"}

        async def decide_approval(self, *, task, approval_id, decision):
            assert task["id"] == RESOURCE_ID
            assert approval_id == OWNER_ID
            calls.append(("decision", decision))
            return {"id": approval_id, "status": "rejected"}

        async def cancel(self, task):
            calls.append(("cancel", task["id"]))
            return {**task, "status": "cancelled"}

    monkeypatch.setattr(code_routes, "authenticate_request", _authenticate_as(_user()))
    monkeypatch.setattr(code_routes, "code_tasks", CodeTasks())

    response = _run_immediate(
        code_routes.decide_code_approval(
            RESOURCE_ID,
            OWNER_ID,
            JsonRequest({"decision": "rejected"}),
        )
    )

    assert response["success"] is True
    assert response["approval"]["status"] == "rejected"
    assert response["task"]["status"] == "cancelled"
    assert calls == [("decision", "rejected"), ("cancel", RESOURCE_ID)]
