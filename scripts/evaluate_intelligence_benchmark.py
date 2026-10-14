"""Deterministically score content-safe Ask Crump intelligence benchmark results."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "benchmarks" / "intelligence" / "manifest.v1.json"
# This parent is already ignored by the repository. Keep response artifacts local.
REPORT_ROOT = (ROOT / "output" / "crump-code-benchmark" / "intelligence-quality").resolve()

SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
SEMVER = re.compile(r"^1\.[0-9]+\.[0-9]+$")
NUMERIC_REFERENCE = re.compile(r"^[0-9]{1,3}$")
BRACKET_REFERENCE = re.compile(r"\[([^\[\]\r\n]{1,64})\]")
REQUIRED_CATEGORIES = frozenset(
    {
        "instruction-following",
        "grounded-current-research",
        "citation-integrity",
        "memory",
        "tool-choice",
        "artifact-intent",
        "safety-refusal",
        "recovery",
    }
)

TOP_LEVEL_FIELDS = frozenset(
    {"schema_version", "suite_id", "suite_version", "content_safety", "release_gate", "cases"}
)
CONTENT_SAFETY_FIELDS = frozenset(
    {"synthetic_only", "contains_customer_content", "contains_secrets"}
)
RELEASE_GATE_FIELDS = frozenset(
    {
        "minimum_mean_score",
        "minimum_case_score",
        "required_category_pass_rate",
        "critical_categories",
    }
)
CASE_FIELDS = frozenset({"id", "category", "prompt", "context", "evidence", "memory", "expected"})
EVIDENCE_FIELDS = frozenset({"id", "text", "as_of"})
MEMORY_FIELDS = frozenset({"id", "text"})
EXPECTED_FIELDS = frozenset(
    {
        "required_substrings",
        "forbidden_substrings",
        "required_tools",
        "allowed_tools",
        "forbidden_tools",
        "artifact",
        "refusal",
        "recovery_status",
        "required_memory_ids",
        "allowed_memory_ids",
        "line_rules",
        "citations",
    }
)
ARTIFACT_FIELDS = frozenset({"type", "editable"})
LINE_RULE_FIELDS = frozenset({"exact_nonempty_lines", "each_prefix"})
CITATIONS_FIELDS = frozenset({"required", "claims"})
CLAIM_FIELDS = frozenset({"text", "allowed_source_ids"})
RESULT_FIELDS = frozenset({"schema_version", "suite_id", "suite_version", "runs"})
RUN_FIELDS = frozenset({"case_id", "response", "tool_calls", "artifact", "metadata"})
METADATA_FIELDS = frozenset({"refusal", "recovery_status", "memory_used"})

SENSITIVE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[opurs]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._-]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(
        r"(?im)^\s*[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*[=:]\s*\S+"
    ),
)

HARD_FAILURES = frozenset(
    {
        "unexpected_run_field",
        "response_invalid",
        "tool_calls_invalid",
        "artifact_invalid",
        "metadata_invalid",
        "sensitive_response_detected",
        "forbidden_text_present",
        "forbidden_tool_called",
        "tool_not_allowlisted",
        "artifact_mismatch",
        "refusal_mismatch",
        "recovery_status_mismatch",
        "memory_not_allowlisted",
        "citation_required",
        "citation_out_of_range",
        "citation_syntax_invalid",
        "citation_claim_unsupported",
    }
)


class IntelligenceBenchmarkError(ValueError):
    """Raised when a manifest or result artifact fails structural validation."""


def _unknown_fields(value: dict[str, Any], allowed: frozenset[str]) -> list[str]:
    return sorted(str(key) for key in value if key not in allowed)


def _contains_sensitive(value: Any) -> bool:
    text = str(value or "")
    return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SAFE_ID.fullmatch(value):
        raise IntelligenceBenchmarkError(f"{label} must be a safe identifier.")
    return value


def _safe_text(value: Any, label: str, *, minimum: int = 1, maximum: int = 4000) -> str:
    if not isinstance(value, str):
        raise IntelligenceBenchmarkError(f"{label} must be text.")
    text = value.strip()
    if not minimum <= len(text) <= maximum or any(ord(character) < 9 for character in text):
        raise IntelligenceBenchmarkError(f"{label} length or characters are invalid.")
    if _contains_sensitive(text):
        raise IntelligenceBenchmarkError(f"{label} contains a sensitive-token pattern.")
    return text


def _string_list(
    value: Any,
    label: str,
    *,
    maximum_items: int = 20,
    allow_empty: bool = True,
    ids: bool = False,
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items or (not allow_empty and not value):
        raise IntelligenceBenchmarkError(f"{label} must be a bounded list.")
    parsed: list[str] = []
    for item in value:
        parsed.append(_safe_id(item, label) if ids else _safe_text(item, label, maximum=500))
    if len(parsed) != len(set(parsed)):
        raise IntelligenceBenchmarkError(f"{label} must not contain duplicates.")
    return parsed


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IntelligenceBenchmarkError("Benchmark JSON could not be read.") from exc
    if not isinstance(value, dict):
        raise IntelligenceBenchmarkError("Benchmark JSON must be an object.")
    return value


def _validate_expected(
    raw: Any,
    *,
    evidence: list[dict[str, Any]],
    memory: list[dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != EXPECTED_FIELDS:
        raise IntelligenceBenchmarkError("Expected assertions must use the exact v1 shape.")

    required_substrings = _string_list(raw["required_substrings"], "required substrings")
    forbidden_substrings = _string_list(raw["forbidden_substrings"], "forbidden substrings")
    if {_normalized(item) for item in required_substrings} & {
        _normalized(item) for item in forbidden_substrings
    }:
        raise IntelligenceBenchmarkError("Required and forbidden text assertions overlap.")

    required_tools = _string_list(raw["required_tools"], "required tools", ids=True)
    allowed_tools = _string_list(raw["allowed_tools"], "allowed tools", ids=True)
    forbidden_tools = _string_list(raw["forbidden_tools"], "forbidden tools", ids=True)
    if not set(required_tools).issubset(allowed_tools):
        raise IntelligenceBenchmarkError("Required tools must be allowlisted.")
    if set(allowed_tools) & set(forbidden_tools):
        raise IntelligenceBenchmarkError("Allowed and forbidden tools overlap.")

    artifact = raw["artifact"]
    if artifact is not None:
        if not isinstance(artifact, dict) or set(artifact) != ARTIFACT_FIELDS:
            raise IntelligenceBenchmarkError("Artifact assertion shape is invalid.")
        _safe_id(artifact.get("type"), "artifact type")
        if not isinstance(artifact.get("editable"), bool):
            raise IntelligenceBenchmarkError("Artifact editable assertion must be boolean.")

    if not isinstance(raw["refusal"], bool):
        raise IntelligenceBenchmarkError("Refusal assertion must be boolean.")
    recovery_status = raw["recovery_status"]
    if recovery_status not in {None, "retryable", "degraded", "blocked"}:
        raise IntelligenceBenchmarkError("Recovery assertion is invalid.")

    memory_ids = {item["id"] for item in memory}
    required_memory_ids = _string_list(
        raw["required_memory_ids"], "required memory IDs", ids=True
    )
    allowed_memory_ids = _string_list(raw["allowed_memory_ids"], "allowed memory IDs", ids=True)
    if not set(required_memory_ids).issubset(allowed_memory_ids):
        raise IntelligenceBenchmarkError("Required memories must be allowlisted.")
    if not set(allowed_memory_ids).issubset(memory_ids):
        raise IntelligenceBenchmarkError("Memory assertions reference unknown memories.")

    line_rules = raw["line_rules"]
    if line_rules is not None:
        if not isinstance(line_rules, dict) or set(line_rules) != LINE_RULE_FIELDS:
            raise IntelligenceBenchmarkError("Line-rule assertion shape is invalid.")
        line_count = line_rules.get("exact_nonempty_lines")
        if not isinstance(line_count, int) or isinstance(line_count, bool) or not 1 <= line_count <= 20:
            raise IntelligenceBenchmarkError("Line count assertion is invalid.")
        _safe_text(line_rules.get("each_prefix"), "line prefix", maximum=20)

    citations = raw["citations"]
    if not isinstance(citations, dict) or set(citations) != CITATIONS_FIELDS:
        raise IntelligenceBenchmarkError("Citation assertion shape is invalid.")
    if not isinstance(citations["required"], bool) or not isinstance(citations["claims"], list):
        raise IntelligenceBenchmarkError("Citation assertions are invalid.")
    if len(citations["claims"]) > 20:
        raise IntelligenceBenchmarkError("Citation claim list is too large.")
    evidence_by_id = {item["id"]: item for item in evidence}
    claims: list[dict[str, Any]] = []
    for raw_claim in citations["claims"]:
        if not isinstance(raw_claim, dict) or set(raw_claim) != CLAIM_FIELDS:
            raise IntelligenceBenchmarkError("Citation claim shape is invalid.")
        claim_text = _safe_text(raw_claim["text"], "citation claim", maximum=500)
        allowed_source_ids = _string_list(
            raw_claim["allowed_source_ids"],
            "citation source IDs",
            allow_empty=False,
            ids=True,
        )
        if not set(allowed_source_ids).issubset(evidence_by_id):
            raise IntelligenceBenchmarkError("Citation claim references unknown evidence.")
        if not any(
            _normalized(claim_text) in _normalized(evidence_by_id[source_id]["text"])
            for source_id in allowed_source_ids
        ):
            raise IntelligenceBenchmarkError("Citation claim is not present in its evidence.")
        claims.append({"text": claim_text, "allowed_source_ids": allowed_source_ids})
    if citations["required"] != bool(claims):
        raise IntelligenceBenchmarkError("Required citations must define at least one claim.")

    return {
        **raw,
        "required_substrings": required_substrings,
        "forbidden_substrings": forbidden_substrings,
        "required_tools": required_tools,
        "allowed_tools": allowed_tools,
        "forbidden_tools": forbidden_tools,
        "required_memory_ids": required_memory_ids,
        "allowed_memory_ids": allowed_memory_ids,
        "citations": {**citations, "claims": claims},
    }


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the complete v1 benchmark manifest."""
    if set(manifest) != TOP_LEVEL_FIELDS:
        raise IntelligenceBenchmarkError("Manifest must use the exact v1 top-level shape.")
    if manifest.get("schema_version") != 1:
        raise IntelligenceBenchmarkError("Unsupported intelligence benchmark schema.")
    suite_id = _safe_id(manifest.get("suite_id"), "suite ID")
    suite_version = manifest.get("suite_version")
    if not isinstance(suite_version, str) or not SEMVER.fullmatch(suite_version):
        raise IntelligenceBenchmarkError("Suite version must be a v1 semantic version.")

    content_safety = manifest.get("content_safety")
    if not isinstance(content_safety, dict) or set(content_safety) != CONTENT_SAFETY_FIELDS:
        raise IntelligenceBenchmarkError("Content-safety declaration is invalid.")
    if content_safety != {
        "synthetic_only": True,
        "contains_customer_content": False,
        "contains_secrets": False,
    }:
        raise IntelligenceBenchmarkError("The fixed corpus must be synthetic and content-safe.")

    gate = manifest.get("release_gate")
    if not isinstance(gate, dict) or set(gate) != RELEASE_GATE_FIELDS:
        raise IntelligenceBenchmarkError("Release-gate shape is invalid.")
    for field in ("minimum_mean_score", "minimum_case_score"):
        value = gate[field]
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 100:
            raise IntelligenceBenchmarkError("Release score thresholds must be integers from 1 to 100.")
    category_rate = gate["required_category_pass_rate"]
    if not isinstance(category_rate, (int, float)) or isinstance(category_rate, bool):
        raise IntelligenceBenchmarkError("Category pass-rate threshold is invalid.")
    if not 0 < float(category_rate) <= 1:
        raise IntelligenceBenchmarkError("Category pass-rate threshold must be within (0, 1].")
    critical_categories = _string_list(
        gate["critical_categories"], "critical categories", allow_empty=False, ids=True
    )
    if not set(critical_categories).issubset(REQUIRED_CATEGORIES):
        raise IntelligenceBenchmarkError("Critical category is unknown.")

    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list) or not 8 <= len(raw_cases) <= 40:
        raise IntelligenceBenchmarkError("The intelligence corpus must contain 8 to 40 cases.")
    cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_categories: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict) or set(raw_case) != CASE_FIELDS:
            raise IntelligenceBenchmarkError("Benchmark case must use the exact v1 shape.")
        case_id = _safe_id(raw_case.get("id"), "case ID")
        if case_id in seen_ids:
            raise IntelligenceBenchmarkError("Case IDs must be unique.")
        seen_ids.add(case_id)
        category = _safe_id(raw_case.get("category"), "category")
        if category not in REQUIRED_CATEGORIES:
            raise IntelligenceBenchmarkError("Case category is not part of the v1 taxonomy.")
        seen_categories.add(category)
        prompt = _safe_text(raw_case.get("prompt"), "prompt", minimum=20, maximum=2000)
        context = _string_list(raw_case.get("context"), "context", maximum_items=12)

        raw_evidence = raw_case.get("evidence")
        if not isinstance(raw_evidence, list) or len(raw_evidence) > 12:
            raise IntelligenceBenchmarkError("Evidence must be a bounded list.")
        evidence: list[dict[str, Any]] = []
        evidence_ids: set[str] = set()
        for item in raw_evidence:
            if not isinstance(item, dict) or set(item) != EVIDENCE_FIELDS:
                raise IntelligenceBenchmarkError("Evidence entry shape is invalid.")
            source_id = _safe_id(item.get("id"), "evidence ID")
            if source_id in evidence_ids:
                raise IntelligenceBenchmarkError("Evidence IDs must be unique within a case.")
            evidence_ids.add(source_id)
            text = _safe_text(item.get("text"), "evidence text", maximum=2000)
            as_of = item.get("as_of")
            if as_of is not None:
                if not isinstance(as_of, str):
                    raise IntelligenceBenchmarkError("Evidence as-of date is invalid.")
                try:
                    date.fromisoformat(as_of)
                except ValueError as exc:
                    raise IntelligenceBenchmarkError("Evidence as-of date is invalid.") from exc
            evidence.append({"id": source_id, "text": text, "as_of": as_of})

        raw_memory = raw_case.get("memory")
        if not isinstance(raw_memory, list) or len(raw_memory) > 12:
            raise IntelligenceBenchmarkError("Memory must be a bounded list.")
        memory: list[dict[str, str]] = []
        memory_ids: set[str] = set()
        for item in raw_memory:
            if not isinstance(item, dict) or set(item) != MEMORY_FIELDS:
                raise IntelligenceBenchmarkError("Memory entry shape is invalid.")
            memory_id = _safe_id(item.get("id"), "memory ID")
            if memory_id in memory_ids:
                raise IntelligenceBenchmarkError("Memory IDs must be unique within a case.")
            memory_ids.add(memory_id)
            memory.append(
                {"id": memory_id, "text": _safe_text(item.get("text"), "memory text", maximum=1000)}
            )

        expected = _validate_expected(raw_case.get("expected"), evidence=evidence, memory=memory)
        cases.append(
            {
                "id": case_id,
                "category": category,
                "prompt": prompt,
                "context": context,
                "evidence": evidence,
                "memory": memory,
                "expected": expected,
            }
        )
    if seen_categories != REQUIRED_CATEGORIES:
        raise IntelligenceBenchmarkError("Every v1 intelligence category must be represented.")
    return {
        **manifest,
        "suite_id": suite_id,
        "suite_version": suite_version,
        "release_gate": {**gate, "critical_categories": critical_categories},
        "cases": cases,
    }


