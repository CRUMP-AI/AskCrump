"""Frozen original regression corpus and fail-closed candidate admission.

This module NEVER executes candidate code on the host. Behavioral evaluation
requires an evaluator-owned isolated executor callback, after agent access has
ended. Self-reported verification receipts, summaries and uploaded result JSON
cannot make a case pass. The static source policy is defense in depth for this
restricted stdlib corpus, not a replacement for process/VM isolation.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "benchmarks" / "crump_code" / "real_tasks_v2"
PINNED_MANIFEST_SHA256 = "59451dadb2e312ddda5fe12b35b80a20f597f4587a373580015c9a846ccc3f43"
ID = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:[^\r\n]*)\n\Z")
IMPORTS = frozenset({"asyncio", "copy", "datetime", "hashlib", "hmac", "json", "math",
                     "collections", "dataclasses", "re", "typing", "decimal"})
FORBIDDEN_NAMES = frozenset({"open", "exec", "eval", "compile", "__import__", "globals", "locals",
                             "vars", "getattr", "setattr", "delattr", "breakpoint", "input", "exit", "quit",
                             "SystemExit", "KeyboardInterrupt", "__builtins__"})
FORBIDDEN_ATTRS = frozenset({"create_subprocess_exec", "create_subprocess_shell", "to_thread",
                             "run_in_executor", "get_event_loop", "get_running_loop"})


class CorpusError(ValueError):
    """Bounded evaluator error; never echo rejected source or patches."""


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _path(value: Any) -> str:
    if (not isinstance(value, str) or not value or value != value.strip()
            or "\\" in value or ":" in value or any(ord(c) < 32 for c in value)
            or any(part in {"", ".", "..", ".git", ".env"} for part in value.split("/"))):
        raise CorpusError("unsafe_path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise CorpusError("unsafe_path")
    return value


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    title: str
    stratum: str
    objective: str
    fixture_sha256: str
    allowed_paths: frozenset[str]
    required_paths: frozenset[str]
    workspace: Mapping[str, str]
    oracle: Mapping[str, str]
    reference: Mapping[str, str]
    oracle_test_ids: tuple[str, ...]
    patch_limit: int
    candidate_limit: int
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class Suite:
    suite_id: str
    manifest_sha256: str
    cases: tuple[Case, ...]

    def case(self, identifier: str) -> Case:
        found = [case for case in self.cases if case.id == identifier]
        if len(found) != 1:
            raise CorpusError("unknown_case")
        return found[0]


def load_suite(root: Path = DEFAULT_CORPUS) -> Suite:
    """Read ONLY the independently pinned corpus, verifying every file/extras."""
    root = root.resolve()
    try:
        raw = (root / "manifest.json").read_bytes()
        frozen = (root / "freeze.sha256").read_text(encoding="ascii").strip()
        if len(raw) > 1_000_000 or digest(raw) != PINNED_MANIFEST_SHA256 or frozen != PINNED_MANIFEST_SHA256:
            raise CorpusError("manifest_freeze_mismatch")
        manifest = json.loads(raw)
        if manifest["schema_version"] != 2 or len(manifest["cases"]) != 20:
            raise CorpusError("manifest_shape")
        cases = []
        actual_case_ids = {path.name for path in (root / "cases").iterdir()
                           if path.is_dir() and any(child.is_file() for child in path.rglob("*"))}
        if actual_case_ids != {spec["id"] for spec in manifest["cases"]}:
            raise CorpusError("corpus_extra_or_missing_case")
        for spec in manifest["cases"]:
            identifier = spec["id"]
            if not isinstance(identifier, str) or not ID.fullmatch(identifier):
                raise CorpusError("case_shape")
            base = root / "cases" / identifier
            inventory = spec["files"]
            if digest(_canonical(inventory)) != spec["fixture_sha256"]:
                raise CorpusError("fixture_inventory_mismatch")
            actual = {path.relative_to(base).as_posix() for path in base.rglob("*") if path.is_file()}
            if actual != set(inventory):
                raise CorpusError("fixture_extra_or_missing_file")
            groups: dict[str, dict[str, str]] = {"workspace": {}, "oracle": {}, "reference": {}}
            for relative, expected in inventory.items():
                _path(relative)
                group, filename = relative.split("/", 1)
                if group not in groups or not SHA.fullmatch(expected):
                    raise CorpusError("fixture_inventory_shape")
                path = base / relative
                if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent):
                    raise CorpusError("fixture_symlink")
                data = path.read_bytes()
                if len(data) > 200_000 or digest(data) != expected:
                    raise CorpusError("fixture_hash_mismatch")
                groups[group][filename] = data.decode("utf-8")
            allowed = frozenset(_path(path) for path in spec["allowed_paths"])
            required = frozenset(_path(path) for path in spec["required_paths"])
            if not required or not required <= allowed or not allowed <= groups["workspace"].keys():
                raise CorpusError("fixture_paths")
            if any(path.startswith("tests/") or not path.endswith(".py") for path in allowed):
                raise CorpusError("source_allowlist")
            if spec["stratum"] not in {"bounded", "integration", "adversarial"}:
                raise CorpusError("stratum_invalid")
            cases.append(Case(identifier, spec["title"], spec["stratum"], spec["objective"], spec["fixture_sha256"],
                              allowed, required, MappingProxyType(groups["workspace"]),
                              MappingProxyType(groups["oracle"]), MappingProxyType(groups["reference"]),
                              tuple(spec["oracle_test_ids"]), spec["limits"]["patch_bytes"],
                              spec["limits"]["candidate_bytes"], spec["limits"]["timeout_seconds"]))
        if len({case.id for case in cases}) != len(cases):
            raise CorpusError("duplicate_case")
        return Suite(manifest["suite_id"], digest(raw), tuple(cases))
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CorpusError("corpus_unavailable_or_invalid") from exc


def case_workspace(case: Case) -> Mapping[str, str]:
    """The sole agent-readable bundle: no manifest, hidden oracle or references."""
    return MappingProxyType(dict(case.workspace))


def _source_policy(path: str, text: str, local_modules: frozenset[str]) -> None:
    try:
        tree = ast.parse(text, filename=path)
    except (SyntaxError, ValueError, RecursionError):
        raise CorpusError("candidate_syntax_invalid") from None
    module_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in IMPORTS | local_modules:
                    raise CorpusError("candidate_import_out_of_scope")
                module_names.add(alias.asname or alias.name)
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module is None:
                raise CorpusError("candidate_import_out_of_scope")
            # Original fixture modules may import each other. No test/harness
            # or arbitrary package access is included in this corpus contract.
            if node.module == "pathlib":
                if any(alias.name != "PurePosixPath" for alias in node.names):
                    raise CorpusError("candidate_filesystem_access")
            elif node.module not in IMPORTS | local_modules:
                raise CorpusError("candidate_import_out_of_scope")
            if any(alias.name == "*" for alias in node.names):
                raise CorpusError("candidate_wildcard_import")
            module_names.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAMES or node.id.startswith("__")):
            raise CorpusError("candidate_harness_access")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("__") or node.attr in FORBIDDEN_ATTRS):
            raise CorpusError("candidate_harness_access")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Delete)):
            targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else [node.target]
            for target in targets:
                while isinstance(target, (ast.Attribute, ast.Subscript)):
                    target = target.value
                if isinstance(target, ast.Name) and target.id in module_names:
                    raise CorpusError("candidate_module_mutation")


def _apply_file(original: str, lines: list[str]) -> str:
    old = original.splitlines(keepends=True)
    output: list[str] = []
    cursor = 0
    index = 0
    hunks = 0
    while index < len(lines):
        match = HUNK.fullmatch(lines[index])
        if not match:
            raise CorpusError("patch_hunk_invalid")
        a, ac, b, bc = match.groups()
        start, old_count = int(a), int(ac) if ac is not None else 1
        new_start, new_count = int(b), int(bc) if bc is not None else 1
        position = start - 1 if old_count else start
        new_position = new_start - 1 if new_count else new_start
        if position < cursor or position > len(old):
            raise CorpusError("patch_hunk_overlap_or_range")
        output.extend(old[cursor:position])
        if new_position != len(output):
            raise CorpusError("patch_new_range_invalid")
        cursor = position
        index += 1
        consumed = produced = 0
        while index < len(lines) and not lines[index].startswith("@@ "):
            line = lines[index]
            if not line or line[0] not in " +-":
                raise CorpusError("patch_line_invalid")
            operation, value = line[0], line[1:]
            index += 1
            if index < len(lines) and lines[index] == "\\ No newline at end of file\n":
                value = value.removesuffix("\n")
                index += 1
            if operation in " -":
                if cursor >= len(old) or old[cursor] != value:
                    raise CorpusError("patch_context_mismatch")
                cursor += 1
                consumed += 1
            if operation in " +":
                output.append(value)
                produced += 1
        if consumed != old_count or produced != new_count:
            raise CorpusError("patch_count_mismatch")
        hunks += 1
    if not hunks:
        raise CorpusError("patch_missing_hunks")
    return "".join([*output, *old[cursor:]])


@dataclass(frozen=True, slots=True)
class Candidate:
    case_id: str
    fixture_sha256: str
    candidate_sha256: str
    workspace: Mapping[str, str]
    changed_paths: tuple[str, ...]


def prepare_candidate(case: Case, patch: str) -> Candidate:
    """Apply exact text diffs in memory; reject scope changes and unsafe cheating."""
    if not isinstance(patch, str) or not patch or "\0" in patch or "\r" in patch:
        raise CorpusError("patch_shape")
    if len(patch.encode("utf-8")) > case.patch_limit or not patch.endswith("\n"):
        raise CorpusError("patch_bound_or_truncated")
    lines = patch.splitlines(keepends=True)
    files = dict(case.workspace)
    changed = []
    index = 0
    while index < len(lines):
        header = re.fullmatch(r"diff --git a/([^\s]+) b/([^\s]+)\n", lines[index])
        if not header or header[1] != header[2]:
            raise CorpusError("patch_file_header_invalid")
        path = _path(header[1])
        if path not in case.allowed_paths or path in changed:
            raise CorpusError("patch_path_out_of_scope_or_repeated")
        index += 1
        if index < len(lines) and lines[index].startswith("index "):
            if not re.fullmatch(r"index [0-9a-f]{7,40}\.\.[0-9a-f]{7,40}(?: 100644)?\n", lines[index]):
                raise CorpusError("patch_index_invalid")
            index += 1
        if lines[index:index+2] != [f"--- a/{path}\n", f"+++ b/{path}\n"]:
            raise CorpusError("patch_unsafe_metadata_or_headers")
        index += 2
        end = index
        while end < len(lines) and not lines[end].startswith("diff --git "):
            end += 1
        result = _apply_file(files[path], lines[index:end])
        if result == files[path]:
            raise CorpusError("patch_noop")
        _source_policy(path, result, frozenset(PurePosixPath(name).stem for name in case.allowed_paths))
        files[path] = result
        changed.append(path)
        index = end
    if not case.required_paths <= set(changed):
        raise CorpusError("patch_required_source_missing")
    if sum(len(content.encode("utf-8")) for content in files.values()) > case.candidate_limit:
        raise CorpusError("candidate_too_large")
    return Candidate(case.id, case.fixture_sha256, digest(_canonical(files)), MappingProxyType(files), tuple(sorted(changed)))


@dataclass(frozen=True, slots=True)
class IsolationRequest:
    candidate: Candidate
    oracle: Mapping[str, str]
    required_test_ids: tuple[str, ...]
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class IsolatedResult:
    """Only an evaluator-owned executor returns this, never the coding agent.

    The executor must keep controller/oracle files immutable, enforce VM/process
    limits, revoke agent tool access before injecting oracles, and independently
    authenticate the exact test collection/result. Candidate stdout is not a
    result receipt. An executor violating this trust contract cannot claim pass.
    """
    fixture_sha256: str
    candidate_sha256: str
    test_ids: tuple[str, ...]
    failures: int
    errors: int
    skipped: int
    exit_code: int
    isolated: bool


async def evaluate_case(case: Case, patch: str, *, execute_isolated: Callable[[IsolationRequest], Awaitable[IsolatedResult]] | None = None) -> dict[str, Any]:
    try:
        candidate = prepare_candidate(case, patch)
    except (CorpusError, UnicodeError, RecursionError):
        return {"case_id": case.id, "status": "rejected", "passed": False, "reason": "candidate_admission_failed"}
    if execute_isolated is None:
        return {"case_id": case.id, "status": "not_evaluated", "passed": False, "reason": "isolated_executor_required"}
    try:
        import asyncio
        async with asyncio.timeout(case.timeout_seconds + 5):
            result = await execute_isolated(IsolationRequest(candidate, case.oracle, case.oracle_test_ids, case.timeout_seconds))
        if (type(result) is not IsolatedResult or result.isolated is not True
                or result.fixture_sha256 != candidate.fixture_sha256 or result.candidate_sha256 != candidate.candidate_sha256
                or len(result.test_ids) != len(case.oracle_test_ids) or set(result.test_ids) != set(case.oracle_test_ids)
                or any(type(value) is not int or value < 0 for value in (result.failures, result.errors, result.skipped))
                or type(result.exit_code) is not int):
            raise CorpusError("untrusted_or_incomplete_receipt")
    except Exception:
        return {"case_id": case.id, "status": "not_evaluated", "passed": False, "reason": "isolated_verification_unconfirmed"}
    passed = result.exit_code == result.failures == result.errors == result.skipped == 0
    return {"case_id": case.id, "status": "passed" if passed else "failed", "passed": passed,
            "reason": None if passed else "oracle_rejected", "fixture_sha256": candidate.fixture_sha256,
            "candidate_sha256": candidate.candidate_sha256, "tests": len(result.test_ids)}


async def evaluate_suite(suite: Suite, patches: Mapping[str, str], *, execute_isolated=None) -> dict[str, Any]:
    """Report EVERY stratum; missing or unverified cases cannot disappear."""
    if not isinstance(patches, Mapping) or set(patches) - {case.id for case in suite.cases}:
        raise CorpusError("unknown_or_invalid_run_set")
    results = []
    strata = {name: {"cases": 0, "evaluated": 0, "passed": 0, "not_evaluated": 0, "rejected": 0}
              for name in ("bounded", "integration", "adversarial")}
    for case in suite.cases:
        if case.id in patches:
            result = await evaluate_case(case, patches[case.id], execute_isolated=execute_isolated)
        else:
            result = {"case_id": case.id, "status": "not_evaluated", "passed": False, "reason": "missing_candidate"}
        results.append({**result, "stratum": case.stratum})
        group = strata[case.stratum]
        group["cases"] += 1
        group["passed"] += int(result["passed"])
        if result["status"] in {"passed", "failed"}: group["evaluated"] += 1
        elif result["status"] in group: group[result["status"]] += 1
    return {"suite_id": suite.suite_id, "manifest_sha256": suite.manifest_sha256, "cases": results,
            "strata": strata, "all_passed": all(result["passed"] for result in results),
            "scope": "Original restricted regression corpus; strata are authored, not calibrated."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-corpus", action="store_true", help="Check frozen original fixtures; execute no candidate code")
    parser.parse_args()
    try:
        suite = load_suite()
    except CorpusError:
        print(json.dumps({"success": False, "code": "CORPUS_INTEGRITY_FAILED"}))
        return 2
    print(json.dumps({"success": True, "suite_id": suite.suite_id, "cases": len(suite.cases),
                      "manifest_sha256": suite.manifest_sha256, "model_runs": 0,
                      "behavioral_quality_evaluated": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
