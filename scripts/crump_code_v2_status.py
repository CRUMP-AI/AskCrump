"""Machine-generated honest labeling for the frozen v2 regression corpus.

Reads the freeze-verified corpus plus the dated solvability record and emits
per-case labels with an aggregate line. It never invents labels: every case is
"Not evaluated (model evaluation not run)" with plumbing coverage shown
separately, and the fix-rate number is null because no model run has happened.

Validation is strict and loud. It refuses to write output if:
- any boolean field is not an actual bool (truthy strings like "false" are
  rejected, not coerced),
- solvability row IDs are duplicated, missing, or extra relative to the suite,
- the solvability record is not bound to this suite_id and manifest_sha256,
- a row's stratum, fixture SHA, counts, or timestamp fail validation,
- a row's oracle_tests is not an actual integer equal to the suite's
  oracle_test_ids count for that case,
- the solvability record claims any model state (model_runs != 0 or
  coding_capability_evaluated not actually False): the honest "not
  evaluated" label may only be emitted when no model run has happened.

Usage: python3 scripts/crump_code_v2_status.py [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_crump_code_v2 import DEFAULT_CORPUS, load_suite

HONEST_STATE = "Model evaluation not run"
AGGREGATE = "Model evaluation not run; 0 cases evaluated; fix rate unavailable"
VALID_STRATA = {"bounded", "integration", "adversarial"}
EXPECTED_CASE_COUNT = 20


def _refuse(reason: str) -> NoReturn:
    raise SystemExit(f"refusing to label: {reason}")


def _require_bool(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        _refuse(
            f"{where} must be an actual boolean, got {type(value).__name__} ({value!r})"
        )
    return value


def _require_int(value: object, where: str) -> int:
    # bool is a subclass of int in Python; exclude it explicitly so True/False
    # can never slip through as 1/0.
    if isinstance(value, bool) or not isinstance(value, int):
        _refuse(
            f"{where} must be an actual integer, got {type(value).__name__} ({value!r})"
        )
    return value


def _require_timestamp(value: object, where: str) -> str:
    if not isinstance(value, str):
        _refuse(
            f"{where} must be an ISO-8601 timestamp string, got {type(value).__name__}"
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _refuse(f"{where} is not a parseable ISO-8601 timestamp: {value!r}")
    if parsed.tzinfo is None:
        _refuse(f"{where} must carry an explicit timezone offset: {value!r}")
    now = datetime.now(timezone.utc)
    if (parsed - now).total_seconds() > 300:
        _refuse(f"{where} is in the future: {value!r}")
    return value


def build_status(corpus_root: Path = DEFAULT_CORPUS) -> dict:
    corpus_root = Path(corpus_root)
    suite = load_suite(corpus_root)
    manifest = json.loads((corpus_root / "manifest.json").read_text(encoding="utf-8"))
    solvability = json.loads(
        (corpus_root / "solvability.v2.json").read_text(encoding="utf-8")
    )

    if not _require_bool(solvability.get("success"), "solvability.success"):
        _refuse("self-check record unsuccessful")

    # No-model-state gate: the honest "not evaluated" label may only be emitted
    # when the record itself claims zero model runs and unevaluated capability.
    # Contradictory input must refuse, not emit the honest label anyway.
    model_runs = _require_int(solvability.get("model_runs"), "solvability.model_runs")
    if model_runs != 0:
        _refuse(
            f"solvability.model_runs is {model_runs}: a model run is recorded, "
            "so 'Model evaluation not run' would be a lie; this generator only "
            "emits the not-evaluated state"
        )
    capability = _require_bool(
        solvability.get("coding_capability_evaluated"),
        "solvability.coding_capability_evaluated",
    )
    if capability:
        _refuse(
            "solvability.coding_capability_evaluated is True: coding capability "
            "is recorded as evaluated, so 'Model evaluation not run' would be "
            "a lie; this generator only emits the not-evaluated state"
        )

    # Suite/manifest binding: the solvability record must describe THIS suite.
    if solvability.get("suite_id") != suite.suite_id:
        _refuse(
            f"solvability suite_id {solvability.get('suite_id')!r} != suite {suite.suite_id!r}"
        )
    if solvability.get("manifest_sha256") != suite.manifest_sha256:
        _refuse("solvability manifest_sha256 does not match the frozen suite manifest")

    rows = solvability.get("cases")
    if not isinstance(rows, list):
        _refuse("solvability.cases must be a list")
    if len(rows) != EXPECTED_CASE_COUNT or len(suite.cases) != EXPECTED_CASE_COUNT:
        _refuse(
            f"expected {EXPECTED_CASE_COUNT} cases, got {len(rows)} rows / {len(suite.cases)} suite cases"
        )

    # ID integrity: no silent dedup, no extras, no missing.
    row_ids = [row.get("id") for row in rows]
    seen: set[str] = set()
    for rid in row_ids:
        if rid in seen:
            _refuse(f"duplicate solvability row id {rid!r}")
        seen.add(rid)
    suite_ids = {case.id for case in suite.cases}
    extras = seen - suite_ids
    missing = suite_ids - seen
    if extras:
        _refuse(f"solvability rows reference unknown case ids: {sorted(extras)}")
    if missing:
        _refuse(f"solvability record missing rows for case ids: {sorted(missing)}")

    plumbing = {row["id"]: row for row in rows}
    cases = []
    for case in suite.cases:
        row = plumbing[case.id]
        if row.get("stratum") != case.stratum:
            _refuse(
                f"stratum mismatch for {case.id}: row {row.get('stratum')!r} != suite {case.stratum!r}"
            )
        if row.get("stratum") not in VALID_STRATA:
            _refuse(f"unknown stratum {row.get('stratum')!r} for {case.id}")
        if row.get("fixture_sha256") != case.fixture_sha256:
            _refuse(f"solvability record inconsistent for {case.id}")
        baseline = _require_bool(
            row.get("baseline_rejected"), f"{case.id}.baseline_rejected"
        )
        reference = _require_bool(
            row.get("reference_accepted"), f"{case.id}.reference_accepted"
        )
        if not (baseline and reference):
            _refuse(f"plumbing incomplete for {case.id}")
        timestamp = _require_timestamp(
            row.get("last_verified_solvable_at"), f"{case.id}.last_verified_solvable_at"
        )
        # oracle_tests must be an actual integer equal to the suite's oracle
        # test count for this case — copied blindly it could be anything.
        oracle_tests = _require_int(row.get("oracle_tests"), f"{case.id}.oracle_tests")
        if oracle_tests != len(case.oracle_test_ids):
            _refuse(
                f"oracle_tests count {oracle_tests} for {case.id} != "
                f"{len(case.oracle_test_ids)} oracle_test_ids in the frozen suite"
            )
        cases.append(
            {
                "id": case.id,
                "stratum": case.stratum,
                "fixture_sha256": case.fixture_sha256,
                "label": "Not evaluated",
                "reason": "model evaluation not run",
                "plumbing": {
                    "baseline_rejected": True,
                    "reference_accepted": True,
                    "oracle_tests": oracle_tests,
                    "last_verified_solvable_at": timestamp,
                },
            }
        )
    return {
        "schema_version": 1,
        "suite_id": suite.suite_id,
        "manifest_sha256": suite.manifest_sha256,
        "honest_state": HONEST_STATE,
        "labels": {
            "verified_fix": 0,
            "attempted_not_fixed": 0,
            "not_evaluated": len(cases),
            "plumbing_only": 0,
        },
        "aggregate": AGGREGATE,
        "fix_rate": None,
        "fix_rate_note": (
            "No model run has been performed. No fix rate is computable: "
            "0 cases evaluated. The fix-rate number gates activation and "
            "marketing, not the merge."
        ),
        "scope": manifest["claim"],
        "excluded_capabilities": manifest["excluded_capabilities"],
        "note": (
            "Plumbing coverage (failing baselines, passing references, frozen "
            "fixtures) is shown per case and is not a model quality result. "
            "Fixture checks do not establish sandbox isolation."
        ),
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_CORPUS / "status.v2.json")
    args = parser.parse_args()
    status = build_status()
    args.out.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "written": str(args.out),
                "cases": len(status["cases"]),
                "honest_state": status["honest_state"],
                "aggregate": status["aggregate"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