def _response_segment(response: str, claim: str) -> str:
    """Return the sentence-like segment containing a required claim."""
    normalized_claim = _normalized(claim)
    for segment in re.split(r"(?<=[.!?])\s+|[\r\n]+", response):
        if normalized_claim in _normalized(segment):
            return segment
    return ""


def _citation_sources(
    response: str, evidence: list[dict[str, Any]]
) -> tuple[set[str], set[str]]:
    """Map production-style [1] citations to ordered internal evidence IDs."""
    sources: set[str] = set()
    failures: set[str] = set()
    for raw_reference in BRACKET_REFERENCE.findall(response):
        if not NUMERIC_REFERENCE.fullmatch(raw_reference) or (
            len(raw_reference) > 1 and raw_reference.startswith("0")
        ):
            failures.add("citation_syntax_invalid")
            continue
        number = int(raw_reference)
        if number < 1 or number > len(evidence):
            failures.add("citation_out_of_range")
            continue
        sources.add(evidence[number - 1]["id"])
    return sources, failures


def _case_result(case: dict[str, Any], run: dict[str, Any], minimum_score: int) -> dict[str, Any]:
    failures: list[str] = []
    checks: list[bool] = []

    def check(condition: bool, failure: str) -> None:
        checks.append(bool(condition))
        if not condition:
            failures.append(failure)

    check(not _unknown_fields(run, RUN_FIELDS), "unexpected_run_field")
    response = run.get("response")
    response_valid = isinstance(response, str) and 1 <= len(response.strip()) <= 12000
    check(response_valid, "response_invalid")
    response_text = response if isinstance(response, str) else ""
    check(not _contains_sensitive(response_text), "sensitive_response_detected")
    response_normalized = _normalized(response_text)

    expected = case["expected"]
    for phrase in expected["required_substrings"]:
        check(_normalized(phrase) in response_normalized, "required_text_missing")
    for phrase in expected["forbidden_substrings"]:
        check(_normalized(phrase) not in response_normalized, "forbidden_text_present")

    raw_tools = run.get("tool_calls")
    tools_valid = (
        isinstance(raw_tools, list)
        and len(raw_tools) <= 20
        and all(isinstance(item, str) and SAFE_ID.fullmatch(item) for item in raw_tools)
        and len(raw_tools) == len(set(raw_tools))
    )
    check(tools_valid, "tool_calls_invalid")
    tools = set(raw_tools) if tools_valid else set()
    for tool in expected["required_tools"]:
        check(tool in tools, "required_tool_missing")
    for tool in expected["forbidden_tools"]:
        check(tool not in tools, "forbidden_tool_called")
    check(tools.issubset(expected["allowed_tools"]), "tool_not_allowlisted")

    artifact = run.get("artifact")
    artifact_valid = artifact is None or (
        isinstance(artifact, dict)
        and set(artifact) == ARTIFACT_FIELDS
        and isinstance(artifact.get("type"), str)
        and bool(SAFE_ID.fullmatch(artifact["type"]))
        and isinstance(artifact.get("editable"), bool)
    )
    check(artifact_valid, "artifact_invalid")
    check(artifact_valid and artifact == expected["artifact"], "artifact_mismatch")

    metadata = run.get("metadata")
    metadata_valid = isinstance(metadata, dict) and not _unknown_fields(metadata, METADATA_FIELDS)
    if metadata_valid:
        metadata_valid = (
            isinstance(metadata.get("refusal"), bool)
            and metadata.get("recovery_status") in {None, "retryable", "degraded", "blocked"}
            and isinstance(metadata.get("memory_used"), list)
            and len(metadata["memory_used"]) <= 20
            and all(isinstance(item, str) and SAFE_ID.fullmatch(item) for item in metadata["memory_used"])
            and len(metadata["memory_used"]) == len(set(metadata["memory_used"]))
        )
    check(metadata_valid, "metadata_invalid")
    safe_metadata = metadata if metadata_valid else {
        "refusal": None,
        "recovery_status": None,
        "memory_used": [],
    }
    check(safe_metadata["refusal"] == expected["refusal"], "refusal_mismatch")
    check(
        safe_metadata["recovery_status"] == expected["recovery_status"],
        "recovery_status_mismatch",
    )
    memories_used = set(safe_metadata["memory_used"])
    for memory_id in expected["required_memory_ids"]:
        check(memory_id in memories_used, "required_memory_missing")
    check(
        memories_used.issubset(expected["allowed_memory_ids"]),
        "memory_not_allowlisted",
    )

    line_rules = expected["line_rules"]
    if line_rules is not None:
        lines = [line.rstrip() for line in response_text.splitlines() if line.strip()]
        check(len(lines) == line_rules["exact_nonempty_lines"], "line_count_mismatch")
        check(
            bool(lines) and all(line.startswith(line_rules["each_prefix"]) for line in lines),
            "line_prefix_mismatch",
        )

    citations, citation_failures = _citation_sources(response_text, case["evidence"])
    check("citation_syntax_invalid" not in citation_failures, "citation_syntax_invalid")
    check("citation_out_of_range" not in citation_failures, "citation_out_of_range")
    citation_rules = expected["citations"]
    if citation_rules["required"]:
        check(bool(citations), "citation_required")
    for claim in citation_rules["claims"]:
        segment = _response_segment(response_text, claim["text"])
        segment_citations, segment_failures = _citation_sources(segment, case["evidence"])
        check(
            bool(segment)
            and not segment_failures
            and bool(segment_citations.intersection(claim["allowed_source_ids"])),
            "citation_claim_unsupported",
        )

    total = max(1, len(checks))
    score = round(100 * sum(checks) / total, 2)
    unique_failures = sorted(set(failures))
    hard_failure = bool(set(unique_failures) & HARD_FAILURES)
    passed = score >= minimum_score and not hard_failure
    return {
        "id": case["id"],
        "category": case["category"],
        "score": score,
        "passed": passed,
        "failures": unique_failures,
    }


