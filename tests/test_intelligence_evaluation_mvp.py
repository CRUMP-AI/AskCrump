from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluate_intelligence_benchmark import (
    IntelligenceBenchmarkError,
    REQUIRED_CATEGORIES,
    _report_path,
    evaluate_benchmark,
    validate_manifest,
)
from scripts import run_intelligence_live_evaluation as live


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "intelligence" / "manifest.v1.json"
PASSING_RESULTS_PATH = (
    ROOT / "benchmarks" / "intelligence" / "fixtures" / "passing_results.v1.json"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest() -> dict:
    return load_json(MANIFEST_PATH)


def load_results() -> dict:
    return load_json(PASSING_RESULTS_PATH)


def run_for(results: dict, case_id: str) -> dict:
    return next(item for item in results["runs"] if item["case_id"] == case_id)


def result_for(report: dict, case_id: str) -> dict:
    return next(item for item in report["cases"] if item["id"] == case_id)


def test_versioned_manifest_is_synthetic_strict_and_covers_every_v1_category():
    manifest = validate_manifest(load_manifest())

    assert manifest["suite_version"] == "1.0.0"
    assert manifest["content_safety"] == {
        "synthetic_only": True,
        "contains_customer_content": False,
        "contains_secrets": False,
    }
    assert {case["category"] for case in manifest["cases"]} == REQUIRED_CATEGORIES
    assert len(manifest["cases"]) == 8


def test_passing_fixture_clears_release_gate_without_echoing_content():
    manifest = load_manifest()
    results = load_results()
    marker = "synthetic-response-marker-never-report"
    run_for(results, "instruction-following-001")["response"] += f"\n{marker}"
    # Preserve the exact two-line constraint while still proving content does not enter reports.
    run_for(results, "instruction-following-001")["response"] = run_for(
        results, "instruction-following-001"
    )["response"].replace(f"\n{marker}", f" {marker}")

    report = evaluate_benchmark(manifest, results)
    encoded = json.dumps(report)

    assert report["passed"] is True
    assert report["passed_case_count"] == 8
    assert report["mean_score"] == 100
    assert all(item["passed"] for item in report["categories"])
    assert marker not in encoded
    assert '"response":' not in encoded
    assert "October 21, 2026" not in encoded


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update({"unknown": True}),
        lambda value: value["cases"][0].update({"unknown": True}),
        lambda value: value["content_safety"].update({"synthetic_only": False}),
        lambda value: value["cases"][0].update({"id": value["cases"][1]["id"]}),
    ],
)
def test_manifest_validation_rejects_drift_and_false_safety_declarations(mutation):
    manifest = load_manifest()
    mutation(manifest)
    with pytest.raises(IntelligenceBenchmarkError):
        validate_manifest(manifest)


def test_manifest_rejects_sensitive_content_and_unsupported_evidence_claims():
    sensitive = load_manifest()
    sensitive["cases"][0]["context"].append(
        "AI_GATEWAY_API_KEY=" + "not-a-real-secret-but-long-enough"
    )
    with pytest.raises(IntelligenceBenchmarkError):
        validate_manifest(sensitive)

    unsupported = load_manifest()
    unsupported["cases"][1]["expected"]["citations"]["claims"][0]["text"] = (
        "A claim absent from its evidence"
    )
    with pytest.raises(IntelligenceBenchmarkError):
        validate_manifest(unsupported)


def test_required_and_forbidden_assertions_fail_without_leaking_values():
    results = load_results()
    marker = "paid social is approved"
    run = run_for(results, "grounded-current-research-001")
    run["response"] = f"{marker} [channel-brief]."

    report = evaluate_benchmark(load_manifest(), results)
    case = result_for(report, "grounded-current-research-001")
    encoded = json.dumps(report)

    assert report["passed"] is False
    assert case["passed"] is False
    assert "required_text_missing" in case["failures"]
    assert "forbidden_text_present" in case["failures"]
    assert marker not in encoded


