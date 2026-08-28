from __future__ import annotations

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
from backend.code_service import normalize_repo_source, sanitize_event_payload


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


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
