from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_autonomous_crump_activation",
    ROOT / "scripts" / "verify_autonomous_crump_activation.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def valid_live_evidence(revision: str) -> dict:
    evidence = {
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "sourceRevision": revision,
        "fixture": "octocat-hello-world-pinned",
        "maxCostCents": 1,
        "liveBenchmark": {
            "providerRuns": 8,
            "holdoutCases": 4,
            "passRate": 0.9,
            "meanScore": 90,
            "repeatable": True,
        },
    }
    evidence.update({name: True for name in MODULE.REQUIRED_LIVE_BOOLEANS})
    return evidence


def test_source_gate_requires_closed_release_lock_and_review_console():
    checks = MODULE.source_checks()
    assert checks
    assert all(check.passed for check in checks), [check.name for check in checks if not check.passed]


def test_live_evidence_contract_accepts_only_complete_current_exact_revision_receipt():
    revision = "a" * 40
    checks = MODULE.live_evidence_checks(valid_live_evidence(revision), revision)
    assert all(check.passed for check in checks)


def test_live_evidence_contract_fails_closed_for_revision_drift_missing_gate_and_secret_field():
    revision = "a" * 40
    evidence = valid_live_evidence("b" * 40)
    evidence["sandboxDestroyed"] = False
    evidence["oidcToken"] = "not-a-real-token"
    checks = {check.name: check.passed for check in MODULE.live_evidence_checks(evidence, revision)}
    assert checks["live_evidence_contains_no_secret_fields"] is False
    assert checks["live_evidence_is_current_and_source_bound"] is False
    assert checks["live_safety_and_operator_boundaries"] is False


def test_live_evidence_contract_rejects_weak_or_unrepeatable_benchmark():
    revision = "a" * 40
    evidence = valid_live_evidence(revision)
    evidence["liveBenchmark"].update(
        {"providerRuns": 7, "holdoutCases": 3, "passRate": 0.89, "meanScore": 89, "repeatable": False}
    )
    checks = {check.name: check.passed for check in MODULE.live_evidence_checks(evidence, revision)}
    assert checks["repeatable_live_quality"] is False


def test_activation_receipt_path_cannot_escape_the_output_boundary(tmp_path):
    try:
        MODULE._write_receipt(tmp_path / "receipt.json", {"safe": True})
    except ValueError as exc:
        assert "output/autonomous-crump-activation" in str(exc)
    else:
        raise AssertionError("Receipt path escaped the bounded output directory.")
