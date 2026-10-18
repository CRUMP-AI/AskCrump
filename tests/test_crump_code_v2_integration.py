"""Tests for the driver <-> executor integration (fake-only, offline).

PLUMBING EVIDENCE ONLY. These tests prove the wiring between the fake
production-loop driver and the fake boundary executor: patch export,
identical-byte binding, synthetic evidence scenarios, roster integrity,
validity marking, and determinism. They prove nothing about model
capability. No model is called; no paid infrastructure is used.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from scripts import crump_code_v2_integration as integ
from scripts.crump_code_v2_fake_driver import export_candidate_patch

REAL_CORPUS = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "crump_code" / "real_tasks_v2"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_corpus(tmp_path, case_ids=("case-a", "case-b", "case-c", "case-d")):
    root = tmp_path / "corpus"
    cases = []
    for cid in case_ids:
        tids = [f"{cid}.t1", f"{cid}.t2"]
        oracle_dir = root / "cases" / cid / "oracle"
        oracle_dir.mkdir(parents=True)
        (oracle_dir / "check.py").write_text(f"# oracle for {cid}\n")
        cases.append({"id": cid, "stratum": "s1", "oracle_test_ids": tids})
    (root / "manifest.json").write_text(json.dumps({"cases": cases}))
    return root


def manifest_sha(root):
    return hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest()


def make_drive_all(case_ids, *, patch_map=None, fail_with=None, fail_case=None,
                   blocked=(), second_call_patch_map=None, corrupt_case=None,
                   tamper=None):
    """Fake drive_all: crafts records and stages patch exports like the driver.

    patch_map: {case_id: bytes} patch bytes, or {case_id: None} for a
    missing (unavailable) patch. corrupt_case: case whose patch file is
    rewritten after export, simulating mutation between export and bind.
    tamper: optional callable(export_dir: Path, case_id: str) run after the
    export for each case, for pair-replacement / sidecar-swap attacks.
    Records carry the REAL returned patch_export metadata, like drive_case.
    """
    calls = {"n": 0}

    async def fake_drive_all(corpus_root, work_root, runner_cls, settings,
                            *, seed="v1", export_patch_to=None):
        calls["n"] += 1
        if fail_with is not None:
            raise fail_with
        active_map = (
            second_call_patch_map if calls["n"] == 2 and second_call_patch_map is not None
            else patch_map
        )
        cases = []
        for cid in case_ids:
            if fail_case == cid:
                cases.append(
                    {
                        "id": cid, "stratum": "s1",
                        "adapter_support": "supported", "blocked_reason": None,
                        "honest_label": "Not evaluated",
                        "honest_reason": "model evaluation not run",
                        "plumbing_only": True,
                        "harness_error": {"type": "RuntimeError", "message": "boom"},
                        "driver": None,
                    }
                )
                continue
            patch = (active_map or {}).get(cid, f"patch-bytes-for-{cid}".encode())
            patch_export = None
            if export_patch_to is not None:
                patch_export = export_candidate_patch(
                    export_dir=Path(export_patch_to), case_id=cid,
                    patch=patch, base_revision="deadbeef",
                )
                if corrupt_case == cid:
                    (Path(export_patch_to) / f"{cid}.patch").write_bytes(b"MUTATED")
                if tamper is not None:
                    tamper(Path(export_patch_to), cid)
            rec = {
                "id": cid, "stratum": "s1",
                "adapter_support": "blocked" if cid in blocked else "supported",
                "blocked_reason": "missing trusted adapter" if cid in blocked else None,
                "honest_label": "Not evaluated",
                "honest_reason": "model evaluation not run",
                "plumbing_only": True,
                "patch_export": patch_export,
                "driver": {
                    "provider": "deterministic-fake", "seed": f"{cid}-v1",
                    "model_calls": 0, "paid_sandbox_used": False,
                    "final_status": "completed", "failure_code": None,
                    "result_patch_bytes": len(patch or b""),
                },
            }
            cases.append(rec)
        return {
            "report": "crump_code_v2_fake_driver",
            "plumbing_evidence_only": True,
            "aggregate": integ.AGGREGATE,
            "fix_rate": None,
            "cases": cases,
        }

    return fake_drive_all


def run_pass(tmp_path, corpus, fake, **kw):
    return integ.run_single_pass(
        corpus_root=corpus,
        work_root=tmp_path / "work",
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
        **kw,
    )


def row_by_id(report, cid):
    return next(r for r in report["cases"] if r["id"] == cid and not r["unexpected"])


# ---------------------------------------------------------------------------
# Driver patch export (pure function)
# ---------------------------------------------------------------------------


def test_export_patch_exact_bytes(tmp_path):
    meta = export_candidate_patch(
        export_dir=tmp_path, case_id="c1", patch="diff --git a/x", base_revision="abc"
    )
    assert (tmp_path / "c1.patch").read_bytes() == b"diff --git a/x"
    assert meta["available"] is True
    assert meta["sha256"] == hashlib.sha256(b"diff --git a/x").hexdigest()
    assert meta["bytes"] == len(b"diff --git a/x")
    sidecar = json.loads((tmp_path / "c1.patch.json").read_text())
    assert sidecar["available"] is True
    assert sidecar["sha256"] == meta["sha256"]


def test_export_patch_empty_is_valid_zero_bytes(tmp_path):
    meta = export_candidate_patch(
        export_dir=tmp_path, case_id="c1", patch="", base_revision=None
    )
    assert (tmp_path / "c1.patch").read_bytes() == b""
    assert meta["available"] is True
    assert meta["bytes"] == 0
    assert meta["sha256"] == hashlib.sha256(b"").hexdigest()


def test_export_patch_missing_is_unavailable_never_fabricated(tmp_path):
    meta = export_candidate_patch(
        export_dir=tmp_path, case_id="c1", patch=None, base_revision="abc"
    )
    assert meta["available"] is False
    assert not (tmp_path / "c1.patch").exists(), "missing patch must not fabricate a file"


def test_export_patch_unexpected_type_not_coerced(tmp_path):
    meta = export_candidate_patch(
        export_dir=tmp_path, case_id="c1", patch=12345, base_revision=None
    )
    assert meta["available"] is False
    assert not (tmp_path / "c1.patch").exists()


# ---------------------------------------------------------------------------
# Driver export wiring through drive_case (real corpus, fake provider turn)
# ---------------------------------------------------------------------------


async def _drive_one_export(tmp_path, monkeypatch, patch_value, export_on=True):
    from types import SimpleNamespace

    from backend.code_runner import CrumpCodeRunner
    from scripts.crump_code_v2_fake_driver import (
        DeterministicFakeProvider,
        drive_case,
    )
    from scripts.evaluate_crump_code_v2 import load_suite

    async def fake_run(self, task, workspace):
        return {
            "status": "completed",
            "failure_code": None,
            "result_patch": patch_value,
            "verification": [],
        }

    monkeypatch.setattr(DeterministicFakeProvider, "run_in_workspace", fake_run)
    suite = load_suite(REAL_CORPUS)
    case = suite.case("rename-boundary")
    settings = SimpleNamespace(
        code_max_agent_steps=8, anthropic_api_key=None, anthropic_model="fake-provider"
    )
    kwargs = {}
    if export_on:
        kwargs["export_patch_to"] = tmp_path / "patches"
    record = await drive_case(
        case,
        corpus_root=REAL_CORPUS,
        work_root=tmp_path / "w",
        runner_cls=CrumpCodeRunner,
        settings=settings,
        seed="t-export",
        **kwargs,
    )
    return record


@pytest.mark.skipif(not REAL_CORPUS.exists(), reason="needs real corpus")
def test_drive_case_exports_patch_when_enabled(tmp_path, monkeypatch):
    record = asyncio.run(_drive_one_export(tmp_path, monkeypatch, "DIFF-BYTES"))
    assert (tmp_path / "patches" / "rename-boundary.patch").read_bytes() == b"DIFF-BYTES"
    assert record["patch_export"]["available"] is True
    assert record["patch_export"]["base_revision"], "base revision should be captured"


@pytest.mark.skipif(not REAL_CORPUS.exists(), reason="needs real corpus")
def test_drive_case_export_default_off(tmp_path, monkeypatch):
    record = asyncio.run(
        _drive_one_export(tmp_path, monkeypatch, "DIFF-BYTES", export_on=False)
    )
    assert record["patch_export"] is None
    assert not (tmp_path / "patches").exists()


# ---------------------------------------------------------------------------
# Integration: happy path (valid report)
# ---------------------------------------------------------------------------


def test_valid_run_small_corpus(tmp_path):
    corpus = make_corpus(tmp_path)
    fake = make_drive_all(
        ("case-a", "case-b", "case-c", "case-d"), blocked=("case-c", "case-d")
    )
    report, code, fatal = integ.run_pipeline(
        corpus_root=corpus,
        work_root=tmp_path / "work",
        out_path=tmp_path / "out" / "report.json",
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
    )
    assert fatal is None
    assert report["report_validity"] == "valid", report["invalid_reasons"]
    assert code == 0
    assert report["fix_rate"] is None
    assert report["aggregate"] == integ.AGGREGATE
    assert len(report["cases"]) == 4
    # scenarios assigned round-robin: clean_pass, assertion_fail, skipped_error, malformed
    assert row_by_id(report, "case-a")["executor"]["outcome"] == "pass"
    assert row_by_id(report, "case-a")["executor"]["expectation_matched"] is True
    assert row_by_id(report, "case-b")["executor"]["outcome"] == "fail"
    assert row_by_id(report, "case-c")["executor"]["reason"] == "non_terminal_test_record"
    assert row_by_id(report, "case-d")["executor"]["reason"] == "malformed_evidence"
    # blocked adapters still exercise synthetic plumbing, labels unchanged
    assert row_by_id(report, "case-c")["adapter_support"] == "blocked"
    assert all(r["honest_label"] == "Not evaluated" for r in report["cases"])
    # candidate bytes retained exactly
    assert (
        row_by_id(report, "case-a")["candidate"]["bytes_hex"]
        == b"patch-bytes-for-case-a".hex()
    )
    # determinism section present and clean
    assert report["determinism"]["canonical_identical"] is True
    # report file written
    assert (tmp_path / "out" / "report.json").exists()


def test_timeout_scenario_via_fakeclock(tmp_path):
    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(("case-a",))
    report, fatal = run_pass(
        tmp_path, corpus, fake, scenario_override={"case-a": "timeout"}
    )
    assert fatal is None
    row = row_by_id(report, "case-a")
    assert row["executor"]["outcome"] == "timeout"
    assert row["executor"]["reason"] == "deadline_expired"
    assert row["executor"]["expectation_matched"] is True
    assert report["report_validity"] == "valid", report["invalid_reasons"]


def test_cancellation_scenario(tmp_path):
    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(("case-a",))
    report, fatal = run_pass(
        tmp_path, corpus, fake, scenario_override={"case-a": "cancellation"}
    )
    assert fatal is None
    row = row_by_id(report, "case-a")
    # The ACTUAL returned OracleResult is recorded (cancel driven through
    # the after_snapshot hook during evaluate), not the expected reason
    # copied into the observed fields.
    assert row["executor"]["outcome"] == "cancelled"
    assert row["executor"]["reason"] == "cancel_accepted"
    assert row["executor"]["expectation_matched"] is True
    assert row["executor"]["evaluation_skipped_after_cancel"] is False
    assert report["report_validity"] == "valid", report["invalid_reasons"]


def test_cancellation_records_actual_not_expected_reason(tmp_path):
    """A rigged executor returning an unexpected cancellation reason must
    fail expectations: proves the observed value is really checked."""
    from types import SimpleNamespace

    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(("case-a",))

    def rigged_factory(corpus_root, clock, deadline_seconds, hooks):
        rigged = SimpleNamespace(
            outcome="cancelled",
            reason_code="some_unexpected_reason",
            evidence_sha256=None,
            evidence_snapshot=None,
        )
        return SimpleNamespace(
            bind=lambda frozen, patch: "handle-1",
            cancel=lambda handle: "cancelled",
            evaluate=lambda handle, evidence: rigged,
        )

    report, fatal = run_pass(
        tmp_path,
        corpus,
        fake,
        scenario_override={"case-a": "cancellation"},
        cancellation_executor_factory=rigged_factory,
    )
    assert fatal is None
    row = row_by_id(report, "case-a")
    assert row["executor"]["outcome"] == "cancelled"
    assert row["executor"]["reason"] == "some_unexpected_reason"
    assert row["executor"]["expectation_matched"] is False
    assert report["report_validity"] == "invalid"
    assert any(
        r.startswith("unexpected_executor_result:case-a")
        for r in report["invalid_reasons"]
    )


# ---------------------------------------------------------------------------
# Integration: failure handling
# ---------------------------------------------------------------------------


def test_global_drive_all_failure(tmp_path):
    corpus = make_corpus(tmp_path, case_ids=("case-a", "case-b"))
    fake = make_drive_all(("case-a", "case-b"), fail_with=RuntimeError("boom"))
    report, code, fatal = integ.run_pipeline(
        corpus_root=corpus,
        work_root=tmp_path / "work",
        out_path=tmp_path / "out" / "report.json",
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
    )
    assert fatal is None
    # report IS written (diagnostics preserved), but invalid; nonzero exit
    assert (tmp_path / "out" / "report.json").exists()
    assert report["report_validity"] == "invalid"
    assert code == 2
    assert len(report["cases"]) == 2
    assert all(r["driver_disposition"] == "unattempted" for r in report["cases"])
    assert any("drive_all" in reason for reason in report["invalid_reasons"])


def test_single_case_harness_error(tmp_path):
    corpus = make_corpus(tmp_path)
    fake = make_drive_all(("case-a", "case-b"), fail_case="case-b")
    report, fatal = run_pass(tmp_path, corpus, fake)
    assert fatal is None
    bad = row_by_id(report, "case-b")
    assert bad["driver_disposition"] == "harness_error"
    assert bad["executor"]["invoked"] is False
    assert bad["executor"]["not_invoked_reason"] == "harness_error_no_evidence"
    assert bad["candidate"]["available"] is False
    good = row_by_id(report, "case-a")
    assert good["executor"]["expectation_matched"] is True
    assert report["report_validity"] == "invalid"
    assert any(r.startswith("harness_error:case-b") for r in report["invalid_reasons"])


def test_missing_vs_empty_patch(tmp_path):
    corpus = make_corpus(tmp_path)
    fake = make_drive_all(
        ("case-a", "case-b"), patch_map={"case-a": b"", "case-b": None}
    )
    report, fatal = run_pass(tmp_path, corpus, fake)
    assert fatal is None
    empty = row_by_id(report, "case-a")
    assert empty["candidate"]["available"] is True
    assert empty["candidate"]["bytes_hex"] == ""
    assert empty["executor"]["invoked"] is True
    missing = row_by_id(report, "case-b")
    assert missing["candidate"]["available"] is False
    assert missing["executor"]["invoked"] is False
    assert missing["executor"]["not_invoked_reason"] == "patch_unavailable"
    assert report["report_validity"] == "invalid"


def test_malformed_roster_manifest_duplicates(tmp_path):
    root = tmp_path / "corpus"
    cases = [
        {"id": "dup", "stratum": "s", "oracle_test_ids": ["t1"]},
        {"id": "dup", "stratum": "s", "oracle_test_ids": ["t1"]},
    ]
    (root / "manifest.json").parent.mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({"cases": cases}))
    roster, fatal = integ.freeze_roster(root)
    assert roster is None
    assert "duplicate" in fatal
    report, code, fatal2 = integ.run_pipeline(
        corpus_root=root,
        work_root=tmp_path / "work",
        out_path=tmp_path / "out" / "report.json",
        seed="v1",
    )
    assert report is None
    assert code == 1
    assert not (tmp_path / "out" / "report.json").exists()


def test_duplicate_driver_records_detected_not_overwritten(tmp_path):
    corpus = make_corpus(tmp_path, case_ids=("case-a",))

    async def fake_drive_all(corpus_root, work_root, runner_cls, settings,
                             *, seed="v1", export_patch_to=None):
        rec = {
            "id": "case-a", "stratum": "s1", "adapter_support": "supported",
            "blocked_reason": None, "honest_label": "Not evaluated",
            "honest_reason": "model evaluation not run", "plumbing_only": True,
            "driver": {"provider": "deterministic-fake"},
        }
        return {"cases": [dict(rec), dict(rec)]}

    report, fatal = run_pass(tmp_path, corpus, fake_drive_all)
    assert fatal is None
    row = row_by_id(report, "case-a")
    assert row["driver_disposition"] == "duplicate_records"
    assert len(row["duplicate_records"]) == 2, "both duplicates retained"
    assert row["executor"]["invoked"] is False
    assert report["report_validity"] == "invalid"
    assert any("duplicate_case_id:case-a" in r for r in report["invalid_reasons"])


def test_unexpected_case_id_detected(tmp_path):
    corpus = make_corpus(tmp_path, case_ids=("case-a",))

    async def fake_drive_all(corpus_root, work_root, runner_cls, settings,
                             *, seed="v1", export_patch_to=None):
        rec = {
            "id": "ghost-case", "stratum": "s1", "adapter_support": "supported",
            "blocked_reason": None, "honest_label": "Not evaluated",
            "honest_reason": "model evaluation not run", "plumbing_only": True,
            "driver": {"provider": "deterministic-fake"},
        }
        return {"cases": [rec]}

    report, fatal = run_pass(tmp_path, corpus, fake_drive_all)
    assert fatal is None
    assert any(r.startswith("missing_case_id:case-a") for r in report["invalid_reasons"])
    assert any(r.startswith("unexpected_case_id:ghost-case") for r in report["invalid_reasons"])
    ghost_rows = [r for r in report["cases"] if r["unexpected"]]
    assert len(ghost_rows) == 1 and ghost_rows[0]["id"] == "ghost-case"
    assert report["report_validity"] == "invalid"


def test_unexpected_executor_result_invalidates(tmp_path, monkeypatch):
    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(("case-a",))
    monkeypatch.setitem(integ.EXPECTED_OUTCOME, "clean_pass", ("fail", None))
    report, fatal = run_pass(
        tmp_path, corpus, fake, scenario_override={"case-a": "clean_pass"}
    )
    assert fatal is None
    row = row_by_id(report, "case-a")
    assert row["executor"]["outcome"] == "pass"  # actual executor behavior
    assert row["executor"]["expectation_matched"] is False
    assert report["report_validity"] == "invalid"
    assert any(
        r.startswith("unexpected_executor_result:case-a") for r in report["invalid_reasons"]
    )


def test_artifact_mutation_detected(tmp_path):
    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(("case-a",), corrupt_case="case-a")
    report, fatal = run_pass(tmp_path, corpus, fake)
    assert fatal is None
    row = row_by_id(report, "case-a")
    assert row["candidate"]["available"] is False
    assert row["candidate"]["unavailable_reason"] == "candidate_artifact_mutated"
    assert row["executor"]["invoked"] is False
    assert report["report_validity"] == "invalid"
    assert any("candidate_artifact_mutated:case-a" in r for r in report["invalid_reasons"])


def test_determinism_failure_still_emits_invalid_report(tmp_path):
    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(
        ("case-a",),
        patch_map={"case-a": b"stable-bytes"},
        second_call_patch_map={"case-a": b"changed-bytes"},
    )
    report, code, fatal = integ.run_pipeline(
        corpus_root=corpus,
        work_root=tmp_path / "work",
        out_path=tmp_path / "out" / "report.json",
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
    )
    assert fatal is None
    # report IS emitted (not swallowed), marked invalid, nonzero exit
    assert (tmp_path / "out" / "report.json").exists()
    assert report["report_validity"] == "invalid"
    assert code == 2
    assert report["determinism"]["canonical_identical"] is False
    assert "determinism_mismatch" in report["invalid_reasons"][-1]


def test_synthetic_evidence_independent_of_driver(tmp_path):
    """Evidence builders never touch driver output: same input, same bytes."""
    ids = ["t1", "t2", "t3"]
    for scenario in integ.SCENARIO_ORDER:
        if scenario in ("timeout", "cancellation"):
            continue
        b1, raw1 = integ.build_synthetic_evidence(scenario, ids)
        b2, raw2 = integ.build_synthetic_evidence(scenario, ids)
        assert raw1 == raw2
        assert b1.evidence_sha256 == b2.evidence_sha256 or scenario == "digest_mismatch"


def test_manifest_digest_mismatch_is_global_error(tmp_path):
    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(("case-a",))
    report, fatal = integ.run_single_pass(
        corpus_root=corpus,
        work_root=tmp_path / "work",
        seed="v1",
        expected_manifest_sha="0" * 64,  # wrong on purpose
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
    )
    assert fatal is None
    assert report["report_validity"] == "invalid"
    assert all(r["driver_disposition"] == "unattempted" for r in report["cases"])
    assert any("manifest_digest_mismatch" in r for r in report["invalid_reasons"])


# ---------------------------------------------------------------------------
# Fix 1: temp path hygiene (sentinels survive; write failures are fatal)
# ---------------------------------------------------------------------------


def test_sentinel_files_survive_pipeline(tmp_path):
    """Preexisting files at the old fixed paths must survive: the pipeline
    uses only uniquely owned temp paths and cleans up only what it created."""
    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(("case-a",))
    work_root = tmp_path / "work"
    work_root.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    sentinel_dirs = [work_root / "pass-a", work_root / "pass-b"]
    for d in sentinel_dirs:
        d.mkdir()
        (d / "sentinel.txt").write_text("do-not-delete")
    probe_sentinel = out_dir / ".integration_write_probe"
    probe_sentinel.write_text("do-not-delete")
    report, code, fatal = integ.run_pipeline(
        corpus_root=corpus,
        work_root=work_root,
        out_path=out_dir / "report.json",
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
    )
    assert fatal is None
    assert code == 0, report["invalid_reasons"]
    for d in sentinel_dirs:
        assert (d / "sentinel.txt").read_text() == "do-not-delete"
    assert probe_sentinel.read_text() == "do-not-delete"
    assert (out_dir / "report.json").exists()


def test_final_write_failure_is_fatal_diagnostic(tmp_path):
    """out_path being a directory must yield the clear fatal diagnostic,
    not an unhandled traceback."""
    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(("case-a",))
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    report, code, fatal = integ.run_pipeline(
        corpus_root=corpus,
        work_root=tmp_path / "work",
        out_path=out_dir,  # a directory, not a file
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
    )
    assert report is None
    assert code == 1
    assert fatal is not None and "failed to write report" in fatal


# ---------------------------------------------------------------------------
# Fix 2: patch identity cross-checks (returned metadata vs sidecar vs bytes)
# ---------------------------------------------------------------------------


def test_patch_pair_replacement_rejected(tmp_path):
    """Export A, then replace BOTH patch file and sidecar with B on disk.
    The driver's returned metadata still describes A -> must be rejected."""
    corpus = make_corpus(tmp_path, case_ids=("case-a",))

    def tamper(export_dir, case_id):
        b_bytes = b"COMPLETELY-DIFFERENT-BYTES"
        (export_dir / f"{case_id}.patch").write_bytes(b_bytes)
        (export_dir / f"{case_id}.patch.json").write_text(json.dumps({
            "case_id": case_id,
            "base_revision": "deadbeef",
            "available": True,
            "sha256": hashlib.sha256(b_bytes).hexdigest(),
            "bytes": len(b_bytes),
            "path": f"{case_id}.patch",
            "note": None,
        }))

    fake = make_drive_all(("case-a",), tamper=tamper)
    report, fatal = run_pass(tmp_path, corpus, fake)
    assert fatal is None
    row = row_by_id(report, "case-a")
    assert row["candidate"]["available"] is False
    assert row["candidate"]["unavailable_reason"] == "candidate_artifact_mutated"
    assert row["executor"]["invoked"] is False
    assert report["report_validity"] == "invalid"
    assert any(
        "candidate_artifact_mutated:case-a" in r for r in report["invalid_reasons"]
    )


