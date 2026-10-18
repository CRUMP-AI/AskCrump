"""Driver <-> executor integration: fake production-loop driver into the fake
boundary executor, offline.

PLUMBING EVIDENCE ONLY. This script drives the frozen corpus with the
deterministic fake provider, exports each case's exact candidate patch bytes,
binds those identical bytes into the FakeBoundaryExecutor, and evaluates
EXPLICITLY SYNTHETIC, independently predetermined evidence against them.

Nothing here evaluates model capability. No model is called. No paid
infrastructure is used. Per-case labels remain "Not evaluated (model
evaluation not run)"; fix_rate stays null.

A synthetic pass NEVER means the candidate fixes the case: the evidence is
arbitrary by construction (declared scenarios below) and carries zero
information about the case or the driver run. Executor outcomes on synthetic
evidence exercise the terminal-path wiring only.

REMAINING LIMITATIONS (explicit, by design):
- Fake driver: in-memory task service and local subprocess sandbox; proves
  the loop runs, nothing about capability or isolation.
- Synthetic evidence is arbitrary; verdicts on it are wiring checks, never
  capability claims.
- In-memory executor registry: replay protection is instance-scoped.
- Timeout/cancellation scenarios use an injected FakeClock and direct
  cancel(); they exercise precedence logic, not real timing behavior.
- Candidate patch bytes are fake-provider output; binding them proves the
  digest pipeline, not patch quality.
- Oracle isolation is evaluator-owned and separately open; nothing here
  claims it.

Exit codes: 0 = report valid; 2 = report written but INVALID (includes
determinism failure); 1 = fatal, no report (unusable manifest or unwritable
destination).

Determinism: the pipeline runs twice into two fresh work roots with fixed
seeds. The canonical projection excludes ONLY these documented volatile
fields: run_id (uuid4 per run), created_utc (wall clock), evaluated_at
(executor wall-clock timestamp). Patch bytes, evidence bytes, digests,
outcomes, and reason codes are compared EXACTLY -- never regex-normalized.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.crump_code_v2_executor import (  # noqa: E402
    BoundaryRefusal,
    EvidenceBundle,
    FakeBoundaryExecutor,
    FakeClock,
    FrozenRun,
    TestRecord,
)

EXPECTED_FROZEN_MANIFEST_SHA = (
    "59451dadb2e312ddda5fe12b35b80a20f597f4587a373580015c9a846ccc3f43"
)
AGGREGATE = "Model evaluation not run; 0 cases evaluated; fix rate unavailable"

LIMITATIONS = [
    "Fake driver proves the production loop runs with scripted provider turns; nothing about model capability.",
    "Synthetic evidence is arbitrary by construction; executor outcomes on synthetic evidence exercise the terminal-path wiring only.",
    "In-memory executor registry: replay protection is instance-scoped.",
    "Timeout/cancellation scenarios use an injected FakeClock and direct cancel(); they exercise precedence logic, not real timing behavior.",
    "Candidate patch bytes are fake-provider output; binding them proves the digest pipeline, not patch quality.",
    "Oracle isolation is evaluator-owned and separately open; nothing here claims it.",
]

# Declared synthetic scenarios, assigned round-robin in roster order.
SCENARIO_ORDER = (
    "clean_pass",
    "assertion_fail",
    "skipped_error",
    "malformed",
    "digest_mismatch",
    "empty",
    "timeout",
    "cancellation",
)

# Predetermined (outcome, reason) per scenario, fixed BEFORE any invocation.
# Literal strings on purpose: the check must not move with the constants.
EXPECTED_OUTCOME: dict[str, tuple[str, str | None]] = {
    "clean_pass": ("pass", None),
    "assertion_fail": ("fail", None),
    "skipped_error": ("incomplete", "non_terminal_test_record"),
    "malformed": ("incomplete", "malformed_evidence"),
    "digest_mismatch": ("incomplete", "evidence_digest_mismatch"),
    "empty": ("incomplete", "missing_test_id"),
    "timeout": ("timeout", "deadline_expired"),
    "cancellation": ("cancelled", "cancel_accepted"),
}

# Canonical projection drops ONLY these documented volatile fields.
_VOLATILE_KEYS = frozenset({"run_id", "created_utc", "evaluated_at"})


def _git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _component_identity(module: Any, script_rel: str) -> dict[str, Any]:
    data = Path(module.__file__).resolve().read_bytes()
    return {"script": script_rel, "blob_sha": _git_blob_sha(data), "bytes": len(data)}


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------


def freeze_roster(corpus_root: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Freeze the expected case roster from the manifest.

    Returns (roster, None) or (None, fatal_diagnostic). A manifest with
    duplicate case ids is malformed: there is no valid roster to freeze.
    """
    manifest_path = Path(corpus_root) / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
        cases = manifest["cases"]
        if not isinstance(cases, list) or not cases:
            raise ValueError("no cases list")
        ids: list[str] = []
        for entry in cases:
            cid = entry.get("id") if isinstance(entry, dict) else None
            if not isinstance(cid, str) or not cid:
                raise ValueError("case entry missing string id")
            ids.append(cid)
    except Exception as exc:
        return None, (
            f"unusable manifest {manifest_path}: {type(exc).__name__}: {exc}"
        )
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        return None, f"malformed roster: duplicate case ids in manifest: {dupes}"
    return (
        [{"id": c["id"], "stratum": c.get("stratum")} for c in cases],
        None,
    )


# ---------------------------------------------------------------------------
# Synthetic evidence (independent of any driver output)
# ---------------------------------------------------------------------------


