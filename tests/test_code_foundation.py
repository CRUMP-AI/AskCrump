from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import app
from backend.code_runner import (
    CodeRunnerError,
    CrumpCodeRunner,
    normalize_workspace_path,
    redact_sensitive_text,
    validate_verification_command,
)
from backend.code_service import (
    CodeApprovalExpiredError,
    CodeTaskExpiredError,
    CodeTaskService,
    normalize_repo_source,
    sanitize_event_payload,
    timestamp_has_passed,
)


ROOT = Path(__file__).resolve().parents[1]
CODE_USER_ID = "00000000-0000-4000-8000-000000000071"
CODE_PROJECT_ID = "00000000-0000-4000-8000-000000000072"
CODE_TASK_ID = "00000000-0000-4000-8000-000000000073"
CODE_APPROVAL_ID = "00000000-0000-4000-8000-000000000074"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class CodeLifecycleDB:
    def __init__(self, task: dict, approval: dict | None = None):
        self.task = dict(task)
        self.approval = dict(approval) if approval else None
        self.events: list[dict] = []

    @staticmethod
    def _matches(row: dict, filters: dict) -> bool:
        for key, expression in filters.items():
            operator, expected = str(expression).split(".", 1)
            actual = row.get(key)
            if operator == "eq" and str(actual) != expected:
                return False
            if operator == "gt" and _timestamp(str(actual)) <= _timestamp(expected):
                return False
            if operator == "lte" and _timestamp(str(actual)) > _timestamp(expected):
                return False
        return True

    async def select_one(self, table, **kwargs):
        row = self.task if table == "code_tasks" else self.approval
        if not row or not self._matches(row, kwargs.get("filters") or {}):
            return None
        return dict(row)

    async def select(self, table, **_kwargs):
        if table == "code_task_events":
            return [dict(item) for item in self.events]
        if table == "code_task_approvals" and self.approval:
            return [dict(self.approval)]
        if table == "code_tasks":
            return [dict(self.task)]
        return []

    async def update(self, table, payload, **kwargs):
        row = self.task if table == "code_tasks" else self.approval
        if not row or not self._matches(row, kwargs.get("filters") or {}):
            return []
        row.update(payload)
        return [dict(row)]

    async def insert(self, table, payload):
        if table == "code_task_events":
            event = {"id": len(self.events) + 1, **payload}
            self.events.append(event)
            return [dict(event)]
        raise AssertionError(f"Unexpected insert into {table}")


def code_task(*, status: str, expires_at: str) -> dict:
    return {
        "id": CODE_TASK_ID,
        "user_id": CODE_USER_ID,
        "project_id": CODE_PROJECT_ID,
        "status": status,
        "expires_at": expires_at,
        "failure_code": None,
    }


def code_approval(*, expires_at: str) -> dict:
    return {
        "id": CODE_APPROVAL_ID,
        "task_id": CODE_TASK_ID,
        "user_id": CODE_USER_ID,
        "project_id": CODE_PROJECT_ID,
        "action_type": "extended_runtime",
        "status": "pending",
        "title": "Continue longer",
        "details": "Review the bounded extension.",
        "expires_at": expires_at,
    }


def test_public_github_source_is_canonical_and_bounded():
    assert normalize_repo_source("https://github.com/openai/codex") == (
        "https://github.com/openai/codex.git",
        None,
    )
    assert normalize_repo_source("https://github.com/openai/codex.git", "main") == (
        "https://github.com/openai/codex.git",
        "main",
    )
    for invalid in (
        "http://github.com/openai/codex",
        "https://token@github.com/openai/codex",
        "https://github.com/openai/codex/tree/main",
        "https://gitlab.com/openai/codex",
        "https://github.com/openai/codex?token=secret",
    ):
        with pytest.raises(ValueError):
            normalize_repo_source(invalid)
    with pytest.raises(ValueError):
        normalize_repo_source("https://github.com/openai/codex", "../secret")


def test_workspace_paths_reject_escape_secrets_and_binary_files():
    assert normalize_workspace_path("src/main.py") == "src/main.py"
    assert normalize_workspace_path("src", require_text=False) == "src"
    for invalid in ("../secret.py", "/etc/passwd", ".git/config", ".env", "image.png"):
        with pytest.raises(ValueError):
            normalize_workspace_path(invalid)


