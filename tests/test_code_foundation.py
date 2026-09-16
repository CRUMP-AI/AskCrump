from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app import app
from conftest import iter_effective_routes
from backend.code_runner import (
    CodeRunnerError,
    CrumpCodeRunner,
    SANDBOX_ENV,
    normalize_workspace_path,
    redact_sensitive_text,
    validate_verification_command,
)
from backend.code_service import (
    CodeApprovalExpiredError,
    CodeSourcePreflightError,
    CodeTaskExpiredError,
    CodeTaskService,
    normalize_repo_source,
    resolve_public_source_revision,
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
            if operator == "is" and expected == "null":
                if actual is not None:
                    return False
                continue
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
    assert validate_verification_command(
        "python3",
        ["-m", "pytest", "-q"],
        allow_project_execution=True,
    ) == (
        "python3",
        ["-m", "pytest", "-q"],
    )
    assert validate_verification_command("git", ["diff", "--stat"])[0] == "git"
    assert validate_verification_command(
        "npm", ["run", "lint"], allow_project_execution=True
    )[0] == "npm"
    for command, args in (
        ("python3", ["-m", "pytest", "-q"]),
        ("python3", ["-m", "unittest", "-q"]),
        ("pytest", ["-q"]),
        ("npm", ["run", "lint"]),
        ("go", ["test", "./..."]),
        ("cargo", ["check", "--locked"]),
        ("make", ["test"]),
    ):
        with pytest.raises(ValueError, match="explicit verification choice"):
            validate_verification_command(command, args)
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


@pytest.mark.asyncio
async def test_prepared_task_persists_immutable_verification_choice():
    class RecordingDB:
        def __init__(self):
            self.calls = []

        async def rpc(self, name, payload, *, retry_transient=False):
            self.calls.append((name, dict(payload), retry_transient))
            return {
                "created": True,
                "task": {
                    "id": CODE_TASK_ID,
                    "user_id": payload["p_user_id"],
                    "project_id": payload["p_project_id"],
                    "mode": payload["p_mode"],
                    "verification_policy": payload["p_verification_policy"],
                },
            }

    database = RecordingDB()
    projects = SimpleNamespace(
        get=AsyncMock(return_value={"id": CODE_PROJECT_ID, "user_id": CODE_USER_ID})
    )
    service = CodeTaskService(database, projects)

    task = await service.create(
        user_id=CODE_USER_ID,
        project_id=CODE_PROJECT_ID,
        objective="Fix the bounded parser",
        mode="implement",
        repo_url="https://github.com/openai/codex",
        verification_policy="project_checks",
    )

    assert task["verification_policy"] == "project_checks"
    name, payload, retry = database.calls[0]
    assert name == "create_code_task_guarded"
    assert payload["p_verification_policy"] == "project_checks"
    assert retry is True
    with pytest.raises(ValueError, match="Plan-only"):
        await service.create(
            user_id=CODE_USER_ID,
            project_id=CODE_PROJECT_ID,
            objective="Plan the parser fix",
            mode="plan",
            repo_url="https://github.com/openai/codex",
            verification_policy="project_checks",
        )


@pytest.mark.asyncio
async def test_failed_verification_is_preserved_and_cannot_transition_ready():
    class RecordingService:
        def __init__(self):
            self.current = {
                "id": CODE_TASK_ID,
                "user_id": CODE_USER_ID,
                "project_id": CODE_PROJECT_ID,
                "status": "provisioning",
                "mode": "implement",
                "usage_receipt": {"eventId": "usage-1"},
            }
            self.events = []

        async def get(self, **_kwargs):
            return dict(self.current)

        async def transition(self, item, target, **kwargs):
            self.current = {**item, **kwargs.get("changes", {}), "status": target}
            self.events.append((kwargs.get("event_type"), kwargs.get("event_payload")))
            return dict(self.current)

        async def append_event(self, _task, event_type, payload):
            self.events.append((event_type, payload))

    class FailingWorkspace:
        def __init__(self):
            self.verification = [
                {
                    "command": "python3 -m pytest -q",
                    "returnCode": 1,
                    "stdout": "1 failed",
                    "stderr": "assertion failed",
                }
            ]

        async def base_revision(self):
            return "a" * 40

        async def list_files(self, _prefix):
            return "src/main.py"

        async def changed_paths(self):
            return ["src/main.py"]

        async def syntax_verify(self, _paths):
            return None

        async def patch(self):
            return "diff --git a/src/main.py b/src/main.py"

    service = RecordingService()
    runner = CrumpCodeRunner(SimpleNamespace(), service)
    runner._agent_loop = AsyncMock(return_value="Implemented the requested change.")
    result = await runner._run_in_workspace(service.current, FailingWorkspace())

    assert result["status"] == "failed"
    assert result["failure_code"] == "CODE_VERIFICATION_FAILED"
    assert result["payment_source"] == "refund_pending"
    assert result["verification"][0]["returnCode"] == 1
    assert result["result_patch"].startswith("diff --git")
    assert "Verification failed" in result["result_summary"]
    assert ("task.completed", {"changedFiles": ["src/main.py"], "status": "completed"}) not in service.events
    assert service.events[-1][0] == "task.failed"
    assert service.events[-1][1]["failureCode"] == "CODE_VERIFICATION_FAILED"


@pytest.mark.asyncio
async def test_public_source_preflight_pins_exact_sha_before_charge_without_live_network():
    sha = "b" * 40

    class FixtureResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"sha": sha}

    class FixtureClient:
        def __init__(self):
            self.requests = []

        async def get(self, url, **kwargs):
            self.requests.append((url, kwargs))
            return FixtureResponse()

    client = FixtureClient()
    resolved = await resolve_public_source_revision(
        "https://github.com/octocat/Hello-World.git",
        "feature/safe-ref",
        client=client,
    )
    assert resolved == sha
    assert client.requests[0][0].endswith("/commits/feature%2Fsafe-ref")
    assert "Authorization" not in client.requests[0][1]["headers"]

    database = CodeLifecycleDB(
        {
            **code_task(status="queued", expires_at="2999-01-01T00:00:00+00:00"),
            "source_ref": "feature/safe-ref",
            "base_revision": None,
        }
    )
    service = CodeTaskService(database, SimpleNamespace())
    pinned = await service.pin_source_revision(database.task, revision=resolved)
    assert pinned["source_ref"] == sha
    assert pinned["base_revision"] == sha
    assert service.pinned_source_revision(pinned) == sha


