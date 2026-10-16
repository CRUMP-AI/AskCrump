"""Corpus consistency/security tests; authored reference success is NOT model quality."""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
import shutil
from unittest.mock import AsyncMock

import pytest

from scripts.evaluate_crump_code_v2 import (
    DEFAULT_CORPUS, PINNED_MANIFEST_SHA256, CorpusError, IsolatedResult,
    case_workspace, evaluate_case, evaluate_suite, load_suite, prepare_candidate,
)
from scripts.verify_crump_code_v2 import run_authored_fixture


SUITE = load_suite()
CASE_IDS = [case.id for case in SUITE.cases]


def reference_patch(case):
    blocks = []
    for path in sorted(case.reference):
        old, new = case.workspace[path], case.reference[path]
        if old != new:
            blocks.append(f"diff --git a/{path} b/{path}\n")
            blocks.extend(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                              fromfile="a/"+path, tofile="b/"+path))
    return "".join(blocks)


def replacement_patch(case, path, value):
    return f"diff --git a/{path} b/{path}\n" + "".join(difflib.unified_diff(
        case.workspace[path].splitlines(keepends=True), value.splitlines(keepends=True),
        fromfile="a/"+path, tofile="b/"+path))


def test_manifest_freeze_provenance_categories_and_agent_boundary():
    manifest = json.loads((DEFAULT_CORPUS / "manifest.json").read_text(encoding="utf-8"))
    assert len(SUITE.cases) == len(set(CASE_IDS)) == 20
    assert SUITE.manifest_sha256 == PINNED_MANIFEST_SHA256
    assert {case["provenance"]["kind"] for case in manifest["cases"]} == {"history-adapted", "original", "original-analogue"}
    assert len({case["provenance"]["commit"] for case in manifest["cases"] if case["provenance"]["commit"]}) >= 6
    assert sum(len(case.allowed_paths)>1 for case in SUITE.cases) >= 6
    assert sum(case["verification_repair"] for case in manifest["cases"]) == 2
    assert {case.stratum for case in SUITE.cases} == {"bounded", "integration", "adversarial"}
    for case in SUITE.cases:
        exposed = case_workspace(case)
        assert "tests/test_visible.py" in exposed and "README.txt" in exposed
        assert not any("hidden" in path or "reference" in path or "oracle" in path or "manifest" in path for path in exposed)
        assert "test_hidden.py" in case.oracle
        assert case.required_paths <= case.allowed_paths
        with pytest.raises(TypeError): exposed["extra.py"] = "not allowed"


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_our_frozen_original_baseline_fails_and_reference_passes_real_hidden_oracle(case_id):
    baseline = run_authored_fixture(case_id, "baseline")
    reference = run_authored_fixture(case_id, "reference")
    assert not baseline.passed, case_id
    assert reference.passed, case_id
    assert reference.tests_run >= 2


@pytest.mark.parametrize("case_id", CASE_IDS)
def test_reference_patch_is_exact_detached_and_source_only(case_id):
    case = SUITE.case(case_id)
    candidate = prepare_candidate(case, reference_patch(case))
    assert candidate.case_id == case.id and candidate.fixture_sha256 == case.fixture_sha256
    assert set(candidate.changed_paths) == case.required_paths
    for path, expected in case.reference.items():
        assert candidate.workspace[path] == expected
    assert candidate.workspace["tests/test_visible.py"] == case.workspace["tests/test_visible.py"]
    with pytest.raises(TypeError): candidate.workspace["x"] = "untrusted"


@pytest.mark.parametrize("tamper", ["fixture", "oracle", "extra", "manifest-and-freeze"])
def test_changed_fixture_or_test_or_updated_manifest_cannot_redefine_the_freeze(tmp_path, tamper):
    root = tmp_path / "corpus"
    shutil.copytree(DEFAULT_CORPUS, root)
    first = CASE_IDS[0]
    if tamper == "fixture": (root / "cases" / first / "workspace" / "merge.py").write_text("pass\n")
    if tamper == "oracle": (root / "cases" / first / "oracle" / "test_hidden.py").write_text("pass\n")
    if tamper == "extra": (root / "cases" / first / "workspace" / "extra.py").write_text("pass\n")
    if tamper == "manifest-and-freeze":
        path=root/"manifest.json"; data=path.read_bytes()+b" "
        path.write_bytes(data); (root/"freeze.sha256").write_text(hashlib.sha256(data).hexdigest())
    with pytest.raises(CorpusError): load_suite(root)


