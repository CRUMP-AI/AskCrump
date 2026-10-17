"""Tests for the deterministic fake-provider driver.

PLUMBING EVIDENCE ONLY. These tests prove the production agent loop
(tool, repair, cancellation, limit, verification, packaging) runs end to end
with a deterministic fake in place of the model provider. They prove nothing
about model capability. No model is called; no paid infrastructure is used.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.code_runner import CodeRunnerError, CrumpCodeRunner, SandboxWorkspace
from scripts.evaluate_crump_code_v2 import load_suite
from scripts.crump_code_v2_fake_driver import (
    PROVIDER_NAME,
    SUPPORTED_OBSERVATION_CONTRACTS,
    DeterministicFakeProvider,
    FakeCodeTaskService,
    LocalSandbox,
    _text_response,
    _tool_response,
    canonical_report,
    default_script,
    drive_all,
    drive_case,
    prepare_workspace,
)

CORPUS_ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "crump_code" / "real_tasks_v2"


def make_settings(**overrides):
    values = {"code_max_agent_steps": 8, "anthropic_api_key": None,
              "anthropic_model": "fake-provider"}
    values.update(overrides)
    return SimpleNamespace(**values)


def make_task(case_id, objective, **overrides):
    task = {"id": f"fake-{case_id}", "user_id": "fake-user", "project_id": "fake-project",
            "status": "provisioning", "mode": "implement", "objective": objective,
            "provider_budget_policy": {"max_input_bytes": 112_000},
            "lease_token": None, "failure_code": None}
    task.update(overrides)
    return task


async def run_with_script(case_id, script, *, seed="t", settings=None,
                          work_root=None, cancel_after_turns=None):
    corpus = CORPUS_ROOT
    suite = load_suite(corpus)
    case = suite.case(case_id)
    dest = Path(work_root) / "ws" if work_root else Path(f"/tmp/fake-driver-{seed}") / "ws"
    prepare_workspace(case_id, corpus, dest)
    settings = settings or make_settings()
    service = FakeCodeTaskService(make_task(case_id, case.objective))
    provider = DeterministicFakeProvider(CrumpCodeRunner, settings, service,
                                         seed=seed, script=script,
                                         cancel_after_turns=cancel_after_turns)
    workspace = SandboxWorkspace(LocalSandbox(str(dest)))
    result = await provider.run_in_workspace(make_task(case_id, case.objective), workspace)
    return provider, service, result, case


def breaking_repair_script(corpus, case_id):
    """Scripted break -> real verification failure -> scripted revert -> pass."""
    content = (corpus / "cases" / case_id / "workspace" / "merge.py").read_text()
    lines = content.splitlines(keepends=True)
    old_tail = lines[-1]
    new_tail = old_tail + 'raise RuntimeError("fake-break")\n'
    verify = {"command": "python3", "args": ["-m", "pytest", "tests/test_visible.py", "-q"]}
    return [
        _tool_response("Reading.", "read_file",
                       {"path": "merge.py", "start_line": 1, "max_lines": 250}),
        _tool_response("Breaking.", "edit_file",
                       {"path": "merge.py", "old": old_tail, "new": new_tail}),
        _tool_response("Checking.", "run_verification", verify),
        _text_response("The change is complete."),
        _tool_response("Reverting.", "edit_file",
                       {"path": "merge.py", "old": new_tail, "new": old_tail}),
        _tool_response("Re-checking.", "run_verification", verify),
        _text_response("Repaired and verified."),
    ]


def test_fake_provider_is_deterministic(tmp_path):
    async def collect():
        service = FakeCodeTaskService(make_task("x", "obj"))
        provider = DeterministicFakeProvider(
            CrumpCodeRunner, make_settings(), service, seed="det",
            script=default_script(_FakeCase()))
        payloads = []
        for step in range(6):
            payloads.append(await provider._request_turn(
                task={}, call_key=f"step:{step}", messages=[], tools=[]))
        return payloads, provider.turn_log

    first, log1 = asyncio.run(collect())
    second, log2 = asyncio.run(collect())
    assert first == second
    assert [t["call_key"] for t in log1] == [t["call_key"] for t in log2]
    # Tool-use ids are stamped deterministically, not randomly.
    ids = [b.get("id") for p in first for b in p["content"]
           if isinstance(b, dict) and b.get("type") == "tool_use"]
    assert ids and len(set(ids)) == len(ids)


class _FakeCase:
    id = "det-case"
    required_paths = frozenset({"merge.py"})
    workspace = {"tests/test_visible.py": "x"}


def test_failure_feedback_engages_real_repair_lifecycle(tmp_path):
    provider, service, result, case = asyncio.run(run_with_script(
        "activity-latest", breaking_repair_script(CORPUS_ROOT, "activity-latest"),
        seed="repair", work_root=tmp_path))
    assert result.get("status") == "completed"
    assert result.get("failure_code") is None
    repair_events = [e for e in service.events
                     if e["event_type"] == "verification.completed"
                     and (e["payload"] or {}).get("status") == "repair_required"]
    assert len(repair_events) >= 1, "the real repair lifecycle must engage"
    assert any(t["saw_repair_feedback"] for t in provider.turn_log), \
        "repair feedback must actually reach the provider"
    receipts = result.get("verification") or []
    assert receipts and all(r.get("returnCode") == 0 for r in receipts)


def test_bad_tool_candidate_recorded_as_tool_error(tmp_path):
    script = [
        {"content": [{"type": "tool_use", "name": "definitely_not_a_tool", "input": {}}]},
        _text_response("Done."),
    ]
    provider, service, result, case = asyncio.run(run_with_script(
        "activity-latest", script, seed="bad", work_root=tmp_path))
    assert result.get("status") == "completed"
    error_events = [e for e in service.events
                    if e["event_type"] == "tool.completed"
                    and (e["payload"] or {}).get("status") == "error"]
    assert error_events, "unknown tool must surface as a tool error, not a crash"


def test_malformed_blocks_do_not_crash_loop(tmp_path):
    script = [
        {"content": ["just a string", 42, None]},
        _text_response("Done."),
    ]
    provider, service, result, case = asyncio.run(run_with_script(
        "activity-latest", script, seed="weird", work_root=tmp_path))
    assert result.get("status") == "completed"
    assert result.get("failure_code") is None


def test_cancellation_mid_run_records_honest_cancel(tmp_path):
    suite = load_suite(CORPUS_ROOT)
    case = suite.case("activity-latest")
    record = asyncio.run(drive_case(
        case, corpus_root=CORPUS_ROOT, work_root=tmp_path,
        runner_cls=CrumpCodeRunner, settings=make_settings(),
        seed="cancel", cancel_after_turns=2))
    driver = record["driver"]
    assert driver["final_status"] == "cancelled"
    assert driver["failure_code"] == "CODE_TASK_CANCELLED"
    assert driver["provider_turns"] == 2, "no provider turn may run after cancellation"
    assert record["honest_label"] == "Not evaluated"


def test_all_twenty_cases_driven_blocked_represented_not_skipped(tmp_path):
    report = asyncio.run(drive_all(
        CORPUS_ROOT, tmp_path, CrumpCodeRunner, make_settings(), seed="all20"))
    assert len(report["cases"]) == 20
    assert report["model_calls"] == 0
    assert report["paid_sandbox_used"] is False
    assert report["plumbing_evidence_only"] is True
    assert report["capability_claims"] == "none"
    assert report["fix_rate"] is None
    by_id = {c["id"]: c for c in report["cases"]}
    for case_id in SUPPORTED_OBSERVATION_CONTRACTS:
        assert by_id[case_id]["adapter_support"] == "supported"
    blocked = [c for c in report["cases"] if c["adapter_support"] == "blocked"]
    assert len(blocked) == 17
    for record in blocked:
        assert record["blocked_reason"] == "missing trusted adapter"
        # Blocked cases are driven AND marked blocked: present, not skipped, not passed.
        assert record["driver"]["provider_turns"] > 0
        assert record["honest_label"] == "Not evaluated"
        assert record["honest_reason"] == "model evaluation not run"
    for record in report["cases"]:
        assert record["plumbing_only"] is True
        assert "fix_rate" not in json.dumps(record["driver"])


def test_two_runs_are_canonically_identical(tmp_path):
    async def drive_two():
        suite = load_suite(CORPUS_ROOT)
        out = []
        for case_id in ("activity-latest", "call-lease"):
            case = suite.case(case_id)
            out.append(await drive_case(
                case, corpus_root=CORPUS_ROOT, work_root=tmp_path / case_id,
                runner_cls=CrumpCodeRunner, settings=make_settings(), seed="det2"))
        return out

    first = asyncio.run(drive_two())
    second = asyncio.run(drive_two())
    assert canonical_report({"cases": first}) == canonical_report({"cases": second})


def test_report_carries_no_capability_language(tmp_path):
    report = asyncio.run(drive_all(
        CORPUS_ROOT, tmp_path, CrumpCodeRunner, make_settings(), seed="lang"))
    text = canonical_report(report)
    assert "Verified fix" not in text
    assert "Attempted" not in text
    assert "fix_rate" not in text or '"fix_rate": null' in text
    assert report["aggregate"] == "Model evaluation not run; 0 cases evaluated; fix rate unavailable"