def test_swapped_sidecars_rejected(tmp_path):
    """Swap the two sidecar files after export: each case's returned
    metadata disagrees with the sidecar on disk -> both rejected."""
    corpus = make_corpus(tmp_path, case_ids=("case-a", "case-b"))

    async def fake_drive_all(corpus_root, work_root, runner_cls, settings,
                             *, seed="v1", export_patch_to=None):
        cases = []
        for cid in ("case-a", "case-b"):
            meta = export_candidate_patch(
                export_dir=Path(export_patch_to), case_id=cid,
                patch=f"patch-{cid}".encode(), base_revision="r",
            )
            cases.append({
                "id": cid, "stratum": "s1",
                "adapter_support": "supported", "blocked_reason": None,
                "honest_label": "Not evaluated",
                "honest_reason": "model evaluation not run",
                "plumbing_only": True,
                "patch_export": meta,
                "driver": {"provider": "deterministic-fake"},
            })
        a_sc = Path(export_patch_to) / "case-a.patch.json"
        b_sc = Path(export_patch_to) / "case-b.patch.json"
        a_txt, b_txt = a_sc.read_text(), b_sc.read_text()
        a_sc.write_text(b_txt)
        b_sc.write_text(a_txt)
        return {"cases": cases}

    report, fatal = run_pass(tmp_path, corpus, fake_drive_all)
    assert fatal is None
    for cid in ("case-a", "case-b"):
        row = row_by_id(report, cid)
        assert row["executor"]["invoked"] is False, cid
        assert row["candidate"]["unavailable_reason"] == "candidate_artifact_mutated"
    assert report["report_validity"] == "invalid"
    assert sum(
        "candidate_artifact_mutated" in r for r in report["invalid_reasons"]
    ) == 2


