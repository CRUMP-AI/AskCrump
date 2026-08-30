from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.evaluate_crump_code_benchmark import (
    BenchmarkConfigError,
    _path,
    _report_path,
    evaluate_benchmark,
    validate_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "crump_code" / "manifest.v1.json"
PINNED_REVISION = "f75ae5c53c167191f7dea7bfbe96d41b04e3add6"


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def patch_for(path: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        "index 1111111..2222222 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )


def passing_artifact(manifest: dict) -> dict:
    runs = []
    for case in manifest["cases"]:
        path = case["required_paths"][0] if case["required_paths"] else ""
        runs.append(
            {
                "case_id": case["id"],
                "mode": case["mode"],
                "status": "completed",
                "base_revision": manifest["source"]["revision"],
                "result_summary": " ".join(case["summary_terms"]),
                "result_patch": patch_for(path) if path else "",
                "verification": [
                    {
                        "command": command,
                        "returnCode": 0,
                        "stdout": "",
                        "stderr": "",
                    }
                    for command in case["required_verifications"]
                ],
                "duration_ms": 1000,
                "attempt_count": 1,
            }
        )
    return {
        "suite_id": manifest["suite_id"],
        "source_revision": manifest["source"]["revision"],
        "runs": runs,
    }


def test_fixed_manifest_is_valid_pinned_and_excluded_from_deployment():
    manifest = validate_manifest(load_manifest())
    assert manifest["source"]["revision"] == PINNED_REVISION
    assert len(manifest["cases"]) == 4
    assert all((ROOT / path).is_file() for case in manifest["cases"] for path in (
        case["required_paths"] + case["forbidden_paths"]
    ))
    vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert "benchmarks/**" in vercel["functions"]["api/index.py"]["excludeFiles"]


def test_all_passing_receipts_score_the_fixed_suite_without_echoing_content():
    manifest = load_manifest()
    artifact = passing_artifact(manifest)
    artifact["runs"][0]["result_summary"] += " private-but-not-secret-marker"
    report = evaluate_benchmark(manifest, artifact)
    encoded = json.dumps(report)
    assert report["passed"] is True
    assert report["passed_case_count"] == 4
    assert report["mean_score"] == 100
    assert all(case == {
        "id": case["id"], "score": 100, "passed": True, "failures": []
    } for case in report["cases"])
    assert "private-but-not-secret-marker" not in encoded
    assert "result_summary" not in encoded
    assert "result_patch" not in encoded


def test_scope_and_sensitive_output_fail_categorically_without_echoing_values():
    manifest = load_manifest()
    artifact = passing_artifact(manifest)
    run = next(item for item in artifact["runs"] if item["case_id"] == "security-headers-001")
    forbidden = manifest["cases"][2]["forbidden_paths"][0]
    secret = "BENCHMARK_TEST_SECRET=" + "not-a-real-secret-value"
    run["result_patch"] = patch_for(forbidden)
    run["verification"][0]["stdout"] = secret
    report = evaluate_benchmark(manifest, artifact)
    result = next(item for item in report["cases"] if item["id"] == "security-headers-001")
    assert result["passed"] is False
    assert {"required_path_missing", "path_out_of_scope", "forbidden_path_changed",
            "sensitive_output_detected"}.issubset(result["failures"])
    encoded = json.dumps(report)
    assert secret not in encoded
    assert forbidden not in encoded


@pytest.mark.parametrize("unsafe", ["/etc/passwd", "../outside.py", "C:/outside.py", "a//b.py"])
def test_manifest_rejects_non_repository_paths(unsafe: str):
    manifest = load_manifest()
    manifest["cases"][0]["required_paths"] = [unsafe]
    manifest["cases"][0]["allowed_paths"] = [unsafe]
    with pytest.raises(BenchmarkConfigError):
        validate_manifest(manifest)
    with pytest.raises(BenchmarkConfigError):
        _path(unsafe)


def test_malformed_patch_and_unsafe_extra_receipt_fail_closed():
    manifest = load_manifest()
    artifact = passing_artifact(manifest)
    run = artifact["runs"][0]
    run["result_patch"] = (
        "diff --git a/C:/escape.py b/C:/escape.py\n"
        "--- a/C:/escape.py\n+++ b/C:/escape.py\n@@ -1 +1 @@\n-x\n+y\n"
    )
    run["verification"].append(
        {"command": "git push", "returnCode": 0, "stdout": "", "stderr": ""}
    )
    report = evaluate_benchmark(manifest, artifact)
    result = report["cases"][0]
    assert result["passed"] is False
    assert "patch_unparseable" in result["failures"]
    assert "verification_command_invalid" in result["failures"]


def test_non_string_run_content_and_receipts_fail_shape_validation():
    manifest = load_manifest()
    artifact = passing_artifact(manifest)
    artifact["runs"][0]["result_patch"] = 123
    artifact["runs"][0]["verification"][0]["stdout"] = []
    report = evaluate_benchmark(manifest, artifact)
    failures = report["cases"][0]["failures"]
    assert "run_shape_invalid" in failures
    assert "verification_shape_invalid" in failures


def test_manifest_path_entries_must_be_strings():
    manifest = load_manifest()
    manifest["cases"][0]["required_paths"] = [123]
    manifest["cases"][0]["allowed_paths"] = [123]
    with pytest.raises(BenchmarkConfigError):
        validate_manifest(manifest)


def test_reports_cannot_escape_the_local_output_boundary():
    allowed = _report_path("output/crump-code-benchmark/report.json")
    assert allowed.parent.name == "crump-code-benchmark"
    with pytest.raises(BenchmarkConfigError):
        _report_path(str(ROOT / "benchmark-report.json"))


def test_evaluator_does_not_execute_candidate_code():
    source = (ROOT / "scripts" / "evaluate_crump_code_benchmark.py").read_text(
        encoding="utf-8"
    )
    assert "import subprocess" not in source
    assert "subprocess." not in source
