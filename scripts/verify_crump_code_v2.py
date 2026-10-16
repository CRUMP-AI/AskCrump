"""Self-check ONLY frozen, originally authored baseline/reference fixtures.

There is deliberately no candidate file/patch/code argument. This program is not
a host executor for model output. A successful self-check establishes corpus
consistency, not coding-agent capability or provider quality.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_crump_code_v2 import DEFAULT_CORPUS, CorpusError, load_suite  # noqa: E402


@dataclass(frozen=True, slots=True)
class AuthoredCheck:
    case_id: str
    variant: str
    passed: bool
    tests_run: int


def run_authored_fixture(case_id: str, variant: str) -> AuthoredCheck:
    """Accept identifiers only; immutable trusted corpus supplies every byte."""
    suite = load_suite()
    case = suite.case(case_id)
    if variant not in {"baseline", "reference"}:
        raise CorpusError("authored_variant_required")
    files = dict(case.workspace)
    if variant == "reference":
        files.update(case.reference)
    with tempfile.TemporaryDirectory(prefix="cv2-") as temporary:
        work = Path(temporary) / "w"
        work.mkdir()
        for path, content in files.items():
            destination = work / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content.encode("utf-8"))
        environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP")
                       if key in os.environ}
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        oracle = DEFAULT_CORPUS / "cases" / case_id / "oracle" / "test_hidden.py"
        result = subprocess.run([sys.executable, "-I", "-S", str(oracle), str(work)],
                                cwd=work, env=environment, capture_output=True, text=True,
                                timeout=case.timeout_seconds, check=False)
        evidence = result.stdout + result.stderr
        count = re.search(r"Ran (\d+) tests? in ", evidence)
        if count is None or int(count[1]) != len(case.oracle_test_ids):
            raise CorpusError("authored_oracle_collection_failed:" + case_id)
        return AuthoredCheck(case_id, variant, result.returncode == 0, int(count[1]))


def verify_authored_corpus() -> dict:
    suite = load_suite()
    cases = []
    for case in suite.cases:
        baseline = run_authored_fixture(case.id, "baseline")
        reference = run_authored_fixture(case.id, "reference")
        cases.append({"id": case.id, "stratum": case.stratum, "fixture_sha256": case.fixture_sha256,
                      "baseline_rejected": not baseline.passed, "reference_accepted": reference.passed,
                      "oracle_tests": reference.tests_run, "last_verified_solvable_at": datetime.now(timezone.utc).isoformat() if reference.passed else None})
    strata = {name: {"cases": sum(row["stratum"]==name for row in cases),
                     "baselines_rejected": sum(row["stratum"]==name and row["baseline_rejected"] for row in cases),
                     "references_accepted": sum(row["stratum"]==name and row["reference_accepted"] for row in cases)}
              for name in ("bounded", "integration", "adversarial")}
    return {"suite_id": suite.suite_id, "manifest_sha256": suite.manifest_sha256,
            "success": all(row["baseline_rejected"] and row["reference_accepted"] for row in cases), "strata": strata,
            "cases": cases, "model_runs": 0, "coding_capability_evaluated": False}


if __name__ == "__main__":
    try:
        report = verify_authored_corpus()
    except (CorpusError, OSError, subprocess.TimeoutExpired):
        print(json.dumps({"success": False, "code": "CORPUS_SELF_CHECK_FAILED", "model_runs": 0}))
        raise SystemExit(2)
    print(json.dumps(report))
    if report["success"]:
        # This is a dated corpus-solvability record, not part of the immutable
        # fixture inventory and never accepted as a candidate/model pass receipt.
        (DEFAULT_CORPUS/"solvability.v2.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    raise SystemExit(0 if report["success"] else 1)