def test_missing_returned_metadata_invalid(tmp_path):
    """A record with no patch_export metadata must not bind on the sidecar
    alone, even if the sidecar exists on disk."""
    corpus = make_corpus(tmp_path, case_ids=("case-a",))

    async def fake_drive_all(corpus_root, work_root, runner_cls, settings,
                             *, seed="v1", export_patch_to=None):
        if export_patch_to is not None:
            # sidecar exists on disk, but the record carries no metadata
            export_candidate_patch(
                export_dir=Path(export_patch_to), case_id="case-a",
                patch=b"bytes", base_revision="r",
            )
        return {"cases": [{
            "id": "case-a", "stratum": "s1",
            "adapter_support": "supported", "blocked_reason": None,
            "honest_label": "Not evaluated",
            "honest_reason": "model evaluation not run",
            "plumbing_only": True,
            "driver": {"provider": "deterministic-fake"},
        }]}

    report, fatal = run_pass(tmp_path, corpus, fake_drive_all)
    assert fatal is None
    row = row_by_id(report, "case-a")
    assert row["executor"]["invoked"] is False
    assert row["executor"]["not_invoked_reason"] == "patch_export_metadata_missing"
    assert report["report_validity"] == "invalid"
    assert any(
        "patch_export_metadata_missing:case-a" in r
        for r in report["invalid_reasons"]
    )