def _pairs_bytes(pairs: list[list[str]]) -> bytes:
    return json.dumps(pairs, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_synthetic_evidence(
    scenario: str, oracle_ids: list[str]
) -> tuple[EvidenceBundle, bytes]:
    """Build explicitly synthetic evidence for a scenario.

    Never derives statuses from driver receipts or any other run output;
    the verdicts are arbitrary by construction.
    """
    if scenario == "clean_pass":
        pairs = [[tid, "pass"] for tid in oracle_ids]
        raw = _pairs_bytes(pairs)
        records = tuple(TestRecord(t, s) for t, s in pairs)
        return EvidenceBundle(records, raw, hashlib.sha256(raw).hexdigest()), raw
    if scenario == "assertion_fail":
        pairs = [[tid, "fail" if i == 0 else "pass"] for i, tid in enumerate(oracle_ids)]
        raw = _pairs_bytes(pairs)
        records = tuple(TestRecord(t, s) for t, s in pairs)
        return EvidenceBundle(records, raw, hashlib.sha256(raw).hexdigest()), raw
    if scenario == "skipped_error":

        def _status(i: int) -> str:
            return "error" if i == 0 else ("skipped" if i == 1 else "pass")

        pairs = [[tid, _status(i)] for i, tid in enumerate(oracle_ids)]
        raw = _pairs_bytes(pairs)
        records = tuple(TestRecord(t, s) for t, s in pairs)
        return EvidenceBundle(records, raw, hashlib.sha256(raw).hexdigest()), raw
    if scenario == "malformed":
        raw = b'{"not": "a [test_id, status] pair list"}'
        return (
            EvidenceBundle((), raw, hashlib.sha256(raw).hexdigest()),
            raw,
        )
    if scenario == "digest_mismatch":
        pairs = [[tid, "pass"] for tid in oracle_ids]
        raw = _pairs_bytes(pairs)
        records = tuple(TestRecord(t, s) for t, s in pairs)
        return EvidenceBundle(records, raw, "0" * 64), raw
    if scenario == "empty":
        raw = _pairs_bytes([])
        return EvidenceBundle((), raw, hashlib.sha256(raw).hexdigest()), raw
    raise ValueError(f"unknown synthetic scenario: {scenario}")


# ---------------------------------------------------------------------------
# Patch intake (bind the IDENTICAL exported bytes)
# ---------------------------------------------------------------------------


def read_exported_patch(
    patch_dir: Path, case_id: str, returned: dict[str, Any] | None
) -> tuple[str, bytes | None, dict[str, Any] | None, str | None]:
    """Read back the driver's patch export, cross-checked against the
    driver's RETURNED metadata -- never the disk sidecar alone.

    The returned metadata is snapshotted at intake from the driver's own
    record (``record["patch_export"]``). Case ID, availability, byte
    length, and digest must agree across all three: returned metadata,
    sidecar file, and retained patch bytes. Any disagreement, or missing
    returned metadata, is an integrity fault. These are consistency
    checks, never authenticity claims.

    Returns (status, raw_bytes, sidecar, detail) where status is one of
    "ok" | "unavailable" | "missing" | "mutated" | "metadata_missing".
    """
    if not isinstance(returned, dict):
        return (
            "metadata_missing",
            None,
            None,
            "no returned patch_export metadata from the driver; "
            "refusing to bind on sidecar alone",
        )
    meta_path = patch_dir / f"{case_id}.patch.json"
    patch_path = patch_dir / f"{case_id}.patch"
    try:
        sidecar = json.loads(meta_path.read_bytes().decode("utf-8"))
    except Exception:
        return "missing", None, None, "patch sidecar missing; no export to bind"
    if not isinstance(sidecar, dict):
        return "missing", None, None, "patch sidecar is not a JSON object"
    # Cross-check returned metadata against the sidecar file: a replaced
    # pair (patch + sidecar swapped on disk after export) must not pass.
    for key in ("case_id", "available", "bytes", "sha256"):
        if returned.get(key) != sidecar.get(key):
            return (
                "mutated",
                None,
                sidecar,
                f"patch identity mismatch on {key!r}: returned "
                f"{returned.get(key)!r} != sidecar {sidecar.get(key)!r}",
            )
    if sidecar.get("case_id") != case_id:
        return (
            "mutated",
            None,
            sidecar,
            f"sidecar case_id {sidecar.get('case_id')!r} != expected {case_id!r}",
        )
    if not sidecar.get("available"):
        return (
            "unavailable",
            None,
            sidecar,
            sidecar.get("note") or "patch unavailable at export time",
        )
    try:
        raw = patch_path.read_bytes()
    except Exception:
        return "missing", None, sidecar, "patch file missing despite available sidecar"
    actual = hashlib.sha256(raw).hexdigest()
    if actual != returned.get("sha256") or len(raw) != returned.get("bytes"):
        return (
            "mutated",
            None,
            sidecar,
            "patch bytes disagree with returned metadata "
            f"(file sha {actual} vs {returned.get('sha256')}, "
            f"len {len(raw)} vs {returned.get('bytes')})",
        )
    return "ok", raw, sidecar, None


# ---------------------------------------------------------------------------
# Executor invocation
# ---------------------------------------------------------------------------


def _default_timeout_executor_factory(
    corpus_root: Path, clock: FakeClock, deadline_seconds: float
) -> FakeBoundaryExecutor:
    return FakeBoundaryExecutor(
        corpus_root,
        clock=clock,
        executor_id="integration-timeout",
        default_deadline_seconds=deadline_seconds,
    )


def _default_cancellation_executor_factory(
    corpus_root: Path,
    clock: FakeClock,
    deadline_seconds: float,
    hooks: dict[str, Any],
) -> FakeBoundaryExecutor:
    return FakeBoundaryExecutor(
        corpus_root,
        clock=clock,
        executor_id="integration-cancellation",
        default_deadline_seconds=deadline_seconds,
        _hooks=hooks,
    )


def invoke_executor(
    ctx: SimpleNamespace, case_id: str, patch_bytes: bytes, scenario: str
) -> dict[str, Any]:
    """Bind the identical patch bytes and run the predetermined scenario.

    Expectations were fixed before invocation (EXPECTED_OUTCOME); the caller
    compares and invalidates on mismatch.
    """
    exp_outcome, exp_reason = EXPECTED_OUTCOME[scenario]
    executor: FakeBoundaryExecutor = ctx.executor
    candidate_sha = hashlib.sha256(patch_bytes).hexdigest()
    sec: dict[str, Any] = {
        "invoked": True,
        "not_invoked_reason": None,
        "evidence_origin": "synthetic",
        "synthetic_scenario": scenario,
        "expected_outcome": exp_outcome,
        "expected_reason": exp_reason,
        "outcome": None,
        "reason": None,
        "expectation_matched": None,
        "evidence_sha256": None,
        "evidence_snapshot_hex": None,
        "evidence_submitted_hex": None,
        "corpus_manifest_sha": executor.manifest_sha256,
        "candidate_artifact_sha": candidate_sha,
        "oracle_suite_sha": executor.oracle_suite_sha256,
        "evaluation_skipped_after_cancel": False,
        "integration_error": None,
    }
    frozen = FrozenRun(
        run_id=uuid.uuid4().hex,
        case_id=case_id,
        corpus_manifest_sha=executor.manifest_sha256,
        candidate_artifact_sha=candidate_sha,
        oracle_suite_sha=executor.oracle_suite_sha256,
        provenance={
            "synthetic_evidence": True,
            "scenario": scenario,
            "integration": "crump_code_v2_integration",
            "seed": ctx.seed,
        },
    )
    oracle_ids = list(executor.expected_test_ids(case_id))
    try:
        if scenario == "cancellation":
            # Cancel DURING evaluate via the after_snapshot hook and record
            # the ACTUAL returned OracleResult -- never copy the expected
            # reason into the observed fields.
            clock = FakeClock()
            cell: dict[str, Any] = {}

            def _cancel_during_evaluate(raw: bytes, snapshot: bytes) -> None:
                cell["executor"].cancel(cell["handle"])

            cexec = ctx.cancellation_executor_factory(
                ctx.corpus_root,
                clock,
                ctx.timeout_deadline_seconds,
                {"after_snapshot": _cancel_during_evaluate},
            )
            cell["executor"] = cexec
            handle = cexec.bind(frozen, patch_bytes)
            cell["handle"] = handle
            evidence, submitted = build_synthetic_evidence("clean_pass", oracle_ids)
            sec["evidence_submitted_hex"] = submitted.hex()
            result = cexec.evaluate(handle, evidence)
            sec["outcome"] = result.outcome
            sec["reason"] = result.reason_code
            sec["evidence_sha256"] = result.evidence_sha256
            if result.evidence_snapshot is not None:
                sec["evidence_snapshot_hex"] = result.evidence_snapshot.hex()
            sec["evaluation_skipped_after_cancel"] = False
        elif scenario == "timeout":
            clock = FakeClock()
            texec = ctx.timeout_executor_factory(
                ctx.corpus_root, clock, ctx.timeout_deadline_seconds
            )
            handle = texec.bind(frozen, patch_bytes)
            clock.advance(ctx.timeout_deadline_seconds * 2)
            evidence, submitted = build_synthetic_evidence("clean_pass", oracle_ids)
            sec["evidence_submitted_hex"] = submitted.hex()
            result = texec.evaluate(handle, evidence)
            sec["outcome"] = result.outcome
            sec["reason"] = result.reason_code
            sec["evidence_sha256"] = result.evidence_sha256
            if result.evidence_snapshot is not None:
                sec["evidence_snapshot_hex"] = result.evidence_snapshot.hex()
        else:
            handle = executor.bind(frozen, patch_bytes)
            evidence, submitted = build_synthetic_evidence(scenario, oracle_ids)
            sec["evidence_submitted_hex"] = submitted.hex()
            result = executor.evaluate(handle, evidence)
            sec["outcome"] = result.outcome
            sec["reason"] = result.reason_code
            sec["evidence_sha256"] = result.evidence_sha256
            if result.evidence_snapshot is not None:
                sec["evidence_snapshot_hex"] = result.evidence_snapshot.hex()
    except BoundaryRefusal as exc:
        sec["integration_error"] = {
            "type": "BoundaryRefusal",
            "code": exc.code,
            "message": exc.detail[:200],
        }
    except Exception as exc:  # noqa: BLE001 - per-case containment
        sec["integration_error"] = {
            "type": type(exc).__name__,
            "message": str(exc)[:200],
        }
    if sec["integration_error"] is None:
        sec["expectation_matched"] = (
            sec["outcome"] == exp_outcome and sec["reason"] == exp_reason
        )
    return sec


# ---------------------------------------------------------------------------
# Per-case processing
# ---------------------------------------------------------------------------


def _executor_section_not_invoked(reason: str) -> dict[str, Any]:
    return {
        "invoked": False,
        "not_invoked_reason": reason,
        "evidence_origin": None,
        "synthetic_scenario": None,
        "expected_outcome": None,
        "expected_reason": None,
        "outcome": None,
        "reason": None,
        "expectation_matched": None,
        "evidence_sha256": None,
        "evidence_snapshot_hex": None,
        "evidence_submitted_hex": None,
        "corpus_manifest_sha": None,
        "candidate_artifact_sha": None,
        "oracle_suite_sha": None,
        "evaluation_skipped_after_cancel": False,
        "integration_error": None,
    }


def _candidate_section() -> dict[str, Any]:
    return {
        "available": False,
        "unavailable_reason": None,
        "sha256": None,
        "bytes_hex": None,
        "export_sha256": None,
        "base_revision": None,
    }


def process_case(
    ctx: SimpleNamespace,
    entry: dict[str, Any],
    records: list[dict[str, Any]],
    index: int,
) -> dict[str, Any]:
    """Build one report row. Never raises: faults are recorded, not thrown."""
    case_id = entry["id"]
    row: dict[str, Any] = {
        "id": case_id,
        "stratum": entry.get("stratum"),
        "honest_label": "Not evaluated",
        "honest_reason": "model evaluation not run",
        "driver_disposition": None,
        "global_error": None,
        "unexpected": False,
        "adapter_support": None,
        "blocked_reason": None,
        "driver": None,
        "duplicate_records": None,
        "candidate": _candidate_section(),
        "executor": _executor_section_not_invoked("not_started"),
    }
    try:
        return _process_case_inner(ctx, entry, records, index, row)
    except Exception as exc:  # noqa: BLE001 - last-resort containment
        row["executor"] = _executor_section_not_invoked("integration_fault")
        row["executor"]["integration_error"] = {
            "type": type(exc).__name__,
            "message": str(exc)[:200],
        }
        ctx.invalid_reasons.append(f"integration_fault:{case_id}:{type(exc).__name__}")
        return row


def _process_case_inner(
    ctx: SimpleNamespace,
    entry: dict[str, Any],
    records: list[dict[str, Any]],
    index: int,
    row: dict[str, Any],
) -> dict[str, Any]:
    case_id = entry["id"]
    if len(records) > 1:
        # Duplicates are detected, never overwritten: both are retained.
        row["driver_disposition"] = "duplicate_records"
        row["duplicate_records"] = [
            {"position": i, "record": r} for i, r in enumerate(records)
        ]
        row["executor"] = _executor_section_not_invoked("duplicate_case_records")
        ctx.invalid_reasons.append(
            f"duplicate_case_id:{case_id} ({len(records)} records retained)"
        )
        return row
    record = records[0]
    row["adapter_support"] = record.get("adapter_support")
    row["blocked_reason"] = record.get("blocked_reason")
    row["driver"] = record
    if record.get("harness_error") is not None or record.get("driver") is None:
        row["driver_disposition"] = "harness_error"
        row["executor"] = _executor_section_not_invoked("harness_error_no_evidence")
        ctx.invalid_reasons.append(f"harness_error:{case_id}")
        return row
    row["driver_disposition"] = (
        "blocked_completed"
        if record.get("adapter_support") == "blocked"
        else "completed"
    )
    # Snapshot the driver's RETURNED patch_export metadata at intake and
    # cross-check it against the sidecar file and the retained bytes.
    # Missing returned metadata is an integrity fault: never bind on the
    # sidecar alone.
    returned_meta = record.get("patch_export")
    status, raw, meta, detail = read_exported_patch(
        ctx.patch_dir, case_id, returned_meta
    )
    if status == "ok":
        assert raw is not None and meta is not None
        row["candidate"].update(
            available=True,
            sha256=hashlib.sha256(raw).hexdigest(),
            bytes_hex=raw.hex(),
            export_sha256=meta.get("sha256"),
            base_revision=meta.get("base_revision"),
        )
    elif status == "unavailable":
        row["candidate"]["unavailable_reason"] = "patch_unavailable"
        row["executor"] = _executor_section_not_invoked("patch_unavailable")
        ctx.invalid_reasons.append(f"patch_unavailable:{case_id}")
        return row
    else:  # "missing", "mutated", or "metadata_missing": integrity fault
        reason = (
            "candidate_artifact_mutated"
            if status == "mutated"
            else (
                "patch_export_metadata_missing"
                if status == "metadata_missing"
                else "patch_file_missing"
            )
        )
        row["candidate"]["unavailable_reason"] = reason
        row["candidate"]["export_sha256"] = (meta or {}).get("sha256")
        row["executor"] = _executor_section_not_invoked(reason)
        row["executor"]["integration_error"] = {
            "type": "ArtifactIntegrity",
            "message": detail,
        }
        ctx.invalid_reasons.append(f"{reason}:{case_id}")
        return row
    scenario = (ctx.scenario_override or {}).get(
        case_id, SCENARIO_ORDER[index % len(SCENARIO_ORDER)]
    )
    if scenario not in EXPECTED_OUTCOME:
        row["executor"] = _executor_section_not_invoked("unknown_scenario")
        row["executor"]["integration_error"] = {
            "type": "Configuration",
            "message": f"unknown scenario {scenario!r}",
        }
        ctx.invalid_reasons.append(f"unknown_scenario:{case_id}:{scenario}")
        return row
    assert raw is not None
    sec = invoke_executor(ctx, case_id, raw, scenario)
    row["executor"] = sec
    if sec["integration_error"] is not None:
        ctx.invalid_reasons.append(
            f"executor_invocation_error:{case_id}:{sec['integration_error']['type']}"
        )
    elif sec["expectation_matched"] is False:
        ctx.invalid_reasons.append(
            f"unexpected_executor_result:{case_id}: scenario={scenario} "
            f"expected=({sec['expected_outcome']},{sec['expected_reason']}) "
            f"observed=({sec['outcome']},{sec['reason']})"
        )
    return row


# ---------------------------------------------------------------------------
# Single pass
# ---------------------------------------------------------------------------


def _global_error_rows(
    roster: list[dict[str, Any]], global_error: str
) -> list[dict[str, Any]]:
    rows = []
    for entry in roster:
        rows.append(
            {
                "id": entry["id"],
                "stratum": entry.get("stratum"),
                "honest_label": "Not evaluated",
                "honest_reason": "model evaluation not run",
                "driver_disposition": "unattempted",
                "global_error": global_error,
                "unexpected": False,
                "adapter_support": None,
                "blocked_reason": None,
                "driver": None,
                "duplicate_records": None,
                "candidate": _candidate_section(),
                "executor": _executor_section_not_invoked("global_error"),
            }
        )
    return rows


def _missing_row(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "stratum": entry.get("stratum"),
        "honest_label": "Not evaluated",
        "honest_reason": "model evaluation not run",
        "driver_disposition": "missing",
        "global_error": None,
        "unexpected": False,
        "adapter_support": None,
        "blocked_reason": None,
        "driver": None,
        "duplicate_records": None,
        "candidate": _candidate_section(),
        "executor": _executor_section_not_invoked("missing_case_record"),
    }


class _ShapeError(ValueError):
    """Driver report failed structural validation."""


def _validate_driver_report_shape(report: Any) -> list[dict[str, Any]]:
    """Validate the driver report's JSON-compatible shape inside containment.

    The report must be a dict, cases a list, every record a dict, every id
    a string. Anything else (None report, null cases, null records,
    unhashable ids) raises _ShapeError so the caller emits the 20-row
    invalid report with the frozen roster retained -- never a traceback,
    never a silent drop.
    """
    if not isinstance(report, dict):
        raise _ShapeError(
            f"driver report is {type(report).__name__}, not a JSON object"
        )
    cases = report.get("cases")
    if not isinstance(cases, list):
        raise _ShapeError(
            f"driver report cases is {type(cases).__name__}, not a list"
        )
    for index, rec in enumerate(cases):
        if not isinstance(rec, dict):
            raise _ShapeError(
                f"case record {index} is {type(rec).__name__}, not a JSON object"
            )
        rid = rec.get("id")
        if not isinstance(rid, str):
            raise _ShapeError(
                f"case record {index} id is {type(rid).__name__}, not a string"
            )
    return cases


def _json_safe(value: Any) -> Any:
    """Return value if JSON-serializable, else a type/repr placeholder.

    The report itself must always be writable with json.dumps, so retained
    observations can never carry unserializable objects.
    """
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return {
            "__unserializable__": type(value).__name__,
            "repr": repr(value)[:500],
        }


def _extract_observations(
    driver_report: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract per-position observations and observed string IDs.

    Returns (observations, observed_ids). Each observation records its
    position in the driver's cases list, the JSON-safe record, the observed
    string id (or None), and a malformed diagnostic (or None). observed_ids
    lists every string id observed, in position order, duplicates included.
    Used when shape validation fails so the original input survives in the
    report instead of being replaced by blank rows.
    """
    observations: list[dict[str, Any]] = []
    observed_ids: list[str] = []
    cases = driver_report.get("cases") if isinstance(driver_report, dict) else None
    if not isinstance(cases, list):
        return observations, observed_ids
    for index, rec in enumerate(cases):
        if isinstance(rec, dict) and isinstance(rec.get("id"), str):
            observations.append(
                {
                    "position": index,
                    "record": _json_safe(rec),
                    "observed_id": rec["id"],
                    "malformed": None,
                }
            )
            observed_ids.append(rec["id"])
        else:
            if isinstance(rec, dict):
                diag = (
                    f"record id is {type(rec.get('id')).__name__}, not a string"
                )
            else:
                diag = f"record is {type(rec).__name__}, not a JSON object"
            observations.append(
                {
                    "position": index,
                    "record": _json_safe(rec),
                    "observed_id": None,
                    "malformed": diag,
                }
            )
    return observations, observed_ids


def _build_report(
    *,
    roster: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    invalid_reasons: list[str],
    seen_ids: set[str],
    dupes: list[str],
    unexpected: list[str],
    executor: Any | None,
    seed: str,
    expected_manifest_sha: str,
    input_observations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the report artifact from rows + bookkeeping.

    Module-level so run_pipeline can publish the frozen-roster invalid
    report on directory failures without running any pass. input_observations
    carries retained driver observations on shape-validation failure
    (None otherwise).
    """
    import scripts.crump_code_v2_executor as executor_mod
    import scripts.crump_code_v2_fake_driver as driver_mod

    missing = [e["id"] for e in roster if e["id"] not in seen_ids]
    validity = "valid" if not invalid_reasons else "invalid"
    return {
        "artifact": "crump_code_v2_driver_executor_integration",
        "schema_version": 1,
        "report_validity": validity,
        "invalid_reasons": list(invalid_reasons),
        "plumbing_evidence_only": True,
        "capability_claims": "none",
        "synthetic_evidence": True,
        "synthetic_note": (
            "A synthetic pass NEVER means the candidate fixes the case: "
            "evidence is arbitrary by construction and carries zero "
            "information about the case or the driver run. Executor "
            "outcomes on synthetic evidence exercise the terminal-path "
            "wiring only."
        ),
        "run_id": uuid.uuid4().hex,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "seed": seed,
        "corpus": {
            "manifest_sha": (
                executor.manifest_sha256 if executor else None
            ),
            "expected_manifest_sha": expected_manifest_sha,
            "case_count": len(roster),
            "frozen": True,
        },
        "components": {
            "driver": {
                **_component_identity(
                    driver_mod, "scripts/crump_code_v2_fake_driver.py"
                ),
                "provider": "deterministic-fake",
                "model_calls": 0,
                "paid_sandbox_used": False,
            },
            "executor": {
                **_component_identity(
                    executor_mod, "scripts/crump_code_v2_executor.py"
                ),
                "kind": "fake",
                "oracle_suite_sha256": (
                    executor.oracle_suite_sha256 if executor else None
                ),
            },
        },
        "synthetic_scenarios": {
            name: {"expected_outcome": o, "expected_reason": r}
            for name, (o, r) in EXPECTED_OUTCOME.items()
        },
        "input_observations": input_observations,
        "cases": rows,
        "completeness": {
            "expected": len(roster),
            "present": len(rows),
            "missing_ids": missing,
            "duplicate_ids": sorted(dupes),
            "unexpected_ids": sorted(unexpected),
        },
        "aggregate": AGGREGATE,
        "fix_rate": None,
        "limitations": list(LIMITATIONS),
    }


def run_single_pass(
    *,
    corpus_root: Path,
    work_root: Path,
    seed: str = "v1",
    expected_manifest_sha: str = EXPECTED_FROZEN_MANIFEST_SHA,
    drive_all_fn: Any | None = None,
    runner_cls: Any | None = None,
    settings: Any | None = None,
    executor_factory: Any | None = None,
    cancellation_executor_factory: Any | None = None,
    scenario_override: dict[str, str] | None = None,
    timeout_deadline_seconds: float = 5.0,
) -> tuple[dict[str, Any] | None, str | None]:
    """Run the full pipeline once. Returns (report, fatal_error).

    Fatal is only set when no valid roster exists (handled by the caller);
    every other failure becomes invalid-marked rows with diagnostics.
    """
    corpus_root = Path(corpus_root)
    work_root = Path(work_root)
    roster, fatal = freeze_roster(corpus_root)
    if fatal:
        return None, fatal
    assert roster is not None
    if executor_factory is None:
        executor_factory = FakeBoundaryExecutor
    if cancellation_executor_factory is None:
        cancellation_executor_factory = _default_cancellation_executor_factory
    ctx = SimpleNamespace(
        corpus_root=corpus_root,
        work_root=work_root,
        patch_dir=work_root / "patches",
        seed=seed,
        scenario_override=scenario_override or {},
        timeout_deadline_seconds=timeout_deadline_seconds,
        timeout_executor_factory=_default_timeout_executor_factory,
        cancellation_executor_factory=cancellation_executor_factory,
        invalid_reasons=[],
        executor=None,
        input_observations=None,
    )

    def _finish(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return _build_report(
            roster=roster,
            rows=rows,
            invalid_reasons=ctx.invalid_reasons,
            seen_ids=seen_ids,
            dupes=dupes,
            unexpected=unexpected,
            executor=ctx.executor,
            seed=seed,
            expected_manifest_sha=expected_manifest_sha,
            input_observations=ctx.input_observations,
        )

    # -- executor construction + frozen digest check -------------------------
    # (initialized before _finish's early-return call sites below)
    seen_ids: set[str] = set()
    dupes: list[str] = []
    unexpected: list[str] = []
    try:
        ctx.executor = executor_factory(corpus_root)
    except Exception as exc:
        ctx.invalid_reasons.append(
            f"executor_construction:{type(exc).__name__}:{str(exc)[:200]}"
        )
        return _finish(_global_error_rows(roster, ctx.invalid_reasons[-1])), None
    if ctx.executor.manifest_sha256 != expected_manifest_sha:
        reason = (
            f"manifest_digest_mismatch: executor={ctx.executor.manifest_sha256} "
            f"expected={expected_manifest_sha}"
        )
        ctx.invalid_reasons.append(reason)
        return _finish(_global_error_rows(roster, reason)), None

    # -- drive + intake (all inside containment) -----------------------------
    # Work-root creation, the drive itself, and roster-shape validation all
    # live here: any ordinary failure becomes the 20-row invalid report
    # with the frozen roster retained. Only BaseException escapes.
    if drive_all_fn is None:
        from scripts.crump_code_v2_fake_driver import drive_all as drive_all_fn

        if runner_cls is None or settings is None:
            raise ValueError("runner_cls and settings are required with the real driver")
    driver_report = None
    try:
        work_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        reason = f"work_root_unwritable:{type(exc).__name__}:{exc}"
        ctx.invalid_reasons.append(reason)
        return _finish(_global_error_rows(roster, reason)), None
    try:
        ctx.patch_dir.mkdir(parents=True, exist_ok=True)
        driver_report = asyncio.run(
            drive_all_fn(
                corpus_root,
                work_root,
                runner_cls,
                settings,
                seed=seed,
                export_patch_to=ctx.patch_dir,
            )
        )
        cases = _validate_driver_report_shape(driver_report)
    except _ShapeError as exc:
        reason = f"driver_report_shape:{exc}"
        ctx.invalid_reasons.append(reason)
        # Retain the original observations with positions and per-record
        # malformed diagnostics instead of replacing them with blank rows.
        # Executor invocations are skipped on this global failure, but the
        # observed string IDs still feed completeness accounting.
        observations, observed_ids = _extract_observations(driver_report)
        ctx.input_observations = {
            "records": observations,
            "observed_string_ids": sorted(set(observed_ids)),
            "note": (
                "Original driver observations retained with positions; "
                "executor invocations skipped on this global shape failure."
            ),
        }
        roster_ids = {e["id"] for e in roster}
        seen_obs: set[str] = set()
        for oid in observed_ids:
            if oid in roster_ids:
                seen_ids.add(oid)
            elif oid not in unexpected:
                unexpected.append(oid)
                ctx.invalid_reasons.append(f"unexpected_case_id:{oid}")
            if oid in seen_obs and oid not in dupes:
                dupes.append(oid)
                ctx.invalid_reasons.append(
                    f"duplicate_case_id:{oid} "
                    f"({observed_ids.count(oid)} observations retained)"
                )
            seen_obs.add(oid)
        return _finish(_global_error_rows(roster, reason)), None
    except Exception as exc:  # noqa: BLE001 - global containment; never BaseException
        reason = f"drive_all:{type(exc).__name__}:{str(exc)[:300]}"
        ctx.invalid_reasons.append(reason)
        return _finish(_global_error_rows(roster, reason)), None

    # -- roster matching (detect, never overwrite) ---------------------------
    by_id: dict[str, list[dict[str, Any]]] = {}
    for rec in cases:
        rid = rec["id"]
        by_id.setdefault(rid, []).append(rec)
    roster_ids = [e["id"] for e in roster]
    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(roster):
        case_id = entry["id"]
        recs = by_id.get(case_id, [])
        if not recs:
            ctx.invalid_reasons.append(f"missing_case_id:{case_id}")
            rows.append(_missing_row(entry))
            continue
        seen_ids.add(case_id)
        if len(recs) > 1:
            dupes.append(case_id)
        rows.append(process_case(ctx, entry, recs, index))
    for rid, recs in by_id.items():
        if rid not in roster_ids:
            unexpected.append(str(rid))
            ctx.invalid_reasons.append(f"unexpected_case_id:{rid}")
            for rec in recs:
                rows.append(
                    {
                        "id": str(rid),
                        "stratum": rec.get("stratum"),
                        "honest_label": "Not evaluated",
                        "honest_reason": "model evaluation not run",
                        "driver_disposition": "unexpected_case_id",
                        "global_error": None,
                        "unexpected": True,
                        "adapter_support": rec.get("adapter_support"),
                        "blocked_reason": rec.get("blocked_reason"),
                        "driver": rec,
                        "duplicate_records": None,
                        "candidate": _candidate_section(),
                        "executor": _executor_section_not_invoked(
                            "unexpected_case_id"
                        ),
                    }
                )
    # A missing roster id paired with an unexpected id looks like a
    # substitution: flag the pairing explicitly, keep both sides listed.
    _missing_now = [e["id"] for e in roster if e["id"] not in seen_ids]
    if _missing_now and unexpected:
        ctx.invalid_reasons.append(
            f"possible_substitution: missing={sorted(_missing_now)} "
            f"unexpected={sorted(unexpected)}"
        )
    return _finish(rows), None


# ---------------------------------------------------------------------------
# Determinism: two passes, canonical projection
# ---------------------------------------------------------------------------


def _project_canonical(value: Any) -> Any:
    """Structural projection excluding ONLY documented volatile fields.

    Volatile: run_id (uuid4 per run), created_utc (wall clock),
    evaluated_at (executor wall-clock timestamp). Everything else --
    patch bytes, evidence bytes, digests, outcomes, reason codes -- is
    compared exactly, never regex-normalized.
    """
    if isinstance(value, dict):
        return {
            k: _project_canonical(v)
            for k, v in sorted(value.items())
            if k not in _VOLATILE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_project_canonical(v) for v in value]
    return value


def canonical_projection(report: dict[str, Any]) -> str:
    return json.dumps(
        _project_canonical(report), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Pipeline: double run, write, exit code
# ---------------------------------------------------------------------------


def _write_report_text(out_path: Path, report: dict[str, Any]) -> str | None:
    """Write the report JSON; return a fatal diagnostic, or None on success.

    The parent directory is created here, inside the same error handling,
    so a caller that reaches publication before creating parents — e.g.
    the work-root failure path — still publishes the report when the
    destination is writable. A real permission failure still returns the
    fatal diagnostic, never a traceback and never silent success.
    """
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        return (
            f"failed to write report {out_path}: {type(exc).__name__}: {exc}"
        )
    return None


def _publish_invalid_report(
    *,
    roster: list[dict[str, Any]],
    reason: str,
    out_path: Path,
    seed: str,
    expected_manifest_sha: str,
) -> tuple[dict[str, Any] | None, int, str | None]:
    """Build and write the frozen-roster invalid report.

    Used when the roster is usable but no pass can run (work-root or
    pass-directory failure): every expected case appears as an unattempted
    row with candidate null and executor not invoked, and the directory
    error is retained in invalid_reasons. Returns (report, 2, None); a
    write failure is the only path returning fatal (None, 1, ...).
    """
    report = _build_report(
        roster=roster,
        rows=_global_error_rows(roster, reason),
        invalid_reasons=[reason],
        seen_ids=set(),
        dupes=[],
        unexpected=[],
        executor=None,
        seed=seed,
        expected_manifest_sha=expected_manifest_sha,
        input_observations=None,
    )
    fatal = _write_report_text(out_path, report)
    if fatal is not None:
        return None, 1, fatal
    return report, 2, None


def run_pipeline(
    *,
    corpus_root: Path,
    work_root: Path,
    out_path: Path,
    seed: str = "v1",
    **pass_kwargs: Any,
) -> tuple[dict[str, Any] | None, int, str | None]:
    """Run the pipeline twice, compare, write the report.

    Returns (report_or_None, exit_code, fatal_or_None).
    Exit codes: 0 = valid; 2 = report written but invalid (includes
    determinism failure); 1 = fatal, no report written (unusable roster
    or unwritable destination/publication failure only).
    """
    corpus_root = Path(corpus_root)
    work_root = Path(work_root)
    out_path = Path(out_path)
    roster, fatal = freeze_roster(corpus_root)
    if fatal:
        return None, 1, fatal
    expected_manifest_sha = pass_kwargs.get(
        "expected_manifest_sha", EXPECTED_FROZEN_MANIFEST_SHA
    )
    try:
        work_root.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        # The roster is usable and the destination was verified writable:
        # publish the frozen-roster invalid report rather than a fatal
        # without one.
        reason = f"work_root_unwritable:{type(exc).__name__}:{exc}"
        return _publish_invalid_report(
            roster=roster,
            reason=reason,
            out_path=out_path,
            seed=seed,
            expected_manifest_sha=expected_manifest_sha,
        )
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Uniquely owned write probe: a fixed path would overwrite/unlink
        # whatever a previous run (or a user) left there. Only the file
        # this run created is ever unlinked.
        fd, probe_name = tempfile.mkstemp(
            dir=out_path.parent, prefix=".integration_write_probe_"
        )
        try:
            os.write(fd, b"ok")
        finally:
            os.close(fd)
        Path(probe_name).unlink()
    except Exception as exc:
        return (
            None,
            1,
            f"unwritable destination {out_path}: {type(exc).__name__}: {exc}",
        )
    # Uniquely owned fresh work roots per pass: fixed pass-a/pass-b paths
    # would rmtree preexisting content. Only these two directories are
    # ever cleaned up.
    try:
        work_a = Path(tempfile.mkdtemp(prefix="crump-integ-pass-a-", dir=work_root))
        work_b = Path(tempfile.mkdtemp(prefix="crump-integ-pass-b-", dir=work_root))
    except Exception as exc:
        # Same as work_root failure: the roster is usable, so publish the
        # frozen-roster invalid report with the directory error retained.
        reason = (
            f"cannot_create_pass_work_dirs:{type(exc).__name__}:{exc}"
        )
        return _publish_invalid_report(
            roster=roster,
            reason=reason,
            out_path=out_path,
            seed=seed,
            expected_manifest_sha=expected_manifest_sha,
        )
    try:
        report_a, fatal_a = run_single_pass(
            corpus_root=corpus_root, work_root=work_a, seed=seed, **pass_kwargs
        )
        report_b, fatal_b = run_single_pass(
            corpus_root=corpus_root, work_root=work_b, seed=seed, **pass_kwargs
        )
        # Pre-checks make fatals unreachable here; handle defensively anyway.
        if fatal_a or report_a is None:
            return None, 1, f"first pass failed fatally: {fatal_a}"
        if fatal_b or report_b is None:
            return None, 1, f"second pass failed fatally: {fatal_b}"
        identical = canonical_projection(report_a) == canonical_projection(report_b)
        report_a["determinism"] = {
            "runs": 2,
            "work_roots": ["pass-a", "pass-b"],
            "canonical_identical": identical,
            "note": (
                "two fresh work roots, fixed seeds; projection excludes only "
                "run_id, created_utc, evaluated_at"
            ),
        }
        if not identical:
            report_a["invalid_reasons"].append(
                "determinism_mismatch: two passes were not canonically identical"
            )
            report_a["report_validity"] = "invalid"
        # The final write lives inside containment: an unwritable out_path
        # (a directory, a permission error) yields the fatal diagnostic,
        # never a traceback.
        fatal_write = _write_report_text(out_path, report_a)
        if fatal_write is not None:
            return None, 1, fatal_write
        code = 0 if report_a["report_validity"] == "valid" else 2
        return report_a, code, None
    finally:
        for d in (work_a, work_b):
            shutil.rmtree(d, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fake driver -> fake executor integration (plumbing only)."
    )
    parser.add_argument(
        "--corpus-root", default="benchmarks/crump_code/real_tasks_v2"
    )
    parser.add_argument("--work-root", default="/tmp/crump-code-v2-integration")
    parser.add_argument("--out", default="integration_report.v1.json")
    parser.add_argument("--seed", default="v1")
    parser.add_argument(
        "--expected-manifest-sha", default=EXPECTED_FROZEN_MANIFEST_SHA
    )
    args = parser.parse_args(argv)

    from backend.code_runner import CrumpCodeRunner

    settings = SimpleNamespace(
        code_max_agent_steps=8, anthropic_api_key=None, anthropic_model="fake-provider"
    )
    report, code, fatal = run_pipeline(
        corpus_root=args.corpus_root,
        work_root=args.work_root,
        out_path=args.out,
        seed=args.seed,
        expected_manifest_sha=args.expected_manifest_sha,
        runner_cls=CrumpCodeRunner,
        settings=settings,
    )
    if fatal is not None:
        print(f"FATAL: {fatal}", file=sys.stderr)
        return 1
    assert report is not None
    print(
        f"wrote {args.out}: validity={report['report_validity']} "
        f"cases={len(report['cases'])} "
        f"invalid_reasons={len(report['invalid_reasons'])}"
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