@pytest.mark.parametrize("attack", ["test-edit", "oracle-edit", "extra-source", "traversal", "binary", "mode", "rename", "truncated", "counts", "context", "repeat", "noop"])
def test_unsafe_extra_or_forged_patch_is_rejected_before_isolation(attack):
    case = SUITE.case("complete-patch")
    good = reference_patch(case)
    path = "artifact.py"
    if attack == "test-edit": patch=good+replacement_patch(case,"tests/test_visible.py","pass\n")
    elif attack == "oracle-edit": patch=good.replace("a/artifact.py","a/oracle/test_hidden.py").replace("b/artifact.py","b/oracle/test_hidden.py")
    elif attack == "extra-source": patch=good.replace("a/artifact.py","a/extra.py").replace("b/artifact.py","b/extra.py")
    elif attack == "traversal": patch=good.replace("artifact.py","../artifact.py")
    elif attack == "binary": patch="diff --git a/artifact.py b/artifact.py\nGIT binary patch\n"
    elif attack == "mode": patch=good.replace("--- a/artifact.py","old mode 100644\nnew mode 100755\n--- a/artifact.py")
    elif attack == "rename": patch=good.replace("diff --git a/artifact.py b/artifact.py","diff --git a/artifact.py b/other.py")
    elif attack == "truncated": patch=good[:-2]
    elif attack == "counts": patch=good.replace("@@ -1,2 +1,9 @@","@@ -1,999 +1,9 @@") if "@@ -1,2 +1,9 @@" in good else good.replace("@@ -1,2", "@@ -1,999")
    elif attack == "context": patch=good.replace("-    return read_bytes", "-    return nonexistent")
    elif attack == "repeat": patch=good+good
    else: patch=f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1,2 +1,2 @@\n"+"".join(" "+line for line in case.workspace[path].splitlines(keepends=True))
    with pytest.raises(CorpusError): prepare_candidate(case,patch)


@pytest.mark.parametrize("source", [
    "import unittest\nunittest.TestCase.assertEqual=lambda *a:None\n",
    "import os\nos._exit(0)\n", "value=__import__('sys')\n", "exec('pass')\n",
    "import asyncio\nasyncio.gather=lambda *a:[]\n", "value=object.__subclasses__()\n",
    "from pathlib import Path\nvalue=Path('oracle/test_hidden.py').read_text()\n",
])
def test_obvious_harness_access_or_module_monkeypatches_cannot_enter_candidate(source):
    case=SUITE.case("complete-patch")
    with pytest.raises(CorpusError): prepare_candidate(case,replacement_patch(case,"artifact.py",source))


@pytest.mark.asyncio
async def test_no_isolation_and_self_reported_success_cannot_create_a_pass():
    case=SUITE.case("complete-patch"); patch=reference_patch(case)
    result=await evaluate_case(case,patch)
    assert result["status"]=="not_evaluated" and result["passed"] is False
    fake=AsyncMock(return_value={"passed":True,"verification":[{"returnCode":0}]})
    result=await evaluate_case(case,patch,execute_isolated=fake)
    assert result["passed"] is False and result["reason"]=="isolated_verification_unconfirmed"
    rejected=AsyncMock(side_effect=AssertionError("rejected patch reached executor"))
    assert not (await evaluate_case(case,"pass",execute_isolated=rejected))["passed"]
    rejected.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [None,"fixture","candidate","missing-test","extra-test","duplicate-test","skip","fail","error","exit","not-isolated","bool-count"])
async def test_executor_contract_binds_identity_collection_and_complete_outcome(fault):
    case=SUITE.case("complete-patch"); patch=reference_patch(case); requests=[]
    async def execute(request):
        requests.append(request)
        result=dict(fixture_sha256=request.candidate.fixture_sha256,candidate_sha256=request.candidate.candidate_sha256,
                    test_ids=request.required_test_ids,failures=0,errors=0,skipped=0,exit_code=0,isolated=True)
        if fault=="fixture": result["fixture_sha256"]="0"*64
        if fault=="candidate": result["candidate_sha256"]="0"*64
        if fault=="missing-test": result["test_ids"]=request.required_test_ids[:-1]
        if fault=="extra-test": result["test_ids"]=(*request.required_test_ids,"Unknown.test_fake")
        if fault=="duplicate-test": result["test_ids"]=(request.required_test_ids[0],)*len(request.required_test_ids)
        if fault=="skip": result["skipped"]=1
        if fault=="fail": result["failures"]=1
        if fault=="error": result["errors"]=1
        if fault=="exit": result["exit_code"]=2
        if fault=="not-isolated": result["isolated"]=False
        if fault=="bool-count": result["failures"]=False
        return IsolatedResult(**result)
    result=await evaluate_case(case,patch,execute_isolated=execute)
    assert result["passed"] is (fault is None)
    assert len(requests)==1
    assert "test_hidden.py" in requests[0].oracle
    assert not any("hidden" in path for path in requests[0].candidate.workspace)


def test_self_check_has_no_candidate_input_and_claims_no_model_result():
    source=(Path(__file__).parents[1]/"scripts"/"verify_crump_code_v2.py").read_text()
    assert 'variant not in {"baseline", "reference"}' in source
    assert '"coding_capability_evaluated": False' in source


@pytest.mark.asyncio
async def test_suite_report_keeps_missing_and_unverified_cases_in_each_stratum():
    case=SUITE.case("complete-patch")
    report=await evaluate_suite(SUITE,{case.id:reference_patch(case)})
    assert len(report["cases"])==20 and report["all_passed"] is False
    assert sum(group["cases"] for group in report["strata"].values())==20
    assert sum(group["not_evaluated"] for group in report["strata"].values())==20
    assert all(group["evaluated"]==group["passed"]==0 for group in report["strata"].values())
    with pytest.raises(CorpusError): await evaluate_suite(SUITE,{"invented-task":"fake"})