# ---------------------------------------------------------------------------
# Fix 3: shape validation inside global containment
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    None,
    "not-a-dict",
    {"cases": None},
    {"cases": [None]},
    {"cases": [{"id": ["unhashable", "id"]}]},
    {"cases": [{"noid": 1}]},
])
def test_malformed_driver_report_shapes(tmp_path, bad):
    """None / null / [null] / unhashable ids must yield the 20-row invalid
    report with the frozen roster retained, never a traceback."""
    corpus = make_corpus(tmp_path, case_ids=("case-a", "case-b"))

    async def fake_drive_all(corpus_root, work_root, runner_cls, settings,
                             *, seed="v1", export_patch_to=None):
        return bad

    report, fatal = run_pass(tmp_path, corpus, fake_drive_all)
    assert fatal is None
    assert report is not None
    assert report["report_validity"] == "invalid"
    assert len(report["cases"]) == 2
    assert all(r["driver_disposition"] == "unattempted" for r in report["cases"])
    assert all(r["honest_label"] == "Not evaluated" for r in report["cases"])
    assert any("driver_report_shape" in r for r in report["invalid_reasons"])


def test_work_root_unwritable_is_invalid_report(tmp_path):
    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(("case-a",))
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    report, fatal = integ.run_single_pass(
        corpus_root=corpus,
        work_root=blocker,
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
    )
    assert fatal is None
    assert report["report_validity"] == "invalid"
    assert all(r["driver_disposition"] == "unattempted" for r in report["cases"])
    assert any("work_root_unwritable" in r for r in report["invalid_reasons"])


