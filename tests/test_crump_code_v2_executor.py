"""Tests for the evaluator-owned executor boundary (fake-interface hardening).

PLUMBING EVIDENCE ONLY. These tests prove the boundary refuses correctly:
bad bindings, fabricated/cross-executor/replayed handles, inexact test-ID
sets, digest mismatches, races, and a malicious producer's attempts. They
prove nothing about model capability and nothing about live isolation.
No model is called; no paid infrastructure is used; no candidate code is
executed. Per-case labels stay "Not evaluated (model evaluation not run)";
fix_rate stays null.
"""

from __future__ import annotations

import hashlib
import json
import threading
import uuid
from pathlib import Path

import pytest

from scripts.crump_code_v2_executor import (
    CODE_BINDING_MISMATCH,
    CODE_REPLAYED_HANDLE,
    CODE_UNKNOWN_HANDLE,
    REASON_AGENT_SURFACE_VIOLATION,
    REASON_CANCEL_ACCEPTED,
    REASON_DEADLINE_EXPIRED,
    REASON_DUPLICATE_TEST_ID,
    REASON_EVIDENCE_DIGEST_MISMATCH,
    REASON_EXTRA_TEST_ID,
    REASON_MISSING_TEST_ID,
    REASON_NON_TERMINAL_TEST_RECORD,
    REASON_REFERENCE_BYTES_PRESENT,
    BoundaryRefusal,
    EvidenceBundle,
    FakeBoundaryExecutor,
    FakeClock,
    FrozenRun,
    MaliciousFakeProducer,
    TestRecord,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CORPUS = REPO_ROOT / "benchmarks" / "crump_code" / "real_tasks_v2"

CASES = [
    ("alpha", ["T.test_one", "T.test_two", "T.test_three"]),
    ("beta", ["T.test_a", "T.test_b"]),
]


def make_corpus(root: Path, cases=CASES) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "cases": [{"id": cid, "oracle_test_ids": list(tids)} for cid, tids in cases]
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for cid, _tids in cases:
        oracle_dir = root / "cases" / cid / "oracle"
        oracle_dir.mkdir(parents=True)
        (oracle_dir / "test_hidden.py").write_text(
            f"# hidden oracle for {cid}\n", encoding="utf-8"
        )
        ref_dir = root / "cases" / cid / "reference"
        ref_dir.mkdir(parents=True)
        (ref_dir / "solution.py").write_text(
            f"# reference solution {cid} :: UNIQUE-REF-BLOB-{cid}\n", encoding="utf-8"
        )
    return root


def make_executor(corpus: Path, **kwargs) -> FakeBoundaryExecutor:
    kwargs.setdefault("clock", FakeClock())
    return FakeBoundaryExecutor(corpus, **kwargs)


def make_frozen(
    ex: FakeBoundaryExecutor,
    case_id: str = "alpha",
    candidate: bytes = b"candidate bytes here",
    run_id: str | None = None,
    **overrides,
) -> FrozenRun:
    fields = {
        "run_id": run_id or f"run-{uuid.uuid4().hex[:12]}",
        "case_id": case_id,
        "corpus_manifest_sha": ex.manifest_sha256,
        "candidate_artifact_sha": hashlib.sha256(candidate).hexdigest(),
        "oracle_suite_sha": ex.oracle_suite_sha256,
        "provenance": {"driver": "fake", "note": "untrusted declaration"},
    }
    fields.update(overrides)
    return FrozenRun(**fields)


def make_evidence(
    pairs: list[tuple[str, str]], raw: bytes | None = None
) -> EvidenceBundle:
    records = tuple(TestRecord(test_id=tid, status=st) for tid, st in pairs)
    blob = (
        raw
        if raw is not None
        else json.dumps(
            [(r.test_id, r.status) for r in records], sort_keys=True
        ).encode()
    )
    return EvidenceBundle(
        test_records=records,
        evidence_bytes=blob,
        evidence_sha256=hashlib.sha256(blob).hexdigest(),
    )


def passing_evidence(case_ids=("T.test_one", "T.test_two", "T.test_three")):
    return make_evidence([(tid, "pass") for tid in case_ids])


@pytest.fixture()
def corpus(tmp_path):
    return make_corpus(tmp_path / "corpus")


@pytest.fixture()
def ex(corpus):
    return make_executor(corpus)


# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------


def test_bind_accepts_valid_run_and_returns_handle(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    assert handle.startswith("hdl_")
    # The snapshot is executor-owned: mutating the caller's buffer changes nothing.
    assert ex._registry[handle].candidate_bytes == candidate


def test_bind_rejects_manifest_mismatch(ex):
    frozen = make_frozen(ex, corpus_manifest_sha="0" * 64)
    with pytest.raises(BoundaryRefusal) as err:
        ex.bind(frozen, b"candidate bytes here")
    assert err.value.code == CODE_BINDING_MISMATCH


def test_bind_rejects_artifact_mismatch(ex):
    frozen = make_frozen(ex, candidate_artifact_sha="0" * 64)
    with pytest.raises(BoundaryRefusal) as err:
        ex.bind(frozen, b"candidate bytes here")
    assert err.value.code == CODE_BINDING_MISMATCH


def test_bind_rejects_oracle_suite_mismatch(ex):
    frozen = make_frozen(ex, oracle_suite_sha="0" * 64)
    with pytest.raises(BoundaryRefusal) as err:
        ex.bind(frozen, b"candidate bytes here")
    assert err.value.code == CODE_BINDING_MISMATCH


def test_bind_rejects_wrong_typed_fields(ex):
    frozen = make_frozen(ex, run_id=12345)  # type: ignore[arg-type]
    with pytest.raises(BoundaryRefusal) as err:
        ex.bind(frozen, b"candidate bytes here")
    assert err.value.code == CODE_BINDING_MISMATCH


def test_bind_rejects_duplicate_run_id(ex):
    candidate = b"candidate bytes here"
    frozen = make_frozen(ex, candidate=candidate, run_id="run-once")
    ex.bind(frozen, candidate)
    with pytest.raises(BoundaryRefusal) as err:
        ex.bind(make_frozen(ex, candidate=candidate, run_id="run-once"), candidate)
    assert err.value.code == CODE_BINDING_MISMATCH


def test_bind_rejects_unknown_case_id(ex):
    frozen = make_frozen(ex, case_id="no-such-case")
    with pytest.raises(BoundaryRefusal) as err:
        ex.bind(frozen, b"candidate bytes here")
    assert err.value.code == CODE_BINDING_MISMATCH


def test_bind_snapshots_bytes_and_freezes_provenance(ex):
    mutable = bytearray(b"candidate bytes here")
    provenance = {"driver": "fake", "nested": {"a": [1, 2]}}
    frozen = make_frozen(ex, candidate=bytes(mutable), provenance=provenance)
    handle = ex.bind(frozen, mutable)
    mutable[:] = b"tampered after bind!!!!"
    provenance["nested"]["a"].append(999)
    record = ex._registry[handle]
    assert record.candidate_bytes == b"candidate bytes here"
    assert record.provenance_frozen["nested"]["a"] == (1, 2)
    # Provenance is recorded but never trusted: deep-frozen and immutable.
    with pytest.raises(TypeError):
        record.provenance_frozen["driver"] = "real"  # type: ignore[index]


# ---------------------------------------------------------------------------
# One-use handles
# ---------------------------------------------------------------------------


def test_evaluate_rejects_fabricated_handle(ex):
    with pytest.raises(BoundaryRefusal) as err:
        ex.evaluate("hdl_fabricated_never_issued", passing_evidence())
    assert err.value.code == CODE_UNKNOWN_HANDLE


def test_evaluate_rejects_cross_executor_handle(corpus):
    ex_a = make_executor(corpus)
    ex_b = make_executor(corpus)
    candidate = b"candidate bytes here"
    foreign_handle = ex_b.bind(make_frozen(ex_b, candidate=candidate), candidate)
    with pytest.raises(BoundaryRefusal) as err:
        ex_a.evaluate(foreign_handle, passing_evidence())
    assert err.value.code == CODE_UNKNOWN_HANDLE


def test_evaluate_rejects_replayed_handle(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    first = ex.evaluate(handle, passing_evidence())
    assert first.outcome == "pass"
    with pytest.raises(BoundaryRefusal) as err:
        ex.evaluate(handle, passing_evidence())
    assert err.value.code == CODE_REPLAYED_HANDLE


def test_concurrent_handle_use_executes_exactly_once(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    evidence = passing_evidence()
    barrier = threading.Barrier(8)
    results: list[tuple[str, str]] = []

    def worker():
        barrier.wait()
        try:
            results.append(("ok", ex.evaluate(handle, evidence).outcome))
        except BoundaryRefusal as exc:
            results.append(("refused", exc.code))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    oks = [r for r in results if r[0] == "ok"]
    refused = [r for r in results if r[0] == "refused"]
    assert len(oks) == 1 and oks[0][1] == "pass"
    assert len(refused) == 7
    assert all(code == CODE_REPLAYED_HANDLE for _, code in refused)


# ---------------------------------------------------------------------------
# Exact test IDs, not counts
# ---------------------------------------------------------------------------


def test_pass_requires_exact_ids_all_pass(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    result = ex.evaluate(handle, passing_evidence())
    assert result.outcome == "pass"
    assert result.reason_code is None
    assert result.expected_test_ids == ("T.test_one", "T.test_two", "T.test_three")
    assert [r.test_id for r in result.test_records] == list(result.expected_test_ids)
    assert result.execution_kind == "fake"  # executor-assigned, always


def test_complete_set_with_failure_is_fail(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    evidence = make_evidence(
        [("T.test_one", "pass"), ("T.test_two", "fail"), ("T.test_three", "pass")]
    )
    result = ex.evaluate(handle, evidence)
    assert result.outcome == "fail"
    assert any(r.status == "fail" for r in result.test_records)


def test_duplicate_test_id_is_incomplete(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    evidence = make_evidence(
        [("T.test_one", "pass"), ("T.test_one", "pass"), ("T.test_three", "pass")]
    )
    result = ex.evaluate(handle, evidence)
    assert result.outcome == "incomplete"
    assert result.reason_code == REASON_DUPLICATE_TEST_ID


def test_same_count_substitution_is_incomplete(ex):
    # Same record count, one ID swapped for an unknown one: cannot pass.
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    evidence = make_evidence(
        [("T.test_one", "pass"), ("T.test_two", "pass"), ("T.test_IMPOSTOR", "pass")]
    )
    result = ex.evaluate(handle, evidence)
    assert result.outcome == "incomplete"
    assert result.reason_code in (REASON_EXTRA_TEST_ID, REASON_MISSING_TEST_ID)


def test_missing_test_id_is_incomplete(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    evidence = make_evidence([("T.test_one", "pass"), ("T.test_two", "pass")])
    result = ex.evaluate(handle, evidence)
    assert result.outcome == "incomplete"
    assert result.reason_code == REASON_MISSING_TEST_ID


def test_extra_test_id_is_incomplete(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    evidence = make_evidence(
        [
            ("T.test_one", "pass"),
            ("T.test_two", "pass"),
            ("T.test_three", "pass"),
            ("T.test_sneaky", "pass"),
        ]
    )
    result = ex.evaluate(handle, evidence)
    assert result.outcome == "incomplete"
    assert result.reason_code == REASON_EXTRA_TEST_ID


@pytest.mark.parametrize("status", ["skipped", "error"])
def test_non_terminal_records_cannot_pass(ex, status):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    evidence = make_evidence(
        [("T.test_one", "pass"), ("T.test_two", status), ("T.test_three", "pass")]
    )
    result = ex.evaluate(handle, evidence)
    assert result.outcome == "incomplete"
    assert result.reason_code == REASON_NON_TERMINAL_TEST_RECORD


def test_evidence_digest_mismatch_is_incomplete(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    good = passing_evidence()
    forged = EvidenceBundle(
        test_records=good.test_records,
        evidence_bytes=b"tampered bytes",
        evidence_sha256=good.evidence_sha256,  # declared digest no longer matches
    )
    result = ex.evaluate(handle, forged)
    assert result.outcome == "incomplete"
    assert result.reason_code == REASON_EVIDENCE_DIGEST_MISMATCH


def test_partial_evidence_with_failure_is_incomplete_retaining_failure(ex):
    # Partial evidence containing a failure is still incomplete — and the
    # failure record is retained, not dropped and not upgraded.
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    evidence = make_evidence([("T.test_one", "pass"), ("T.test_two", "fail")])
    result = ex.evaluate(handle, evidence)
    assert result.outcome == "incomplete"
    assert result.reason_code == REASON_MISSING_TEST_ID
    assert ("T.test_two", "fail") in [
        (r.test_id, r.status) for r in result.test_records
    ]


# ---------------------------------------------------------------------------
# Lifecycle: cancel, deadlines, races
# ---------------------------------------------------------------------------


def test_accepted_cancellation_prevents_later_pass(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    assert ex.cancel(handle) == "cancelled"
    # The accepted cancellation consumed the handle: no later pass possible.
    with pytest.raises(BoundaryRefusal) as err:
        ex.evaluate(handle, passing_evidence())
    assert err.value.code == CODE_REPLAYED_HANDLE


def test_cancel_is_terminal_and_immutable(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    assert ex.cancel(handle) == "cancelled"
    assert ex.cancel(handle) == "cancelled"  # second cancel: no-op, stays cancelled


def test_cancel_unknown_handle_refused(ex):
    with pytest.raises(BoundaryRefusal) as err:
        ex.cancel("hdl_nope")
    assert err.value.code == CODE_UNKNOWN_HANDLE


def test_expired_deadline_at_evaluate_is_timeout(tmp_path):
    clock = FakeClock()
    ex = make_executor(
        make_corpus(tmp_path / "corpus-deadline"),
        clock=clock,
        default_deadline_seconds=10.0,
    )
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    clock.advance(11.0)
    result = ex.evaluate(handle, passing_evidence())
    assert result.outcome == "timeout"
    assert result.reason_code == REASON_DEADLINE_EXPIRED


def _gated_evaluate(ex, handle, evidence):
    """Run evaluate with the oracle phase gated so the test can interleave."""
    entered = threading.Event()
    release = threading.Event()
    original = ex._oracle_phase

    def gated(record, ev, surface):
        entered.set()
        assert release.wait(10)
        return original(record, ev, surface)

    ex._oracle_phase = gated
    outcome: dict = {}
    thread = threading.Thread(
        target=lambda: outcome.update(result=ex.evaluate(handle, evidence))
    )
    thread.start()
    assert entered.wait(10)
    return outcome, thread, release


def test_cancel_completion_race_cancel_wins(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    outcome, thread, release = _gated_evaluate(ex, handle, passing_evidence())
    assert ex.cancel(handle) == "cancelled"
    release.set()
    thread.join(10)
    result = outcome["result"]
    assert result.outcome == "cancelled"
    assert result.reason_code == REASON_CANCEL_ACCEPTED


def test_deadline_completion_race_deadline_wins(tmp_path):
    clock = FakeClock()
    ex = make_executor(
        make_corpus(tmp_path / "corpus-deadline-race"),
        clock=clock,
        default_deadline_seconds=10.0,
    )
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    outcome, thread, release = _gated_evaluate(ex, handle, passing_evidence())
    clock.advance(11.0)  # deadline expires mid-evaluation
    release.set()
    thread.join(10)
    result = outcome["result"]
    assert result.outcome == "timeout"
    assert result.reason_code == REASON_DEADLINE_EXPIRED


def test_late_callback_after_terminal_is_ignored(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    first = ex.evaluate(handle, passing_evidence())
    assert first.outcome == "pass"
    # A late callback (second evaluate) is refused; terminal state stands.
    with pytest.raises(BoundaryRefusal) as err:
        ex.evaluate(handle, passing_evidence())
    assert err.value.code == CODE_REPLAYED_HANDLE


def test_timeout_permits_explicitly_partial_evidence(tmp_path):
    clock = FakeClock()
    ex = make_executor(
        make_corpus(tmp_path / "corpus-timeout-partial"),
        clock=clock,
        default_deadline_seconds=10.0,
    )
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    clock.advance(11.0)
    partial = make_evidence([("T.test_one", "pass")])
    result = ex.evaluate(handle, partial)
    assert result.outcome == "timeout"
    assert result.reason_code == REASON_DEADLINE_EXPIRED


# ---------------------------------------------------------------------------
# Execution kind: executor-assigned, always fake
# ---------------------------------------------------------------------------


def test_execution_kind_always_fake_never_caller_upgradable(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    result = ex.evaluate(handle, passing_evidence())
    assert result.execution_kind == "fake"
    # Identity fields come from executor state, not the caller.
    assert result.executor_id == ex.executor_id
    assert isinstance(result.sequence, int) and result.sequence >= 1


# ---------------------------------------------------------------------------
# Revoked surface + reference exclusion (mock-level; see honesty framing)
# ---------------------------------------------------------------------------


def test_revoked_surface_refuses_and_records_attempts(ex):
    surface = ex.agent_surface
    with pytest.raises(BoundaryRefusal) as err:
        surface.invoke("write_file", path="x.py", content="y")
    assert err.value.code == REASON_AGENT_SURFACE_VIOLATION
    assert surface.attempts == ["write_file"]


def test_reference_bytes_in_candidate_never_pass(corpus):
    # A candidate smuggling reference-solution bytes can never pass, even
    # with all-pass evidence. HONESTY NOTE: a byte scan does not prove live
    # isolation; it is a mechanical tripwire in the fake.
    ref_blob = (corpus / "cases" / "alpha" / "reference" / "solution.py").read_bytes()
    smuggled = b"candidate bytes here\n" + ref_blob
    ex = make_executor(corpus)
    handle = ex.bind(make_frozen(ex, candidate=smuggled), smuggled)
    result = ex.evaluate(handle, passing_evidence())
    assert result.outcome == "incomplete"
    assert result.reason_code == REASON_REFERENCE_BYTES_PRESENT


# ---------------------------------------------------------------------------
# Malicious fake producer
# ---------------------------------------------------------------------------


def test_malicious_producer_replay_refused(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    producer = MaliciousFakeProducer(ex)
    assert producer.replay_handle(handle, passing_evidence()) == CODE_REPLAYED_HANDLE


def test_malicious_producer_fabricated_handle_refused(ex):
    producer = MaliciousFakeProducer(ex)
    assert producer.use_fabricated_handle(passing_evidence()) == CODE_UNKNOWN_HANDLE


def test_malicious_producer_cross_executor_handle_refused(corpus):
    ex_a = make_executor(corpus)
    ex_b = make_executor(corpus)
    candidate = b"candidate bytes here"
    foreign = ex_b.bind(make_frozen(ex_b, candidate=candidate), candidate)
    producer = MaliciousFakeProducer(ex_a)
    assert (
        producer.use_foreign_handle(foreign, passing_evidence()) == CODE_UNKNOWN_HANDLE
    )


def test_malicious_producer_forged_evidence_is_incomplete(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    producer = MaliciousFakeProducer(ex)
    result = producer.submit_forged_evidence(handle, passing_evidence(), b"forged!!")
    assert result.outcome == "incomplete"
    assert result.reason_code == REASON_EVIDENCE_DIGEST_MISMATCH


def test_malicious_producer_smuggled_extra_test_is_incomplete(ex):
    candidate = b"candidate bytes here"
    handle = ex.bind(make_frozen(ex, candidate=candidate), candidate)
    producer = MaliciousFakeProducer(ex)
    result = producer.smuggle_extra_test(handle, passing_evidence(), "T.test_sneaky")
    assert result.outcome == "incomplete"
    assert result.reason_code == REASON_EXTRA_TEST_ID


def test_malicious_producer_revoked_tools_refused(ex):
    producer = MaliciousFakeProducer(ex)
    assert producer.invoke_revoked_tools() == REASON_AGENT_SURFACE_VIOLATION


# ---------------------------------------------------------------------------
# Determinism across fresh run IDs (semantic, not timestamps/IDs)
# ---------------------------------------------------------------------------


def _semantic(result):
    return (
        result.outcome,
        result.reason_code,
        tuple((r.test_id, r.status) for r in result.test_records),
        result.expected_test_ids,
        result.execution_kind,
    )


def test_determinism_across_fresh_run_ids(ex):
    candidate = b"candidate bytes here"
    evidence = make_evidence(
        [("T.test_one", "pass"), ("T.test_two", "fail"), ("T.test_three", "pass")]
    )
    seen = set()
    for _ in range(2):
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        assert run_id not in seen
        seen.add(run_id)
        handle = ex.bind(make_frozen(ex, candidate=candidate, run_id=run_id), candidate)
        result = ex.evaluate(handle, evidence)
        assert _semantic(result) == (
            "fail",
            None,
            (
                ("T.test_one", "pass"),
                ("T.test_two", "fail"),
                ("T.test_three", "pass"),
            ),
            ("T.test_one", "T.test_two", "T.test_three"),
            "fake",
        )


# ---------------------------------------------------------------------------
# Integration: real frozen corpus
# ---------------------------------------------------------------------------


def test_real_corpus_binds_with_frozen_digests():
    ex = make_executor(REAL_CORPUS, clock=FakeClock())
    assert len(ex._expected_ids) == 20
    # Oracle suite digest is stable across executor instances.
    ex2 = make_executor(REAL_CORPUS, clock=FakeClock())
    assert ex.oracle_suite_sha256 == ex2.oracle_suite_sha256
    # A real case binds and its expected IDs match the frozen manifest.
    case_id = "activity-latest"
    manifest = json.loads((REAL_CORPUS / "manifest.json").read_text(encoding="utf-8"))
    expected = next(
        c["oracle_test_ids"] for c in manifest["cases"] if c["id"] == case_id
    )
    assert list(ex.expected_test_ids(case_id)) == expected
    candidate = b"candidate bytes for activity-latest"
    handle = ex.bind(make_frozen(ex, case_id=case_id, candidate=candidate), candidate)
    assert handle.startswith("hdl_")


def test_honest_labels_untouched_by_executor():
    # The executor changes nothing about per-case labels: the committed
    # status record still says exactly what the status generator wrote.
    status = (
        REPO_ROOT / "benchmarks" / "crump_code" / "real_tasks_v2" / "status.v2.json"
    )
    record = json.loads(status.read_text(encoding="utf-8"))
    assert (
        record["aggregate"]
        == "Model evaluation not run; 0 cases evaluated; fix rate unavailable"
    )
    assert record["fix_rate"] is None
    assert len(record["cases"]) == 20
    assert all(c["label"] == "Not evaluated" for c in record["cases"])
    assert all(c["reason"] == "model evaluation not run" for c in record["cases"])
