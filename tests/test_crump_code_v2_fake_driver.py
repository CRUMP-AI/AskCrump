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

from backend.code_runner import CrumpCodeRunner, SandboxWorkspace
from scripts.crump_code_v2_fake_driver import (
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
from scripts.evaluate_crump_code_v2 import load_suite

CORPUS_ROOT = (
    Path(__file__).resolve().parents[1] / "benchmarks" / "crump_code" / "real_tasks_v2"
)


def make_settings(**overrides):
    values = {
        "code_max_agent_steps": 8,
        "anthropic_api_key": None,
        "anthropic_model": "fake-provider",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_task(case_id, objective, **overrides):
    task = {
        "id": f"fake-{case_id}",
        "user_id": "fake-user",
        "project_id": "fake-project",
        "status": "provisioning",
        "mode": "implement",
        "objective": objective,
        "provider_budget_policy": {"max_input_bytes": 112_000},
        "lease_token": None,
        "failure_code": None,
    }
    task.update(overrides)
    return task


async def run_with_script(
    case_id, script, *, seed="t", settings=None, work_root=None, cancel_after_turns=None
):
    corpus = CORPUS_ROOT
    suite = load_suite(corpus)
    case = suite.case(case_id)
    dest = (
        Path(work_root) / "ws" if work_root else Path(f"/tmp/fake-driver-{seed}") / "ws"
    )
    prepare_workspace(case_id, corpus, dest)
    settings = settings or make_settings()
    service = FakeCodeTaskService(make_task(case_id, case.objective))
    provider = DeterministicFakeProvider(
        CrumpCodeRunner,
        settings,
        service,
        seed=seed,
        script=script,
        cancel_after_turns=cancel_after_turns,
    )
    workspace = SandboxWorkspace(LocalSandbox(str(dest)))
    result = await provider.run_in_workspace(
        make_task(case_id, case.objective), workspace
    )
    return provider, service, result, case


def breaking_repair_script(corpus, case_id):
    """Scripted break -> real verification failure -> scripted revert -> pass."""
    content = (corpus / "cases" / case_id / "workspace" / "merge.py").read_text()
    lines = content.splitlines(keepends=True)
    old_tail = lines[-1]
    new_tail = old_tail + 'raise RuntimeError("fake-break")\n'
    verify = {
        "command": "python3",
        "args": ["-m", "pytest", "tests/test_visible.py", "-q"],
    }
    return [
        _tool_response(
            "Reading.",
            "read_file",
            {"path": "merge.py", "start_line": 1, "max_lines": 250},
        ),
        _tool_response(
            "Breaking.",
            "edit_file",
            {"path": "merge.py", "old": old_tail, "new": new_tail},
        ),
        _tool_response("Checking.", "run_verification", verify),
        _text_response("The change is complete."),
        _tool_response(
            "Reverting.",
            "edit_file",
            {"path": "merge.py", "old": new_tail, "new": old_tail},
        ),
        _tool_response("Re-checking.", "run_verification", verify),
        _text_response("Repaired and verified."),
    ]


def test_fake_provider_is_deterministic(tmp_path):
    async def collect():
        service = FakeCodeTaskService(make_task("x", "obj"))
        provider = DeterministicFakeProvider(
            CrumpCodeRunner,
            make_settings(),
            service,
            seed="det",
            script=default_script(_FakeCase()),
        )
        payloads = []
        for step in range(6):
            payloads.append(
                await provider._request_turn(
                    task={}, call_key=f"step:{step}", messages=[], tools=[]
                )
            )
        return payloads, provider.turn_log

    first, log1 = asyncio.run(collect())
    second, log2 = asyncio.run(collect())
    assert first == second
    assert [t["call_key"] for t in log1] == [t["call_key"] for t in log2]
    # Tool-use ids are stamped deterministically, not randomly.
    ids = [
        b.get("id")
        for p in first
        for b in p["content"]
        if isinstance(b, dict) and b.get("type") == "tool_use"
    ]
    assert ids and len(set(ids)) == len(ids)


class _FakeCase:
    id = "det-case"
    required_paths = frozenset({"merge.py"})
    workspace = {"tests/test_visible.py": "x"}


def test_failure_feedback_engages_real_repair_lifecycle(tmp_path):
    provider, service, result, case = asyncio.run(
        run_with_script(
            "activity-latest",
            breaking_repair_script(CORPUS_ROOT, "activity-latest"),
            seed="repair",
            work_root=tmp_path,
        )
    )
    assert result.get("status") == "completed"
    assert result.get("failure_code") is None
    repair_events = [
        e
        for e in service.events
        if e["event_type"] == "verification.completed"
        and (e["payload"] or {}).get("status") == "repair_required"
    ]
    assert len(repair_events) >= 1, "the real repair lifecycle must engage"
    assert any(t["saw_repair_feedback"] for t in provider.turn_log), (
        "repair feedback must actually reach the provider"
    )
    receipts = result.get("verification") or []
    assert receipts and all(r.get("returnCode") == 0 for r in receipts)


def test_bad_tool_candidate_recorded_as_tool_error(tmp_path):
    script = [
        {
            "content": [
                {"type": "tool_use", "name": "definitely_not_a_tool", "input": {}}
            ]
        },
        _text_response("Done."),
    ]
    provider, service, result, case = asyncio.run(
        run_with_script("activity-latest", script, seed="bad", work_root=tmp_path)
    )
    assert result.get("status") == "completed"
    error_events = [
        e
        for e in service.events
        if e["event_type"] == "tool.completed"
        and (e["payload"] or {}).get("status") == "error"
    ]
    assert error_events, "unknown tool must surface as a tool error, not a crash"


def test_malformed_blocks_do_not_crash_loop(tmp_path):
    script = [
        {"content": ["just a string", 42, None]},
        _text_response("Done."),
    ]
    provider, service, result, case = asyncio.run(
        run_with_script("activity-latest", script, seed="weird", work_root=tmp_path)
    )
    assert result.get("status") == "completed"
    assert result.get("failure_code") is None


def test_cancellation_mid_run_records_honest_cancel(tmp_path):
    suite = load_suite(CORPUS_ROOT)
    case = suite.case("activity-latest")
    record = asyncio.run(
        drive_case(
            case,
            corpus_root=CORPUS_ROOT,
            work_root=tmp_path,
            runner_cls=CrumpCodeRunner,
            settings=make_settings(),
            seed="cancel",
            cancel_after_turns=2,
        )
    )
    driver = record["driver"]
    assert driver["final_status"] == "cancelled"
    assert driver["failure_code"] == "CODE_TASK_CANCELLED"
    assert driver["provider_turns"] == 2, "no provider turn may run after cancellation"
    assert record["honest_label"] == "Not evaluated"


def test_all_twenty_cases_driven_blocked_represented_not_skipped(tmp_path):
    report = asyncio.run(
        drive_all(CORPUS_ROOT, tmp_path, CrumpCodeRunner, make_settings(), seed="all20")
    )
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
            out.append(
                await drive_case(
                    case,
                    corpus_root=CORPUS_ROOT,
                    work_root=tmp_path / case_id,
                    runner_cls=CrumpCodeRunner,
                    settings=make_settings(),
                    seed="det2",
                )
            )
        return out

    first = asyncio.run(drive_two())
    second = asyncio.run(drive_two())
    assert canonical_report({"cases": first}) == canonical_report({"cases": second})


def test_write_file_lands_with_expected_content_and_patch_retained(tmp_path):
    """write_file must work through the fs adapter and stay in the packaged patch.

    Regression test for the LocalSandbox AttributeError: production
    SandboxWorkspace.write_file requires sandbox.fs.mkdir/write_text.
    """
    content = "operator notes\nsecond line\n"
    script = [
        _tool_response(
            "Writing notes.", "write_file", {"path": "notes.txt", "content": content}
        ),
        _tool_response(
            "Checking.",
            "run_verification",
            {"command": "python3", "args": ["-m", "pytest", "tests/test_visible.py", "-q"]},
        ),
        _text_response("Done."),
    ]
    provider, service, result, case = asyncio.run(
        run_with_script("activity-latest", script, seed="write", work_root=tmp_path)
    )
    assert result.get("status") == "completed"
    assert result.get("failure_code") is None
    written = tmp_path / "ws" / "notes.txt"
    assert written.read_text(encoding="utf-8") == content
    write_events = [
        e
        for e in service.events
        if e["event_type"] == "tool.completed"
        and (e["payload"] or {}).get("tool") == "write_file"
        and (e["payload"] or {}).get("status") == "completed"
    ]
    assert write_events, "write_file must complete through the production tool path"
    patch = result.get("result_patch") or ""
    assert patch, "a nonempty patch must be retained and packaged"
    assert "notes.txt" in patch
    assert "operator notes" in patch


def test_write_file_rejects_workspace_escape(tmp_path):
    """The local fs adapter must refuse paths escaping the workspace root."""
    sandbox = LocalSandbox(str(tmp_path))
    with pytest.raises(ValueError):
        asyncio.run(sandbox.fs.write_text("../escape.txt", "x"))
    with pytest.raises(ValueError):
        asyncio.run(sandbox.fs.write_text("/abs.txt", "x"))


def test_harness_error_in_one_case_does_not_stop_suite(tmp_path, monkeypatch):
    """An unexpected error in one case is recorded; the rest stay represented."""
    import scripts.crump_code_v2_fake_driver as fd

    real_drive_case = fd.drive_case

    async def flaky_drive_case(case, **kwargs):
        if case.id == "call-lease":
            raise RuntimeError("injected harness failure")
        return await real_drive_case(case, **kwargs)

    monkeypatch.setattr(fd, "drive_case", flaky_drive_case)
    report = asyncio.run(
        fd.drive_all(CORPUS_ROOT, tmp_path, CrumpCodeRunner, make_settings(), seed="contain")
    )
    assert len(report["cases"]) == 20
    by_id = {c["id"]: c for c in report["cases"]}
    bad = by_id["call-lease"]
    assert bad["driver"] is None
    assert bad["harness_error"]["type"] == "RuntimeError"
    assert "injected harness failure" in bad["harness_error"]["message"]
    assert bad["honest_label"] == "Not evaluated"
    assert bad["honest_reason"] == "model evaluation not run"
    for record in report["cases"]:
        if record["id"] == "call-lease":
            continue
        assert record["driver"] is not None
        assert "harness_error" not in record


def test_turn_limit_exhaustion_terminates_honestly(tmp_path):
    """Hitting the step limit ends the run with the limit recorded, not a crash."""
    script = [
        _tool_response(
            "Reading.", "read_file", {"path": "merge.py", "start_line": 1, "max_lines": 50}
        ),
    ]
    provider, service, result, case = asyncio.run(
        run_with_script(
            "activity-latest",
            script,
            seed="turnlimit",
            settings=make_settings(code_max_agent_steps=1),
            work_root=tmp_path,
        )
    )
    assert result.get("status") == "failed"
    assert result.get("failure_code") == "CODE_STEP_LIMIT"
    assert len(provider.turn_log) == 1, "no provider turn may run past the step limit"


def _persistently_broken_script(corpus, case_id):
    """Break the source and keep its visible checks failing: repair must give up.

    The syntax check alone passes, so the repair limit is only reached when a
    requested behavioral check keeps failing across rounds.
    """
    content = (corpus / "cases" / case_id / "workspace" / "merge.py").read_text()
    lines = content.splitlines(keepends=True)
    old_tail = lines[-1]
    new_tail = old_tail + 'raise RuntimeError("fake-break")\n'
    verify = {
        "command": "python3",
        "args": ["-m", "pytest", "tests/test_visible.py", "-q"],
    }
    return [
        _tool_response(
            "Reading.",
            "read_file",
            {"path": "merge.py", "start_line": 1, "max_lines": 250},
        ),
        _tool_response(
            "Breaking.",
            "edit_file",
            {"path": "merge.py", "old": old_tail, "new": new_tail},
        ),
        _tool_response("Checking.", "run_verification", verify),
        _text_response("Summary one."),
        _text_response("Summary two."),
        _text_response("Summary three."),
    ]


def test_repair_limit_exhaustion_terminates_honestly(tmp_path):
    """Hitting the repair limit ends the run with the limit recorded, not a crash."""
    provider, service, result, case = asyncio.run(
        run_with_script(
            "activity-latest",
            _persistently_broken_script(CORPUS_ROOT, "activity-latest"),
            seed="repairlimit",
            work_root=tmp_path,
        )
    )
    assert result.get("status") == "failed"
    assert result.get("failure_code") == "CODE_VERIFICATION_FAILED"
    # 3 tool turns + 3 text turns; the third failure hits the repair limit.
    assert len(provider.turn_log) == 6, "loop must stop when the repair limit is hit"
    repair_rounds = sum(
        1
        for e in service.events
        if e["event_type"] == "verification.completed"
        and (e["payload"] or {}).get("status") == "repair_required"
    )
    assert repair_rounds >= 2, "repair lifecycle must engage before the limit stops it"


def test_report_carries_no_capability_language(tmp_path):
    report = asyncio.run(
        drive_all(CORPUS_ROOT, tmp_path, CrumpCodeRunner, make_settings(), seed="lang")
    )
    text = canonical_report(report)
    assert "Verified fix" not in text
    assert "Attempted" not in text
    assert "fix_rate" not in text or '"fix_rate": null' in text
    assert (
        report["aggregate"]
        == "Model evaluation not run; 0 cases evaluated; fix rate unavailable"
    )