# ---------------------------------------------------------------------------
# Fix 5: driver CLI --export-patches determinism (actual CLI path)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not REAL_CORPUS.exists(), reason="needs real corpus")
def test_driver_cli_export_patches_determinism(tmp_path, monkeypatch):
    """Run the driver's ACTUAL main() with --export-patches: both
    determinism passes must export, so the self-check passes."""
    import sys

    from scripts import crump_code_v2_fake_driver as drv

    monkeypatch.setattr(sys, "argv", [
        "crump_code_v2_fake_driver",
        "--corpus-root", str(REAL_CORPUS),
        "--work-root", str(tmp_path / "w"),
        "--out", str(tmp_path / "report.json"),
        "--seed", "v1",
        "--export-patches", str(tmp_path / "patches"),
    ])
    drv.main()  # must not raise SystemExit
    assert (tmp_path / "patches").is_dir()
    assert (tmp_path / "patches-second").is_dir()
    assert (tmp_path / "report.json").exists()
    first = sorted(p.name for p in (tmp_path / "patches").iterdir())
    second = sorted(p.name for p in (tmp_path / "patches-second").iterdir())
    assert first and first == second


# ---------------------------------------------------------------------------
# Review fixes: pipeline publishes invalid report on directory failures;
# shape failure retains original observations
# ---------------------------------------------------------------------------


