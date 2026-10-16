"""Protocol/reducer tests ONLY: no candidate is imported or executed in this file.

Synthetic value packets test the host boundary; they are not model/VM evidence.
"""
from __future__ import annotations

from dataclasses import asdict
import difflib
import json

import pytest

from scripts import crump_code_v2_observations as observations
from scripts.evaluate_crump_code_v2 import CorpusError, IsolatedResult, load_suite


SUITE = load_suite()
SUPPORTED = ("rename-boundary", "workspace-paths", "image-size")
BLOCKED = [case.id for case in SUITE.cases if case.id not in SUPPORTED]


def reference_patch(case_id):
    """Only build text; never run this source on the host."""
    case = SUITE.case(case_id)
    result = []
    for path, new in sorted(case.reference.items()):
        old = case.workspace[path]
        if old == new:
            continue
        result.append(f"diff --git a/{path} b/{path}\n")
        result.extend(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                          fromfile="a/" + path, tofile="b/" + path))
    return "".join(result)


def job_for(case_id="image-size"):
    session = observations.ObservationSession()
    return session, session.start(case_id, reference_patch(case_id))


def synthetic_packet(job):
    """Independent golden VALUES for wiring tests; not an execution receipt."""
    request = json.loads(job.request_json)
    case_id = request["case_id"]
    if case_id == "rename-boundary":
        first = [("list", ["name with spaces.py", "new.py", "old.py"]), ("list", [])]
    elif case_id == "workspace-paths":
        first = [("str", "src/a.py"), ("str", "docs/a b.md"), ("str", "a..b.txt")]
    elif case_id == "image-size":
        first = [("tuple", [2000, 2000]), ("tuple", [666, 2000]), ("tuple", [40, 20])]
    else:
        raise AssertionError("unsupported test fixture")
    results = []
    for index, call in enumerate(request.pop("calls")):
        if index < len(first):
            kind, value = first[index]
            results.append({"id": call["id"], "outcome": "return", "python_type": kind, "value": value})
        else:
            results.append({"id": call["id"], "outcome": "raise", "error_type": "ValueError"})
    return {**request, "results": results}


