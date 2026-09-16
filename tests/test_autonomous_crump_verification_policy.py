from pathlib import Path

from backend.code_runner import _tool_definitions


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_project_execution_tool_is_absent_until_explicitly_allowed():
    built_in_only = _tool_definitions("implement", allow_project_checks=False)
    project_checks = _tool_definitions("implement", allow_project_checks=True)

    assert "run_verification" not in {item["name"] for item in built_in_only}
    assert "run_verification" in {item["name"] for item in project_checks}
    assert "run_verification" not in {
        item["name"] for item in _tool_definitions("plan", allow_project_checks=True)
    }


def test_verification_policy_migration_is_bounded_and_defaults_closed():
    migration = read(
        "migrations/20260916233000_autonomous_crump_verification_policy.sql"
    ).lower()
    assert "verification_policy text not null default 'syntax_only'" in migration
    assert "check (verification_policy in ('syntax_only', 'project_checks'))" in migration
    assert "public.code_tasks.verification_policy" in migration
    assert "keep_code_task_verification_policy_immutable" in migration
    assert "before update of verification_policy on public.code_tasks" in migration
    assert "new.verification_policy is distinct from old.verification_policy" in migration
    assert "from public, anon, authenticated, service_role" in migration


def test_runner_and_api_use_the_durable_task_policy():
    runner = read("backend/code_runner.py")
    service = read("backend/code_service.py")
    routes = read("backend/routes/code.py")

    assert 'task.get("verification_policy")' in runner
    assert "allow_project_execution=self.allow_project_checks" in runner
    assert '"p_verification_policy": normalized_verification_policy' in service
    assert 'payload.get("verificationPolicy")' in routes
    assert '"verification_policy"' not in service.split("hidden = {", 1)[1].split("}", 1)[0]