def test_pipeline_work_root_is_file_writes_invalid_report(tmp_path):
    """run_pipeline (not just run_single_pass) with work_root as a regular
    file: the frozen-roster invalid report must be published to out_path,
    not a fatal without a report."""
    corpus = make_corpus(tmp_path, case_ids=("case-a", "case-b"))
    fake = make_drive_all(("case-a", "case-b"))
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    out_path = tmp_path / "report.json"
    report, code, fatal = integ.run_pipeline(
        corpus_root=corpus,
        work_root=blocker,
        out_path=out_path,
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
    )
    assert fatal is None, fatal
    assert code == 2
    assert out_path.exists(), "invalid report must be written"
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["report_validity"] == "invalid"
    assert len(written["cases"]) == 2
    for row in written["cases"]:
        assert row["driver_disposition"] == "unattempted"
        assert row["honest_label"] == "Not evaluated"
        assert row["honest_reason"] == "model evaluation not run"
        assert row["candidate"]["available"] is False
        assert row["executor"]["invoked"] is False
    assert any("work_root_unwritable" in r for r in written["invalid_reasons"])
    assert written["fix_rate"] is None
    assert written["aggregate"] == integ.AGGREGATE


def test_pipeline_pass_dir_failure_writes_invalid_report(tmp_path, monkeypatch):
    """Injected pass-directory creation failure: the invalid report is
    published with the directory error retained, exit nonzero."""
    corpus = make_corpus(tmp_path, case_ids=("case-a", "case-b"))
    fake = make_drive_all(("case-a", "case-b"))
    out_path = tmp_path / "report.json"

    def boom(*a, **k):
        raise OSError("injected mkdtemp failure")

    monkeypatch.setattr(integ.tempfile, "mkdtemp", boom)
    report, code, fatal = integ.run_pipeline(
        corpus_root=corpus,
        work_root=tmp_path / "work",
        out_path=out_path,
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
    )
    assert fatal is None, fatal
    assert code == 2
    assert out_path.exists(), "invalid report must be written"
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["report_validity"] == "invalid"
    assert len(written["cases"]) == 2
    assert all(
        r["driver_disposition"] == "unattempted" for r in written["cases"]
    )
    assert all(r["executor"]["invoked"] is False for r in written["cases"])
    assert any(
        "cannot_create_pass_work_dirs" in r for r in written["invalid_reasons"]
    )
    assert written["fix_rate"] is None


