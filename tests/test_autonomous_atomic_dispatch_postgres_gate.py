from __future__ import annotations

import ast
import ipaddress
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "verify_autonomous_atomic_dispatch_postgres.py"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DOCUMENTATION = ROOT / "docs" / "AUTONOMOUS_CRUMP_ATOMIC_DISPATCH_POSTGRES_GATE.md"
REQUIREMENTS = ROOT / "requirements-postgres-test.txt"


def test_autonomous_atomic_postgres_harness_targets_exact_migration_and_probes() -> None:
    source = HARNESS.read_text(encoding="utf-8")

    assert 'MIGRATION_TARGET = "20260916231500_autonomous_crump_atomic_dispatch.sql"' in source
    assert 'DATABASE_PREFIX = "askcrump_autonomous_atomic_"' in source
    assert "verify_schema_and_privileges(test_url)" in source
    for probe in (
        "probe_not_ready_paths",
        "probe_receipt_replay_and_worker",
        "probe_same_task_concurrency",
        "probe_last_included_slot_concurrency",
        "probe_credit_replay",
        "probe_credit_denials",
        "probe_post_charge_rollbacks",
        "probe_internal_tier",
    ):
        assert f"def {probe}(" in source
        assert f"{probe}(admin, test_url)" in source
    assert "ThreadPoolExecutor" in source
    assert "threading.Barrier" in source
    assert "injected post-charge task update failure" in source
    assert "public.claim_code_task" in source
    assert "public.dispatch_code_task" in source
    assert 'execute_grantees == ["postgres", "service_role"]' in source


def test_autonomous_atomic_postgres_gate_requires_owned_cluster_attestation() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    documentation = " ".join(DOCUMENTATION.read_text(encoding="utf-8").lower().split())
    main = source[source.index("def main()") :]

    assert 'ATTESTATION_ENV = "ASKCRUMP_DISPOSABLE_POSTGRES_ACK"' in source
    assert 'ATTESTATION_VALUE = "I_OWN_THIS_DISPOSABLE_LOCAL_CLUSTER"' in source
    assert "validate_disposable_attestation()" in main
    assert main.index("validate_disposable_attestation()") < main.index(
        "validate_admin_connection(admin_url)"
    )
    assert "server_address is not None and is_loopback_host(str(server_address))" in source
    assert "GITHUB_ACTIONS" not in source
    assert "not a loopback proxy or tunnel" in source
    assert "cannot detect a loopback proxy or tunnel" in documentation
    assert "database_created = True" in source
    assert source.index("database_created = True") > source.index(
        "create database {} template template0"
    )


def test_autonomous_atomic_postgres_loopback_parser_is_fail_closed() -> None:
    source = HARNESS.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "is_loopback_host"
    )
    namespace = {"ipaddress": ipaddress}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(HARNESS), "exec"), namespace)
    is_loopback_host = namespace["is_loopback_host"]

    for value in ("localhost", "127.0.0.1", "127.0.0.1/32", "::1", "::1/128", "[::1]"):
        assert is_loopback_host(value) is True
    for value in (
        None,
        "",
        "127.0.0.1/8",
        "127.0.0.1,10.0.0.1",
        "10.0.0.1",
        "10.0.0.1/32",
        "example.com",
    ):
        assert is_loopback_host(value) is False


def test_autonomous_atomic_postgres_ci_owns_loopback_postgres_15() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    job = workflow[workflow.index("  autonomous-atomic-postgres:") : workflow.index("\n  python:")]

    assert "services:" not in job
    assert "docker run --detach --rm" in job
    assert "--network host" in job
    assert "postgres:15" in job
    assert "-c listen_addresses=127.0.0.1" in job
    assert "-c port=55433" in job
    assert "127.0.0.1:55433/postgres" in job
    assert "ASKCRUMP_DISPOSABLE_POSTGRES_ACK: I_OWN_THIS_DISPOSABLE_LOCAL_CLUSTER" in job
    assert "if: always()" in job
    assert "docker stop askcrump-autonomous-atomic-postgres || true" in job
    assert REQUIREMENTS.read_text(encoding="utf-8") == "psycopg[binary]==3.3.5\n"


def test_autonomous_atomic_postgres_evidence_is_honest_about_unexecuted_gate() -> None:
    documentation = " ".join(DOCUMENTATION.read_text(encoding="utf-8").lower().split())

    assert "source-only validation is not database evidence" in documentation
    assert "not yet executed" in documentation
    assert "no production" in documentation
    assert "ci-only mirror or pull request" in documentation
