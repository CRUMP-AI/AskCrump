"""Score fixed Crump Code artifacts without executing or echoing candidate code."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.code_runner import validate_verification_command  # noqa: E402


DEFAULT_MANIFEST = ROOT / "benchmarks" / "crump_code" / "manifest.v1.json"
REPORT_ROOT = (ROOT / "output" / "crump-code-benchmark").resolve()
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
DIFF_HEADER = re.compile(r"^diff --git a/([^\r\n]+) b/([^\r\n]+)$", re.MULTILINE)
FILE_HEADER = re.compile(r"^(?:--- a/|\+\+\+ b/)([^\r\n]+)$", re.MULTILINE)
SENSITIVE_PATTERNS = (
    re.compile(
        r"(?im)^\s*[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PRIVATE)[A-Z0-9_]*\s*[=:]\s*\S+"
    ),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[opurs]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b"),
)
TOP_LEVEL_FIELDS = frozenset(
    {"schema_version", "suite_id", "source", "pass_threshold", "cases"}
)
CASE_FIELDS = frozenset(
    {
        "id",
        "mode",
        "objective",
        "required_paths",
        "allowed_paths",
        "forbidden_paths",
        "required_verifications",
        "summary_terms",
        "limits",
    }
)
ARTIFACT_FIELDS = frozenset({"suite_id", "source_revision", "runs"})
RUN_FIELDS = frozenset(
    {
        "case_id",
        "mode",
        "status",
        "base_revision",
        "result_summary",
        "result_patch",
        "verification",
        "duration_ms",
        "attempt_count",
    }
)
VERIFICATION_FIELDS = frozenset({"command", "returnCode", "stdout", "stderr"})


class BenchmarkConfigError(ValueError):
    pass


def _unknown_fields(value: dict[str, Any], allowed: frozenset[str]) -> list[str]:
    return sorted(str(key) for key in value if key not in allowed)


def _path(value: Any) -> str:
    raw = str(value or "").replace("\\", "/").strip()
    if (
        raw.startswith("/")
        or raw.endswith("/")
        or "//" in raw
        or re.match(r"^[A-Za-z]:/", raw)
        or any(ord(character) < 32 for character in raw)
        or len(raw) > 240
    ):
        raise BenchmarkConfigError("Benchmark paths must stay inside the repository.")
    parsed = PurePosixPath(raw)
    if (
        not raw
        or parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or parsed.parts[0].lower() == ".git"
    ):
        raise BenchmarkConfigError("Benchmark paths must stay inside the repository.")
    return parsed.as_posix()


def _contains_sensitive(value: Any) -> bool:
    text = str(value or "")
    return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BenchmarkConfigError("Benchmark JSON could not be read.") from exc
    if not isinstance(value, dict):
        raise BenchmarkConfigError("Benchmark JSON must be an object.")
    return value


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if _unknown_fields(manifest, TOP_LEVEL_FIELDS):
        raise BenchmarkConfigError("Manifest contains unsupported top-level fields.")
    if manifest.get("schema_version") != 1:
        raise BenchmarkConfigError("Unsupported benchmark schema version.")
    if not isinstance(manifest.get("suite_id"), str):
        raise BenchmarkConfigError("Benchmark suite ID is invalid.")
    suite_id = manifest["suite_id"]
    if not SAFE_ID.fullmatch(suite_id):
        raise BenchmarkConfigError("Benchmark suite ID is invalid.")
    threshold = manifest.get("pass_threshold")
    if not isinstance(threshold, int) or isinstance(threshold, bool) or not 1 <= threshold <= 100:
        raise BenchmarkConfigError("Benchmark pass threshold must be between 1 and 100.")
    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != {"repository_url", "revision"}:
        raise BenchmarkConfigError("Benchmark source must contain repository_url and revision.")
    if source.get("repository_url") != "https://github.com/CRUMP-AI/AskCrump.git":
        raise BenchmarkConfigError("Benchmark source is not the approved public fixture.")
    if not isinstance(source.get("revision"), str):
        raise BenchmarkConfigError("Benchmark revision must be one full Git SHA.")
    revision = source["revision"]
    if not REVISION.fullmatch(revision):
        raise BenchmarkConfigError("Benchmark revision must be one full Git SHA.")

    cases = manifest.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 20:
        raise BenchmarkConfigError("Benchmark must contain between 1 and 20 cases.")
    seen: set[str] = set()
    normalized_cases: list[dict[str, Any]] = []
    for raw_case in cases:
        if not isinstance(raw_case, dict) or _unknown_fields(raw_case, CASE_FIELDS):
            raise BenchmarkConfigError("Benchmark case shape is invalid.")
        if not isinstance(raw_case.get("id"), str):
            raise BenchmarkConfigError("Benchmark case IDs must be unique and safe.")
        case_id = raw_case["id"]
        if not SAFE_ID.fullmatch(case_id) or case_id in seen:
            raise BenchmarkConfigError("Benchmark case IDs must be unique and safe.")
        seen.add(case_id)
        if not isinstance(raw_case.get("mode"), str):
            raise BenchmarkConfigError("Benchmark mode must be plan or implement.")
        mode = raw_case["mode"]
        if mode not in {"plan", "implement"}:
            raise BenchmarkConfigError("Benchmark mode must be plan or implement.")
        if not isinstance(raw_case.get("objective"), str):
            raise BenchmarkConfigError("Benchmark objective is invalid.")
        objective = raw_case["objective"].strip()
        if not 20 <= len(objective) <= 2000 or _contains_sensitive(objective):
            raise BenchmarkConfigError("Benchmark objective is invalid.")

        normalized: dict[str, list[str]] = {}
        for field in ("required_paths", "allowed_paths", "forbidden_paths"):
            values = raw_case.get(field)
            if (
                not isinstance(values, list)
                or len(values) > 40
                or any(not isinstance(item, str) for item in values)
            ):
                raise BenchmarkConfigError("Benchmark path lists are invalid.")
            paths = [_path(item) for item in values]
            if len(paths) != len(set(paths)):
                raise BenchmarkConfigError("Benchmark paths must not repeat.")
            normalized[field] = paths
        if not set(normalized["required_paths"]).issubset(normalized["allowed_paths"]):
            raise BenchmarkConfigError("Required paths must be allowlisted.")
        if set(normalized["allowed_paths"]) & set(normalized["forbidden_paths"]):
            raise BenchmarkConfigError("Allowed and forbidden paths must not overlap.")
        if mode == "plan" and (
            normalized["required_paths"] or normalized["allowed_paths"]
        ):
            raise BenchmarkConfigError("Plan cases must not allow edits.")
        if mode == "implement" and not normalized["required_paths"]:
            raise BenchmarkConfigError("Implement cases must require a source edit.")

        verification = raw_case.get("required_verifications")
        if not isinstance(verification, list) or len(verification) > 10:
            raise BenchmarkConfigError("Required verification list is invalid.")
        required_verification: list[str] = []
        for command in verification:
            if not isinstance(command, str):
                raise BenchmarkConfigError("Required verification command is invalid.")
            command_text = command.strip()
            if not command_text or len(command_text) > 1000:
                raise BenchmarkConfigError("Required verification command is invalid.")
            pieces = shlex.split(command_text, posix=True)
            if not pieces:
                raise BenchmarkConfigError("Required verification command is invalid.")
            try:
                executable, args = validate_verification_command(pieces[0], pieces[1:])
            except ValueError as exc:
                raise BenchmarkConfigError(
                    "Required verification is outside the safe allowlist."
                ) from exc
            canonical = " ".join([executable, *args])
            if canonical != command_text:
                raise BenchmarkConfigError("Required verification is not canonical.")
            required_verification.append(canonical)
        if len(required_verification) != len(set(required_verification)):
            raise BenchmarkConfigError("Required verification commands must not repeat.")
        if mode == "implement" and not required_verification:
            raise BenchmarkConfigError("Implement cases need a required verification.")
        if mode == "plan" and required_verification:
            raise BenchmarkConfigError("Plan cases do not execute verification.")

        terms = raw_case.get("summary_terms")
        if (
            not isinstance(terms, list)
            or not 1 <= len(terms) <= 12
            or any(
                not isinstance(term, str) or not term.strip() or len(term) > 80
                or _contains_sensitive(term)
                for term in terms
            )
        ):
            raise BenchmarkConfigError("Summary evidence terms are invalid.")
        limits = raw_case.get("limits")
        if not isinstance(limits, dict) or set(limits) != {
            "duration_ms",
            "max_attempts",
            "max_patch_bytes",
        }:
            raise BenchmarkConfigError("Benchmark limits are invalid.")
        duration_ms = limits.get("duration_ms")
        max_attempts = limits.get("max_attempts")
        max_patch_bytes = limits.get("max_patch_bytes")
        values = (duration_ms, max_attempts, max_patch_bytes)
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            raise BenchmarkConfigError("Benchmark limits must be integers.")
        if not 1000 <= duration_ms <= 300000 or not 1 <= max_attempts <= 5:
            raise BenchmarkConfigError("Benchmark duration or attempt limit is invalid.")
        if not 0 <= max_patch_bytes <= 200000:
            raise BenchmarkConfigError("Benchmark patch limit is invalid.")
        if (mode == "plan") != (max_patch_bytes == 0):
            raise BenchmarkConfigError("Only plan cases may use a zero patch budget.")

        normalized_cases.append(
            {
                **raw_case,
                **normalized,
                "required_verifications": required_verification,
                "summary_terms": [str(term).strip() for term in terms],
            }
        )
    return {**manifest, "cases": normalized_cases}


def patch_paths(patch: str) -> set[str]:
    if not patch.strip() or "GIT binary patch" in patch or "\x00" in patch:
        return set()
    paths: set[str] = set()
    matches = list(DIFF_HEADER.finditer(patch))
    diff_lines = [line for line in patch.splitlines() if line.startswith("diff --git ")]
    if len(matches) != len(diff_lines):
        return set()
    for match in matches:
        left, right = match.groups()
        if left.startswith('"') or right.startswith('"'):
            return set()
        normalized_left = _path(left)
        normalized_right = _path(right)
        if normalized_left != normalized_right:
            return set()
        paths.add(normalized_right)
    try:
        file_headers = {_path(value) for value in FILE_HEADER.findall(patch)}
    except BenchmarkConfigError:
        return set()
    if file_headers != paths:
        return set()
    return paths


def _verification_failures(case: dict[str, Any], value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > 20:
        return ["verification_shape_invalid"]
    receipts: dict[str, int] = {}
    failures: list[str] = []
    for receipt in value:
        if not isinstance(receipt, dict) or _unknown_fields(receipt, VERIFICATION_FIELDS):
            return ["verification_shape_invalid"]
        if any(not isinstance(receipt.get(field), str) for field in ("command", "stdout", "stderr")):
            return ["verification_shape_invalid"]
        command = receipt["command"]
        return_code = receipt.get("returnCode")
        if not command or not isinstance(return_code, int) or isinstance(return_code, bool):
            return ["verification_shape_invalid"]
        try:
            pieces = shlex.split(command, posix=True)
            executable, args = validate_verification_command(pieces[0], pieces[1:])
            canonical = " ".join([executable, *args])
        except (IndexError, ValueError):
            failures.append("verification_command_invalid")
            continue
        if canonical != command:
            failures.append("verification_command_invalid")
            continue
        if command not in case["required_verifications"]:
            failures.append("verification_unexpected")
        if command in receipts:
            failures.append("verification_duplicate")
        receipts[command] = return_code
        if return_code != 0:
            failures.append("verification_failed")
    for required in case["required_verifications"]:
        if required not in receipts:
            failures.append("verification_missing")
        elif receipts[required] != 0:
            failures.append("required_verification_failed")
    return sorted(set(failures))


def _run_result(case: dict[str, Any], run: dict[str, Any], revision: str) -> dict[str, Any]:
    failures: list[str] = []
    if _unknown_fields(run, RUN_FIELDS):
        failures.append("unexpected_run_field")
    if any(
        not isinstance(run.get(field), str)
        for field in (
            "case_id",
            "mode",
            "status",
            "base_revision",
            "result_summary",
            "result_patch",
        )
    ):
        failures.append("run_shape_invalid")
    if str(run.get("mode") or "") != case["mode"]:
        failures.append("wrong_mode")
    if str(run.get("base_revision") or "") != revision:
        failures.append("wrong_revision")
    if str(run.get("status") or "") != "completed":
        failures.append("not_completed")

    summary = str(run.get("result_summary") or "")
    if not summary.strip() or any(
        term.casefold() not in summary.casefold() for term in case["summary_terms"]
    ):
        failures.append("summary_incomplete")

    patch = str(run.get("result_patch") or "")
    if len(patch.encode("utf-8", errors="replace")) > case["limits"]["max_patch_bytes"]:
        failures.append("patch_too_large")
    paths: set[str] = set()
    if case["mode"] == "plan":
        if patch.strip():
            failures.append("plan_changed_source")
    else:
        try:
            paths = patch_paths(patch)
        except BenchmarkConfigError:
            failures.append("patch_unparseable")
        if not patch.strip():
            failures.append("patch_missing")
        elif not paths or "@@" not in patch:
            failures.append("patch_unparseable")
        if not set(case["required_paths"]).issubset(paths):
            failures.append("required_path_missing")
        if paths - set(case["allowed_paths"]):
            failures.append("path_out_of_scope")
        if paths & set(case["forbidden_paths"]):
            failures.append("forbidden_path_changed")

    failures.extend(_verification_failures(case, run.get("verification")))

    sensitive_values: list[Any] = [summary, patch]
    verification = run.get("verification")
    if isinstance(verification, list):
        for receipt in verification:
            if isinstance(receipt, dict):
                sensitive_values.extend((receipt.get("stdout"), receipt.get("stderr")))
    if any(_contains_sensitive(value) for value in sensitive_values):
        failures.append("sensitive_output_detected")

    duration = run.get("duration_ms")
    if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
        failures.append("duration_invalid")
    elif duration > case["limits"]["duration_ms"]:
        failures.append("duration_limit_exceeded")
    attempts = run.get("attempt_count")
    if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
        failures.append("attempt_count_invalid")
    elif attempts > case["limits"]["max_attempts"]:
        failures.append("attempt_limit_exceeded")

    unique_failures = sorted(set(failures))
    failure_set = set(unique_failures)
    identity_ok = not {
        "run_shape_invalid",
        "unexpected_run_field",
        "wrong_mode",
        "wrong_revision",
    } & failure_set
    status_ok = "not_completed" not in failure_set
    scope_codes = {
        "patch_too_large",
        "patch_missing",
        "patch_unparseable",
        "required_path_missing",
        "path_out_of_scope",
        "forbidden_path_changed",
        "plan_changed_source",
    }
    evidence_codes = {
        "summary_incomplete",
        "verification_shape_invalid",
        "verification_failed",
        "verification_missing",
        "required_verification_failed",
        "verification_command_invalid",
        "verification_unexpected",
        "verification_duplicate",
    }
    efficiency_codes = {
        "duration_invalid",
        "duration_limit_exceeded",
        "attempt_count_invalid",
        "attempt_limit_exceeded",
    }
    score = 0
    score += 20 if status_ok else 0
    score += 15 if identity_ok else 0
    score += 25 if not scope_codes & failure_set else 0
    score += 25 if not evidence_codes & failure_set else 0
    score += 5 if "sensitive_output_detected" not in failure_set else 0
    score += 10 if not efficiency_codes & failure_set else 0
    return {
        "id": case["id"],
        "score": score,
        "passed": not unique_failures,
        "failures": unique_failures,
    }


def evaluate_benchmark(
    manifest_value: dict[str, Any],
    artifact: dict[str, Any],
) -> dict[str, Any]:
    manifest = validate_manifest(manifest_value)
    suite_failures: list[str] = []
    if _unknown_fields(artifact, ARTIFACT_FIELDS):
        suite_failures.append("unexpected_artifact_field")
    if not isinstance(artifact.get("suite_id"), str) or not isinstance(
        artifact.get("source_revision"), str
    ):
        suite_failures.append("artifact_shape_invalid")
    if str(artifact.get("suite_id") or "") != manifest["suite_id"]:
        suite_failures.append("wrong_suite")
    revision = manifest["source"]["revision"]
    if str(artifact.get("source_revision") or "") != revision:
        suite_failures.append("wrong_source_revision")
    raw_runs = artifact.get("runs")
    if not isinstance(raw_runs, list) or len(raw_runs) > 20:
        raise BenchmarkConfigError("Run artifact must contain at most 20 runs.")

    by_id: dict[str, dict[str, Any]] = {}
    for raw_run in raw_runs:
        if not isinstance(raw_run, dict):
            raise BenchmarkConfigError("Every benchmark run must be an object.")
        raw_case_id = raw_run.get("case_id")
        if not isinstance(raw_case_id, str):
            suite_failures.append("run_shape_invalid")
            continue
        case_id = raw_case_id
        if case_id in by_id:
            suite_failures.append("duplicate_case")
            continue
        by_id[case_id] = raw_run
    expected_ids = {case["id"] for case in manifest["cases"]}
    if set(by_id) - expected_ids:
        suite_failures.append("unknown_case")

    results: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        run = by_id.get(case["id"])
        if not run:
            results.append(
                {
                    "id": case["id"],
                    "score": 0,
                    "passed": False,
                    "failures": ["missing_run"],
                }
            )
            continue
        results.append(_run_result(case, run, revision))
    mean_score = round(sum(item["score"] for item in results) / len(results), 2)
    threshold = manifest["pass_threshold"]
    passed_cases = sum(1 for item in results if item["passed"])
    passed = (
        not suite_failures
        and passed_cases == len(results)
        and mean_score >= threshold
    )
    return {
        "schema_version": 1,
        "suite_id": manifest["suite_id"],
        "source_revision": revision,
        "case_count": len(results),
        "passed_case_count": passed_cases,
        "mean_score": mean_score,
        "pass_threshold": threshold,
        "passed": passed,
        "suite_failures": sorted(set(suite_failures)),
        "cases": results,
    }


def _report_path(value: str) -> Path:
    path = Path(value)
    target = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if REPORT_ROOT != target and REPORT_ROOT not in target.parents:
        raise BenchmarkConfigError(
            "Benchmark reports must stay under output/crump-code-benchmark."
        )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", help="Local JSON run artifact; never commit it.")
    parser.add_argument(
        "--report",
        help="Optional JSON output under output/crump-code-benchmark.",
    )
    args = parser.parse_args(argv)
    try:
        report = evaluate_benchmark(
            _load(DEFAULT_MANIFEST),
            _load(Path(args.runs).resolve()),
        )
        encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
        if args.report:
            report_path = _report_path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 0 if report["passed"] else 1
    except BenchmarkConfigError as exc:
        print(
            json.dumps(
                {
                    "passed": False,
                    "suite_failures": ["invalid_benchmark_input"],
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