def test_shape_failure_retains_original_observations(tmp_path):
    """Mixed input [valid expected, duplicate, unexpected-case, null]:
    the written report must retain the original records with positions and
    malformed diagnostics, extract observed string IDs for completeness
    accounting, and invoke no executor."""
    from scripts.crump_code_v2_executor import FakeBoundaryExecutor

    corpus = make_corpus(tmp_path, case_ids=("case-a", "case-b", "case-c"))
    evaluate_calls = {"n": 0}

    class SpyExecutor(FakeBoundaryExecutor):
        def evaluate(self, *a, **k):
            evaluate_calls["n"] += 1
            return super().evaluate(*a, **k)

    def base_record(cid):
        return {
            "id": cid,
            "stratum": "s1",
            "adapter_support": "supported",
            "blocked_reason": None,
            "honest_label": "Not evaluated",
            "honest_reason": "model evaluation not run",
            "plumbing_only": True,
            "driver": {"provider": "deterministic-fake"},
        }

    async def fake_drive_all(corpus_root, work_root, runner_cls, settings,
                             *, seed="v1", export_patch_to=None):
        return {
            "report": "crump_code_v2_fake_driver",
            "plumbing_evidence_only": True,
            "aggregate": integ.AGGREGATE,
            "fix_rate": None,
            "cases": [
                base_record("case-a"),    # valid expected
                base_record("case-a"),    # duplicate
                base_record("nope-zzz"),  # unexpected-case
                None,                     # malformed -> shape error
            ],
        }

    out_path = tmp_path / "report.json"
    report, code, fatal = integ.run_pipeline(
        corpus_root=corpus,
        work_root=tmp_path / "work",
        out_path=out_path,
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake_drive_all,
        runner_cls=None,
        settings=None,
        executor_factory=SpyExecutor,
    )
    assert fatal is None, fatal
    assert code == 2
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["report_validity"] == "invalid"

    # Original observations retained with positions and diagnostics.
    obs = written["input_observations"]
    assert obs is not None
    recs = obs["records"]
    assert [r["position"] for r in recs] == [0, 1, 2, 3]
    assert recs[0]["observed_id"] == "case-a" and recs[0]["malformed"] is None
    assert recs[1]["observed_id"] == "case-a" and recs[1]["malformed"] is None
    assert recs[2]["observed_id"] == "nope-zzz" and recs[2]["malformed"] is None
    assert recs[3]["observed_id"] is None
    assert "not a JSON object" in recs[3]["malformed"]
    assert recs[0]["record"]["id"] == "case-a"
    assert recs[2]["record"]["id"] == "nope-zzz"
    assert sorted(obs["observed_string_ids"]) == ["case-a", "nope-zzz"]

    # Completeness accounting from observed IDs, even though invalid.
    comp = written["completeness"]
    assert comp["unexpected_ids"] == ["nope-zzz"]
    assert comp["duplicate_ids"] == ["case-a"]
    assert sorted(comp["missing_ids"]) == ["case-b", "case-c"]

    reasons = written["invalid_reasons"]
    assert any("driver_report_shape" in r for r in reasons)
    assert any("unexpected_case_id:nope-zzz" in r for r in reasons)
    assert any("duplicate_case_id:case-a" in r for r in reasons)

    # All rows unattempted; no executor invocation anywhere.
    assert len(written["cases"]) == 3
    for row in written["cases"]:
        assert row["driver_disposition"] == "unattempted"
        assert row["executor"]["invoked"] is False
        assert row["honest_label"] == "Not evaluated"
    assert evaluate_calls["n"] == 0, "no executor invocations on shape failure"
    assert written["fix_rate"] is None
    assert written["aggregate"] == integ.AGGREGATE