def test_citation_checks_reject_unknown_and_wrong_sources():
    unknown = load_results()
    run_for(unknown, "citation-integrity-001")["response"] = (
        "The pilot processed 120 test tasks, and 108 met the acceptance rubric "
        "[3]. It did not measure real customer retention [2]."
    )
    unknown_case = result_for(
        evaluate_benchmark(load_manifest(), unknown), "citation-integrity-001"
    )
    assert {"citation_out_of_range", "citation_claim_unsupported"}.issubset(
        unknown_case["failures"]
    )

    wrong = load_results()
    run_for(wrong, "citation-integrity-001")["response"] = (
        "The pilot processed 120 test tasks, and 108 met the acceptance rubric [2]. "
        "It did not measure real customer retention [1]."
    )
    wrong_case = result_for(
        evaluate_benchmark(load_manifest(), wrong), "citation-integrity-001"
    )
    assert "citation_claim_unsupported" in wrong_case["failures"]
    assert wrong_case["passed"] is False


def test_numeric_citations_map_by_evidence_position_and_symbolic_syntax_cannot_pass():
    numeric_report = evaluate_benchmark(load_manifest(), load_results())
    assert result_for(numeric_report, "citation-integrity-001")["failures"] == []
    assert result_for(numeric_report, "grounded-current-research-001")["failures"] == []

    symbolic = load_results()
    run_for(symbolic, "citation-integrity-001")["response"] = (
        "The pilot processed 120 test tasks, and 108 met the acceptance rubric "
        "[performance-note]. It did not measure real customer retention [risk-note]."
    )
    case = result_for(
        evaluate_benchmark(load_manifest(), symbolic), "citation-integrity-001"
    )

    assert case["passed"] is False
    assert "citation_syntax_invalid" in case["failures"]
    assert "citation_required" in case["failures"]
    assert "citation_claim_unsupported" in case["failures"]


@pytest.mark.parametrize("reference", ["[0]", "[3]", "[999]"])
def test_zero_and_out_of_range_numeric_citations_fail(reference: str):
    results = load_results()
    run_for(results, "citation-integrity-001")["response"] = (
        "The pilot processed 120 test tasks, and 108 met the acceptance rubric "
        f"{reference}. It did not measure real customer retention [2]."
    )

    case = result_for(
        evaluate_benchmark(load_manifest(), results), "citation-integrity-001"
    )

    assert case["passed"] is False
    assert "citation_out_of_range" in case["failures"]


def test_leading_zero_citation_is_not_accepted_as_a_production_numeric_marker():
    results = load_results()
    run_for(results, "citation-integrity-001")["response"] = (
        "The pilot processed 120 test tasks, and 108 met the acceptance rubric [01]. "
        "It did not measure real customer retention [2]."
    )
    case = result_for(
        evaluate_benchmark(load_manifest(), results), "citation-integrity-001"
    )

    assert case["passed"] is False
    assert "citation_syntax_invalid" in case["failures"]


def test_tool_memory_artifact_refusal_and_recovery_contracts_fail_closed():
    results = load_results()
    run_for(results, "tool-choice-001")["tool_calls"] = ["image.generate"]
    run_for(results, "memory-boundaries-001")["metadata"]["memory_used"].append(
        "unapproved-memory"
    )
    run_for(results, "artifact-intent-001")["artifact"] = {"type": "pdf", "editable": False}
    run_for(results, "safety-refusal-001")["metadata"]["refusal"] = False
    run_for(results, "recovery-001")["metadata"]["recovery_status"] = None

    report = evaluate_benchmark(load_manifest(), results)

    assert "forbidden_tool_called" in result_for(report, "tool-choice-001")["failures"]
    assert "memory_not_allowlisted" in result_for(report, "memory-boundaries-001")["failures"]
    assert "artifact_mismatch" in result_for(report, "artifact-intent-001")["failures"]
    assert "refusal_mismatch" in result_for(report, "safety-refusal-001")["failures"]
    assert "recovery_status_mismatch" in result_for(report, "recovery-001")["failures"]
    assert report["passed"] is False