def test_verification_policy_has_no_shell_install_publish_or_source_writes():
    assert validate_verification_command("python3", ["-m", "pytest", "-q"]) == (
        "python3",
        ["-m", "pytest", "-q"],
    )
    assert validate_verification_command("git", ["diff", "--stat"])[0] == "git"
    assert validate_verification_command("npm", ["run", "lint"])[0] == "npm"
    for command, args in (
        ("bash", ["-lc", "echo nope"]),
        ("git", ["push"]),
        ("npm", ["install"]),
        ("npm", ["publish"]),
        ("ruff", ["check", "--fix"]),
        ("python3", ["script.py"]),
    ):
        with pytest.raises(ValueError):
            validate_verification_command(command, args)


def test_model_and_audit_outputs_redact_secrets_and_drop_arbitrary_payloads():
    fake_stripe_key = "sk_" + "live_" + "abcdefghijklmnopqrstuvwxyz"
    redacted = redact_sensitive_text(
        f"OPENAI_API_KEY=super-secret\nSTRIPE={fake_stripe_key}"
    )
    assert "super-secret" not in redacted
    assert "sk_live_" not in redacted
    assert sanitize_event_payload(
        {"tool": "read_file", "path": "src/main.py", "prompt": "private", "output": "private"}
    ) == {"tool": "read_file", "path": "src/main.py"}


def test_code_routes_are_authenticated_server_surfaces():
    routes = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }
    assert ("GET", "/api/projects/{project_id}/code/tasks") in routes
    assert ("POST", "/api/projects/{project_id}/code/tasks") in routes
    assert ("GET", "/api/code/tasks/{task_id}") in routes
    assert ("POST", "/api/code/tasks/{task_id}/run") in routes
    assert ("POST", "/api/code/tasks/{task_id}/cancel") in routes
    assert ("POST", "/api/code/tasks/{task_id}/approvals/{approval_id}") in routes
    source = read("backend/routes/code.py")
    assert "authenticate_request(request, db, settings)" in source
    assert "features.consume(" in source
    assert 'request.headers.get("x-vercel-oidc-token")' in source
    assert 'payload.get("confirmed") is not True' in source
    assert '"RUN_CONFIRMATION_REQUIRED"' in source
    assert source.index("ensure_not_expired(task)") < source.index("features.consume(")


def test_code_schema_is_private_audited_and_deny_all_by_contract():
    migration = read("migrations/20260827145025_crump_code_foundation.sql")
    hardening = read("migrations/20260827161713_crump_code_privilege_hardening.sql")
    for table in ("code_tasks", "code_task_events", "code_task_approvals"):
        assert f"alter table public.{table} enable row level security" in migration
        assert f"revoke all on table public.{table} from public, anon, authenticated" in migration
        assert f"revoke all on table public.{table} from service_role" in migration
        assert f"revoke all on table public.{table} from service_role" in hardening
    assert "network_policy = 'deny_all'" in migration
    assert "grant all on table public.code_tasks to service_role" in migration
    assert "grant select, insert on table public.code_task_events to service_role" in hardening
    assert "grant select, insert, update on table public.code_task_approvals to service_role" in hardening
    assert "generated always as identity" in migration
    assert "approval.requested" in migration and "publish" in migration


def test_code_audit_foreign_keys_remain_indexed_for_bounded_cleanup():
    migration = read("migrations/20260829200000_code_task_foreign_key_indexes.sql")
    for table in ("code_task_events", "code_task_approvals"):
        for column in ("user_id", "project_id"):
            assert f"on public.{table}({column})" in migration


def test_sandbox_execution_is_ephemeral_bounded_and_has_no_environment():
    source = read("backend/code_runner.py")
    assert "NetworkPolicy.deny_all()" in source
    assert "persistent=False" in source
    assert "env={}" in source
    assert "destroy=True" in source
    assert "vcpus=2, memory=4096" in source
    assert "MAX_PATCH = 200_000" in source
    assert "await self._ensure_not_cancelled(task)" in source


@pytest.mark.asyncio
async def test_cancelled_code_task_stops_before_the_next_expensive_step():
    class CancelledTaskService:
        async def get(self, **_kwargs):
            return {"status": "cancelled"}

    runner = CrumpCodeRunner(SimpleNamespace(), CancelledTaskService())
    with pytest.raises(CodeRunnerError) as exc:
        await runner._ensure_not_cancelled({"id": "task-id", "user_id": "user-id"})
    assert exc.value.code == "CODE_TASK_CANCELLED"

    with pytest.raises(CodeRunnerError) as run_exc:
        await runner.run({"id": "task-id", "user_id": "user-id"}, oidc_token="unused")
    assert run_exc.value.code == "CODE_TASK_CANCELLED"