def test_pipeline_publish_failure_is_fatal_without_report(tmp_path):
    """work_root unusable AND destination unwritable: no report can be
    published -> fatal diagnostic, no report file. No-report is reserved
    for unusable roster or publication failure only."""
    corpus = make_corpus(tmp_path, case_ids=("case-a",))
    fake = make_drive_all(("case-a",))
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    out_path = blocker / "report.json"  # parent is a file: unwritable
    report, code, fatal = integ.run_pipeline(
        corpus_root=corpus,
        work_root=blocker,
        out_path=out_path,
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
    )
    assert report is None
    assert code == 1
    assert fatal is not None


def test_pipeline_work_root_is_file_writes_nested_invalid_report(tmp_path):
    """Reviewer repro: work_root is an existing regular file and out_path
    parents do not exist yet. The invalid report must be published at the
    nested path (exit 2, no fatal) — not an avoidable fatal without one."""
    from scripts.crump_code_v2_executor import FakeBoundaryExecutor

    corpus = make_corpus(tmp_path, case_ids=("case-a", "case-b"))
    fake = make_drive_all(("case-a", "case-b"))
    evaluate_calls = {"n": 0}

    class SpyExecutor(FakeBoundaryExecutor):
        def evaluate(self, *a, **k):
            evaluate_calls["n"] += 1
            return super().evaluate(*a, **k)

    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    out_path = tmp_path / "new" / "nested" / "report.json"
    assert not out_path.parent.exists()
    report, code, fatal = integ.run_pipeline(
        corpus_root=corpus,
        work_root=blocker,
        out_path=out_path,
        seed="v1",
        expected_manifest_sha=manifest_sha(corpus),
        drive_all_fn=fake,
        runner_cls=None,
        settings=None,
        executor_factory=SpyExecutor,
    )
    assert fatal is None, fatal
    assert code == 2
    assert out_path.exists(), "invalid report must be written at nested path"
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["report_validity"] == "invalid"
    assert sorted(r["id"] for r in written["cases"]) == ["case-a", "case-b"]
    for row in written["cases"]:
        assert row["driver_disposition"] == "unattempted"
        assert row["honest_label"] == "Not evaluated"
        assert row["honest_reason"] == "model evaluation not run"
        assert row["candidate"]["available"] is False
        assert row["executor"]["invoked"] is False
    assert any("work_root_unwritable" in r for r in written["invalid_reasons"])
    assert evaluate_calls["n"] == 0, "zero executor evaluations"
    assert written["fix_rate"] is None
    assert written["aggregate"] == integ.AGGREGATE