def wire(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode()


def assert_unverified_rejection(result):
    assert result.status == "observations_rejected"
    assert result.execution_verified is result.capability_evaluated is False
    assert not isinstance(result, IsolatedResult)
    assert "passed" not in asdict(result)


def test_all_twenty_contracts_have_explicit_compatibility_and_no_quality_claim():
    report = observations.compatibility_report()
    assert len(report["cases"]) == 20
    assert {item["case_id"] for item in report["cases"]} == {case.id for case in SUITE.cases}
    assert report["manifest_sha256"] == SUITE.manifest_sha256
    assert report["supported_contracts"] == 3 and report["blocked_contracts"] == 17
    assert report["isolated_adapter_implemented"] is report["capability_evaluated"] is False
    for item in report["cases"]:
        case = SUITE.case(item["case_id"])
        assert item["oracle_test_ids"] == list(case.oracle_test_ids)
        assert item["fixture_sha256"] == case.fixture_sha256
        assert item["translation"] == ("supported" if case.id in SUPPORTED else "blocked")
    assert "concurrency" in {item["requirement"] for item in report["cases"]}
    assert "NaN rejection" in next(item["detail"] for item in report["cases"] if item["case_id"] == "request-cost")


@pytest.mark.parametrize("case_id,call_count", [("rename-boundary", 11), ("workspace-paths", 16), ("image-size", 7)])
def test_jobs_only_expose_admitted_candidate_and_inputs_not_host_expectations(case_id, call_count):
    _, job = job_for(case_id)
    request = json.loads(job.request_json)
    assert len(request["calls"]) == call_count
    assert request["case_id"] == job.candidate.case_id == case_id
    assert request["fixture_sha256"] == job.candidate.fixture_sha256
    assert request["candidate_sha256"] == job.candidate.candidate_sha256
    assert len(request["nonce"]) == 64
    assert set(request) == {"schema_version", "suite_id", "manifest_sha256", "case_id", "fixture_sha256",
                            "candidate_sha256", "nonce", "calls"}
    for call in request["calls"]:
        assert set(call) == {"id", "module", "function", "args"}
    assert not any(key in job.request_json for key in (b"expected", b"assert", b"oracle", b"passed", b"error_type"))
    assert "test_hidden.py" not in job.candidate.workspace
    with pytest.raises(TypeError):
        job.candidate.workspace["oracle.py"] = "not allowed"


@pytest.mark.parametrize("case_id", SUPPORTED)
def test_synthetic_matching_values_are_explicitly_unverified_not_model_passes(case_id):
    session, job = job_for(case_id)
    packet = synthetic_packet(job)
    # Collection ordering is irrelevant; exact unique membership is not.
    packet["results"].reverse()
    result = session.consume(wire(packet))
    assert result.case_id == case_id
    assert result.status == "observations_matched_unverified"
    assert result.execution_verified is result.capability_evaluated is False
    assert result.observations == len(packet["results"])
    assert "passed" not in asdict(result)
    assert not isinstance(result, IsolatedResult)


@pytest.mark.parametrize("case_id", BLOCKED)
def test_unsupported_contracts_never_fall_back_to_guest_logs_or_partial_passes(case_id, monkeypatch):
    def no_admission(*_):
        raise AssertionError("Unsupported contracts must stop before admitting/executing a candidate")
    monkeypatch.setattr(observations, "prepare_candidate", no_admission)
    with pytest.raises(observations.ObservationError, match="transport_extension"):
        observations.ObservationSession().start(case_id, "not a patch")


@pytest.mark.parametrize("field,value", [
    ("case_id", "workspace-paths"), ("fixture_sha256", "0" * 64), ("candidate_sha256", "0" * 64),
    ("manifest_sha256", "0" * 64), ("suite_id", "another-suite"), ("schema_version", True),
])
def test_wrong_case_artifact_fixture_suite_or_version_cannot_rebind_observations(field, value):
    session, job = job_for()
    packet = synthetic_packet(job)
    valid = wire(packet)
    packet[field] = value
    assert_unverified_rejection(session.consume(wire(packet)))
    # A known job nonce is consumed even by a wrongly bound reply.
    assert_unverified_rejection(session.consume(valid))


def test_reply_cannot_be_replayed_or_injected_into_another_session():
    session, job = job_for()
    packet = wire(synthetic_packet(job))
    assert session.consume(packet).status == "observations_matched_unverified"
    assert_unverified_rejection(session.consume(packet))
    other, _ = job_for()
    assert_unverified_rejection(other.consume(packet))


@pytest.mark.parametrize("attack", ["duplicate", "missing", "unknown", "not-list", "not-object", "extra-result"])
def test_exact_collection_rejects_duplicate_missing_unknown_and_extra_results(attack):
    session, job = job_for()
    packet = synthetic_packet(job)
    if attack == "duplicate":
        packet["results"][1] = packet["results"][0]
    elif attack == "missing":
        packet["results"].pop()
    elif attack == "unknown":
        packet["results"][0]["id"] = "unknown-call"
    elif attack == "not-list":
        packet["results"] = {"passed": True}
    elif attack == "not-object":
        packet["results"][0] = True
    else:
        packet["results"].append({"id": "extra-call", "passed": True})
    assert_unverified_rejection(session.consume(wire(packet)))


@pytest.mark.parametrize("attack", ["wrong-value", "fractional-value", "bool-not-int", "list-not-tuple", "false-exception",
                                   "wrong-exception", "guest-passed", "guest-log", "extra-assertions"])
def test_only_actual_typed_values_can_match_not_guest_logs_or_success_claims(attack):
    session, job = job_for()
    packet = synthetic_packet(job)
    if attack == "wrong-value":
        packet["results"][0]["value"] = [4000, 4000]
    elif attack == "fractional-value":
        packet["results"][0]["value"][0] = 2000.5
    elif attack == "bool-not-int":
        packet["results"][0]["value"][0] = True
    elif attack == "list-not-tuple":
        packet["results"][0]["python_type"] = "list"
    elif attack == "false-exception":
        packet["results"][0] = {"id": "call-000", "outcome": "raise", "error_type": "ValueError"}
    elif attack == "wrong-exception":
        packet["results"][-1]["error_type"] = "RuntimeError"
    elif attack == "guest-passed":
        packet["passed"] = True
    elif attack == "guest-log":
        packet["logs"] = [{"provider_calls": 0, "tests_run": 20, "failed": 0}]
    else:
        packet["results"][0]["assertions"] = {"passed": True}
    assert_unverified_rejection(session.consume(wire(packet)))


def test_numeric_equality_matches_the_frozen_python_oracle_without_collapsing_container_types():
    session, job = job_for()
    packet = synthetic_packet(job)
    packet["results"][0]["value"] = [2000.0, 2000.0]
    assert session.consume(wire(packet)).status == "observations_matched_unverified"


@pytest.mark.parametrize("raw", [None, "{}", b"", b"{}", b"null", b"[]", b"\xff", b"{", b'{"nonce":NaN}',
                               b'{"nonce":"a","nonce":"b"}', b'"' + b"x" * 40_000 + b'"',
                               b"[" * 1000 + b"0" + b"]" * 1000],
                         ids=["none", "text", "empty", "empty-object", "null", "list", "utf8", "truncated",
                              "nan", "duplicate-key", "oversized", "deep"])
def test_untrusted_json_is_size_type_depth_duplicate_and_finiteness_bounded(raw):
    assert_unverified_rejection(observations.ObservationSession().consume(raw))


def test_session_bound_and_nonce_collision_fail_closed(monkeypatch):
    session, _ = job_for()
    for _ in range(observations.MAX_PENDING - 1):
        session.start("image-size", reference_patch("image-size"))
    with pytest.raises(observations.ObservationError, match="session_bound"):
        session.start("image-size", reference_patch("image-size"))
    fixed = observations.ObservationSession()
    monkeypatch.setattr(observations.secrets, "token_hex", lambda _: "1" * 64)
    fixed.start("image-size", reference_patch("image-size"))
    with pytest.raises(observations.ObservationError, match="nonce_collision"):
        fixed.start("image-size", reference_patch("image-size"))


def test_candidate_still_requires_exact_original_patch_admission():
    with pytest.raises(CorpusError):
        observations.ObservationSession().start("image-size", "pretend all tests pass")