def test_candidate_secret_pattern_is_a_hard_failure_and_is_never_reported():
    results = load_results()
    secret = "Authorization: Bearer " + "a" * 32
    run_for(results, "recovery-001")["response"] += f" {secret}"

    report = evaluate_benchmark(load_manifest(), results)
    case = result_for(report, "recovery-001")
    encoded = json.dumps(report)

    assert case["passed"] is False
    assert "sensitive_response_detected" in case["failures"]
    assert secret not in encoded


def test_result_artifact_shape_is_strict_and_missing_cases_fail_release():
    extra = load_results()
    extra["debug"] = True
    with pytest.raises(IntelligenceBenchmarkError):
        evaluate_benchmark(load_manifest(), extra)

    missing = load_results()
    missing["runs"] = missing["runs"][:-1]
    report = evaluate_benchmark(load_manifest(), missing)
    assert report["passed"] is False
    assert "missing_run" in result_for(report, "recovery-001")["failures"]
    assert "case_score_below_threshold" in report["suite_failures"]


def test_unexpected_per_run_field_is_a_hard_release_failure():
    results = load_results()
    run_for(results, "instruction-following-001")["debug"] = "must not be accepted"

    report = evaluate_benchmark(load_manifest(), results)
    case = result_for(report, "instruction-following-001")

    assert case["passed"] is False
    assert "unexpected_run_field" in case["failures"]
    assert report["passed"] is False


@pytest.mark.parametrize("invalid_response", [123, "x" * 12001])
def test_non_string_and_oversized_responses_are_hard_release_failures(invalid_response):
    results = load_results()
    run_for(results, "instruction-following-001")["response"] = invalid_response

    report = evaluate_benchmark(load_manifest(), results)
    case = result_for(report, "instruction-following-001")

    assert case["passed"] is False
    assert "response_invalid" in case["failures"]
    assert report["passed"] is False


@pytest.mark.parametrize(
    "invalid_tools",
    ["web.search", ["web.search", "web.search"], [123], ["not allowed"]],
)
def test_invalid_tool_call_shapes_are_hard_release_failures(invalid_tools):
    results = load_results()
    run_for(results, "tool-choice-001")["tool_calls"] = invalid_tools

    report = evaluate_benchmark(load_manifest(), results)
    case = result_for(report, "tool-choice-001")

    assert case["passed"] is False
    assert "tool_calls_invalid" in case["failures"]
    assert report["passed"] is False


@pytest.mark.parametrize(
    "invalid_artifact",
    ["pptx", {"type": "pptx"}, {"type": "pptx", "editable": "yes"}],
)
def test_invalid_artifact_shapes_are_hard_release_failures(invalid_artifact):
    results = load_results()
    run_for(results, "artifact-intent-001")["artifact"] = invalid_artifact

    report = evaluate_benchmark(load_manifest(), results)
    case = result_for(report, "artifact-intent-001")

    assert case["passed"] is False
    assert "artifact_invalid" in case["failures"]
    assert report["passed"] is False


@pytest.mark.parametrize(
    "invalid_metadata",
    [
        "not-an-object",
        {"refusal": False, "recovery_status": None},
        {"refusal": "false", "recovery_status": None, "memory_used": []},
        {"refusal": False, "recovery_status": None, "memory_used": ["same", "same"]},
    ],
)
def test_invalid_metadata_shapes_are_hard_release_failures(invalid_metadata):
    results = load_results()
    run_for(results, "memory-boundaries-001")["metadata"] = invalid_metadata

    report = evaluate_benchmark(load_manifest(), results)
    case = result_for(report, "memory-boundaries-001")

    assert case["passed"] is False
    assert "metadata_invalid" in case["failures"]
    assert report["passed"] is False


