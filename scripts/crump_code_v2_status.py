"""Machine-generated honest labeling for the frozen v2 regression corpus.

Reads the freeze-verified corpus plus the dated solvability record and emits
per-case labels with an aggregate line. It never invents labels: every case is
"Not evaluated (model evaluation not run)" with plumbing coverage shown
separately, and the fix-rate number is null because no model run has happened.

Refuses to write output if the self-check record is missing, unsuccessful, or
inconsistent with the frozen fixtures.

Usage: python3 scripts/crump_code_v2_status.py [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_crump_code_v2 import DEFAULT_CORPUS, load_suite  # noqa: E402

HONEST_STATE = "Model evaluation not run"
AGGREGATE = "0/20 - authored regression reductions, sandboxed harness"


def build_status() -> dict:
    suite = load_suite()
    manifest = json.loads((DEFAULT_CORPUS / "manifest.json").read_text(encoding="utf-8"))
    raw = (DEFAULT_CORPUS / "solvability.v2.json").read_text(encoding="utf-8")
    solvability = json.loads(raw)
    if solvability.get("success") is not True:
        raise SystemExit("self-check record unsuccessful; refusing to label")
    plumbing = {row["id"]: row for row in solvability["cases"]}
    cases = []
    for case in suite.cases:
        row = plumbing.get(case.id)
        if row is None or row.get("fixture_sha256") != case.fixture_sha256:
            raise SystemExit(f"solvability record inconsistent for {case.id}; refusing to label")
        if not (row.get("baseline_rejected") and row.get("reference_accepted")):
            raise SystemExit(f"plumbing incomplete for {case.id}; refusing to label")
        cases.append({
            "id": case.id,
            "stratum": case.stratum,
            "fixture_sha256": case.fixture_sha256,
            "label": "Not evaluated",
            "reason": "model evaluation not run",
            "plumbing": {
                "baseline_rejected": True,
                "reference_accepted": True,
                "oracle_tests": row["oracle_tests"],
                "last_verified_solvable_at": row["last_verified_solvable_at"],
            },
        })
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
        "fix_rate_note": ("No model run has been performed. The fix-rate number gates "
                          "activation and marketing, not the merge, and is not computable "
                          "from this file."),
        "scope": manifest["claim"],
        "excluded_capabilities": manifest["excluded_capabilities"],
        "note": ("Plumbing coverage (failing baselines, passing references, frozen "
                 "fixtures) is shown per case and is not a model quality result."),
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_CORPUS / "status.v2.json")
    args = parser.parse_args()
    status = build_status()
    args.out.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "written": str(args.out),
        "cases": len(status["cases"]),
        "honest_state": status["honest_state"],
        "aggregate": status["aggregate"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