@pytest.mark.asyncio
async def test_public_source_preflight_fails_unmetered_on_invalid_revision_shape():
    class InvalidResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"sha": "moving-branch"}

    class InvalidClient:
        async def get(self, _url, **_kwargs):
            return InvalidResponse()

    with pytest.raises(CodeSourcePreflightError) as exc:
        await resolve_public_source_revision(
            "https://github.com/octocat/Hello-World",
            "main",
            client=InvalidClient(),
        )
    assert "No run was started or charged" in str(exc.value)


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
        for route in iter_effective_routes(app)
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
    cron_source = read("backend/routes/manuscripts.py")
    assert "authenticate_request(request, db, settings)" in source
    assert "features.authorize(" in source
    assert "code_tasks.accept_run(" in source
    assert "features.consume(" not in source
    assert "features.refund(" not in source
    assert 'request.headers.get("x-vercel-oidc-token")' in cron_source
    assert 'payload.get("confirmed") is not True' in source
    assert '"RUN_CONFIRMATION_REQUIRED"' in source
    assert source.index("ensure_not_expired(task)") < source.index("features.authorize(")
    assert source.index("features.authorize(") < source.index("code_tasks.accept_run(")


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


def test_sandbox_execution_is_ephemeral_bounded_and_injects_only_fixed_safety_environment():
    source = read("backend/code_runner.py")
    assert "NetworkPolicy.deny_all()" in source
    assert "persistent=False" in source
    assert "env=SANDBOX_ENV" in source
    assert SANDBOX_ENV == {
        "NO_COLOR": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": "/tmp/autonomous-crump-pycache",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    assert not any("KEY" in name or "TOKEN" in name or "SECRET" in name for name in SANDBOX_ENV)
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
async def test_worker_stops_when_its_private_lease_is_replaced():
    class ReclaimedTaskService:
        async def get(self, **_kwargs):
            return {"status": "provisioning", "lease_token": "new-owner"}

    runner = CrumpCodeRunner(SimpleNamespace(), ReclaimedTaskService())
    with pytest.raises(CodeRunnerError) as exc:
        await runner._ensure_not_cancelled(
            {"id": "task-id", "user_id": "user-id", "lease_token": "old-owner"}
        )
    assert exc.value.code == "CODE_TASK_LEASE_LOST"


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
    assert "CODE_WORKSPACE_PUBLIC_RELEASED = False" in config
    assert "CODE_WORKSPACE_PUBLIC_RELEASED\n            and _bool" in config
    assert "CODE_MAX_DURATION_SECONDS" in config
    assert "vercel==0.10.0" in requirements


def test_environment_switch_cannot_bypass_the_code_source_release_lock(monkeypatch):
    from backend import config

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CRUMP_ENABLE_CODE_WORKSPACE", "true")
    config.get_settings.cache_clear()
    try:
        settings = config.get_settings()
        assert config.CODE_WORKSPACE_PUBLIC_RELEASED is False
        assert settings.code_workspace_enabled is False
    finally:
        config.get_settings.cache_clear()


def test_every_code_entry_point_uses_the_authoritative_settings_lock():
    entry_points = (
        "backend/routes/code.py",
        "backend/routes/features.py",
        "backend/code_worker.py",
    )

    for path in entry_points:
        source = read(path)
        assert "settings.code_workspace_enabled" in source
        assert "CRUMP_ENABLE_CODE_WORKSPACE" not in source
        assert "CODE_WORKSPACE_PUBLIC_RELEASED" not in source