def test_duplicate_and_unknown_runs_are_release_blocking():
    duplicate = load_results()
    duplicate["runs"].append(dict(duplicate["runs"][0]))
    duplicate_report = evaluate_benchmark(load_manifest(), duplicate)
    assert duplicate_report["passed"] is False
    assert "duplicate_case" in duplicate_report["suite_failures"]

    unknown = load_results()
    unknown_run = dict(unknown["runs"][0])
    unknown_run["case_id"] = "unknown-case-001"
    unknown["runs"].append(unknown_run)
    unknown_report = evaluate_benchmark(load_manifest(), unknown)
    assert unknown_report["passed"] is False
    assert "unknown_case" in unknown_report["suite_failures"]


def test_report_path_cannot_escape_existing_ignored_output_boundary():
    allowed = _report_path(
        "output/crump-code-benchmark/intelligence-quality/report.json"
    )
    assert allowed.parent.name == "intelligence-quality"
    with pytest.raises(IntelligenceBenchmarkError):
        _report_path("output/intelligence-quality/report.json")
    with pytest.raises(IntelligenceBenchmarkError):
        _report_path(str(ROOT / "benchmark-report.json"))


def test_package_and_ci_expose_an_offline_evaluator_contract_check():
    package = load_json(ROOT / "package.json")
    command = package["scripts"]["test:intelligence-contract"]
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert command == (
        "python scripts/evaluate_intelligence_benchmark.py "
        "benchmarks/intelligence/fixtures/passing_results.v1.json"
    )
    assert "name: Validate offline intelligence evaluator contract" in workflow
    assert "run: npm run test:intelligence-contract" in workflow
    assert "test:intelligence-gate" not in package["scripts"]
    assert "run_intelligence_live_evaluation.py" not in command
    assert "AI_GATEWAY" not in command


def test_live_gateway_has_no_default_model_and_requires_three_explicit_opt_ins():
    args = live.build_parser().parse_args([str(PASSING_RESULTS_PATH)])
    assert args.model is None
    with pytest.raises(live.LiveEvaluationError):
        live.require_live_authorization(args)

    args.live = True
    args.model = "provider/evaluation-model"
    with pytest.raises(live.LiveEvaluationError):
        live.require_live_authorization(args)
    args.acknowledge_spend = True
    with pytest.raises(live.LiveEvaluationError):
        live.require_live_authorization(args)
    args.confirm_synthetic_only = True
    live.require_live_authorization(args)


def test_ordinary_live_runner_invocation_never_reaches_network(monkeypatch, capsys):
    called = False

    def forbidden_network(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must remain off")

    monkeypatch.setattr(live, "_post_gateway", forbidden_network)
    exit_code = live.main([str(PASSING_RESULTS_PATH)])

    assert exit_code == 2
    assert called is False
    assert "live_evaluation_not_run" in capsys.readouterr().out


def test_live_report_sanitizers_keep_only_numeric_or_boolean_fields():
    answer = live._numeric_answer(
        {
            "probability": 0.97,
            "confidence": 0.8,
            "reasoning": "model prose must not be retained",
            "value": True,
        }
    )
    usage = live._safe_usage(
        {"inputTokens": 12, "outputTokens": 3, "providerMessage": "discard me"}
    )

    assert answer == {"probability": 0.97, "confidence": 0.8, "value": True}
    assert usage == {"inputTokens": 12, "outputTokens": 3}
    assert "reasoning" not in answer


def test_live_report_sanitizers_drop_nan_and_infinity():
    assert live._numeric_answer(float("nan")) == {}
    assert live._numeric_answer(float("inf")) == {}
    assert live._numeric_answer({"probability": float("nan"), "score": float("inf")}) == {}
    assert live._safe_usage(
        {"inputTokens": float("nan"), "outputTokens": float("inf"), "validTokens": 4}
    ) == {"validTokens": 4}