@pytest.mark.asyncio
async def test_expired_code_task_is_terminal_before_claim_or_charge():
    database = CodeLifecycleDB(
        code_task(status="queued", expires_at="2000-01-01T00:00:00+00:00")
    )
    service = CodeTaskService(database, SimpleNamespace())

    task = await service.get(
        user_id=CODE_USER_ID,
        task_id=CODE_TASK_ID,
        include_history=True,
    )

    assert task["status"] == "cancelled"
    assert task["failure_code"] == "CODE_TASK_EXPIRED"
    assert task["completed_at"]
    assert [event["event_type"] for event in task["events"]] == ["task.cancelled"]
    assert task["events"][0]["payload"] == {
        "failureCode": "CODE_TASK_EXPIRED",
        "status": "cancelled",
    }
    with pytest.raises(CodeTaskExpiredError):
        await service.claim(task)
    assert not any(event["event_type"] == "task.claimed" for event in database.events)


@pytest.mark.asyncio
async def test_code_task_list_reconciles_expiry_before_rendering():
    database = CodeLifecycleDB(
        code_task(status="queued", expires_at="2000-01-01T00:00:00+00:00")
    )

    async def get_project(_user_id, _project_id):
        return {"id": CODE_PROJECT_ID}

    service = CodeTaskService(database, SimpleNamespace(get=get_project))
    tasks = await service.list(user_id=CODE_USER_ID, project_id=CODE_PROJECT_ID)

    assert tasks[0]["status"] == "cancelled"
    assert tasks[0]["failure_code"] == "CODE_TASK_EXPIRED"


@pytest.mark.asyncio
async def test_expired_code_approval_is_recorded_and_cancels_the_waiting_task():
    database = CodeLifecycleDB(
        code_task(status="awaiting_approval", expires_at="2999-01-01T00:00:00+00:00"),
        code_approval(expires_at="2000-01-01T00:00:00+00:00"),
    )
    service = CodeTaskService(database, SimpleNamespace())

    task = await service.get(
        user_id=CODE_USER_ID,
        task_id=CODE_TASK_ID,
        include_history=True,
    )

    assert task["status"] == "cancelled"
    assert task["failure_code"] == "CODE_APPROVAL_EXPIRED"
    assert task["approvals"][0]["status"] == "expired"
    assert [event["event_type"] for event in task["events"]] == [
        "approval.decided",
        "task.cancelled",
    ]
    assert task["events"][0]["payload"]["decision"] == "expired"


@pytest.mark.asyncio
async def test_expired_approval_cannot_win_a_late_decision_race():
    task = code_task(status="awaiting_approval", expires_at="2999-01-01T00:00:00+00:00")
    database = CodeLifecycleDB(
        task,
        code_approval(expires_at="2000-01-01T00:00:00+00:00"),
    )
    service = CodeTaskService(database, SimpleNamespace())

    with pytest.raises(CodeApprovalExpiredError):
        await service.decide_approval(
            task=task,
            approval_id=CODE_APPROVAL_ID,
            decision="approved",
        )

    assert database.approval["status"] == "expired"
    assert database.task["status"] == "cancelled"
    assert database.task["failure_code"] == "CODE_APPROVAL_EXPIRED"


def test_code_expiry_comparison_is_timezone_aware_and_fail_safe():
    reference = datetime(2026, 8, 30, tzinfo=timezone.utc)
    assert timestamp_has_passed("2026-08-29T23:59:59Z", now=reference)
    assert not timestamp_has_passed("2026-08-30T00:00:01+00:00", now=reference)
    assert not timestamp_has_passed("not-a-timestamp", now=reference)


def test_crump_code_is_professional_and_cost_guarded():
    policy = read("backend/feature_service.py")
    config = read("backend/config.py")
    requirements = read("requirements.txt")
    assert '"code_workspace"' in policy
    assert '"professional"' in policy
    assert '12,' in policy
    assert "code_workspace_enabled" in config
    assert "CODE_MAX_DURATION_SECONDS" in config
    assert "vercel==0.10.0" in requirements