def evaluate_benchmark(
    manifest_value: dict[str, Any], result_value: dict[str, Any]
) -> dict[str, Any]:
    """Return a content-free deterministic report for one complete result artifact."""
    manifest = validate_manifest(manifest_value)
    if not isinstance(result_value, dict) or _unknown_fields(result_value, RESULT_FIELDS):
        raise IntelligenceBenchmarkError("Result artifact contains unsupported fields.")
    if result_value.get("schema_version") != 1:
        raise IntelligenceBenchmarkError("Result artifact schema version is invalid.")

    suite_failures: list[str] = []
    if result_value.get("suite_id") != manifest["suite_id"]:
        suite_failures.append("wrong_suite")
    if result_value.get("suite_version") != manifest["suite_version"]:
        suite_failures.append("wrong_suite_version")
    raw_runs = result_value.get("runs")
    if not isinstance(raw_runs, list) or len(raw_runs) > 40:
        raise IntelligenceBenchmarkError("Result artifact must contain at most 40 runs.")
    by_id: dict[str, dict[str, Any]] = {}
    for run in raw_runs:
        if not isinstance(run, dict):
            raise IntelligenceBenchmarkError("Every result run must be an object.")
        case_id = run.get("case_id")
        if not isinstance(case_id, str):
            raise IntelligenceBenchmarkError("Every result run needs a case ID.")
        if case_id in by_id:
            suite_failures.append("duplicate_case")
            continue
        by_id[case_id] = run
    expected_ids = {case["id"] for case in manifest["cases"]}
    if set(by_id) - expected_ids:
        suite_failures.append("unknown_case")

    minimum_case_score = manifest["release_gate"]["minimum_case_score"]
    case_results: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        run = by_id.get(case["id"])
        if run is None:
            case_results.append(
                {
                    "id": case["id"],
                    "category": case["category"],
                    "score": 0,
                    "passed": False,
                    "failures": ["missing_run"],
                }
            )
        else:
            case_results.append(_case_result(case, run, minimum_case_score))

    mean_score = round(sum(item["score"] for item in case_results) / len(case_results), 2)
    category_cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in case_results:
        category_cases[item["category"]].append(item)
    category_results: list[dict[str, Any]] = []
    required_rate = float(manifest["release_gate"]["required_category_pass_rate"])
    critical = set(manifest["release_gate"]["critical_categories"])
    for category in sorted(category_cases):
        items = category_cases[category]
        passed_count = sum(1 for item in items if item["passed"])
        pass_rate = round(passed_count / len(items), 4)
        average_score = round(sum(item["score"] for item in items) / len(items), 2)
        category_passed = pass_rate >= required_rate and (
            category not in critical or average_score == 100
        )
        category_results.append(
            {
                "category": category,
                "case_count": len(items),
                "passed_case_count": passed_count,
                "pass_rate": pass_rate,
                "mean_score": average_score,
                "critical": category in critical,
                "passed": category_passed,
            }
        )
        if pass_rate < required_rate:
            suite_failures.append("category_pass_rate_below_threshold")
        if category in critical and average_score != 100:
            suite_failures.append("critical_category_not_perfect")

    if mean_score < manifest["release_gate"]["minimum_mean_score"]:
        suite_failures.append("mean_score_below_threshold")
    if any(item["score"] < minimum_case_score for item in case_results):
        suite_failures.append("case_score_below_threshold")

    unique_suite_failures = sorted(set(suite_failures))
    passed_case_count = sum(1 for item in case_results if item["passed"])
    return {
        "schema_version": 1,
        "suite_id": manifest["suite_id"],
        "suite_version": manifest["suite_version"],
        "case_count": len(case_results),
        "passed_case_count": passed_case_count,
        "mean_score": mean_score,
        "release_threshold": manifest["release_gate"]["minimum_mean_score"],
        "passed": not unique_suite_failures and all(item["passed"] for item in category_results),
        "suite_failures": unique_suite_failures,
        "categories": category_results,
        "cases": case_results,
    }


def _report_path(value: str) -> Path:
    path = Path(value)
    target = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if REPORT_ROOT != target and REPORT_ROOT not in target.parents:
        raise IntelligenceBenchmarkError(
            "Reports must stay under output/crump-code-benchmark/intelligence-quality."
        )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", help="Local synthetic result JSON; do not commit real responses.")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Versioned manifest path.")
    parser.add_argument(
        "--report",
        help="Optional JSON path under output/crump-code-benchmark/intelligence-quality.",
    )
    args = parser.parse_args(argv)
    try:
        report = evaluate_benchmark(
            _load(Path(args.manifest).resolve()),
            _load(Path(args.results).resolve()),
        )
        encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
        if args.report:
            report_path = _report_path(args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(encoded + "\n", encoding="utf-8")
        print(encoded)
        return 0 if report["passed"] else 1
    except IntelligenceBenchmarkError as exc:
        print(
            json.dumps(
                {"passed": False, "suite_failures": ["invalid_benchmark_input"]},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        print(str(exc), file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
