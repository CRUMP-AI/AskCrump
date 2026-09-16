"""Fail-closed, no-spend activation gate for the Autonomous Crump source candidate."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {"token", "key", "secret", "password", "credential", "authorization"}
)
REQUIRED_LIVE_BOOLEANS = (
    "publicFeatureDisabledDuringDrill",
    "oidcProjectScopeVerified",
    "denyAllNetworkVerified",
    "emptyEnvironmentVerified",
    "sandboxDestroyed",
    "cancellationVerified",
    "expiryVerified",
    "refundVerified",
    "monitoringVisible",
    "rollbackVerified",
    "unitCostEnvelopeApproved",
    "operatorActivationApproved",
)

# A JSON document supplied beside this script is evidence input, not trust. These
# checked-in decisions intentionally keep public activation impossible until a
# separate, reviewed implementation verifies an owner-controlled signature and
# records the release decision in source.
TRUSTED_LIVE_ATTESTATION_VERIFIER_IMPLEMENTED = False
PUBLIC_ACTIVATION_SOURCE_DECISION_APPROVED = False
PUBLIC_RELEASE_CONTROLS_EXPECTED_CLOSED = True
KNOWN_P0_ACTIVATION_HOLDS = (
    "atomic exactly-once charge, allowance, dispatch, crash recovery, and owner-only compensation",
    "per-user and global concurrency plus daily model and Sandbox budget circuit breakers",
    "protected live end-to-end cancellation, refund, destruction, latency, cost, and rollback proof",
)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def _run_json(command: list[str], *, cwd: Path = ROOT) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{Path(command[0]).name} failed with exit {result.returncode}."
        )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"{Path(command[0]).name} returned no receipt.")
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{Path(command[0]).name} returned an invalid receipt.") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{Path(command[0]).name} returned an invalid receipt shape.")
    return value


def _git_command(*args: str) -> subprocess.CompletedProcess[str] | None:
    candidates = [
        os.getenv("GIT_EXECUTABLE", "").strip(),
        "git",
    ]
    for executable in candidates:
        if not executable:
            continue
        try:
            result = subprocess.run(
                [executable, *args],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            continue
        return result
    return None


def _git_revision() -> str:
    result = _git_command("rev-parse", "HEAD")
    if result is not None:
        revision = result.stdout.strip().lower()
        if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", revision):
            return revision
    return "unavailable"


def _git_tree_clean() -> bool:
    result = _git_command("status", "--porcelain=v1", "--untracked-files=all")
    return bool(result is not None and result.returncode == 0 and not result.stdout.strip())


def source_checks() -> list[Check]:
    config = _read("backend/config.py")
    routes = _read("backend/routes/code.py")
    worker = _read("backend/code_worker.py")
    loader = _read("public/crump-code-loader.js")
    workspace = _read("public/crump-code-5.9.35.js")
    matrix = _read("scripts/verify-browser-control-matrix.mjs")
    code_runner = _read("backend/code_runner.py")
    code_service = _read("backend/code_service.py")
    verification_migration = _read(
        "migrations/20260916233000_autonomous_crump_verification_policy.sql"
    )
    return [
        Check(
            "source_release_lock_closed",
            "CODE_WORKSPACE_PUBLIC_RELEASED = False" in config,
            "The checked-in public release lock must remain false in this candidate.",
        ),
        Check(
            "two_independent_compute_stops",
            "CODE_WORKSPACE_PUBLIC_RELEASED"
            in config
            and "_bool(os.getenv('CRUMP_ENABLE_CODE_WORKSPACE'), False)" in config,
            "Source lock and operator environment switch must both gate compute.",
        ),
        Check(
            "shared_authoritative_setting",
            "settings.code_workspace_enabled" in routes
            and "settings.code_workspace_enabled" in worker
            and "CRUMP_ENABLE_CODE_WORKSPACE" not in routes
            and "CRUMP_ENABLE_CODE_WORKSPACE" not in worker,
            "Routes and worker must consume the shared setting without an environment bypass.",
        ),
        Check(
            "autonomous_review_console",
            "AUTONOMOUS CRUMP · PRIVATE PREVIEW" in workspace
            and "function renderProgress(container, task)" in workspace
            and "function renderPatch(container, task)" in workspace
            and "Connection paused. The private worker continues safely" in workspace,
            "The candidate must expose durable progress, reconnect truth, checks, and file-scoped diff review.",
        ),
        Check(
            "disabled_lazy_load_preserved",
            "if (!configured(data))" in loader
            and "await loadWorkspace(data);" in loader
            and "verify-autonomous-crump-review.cjs" in matrix
            and "verify-code-lazy-load.cjs" in matrix,
            "Disabled accounts must not load the full workspace; both browser proofs stay inventory-locked.",
        ),
        Check(
            "owner_authorized_verification_policy",
            "verification_policy text not null default 'syntax_only'"
            in verification_migration
            and "('syntax_only', 'project_checks')" in verification_migration
            and "before update of verification_policy on public.code_tasks"
            in verification_migration
            and "new.verification_policy is distinct from old.verification_policy"
            in verification_migration
            and "allow_project_execution=self.allow_project_checks" in code_runner
            and '_tool_definitions(mode, allow_project_checks=allow_project_checks)'
            in code_runner
            and "Plan-only tasks cannot execute repository checks." in code_service
            and "Repository tests are executable code." in workspace
            and "I authorize bounded repository tests/checks" in workspace,
            "Repository-owned executable checks must default closed and require one durable owner choice before the model can request them or receive bounded output.",
        ),
    ]


def offline_runtime_checks() -> tuple[list[Check], dict[str, Any], dict[str, Any]]:
    smoke = _run_json(
        [sys.executable, str(ROOT / "scripts/run_crump_code_sandbox_smoke.py"), "--dry-run"]
    )
    private_output = ROOT / "output" / "crump-code-benchmark"
    private_output.mkdir(parents=True, exist_ok=True)
    nonce = uuid4().hex
    artifact_name = f"autonomous-readiness-{nonce}-artifact.json"
    report_name = f"autonomous-readiness-{nonce}-report.json"
    artifact = private_output / artifact_name
    report = private_output / report_name
    try:
        benchmark = _run_json(
            [
                sys.executable,
                str(ROOT / "scripts/run_crump_code_offline_benchmark.py"),
                "--artifact",
                artifact_name,
                "--report",
                report_name,
            ]
        )
    finally:
        artifact.unlink(missing_ok=True)
        report.unlink(missing_ok=True)
    smoke_safe = all(
        (
            smoke.get("success") is True,
            smoke.get("mode") == "dry-run",
            smoke.get("liveRunAuthorized") is False,
            smoke.get("networkPolicy") == "deny-all",
            smoke.get("modelCalls") == 0,
            smoke.get("databaseWrites") == 0,
            smoke.get("customerData") is False,
            smoke.get("injectedEnvironmentVariables") == 5,
            smoke.get("injectedSensitiveEnvironmentVariables") == 0,
            smoke.get("publicFeatureMustRemainDisabled") is True,
            smoke.get("destroy") is True,
        )
    )
    benchmark_safe = all(
        (
            benchmark.get("passed") is True,
            benchmark.get("case_count") == 4,
            benchmark.get("passed_case_count") == 4,
            float(benchmark.get("mean_score") or 0) >= 90,
        )
    )
    return (
        [
            Check(
                "zero_network_zero_spend_sandbox_dry_run",
                smoke_safe,
                "Dry receipt must prove zero model calls, writes, customer data, sensitive environment injection, and live authorization.",
            ),
            Check(
                "fixed_offline_orchestration_benchmark",
                benchmark_safe,
                "All four fixed cases must pass the real orchestration path at or above the 90-point threshold.",
            ),
        ],
        smoke,
        benchmark,
    )


def _contains_forbidden_evidence_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z]", "", str(key).lower())
            if any(word in normalized for word in FORBIDDEN_EVIDENCE_KEYS):
                return True
            if _contains_forbidden_evidence_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_evidence_key(item) for item in value)
    return False


def _finite_number(value: Any, *, minimum: float = 0.0) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < minimum or parsed in (float("inf"), float("-inf")) or parsed != parsed:
        return None
    return parsed


def live_evidence_checks(evidence: dict[str, Any], revision: str) -> list[Check]:
    benchmark = evidence.get("liveBenchmark")
    benchmark = benchmark if isinstance(benchmark, dict) else {}
    recorded_at = str(evidence.get("recordedAt") or "")
    try:
        recorded = datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
        if recorded.tzinfo is None:
            recorded = recorded.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - recorded.astimezone(timezone.utc)).total_seconds() / 3600
        fresh = 0 <= age_hours <= 72
    except ValueError:
        fresh = False
    provider_runs = int(benchmark.get("providerRuns") or 0)
    measured_runs = int(benchmark.get("measuredRuns") or 0)
    costed_runs = int(benchmark.get("costedRuns") or 0)
    mean_latency = _finite_number(benchmark.get("measuredMeanLatencyMs"), minimum=0.001)
    p95_latency = _finite_number(benchmark.get("measuredP95LatencyMs"), minimum=0.001)
    approved_p95_latency = _finite_number(benchmark.get("approvedP95LatencyMs"), minimum=0.001)
    mean_unit_cost = _finite_number(benchmark.get("actualMeanUnitCostCents"), minimum=0.0)
    p95_unit_cost = _finite_number(benchmark.get("actualP95UnitCostCents"), minimum=0.0)
    approved_p95_unit_cost = _finite_number(
        benchmark.get("approvedP95UnitCostCeilingCents"), minimum=0.001
    )
    return [
        Check(
            "live_evidence_contains_no_secret_fields",
            not _contains_forbidden_evidence_key(evidence),
            "Evidence may contain only bounded outcomes, never credentials or tokens.",
        ),
        Check(
            "live_evidence_is_current_and_source_bound",
            fresh
            and revision != "unavailable"
            and str(evidence.get("sourceRevision") or "").lower() == revision,
            "Evidence must be no more than 72 hours old and bind the exact candidate revision.",
        ),
        Check(
            "fixed_public_fixture_and_budget",
            evidence.get("fixture") == "octocat-hello-world-pinned"
            and evidence.get("maxCostCents") == 1,
            "The live safety drill must use only the pinned public fixture and one-cent ceiling.",
        ),
        Check(
            "live_safety_and_operator_boundaries",
            all(evidence.get(name) is True for name in REQUIRED_LIVE_BOOLEANS),
            "Every OIDC, isolation, destruction, cancellation, refund, monitoring, rollback, cost, and operator gate must be explicit.",
        ),
        Check(
            "repeatable_live_quality",
            provider_runs >= 8
            and int(benchmark.get("holdoutCases") or 0) >= 4
            and float(benchmark.get("passRate") or 0) >= 0.9
            and float(benchmark.get("meanScore") or 0) >= 90
            and benchmark.get("repeatable") is True,
            "Live provider evidence needs at least eight runs, four injected holdouts, 90% pass rate, 90 mean score, and repeatability.",
        ),
        Check(
            "measured_live_latency_envelope",
            measured_runs >= provider_runs >= 8
            and mean_latency is not None
            and p95_latency is not None
            and approved_p95_latency is not None
            and mean_latency <= p95_latency <= approved_p95_latency,
            "Live evidence needs measured-run mean and p95 latency within a pre-approved p95 ceiling.",
        ),
        Check(
            "actual_live_unit_cost_envelope",
            costed_runs >= provider_runs >= 8
            and mean_unit_cost is not None
            and p95_unit_cost is not None
            and approved_p95_unit_cost is not None
            and mean_unit_cost <= p95_unit_cost <= approved_p95_unit_cost,
            "Live evidence needs actual measured mean and p95 unit cost within a pre-approved p95 cost ceiling.",
        ),
    ]


def trusted_live_attestation_verified(_evidence: dict[str, Any] | None) -> bool:
    """Fail closed until an owner-controlled signature verifier is implemented."""
    if not TRUSTED_LIVE_ATTESTATION_VERIFIER_IMPLEMENTED:
        return False
    # A future implementation must verify an owner-controlled signature here.
    return False


def build_receipt(*, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    revision = _git_revision()
    checks = source_checks()
    checks.extend(
        [
            Check(
                "source_revision_resolved",
                revision != "unavailable",
                "The activation candidate must bind a full Git revision.",
            ),
            Check(
                "source_tree_clean",
                _git_tree_clean(),
                "The activation decision cannot run from an uncommitted or untracked source tree.",
            ),
        ]
    )
    runtime_checks, smoke, benchmark = offline_runtime_checks()
    checks.extend(runtime_checks)
    live_checks = live_evidence_checks(evidence, revision) if evidence is not None else []
    checks.extend(live_checks)
    local_source_checks_passed = all(
        check.passed for check in checks if check not in live_checks
    )
    source_candidate_ready = local_source_checks_passed and not KNOWN_P0_ACTIVATION_HOLDS
    live_evidence_checklist_satisfied = bool(live_checks) and all(
        check.passed for check in live_checks
    )
    trusted_attestation_verified = trusted_live_attestation_verified(evidence)
    public_activation_ready = all(
        (
            source_candidate_ready,
            live_evidence_checklist_satisfied,
            trusted_attestation_verified,
            PUBLIC_ACTIVATION_SOURCE_DECISION_APPROVED,
            not PUBLIC_RELEASE_CONTROLS_EXPECTED_CLOSED,
        )
    )
    remaining = list(KNOWN_P0_ACTIVATION_HOLDS)
    if not live_evidence_checklist_satisfied:
        remaining.extend(
            [
                "one exact-source public-fixture Sandbox/OIDC drill with lifecycle proof",
                "repeatable provider quality plus measured mean/p95 latency and actual mean/p95 unit cost",
            ]
        )
    if not trusted_attestation_verified:
        remaining.append("an owner-controlled signed attestation verifier and a valid trusted attestation")
    if not PUBLIC_ACTIVATION_SOURCE_DECISION_APPROVED:
        remaining.append("an explicit reviewed activation decision recorded in source")
    if PUBLIC_RELEASE_CONTROLS_EXPECTED_CLOSED:
        remaining.append("a separate reviewed change that opens both independent release controls")
    return {
        "schemaVersion": 1,
        "product": "Autonomous Crump",
        "internalFeature": "crump_code",
        "sourceRevision": revision,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "localSourceChecksPassed": local_source_checks_passed,
        "sourceCandidateReady": source_candidate_ready,
        "liveEvidenceChecklistSatisfied": live_evidence_checklist_satisfied,
        "trustedLiveAttestationVerified": trusted_attestation_verified,
        "sourceActivationDecisionApproved": PUBLIC_ACTIVATION_SOURCE_DECISION_APPROVED,
        "publicActivationReady": public_activation_ready,
        "publicReleaseLockExpectedClosed": True,
        "activationControlsExpectedClosed": PUBLIC_RELEASE_CONTROLS_EXPECTED_CLOSED,
        "knownP0ActivationHolds": list(KNOWN_P0_ACTIVATION_HOLDS),
        "networkRequestsByVerifier": 0,
        "modelCallsByVerifier": 0,
        "databaseWritesByVerifier": 0,
        "providerSpendByVerifierCents": 0,
        "checks": [check.__dict__ for check in checks],
        "offlineProof": {
            "sandboxDryRun": {
                "success": smoke.get("success"),
                "networkPolicy": smoke.get("networkPolicy"),
                "destroy": smoke.get("destroy"),
                "modelCalls": smoke.get("modelCalls"),
                "databaseWrites": smoke.get("databaseWrites"),
            },
            "benchmark": {
                "suiteId": benchmark.get("suite_id"),
                "caseCount": benchmark.get("case_count"),
                "passedCaseCount": benchmark.get("passed_case_count"),
                "meanScore": benchmark.get("mean_score"),
                "passed": benchmark.get("passed"),
            },
        },
        "remainingExternalGates": remaining,
    }


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    output_root = (ROOT / "output" / "autonomous-crump-activation").resolve()
    resolved = path.resolve()
    if output_root != resolved.parent and output_root not in resolved.parents:
        raise ValueError("Receipt must stay under output/autonomous-crump-activation.")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run Autonomous Crump's zero-network source gate. Supplied JSON can satisfy the "
            "live-evidence checklist but cannot authorize public activation; a trusted attestation "
            "verifier, source decision, and separate release-control change are still required."
        )
    )
    parser.add_argument("--live-evidence", type=Path)
    parser.add_argument("--require-public-activation", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.require_public_activation and not args.live_evidence:
        parser.error("--require-public-activation requires --live-evidence")
    evidence = None
    if args.live_evidence:
        try:
            evidence = json.loads(args.live_evidence.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Live evidence is unavailable or invalid: {type(exc).__name__}") from exc
        if not isinstance(evidence, dict):
            raise SystemExit("Live evidence must be one JSON object.")
    receipt = build_receipt(evidence=evidence)
    if args.receipt:
        _write_receipt(args.receipt, receipt)
    print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
    if not receipt["localSourceChecksPassed"]:
        return 1
    if args.require_public_activation and not receipt["publicActivationReady"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
