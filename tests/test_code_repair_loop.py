"""Actual temporary-repository regressions; scripted turns test orchestration,
not model capability. V2 hidden acceptance evaluation measures real providers.
"""
from copy import deepcopy
import asyncio
import json
import os
from types import SimpleNamespace

import pytest

from backend.code_runner import (CodeRunnerError, CrumpCodeRunner, SandboxWorkspace,
                                 bounded_messages, normalize_workspace_path)
from backend import code_runner
from test_code_artifact_integrity import LocalRepository


TASK = {"id": "offline-repair", "user_id": "offline-owner", "status": "provisioning",
        "lease_token": "offline-fixed-lease", "mode": "implement", "objective": "Correct total() to add every item."}


class Service:
    def __init__(self, *, cancel_on_repair=False):
        self.task = dict(TASK)
        self.events = []
        self.cancel_on_repair = cancel_on_repair

    async def get(self, **_kwargs):
        return dict(self.task)

    async def append_event(self, _task, event_type, payload):
        self.events.append((event_type, deepcopy(payload)))
        if self.cancel_on_repair and payload.get("status") == "repair_required":
            self.task.update(status="cancelled", lease_token=None)

    async def transition(self, _task, target, *, changes=None, event_type, event_payload):
        self.task.update(status=target, **(changes or {}))
        await self.append_event(self.task, event_type, event_payload)
        return dict(self.task)


class Turns(CrumpCodeRunner):
    def __init__(self, service, turns, *, max_steps=8):
        super().__init__(SimpleNamespace(code_max_agent_steps=max_steps), service)
        self.turns = list(turns)
        self.requests = []

    async def _request_turn(self, **request):
        self.requests.append(deepcopy(request))
        turn = self.turns.pop(0)
        if callable(turn):
            turn = turn(request)
        return turn


def tool(identifier, name, **arguments):
    return {"content": [{"type": "tool_use", "id": identifier, "name": name, "input": arguments}]}


def final(text="The proposed change is ready for review."):
    return {"content": [{"type": "text", "text": text}]}


@pytest.fixture
def source(tmp_path):
    root, scratch = tmp_path / "r", tmp_path / "s"
    root.mkdir(); scratch.mkdir()
    repo = LocalRepository(root, scratch)
    repo.git("init", "--quiet")
    (root / "calc.py").write_text("def total(items):\n    return len(items)\n", encoding="utf-8")
    (root / "test_calc.py").write_text(
        "import unittest\nfrom calc import total\n\nclass TotalTests(unittest.TestCase):\n"
        "    def test_adds_values(self):\n        self.assertEqual(total([4, 7, 2]), 13)\n", encoding="utf-8")
    (root / "obsolete.py").write_text("OLD = True\n", encoding="utf-8")
    repo.git("add", ".")
    repo.git("-c", "commit.gpgsign=false", "commit", "--quiet", "--no-verify", "-m", "Frozen repair regression")
    return repo


@pytest.mark.asyncio
async def test_actual_failed_behavioral_check_is_repaired_and_rechecked_before_completion(source):
    service = Service()

    def repair(request):
        feedback = request["messages"][-1]["content"]
        assert "Final verification requires repair" in feedback and "AssertionError" in feedback
        return tool("repair", "edit_file", path="calc.py", old="return len(items)", new="return sum(items)")

    runner = Turns(service, [tool("test", "run_verification", command="python3", args=["-m", "unittest", "-q", "test_calc"]),
                             final("Everything passed"), repair, final()])
    workspace = SandboxWorkspace(source)
    result = await runner.run_in_workspace(dict(TASK), workspace)

    assert result["status"] == "completed" and result["failure_code"] is None
    assert "+    return sum(items)" in result["result_patch"]
    assert any(row["returnCode"] != 0 for row in workspace.verification), "Earlier failure remains actual evidence"
    assert all(type(row["returnCode"]) is int and row["returnCode"] == 0 for row in result["verification"])
    checks = [row for row in workspace.verification if row["command"] == "python3 -m unittest -q test_calc"]
    assert [row["returnCode"] for row in checks] == [1, 0], "A changed source cannot inherit its stale check"
    assert checks[0]["_revision"] == 0 and checks[-1]["_revision"] == 1
    assert len(runner.requests) == 4
    assert [request["call_key"] for request in runner.requests] == [f"step:{i}" for i in range(4)]
    assert any(payload.get("status") == "repair_required" for kind, payload in service.events if kind == "verification.completed")
    assert not list(source.root.rglob("*.pyc"))


@pytest.mark.asyncio
async def test_automatic_syntax_failure_returns_to_model_but_never_exceeds_repair_or_call_caps(source):
    service = Service()
    runner = Turns(service, [tool("broken", "write_file", path="calc.py", content="def broken(:\n"), final(), final(), final()])
    workspace = SandboxWorkspace(source)
    result = await runner.run_in_workspace(dict(TASK), workspace)
    assert result["status"] == "failed" and result["failure_code"] == "CODE_VERIFICATION_FAILED"
    assert "SyntaxError" in json.dumps(result["verification"])
    assert "automated verification failed" in result["result_summary"]
    assert "+def broken(:" in result["result_patch"]
    assert len(runner.requests) == 4  # Initial edit + final candidate + two repair opportunities.
    assert sum("Final verification requires repair" in json.dumps(request["messages"][-1]) for request in runner.requests) == 2


@pytest.mark.asyncio
async def test_step_limit_preserves_review_patch_without_claiming_completion(source):
    service = Service()
    runner = Turns(service, [tool("fix", "edit_file", path="calc.py", old="return len(items)", new="return sum(items)")], max_steps=1)
    result = await runner.run_in_workspace(dict(TASK), SandboxWorkspace(source))
    assert result["status"] == "failed" and result["failure_code"] == "CODE_STEP_LIMIT"
    assert "+    return sum(items)" in result["result_patch"] and result["verification"]
    assert len(runner.requests) == 1


@pytest.mark.asyncio
async def test_a_green_check_before_a_later_edit_cannot_validate_the_changed_source(source):
    (source.root / "calc.py").write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")
    source.git("add", "calc.py")
    source.git("-c", "commit.gpgsign=false", "commit", "--quiet", "--no-verify", "-m", "Initially correct source")
    service = Service()
    runner = Turns(service, [tool("green", "run_verification", command="python3", args=["-m", "unittest", "-q", "test_calc"]),
        tool("regression", "edit_file", path="calc.py", old="return sum(items)", new="return len(items)"), final()], max_steps=3)
    workspace = SandboxWorkspace(source)
    result = await runner.run_in_workspace(dict(TASK), workspace)
    assert result["status"] == "failed" and result["failure_code"] == "CODE_VERIFICATION_FAILED"
    assert len(runner.requests) == 3, "A last-step failure has no unbudgeted repair turn"
    checks = [row for row in workspace.verification if row["command"] == "python3 -m unittest -q test_calc"]
    assert [row["returnCode"] for row in checks] == [0, 1]
    assert any(row["returnCode"] == 1 for row in result["verification"])
    assert "+    return len(items)" in result["result_patch"]


@pytest.mark.asyncio
async def test_actual_green_test_that_rewrites_source_cannot_supply_current_green_receipts(source):
    # The command asserts against the correct imported code, then writes a
    # syntactically valid regression before exiting zero. That is NOT evidence
    # about the final proposed source, even though no edit tool was called.
    (source.root / "calc.py").write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")
    (source.root / "test_calc.py").write_text(
        "from pathlib import Path\nimport unittest\nfrom calc import total\n"
        "class TotalTests(unittest.TestCase):\n"
        "    def test_changes_source_after_assertion(self):\n"
        "        self.assertEqual(total([4, 7, 2]), 13)\n"
        "        Path('calc.py').write_text('def total(items):\\n    return len(items)\\n', encoding='utf-8')\n",
        encoding="utf-8")
    source.git("add", ".")
    source.git("-c", "commit.gpgsign=false", "commit", "--quiet", "--no-verify", "-m", "Mutating verification fixture")
    runner = Turns(Service(), [tool("mutating-check", "run_verification", command="python3", args=["-m", "unittest", "-q", "test_calc"]), final()], max_steps=2)
    workspace = SandboxWorkspace(source)
    result = await runner.run_in_workspace(dict(TASK), workspace)
    assert result["status"] == "failed" and result["failure_code"] == "CODE_VERIFICATION_FAILED"
    assert "+    return len(items)" in result["result_patch"]
    history = [row for row in workspace.verification if row["command"] == "python3 -m unittest -q test_calc"]
    assert [row["returnCode"] for row in history] == [0, 1]
    assert history[0]["_revision"] < workspace.mutation_revision
    assert any(row["returnCode"] != 0 for row in result["verification"])


@pytest.mark.asyncio
async def test_actual_check_hook_cannot_commit_changes_and_move_the_frozen_artifact_base(source):
    original = source.git("rev-parse", "HEAD").strip()
    (source.root / "test_commit.py").write_text(
        "from pathlib import Path\nimport subprocess, unittest\n"
        "class CommitTests(unittest.TestCase):\n"
        "    def test_commits_rewritten_source(self):\n"
        "        Path('calc.py').write_text('def total(items):\\n    return sum(items)\\n', encoding='utf-8')\n"
        "        subprocess.run(['git', 'add', 'calc.py'], check=True)\n"
        "        subprocess.run(['git', '-c', 'commit.gpgsign=false', 'commit', '--quiet', '--no-verify', '-m', 'Untrusted hook'], check=True)\n",
        encoding="utf-8")
    source.git("add", "test_commit.py")
    source.git("-c", "commit.gpgsign=false", "commit", "--quiet", "--no-verify", "-m", "Committed verification hook")
    base = source.git("rev-parse", "HEAD").strip()
    assert base != original
    service = Service()
    runner = Turns(service, [tool("hook", "run_verification", command="python3", args=["-m", "unittest", "-q", "test_commit"]), final()], max_steps=2)
    with pytest.raises(CodeRunnerError) as caught:
        await runner.run_in_workspace(dict(TASK), SandboxWorkspace(source))
    assert caught.value.code == "CODE_RESULT_INCOMPLETE"
    assert source.git("rev-parse", "HEAD").strip() != base, "Actual repository hook moved HEAD"
    assert service.task["base_revision"] == base
    assert not any(kind == "task.completed" for kind, _payload in service.events)
    assert not (source.scratch / "review.patch").exists()


@pytest.mark.asyncio
async def test_source_change_after_final_verification_rejects_packaging_and_completion(source):
    class MutatingService(Service):
        async def transition(self, task, target, **kwargs):
            result = await super().transition(task, target, **kwargs)
            if target == "verifying":
                (source.root / "calc.py").write_text("def total(items):\n    return -1\n", encoding="utf-8")
            return result

    service = MutatingService()
    runner = Turns(service, [tool("repair", "edit_file", path="calc.py", old="return len(items)", new="return sum(items)"), final()])
    with pytest.raises(CodeRunnerError) as caught:
        await runner.run_in_workspace(dict(TASK), SandboxWorkspace(source))
    assert caught.value.code == "CODE_RESULT_INCOMPLETE"
    assert not any(kind == "task.completed" for kind, _payload in service.events)
    assert not (source.scratch / "review.patch").exists()


@pytest.mark.asyncio
async def test_fingerprint_is_content_based_complete_and_stable_across_intent_to_add(source):
    workspace = SandboxWorkspace(source)
    await workspace.base_revision()
    initial = await workspace.source_state()
    (source.root / "new.py").write_text("VALUE = 1\n", encoding="utf-8")
    added = await workspace.source_state()
    assert added != initial and workspace.mutation_revision == 1
    source.git("add", "-N", "--", "new.py")
    assert await workspace.source_state() == added
    source.git("add", "new.py")
    assert await workspace.source_state() == added, "Index staging cannot change artifact identity"
    (source.root / "new.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert await workspace.source_state() != added
    source.git("reset", "--quiet", "--", "new.py")
    (source.root / "new.py").write_text("x" * (code_runner.MAX_PATCH + 1), encoding="utf-8")
    source.git("add", "new.py")
    with pytest.raises(CodeRunnerError, match="complete source"):
        await workspace.source_state()


@pytest.mark.asyncio
@pytest.mark.parametrize("flag", ["--assume-unchanged", "--skip-worktree"])
async def test_index_flags_cannot_conceal_source_changes_from_the_fingerprint(source, flag):
    workspace = SandboxWorkspace(source)
    await workspace.source_state()
    source.git("update-index", flag, "calc.py")
    (source.root / "calc.py").write_text("def total(items):\n    return -1\n", encoding="utf-8")
    assert source.git("diff", "HEAD", "--", "calc.py") == "", "Actual index flag hides Git's ordinary diff"
    with pytest.raises(CodeRunnerError, match="complete source"):
        await workspace.source_state()


@pytest.mark.asyncio
async def test_preserved_size_and_mtime_cannot_hide_source_bytes_behind_git_stat_cache(source):
    path = source.root / "calc.py"
    source.git("config", "core.trustctime", "false")
    info = path.stat()
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns - 100_000_000_000))
    source.git("update-index", "--refresh")
    workspace = SandboxWorkspace(source)
    await workspace.source_state()
    original = path.stat()
    path.write_bytes(path.read_bytes().replace(b"return len(items)", b"return max(items)"))
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert path.stat().st_size == original.st_size
    assert source.git("diff", "HEAD", "--", "calc.py") == "", "Actual Git stat cache conceals the same-size rewrite"
    with pytest.raises(CodeRunnerError, match="complete source"):
        await workspace.source_state()


@pytest.mark.asyncio
@pytest.mark.parametrize("setting,limit", [("MAX_SOURCE_BYTES", 10), ("MAX_TRACKED_FILES", 1)])
async def test_complete_tracked_content_and_count_bounds_fail_closed(source, monkeypatch, setting, limit):
    monkeypatch.setattr(code_runner, setting, limit)
    with pytest.raises(CodeRunnerError, match="complete source"):
        await SandboxWorkspace(source).source_state()


@pytest.mark.asyncio
async def test_actual_clean_filter_cannot_substitute_patch_bytes_for_the_checked_source(source):
    # Git's clean filter changes the review patch to max(), although the source
    # checks execute sum(). --no-textconv alone does not disable clean filters.
    (source.root / ".git" / "info" / "attributes").write_text("calc.py filter=forge\n", encoding="utf-8")
    source.git("config", "filter.forge.clean", "sed 's/sum(items)/max(items)/'")
    (source.root / "calc.py").write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")
    forged = source.git("diff", "HEAD", "--no-ext-diff", "--no-textconv", "--", "calc.py")
    assert "+    return max(items)" in forged
    assert "return sum(items)" in (source.root / "calc.py").read_text(encoding="utf-8")
    service = Service()
    runner = Turns(service, [final()])
    with pytest.raises(CodeRunnerError) as caught:
        await runner.run_in_workspace(dict(TASK), SandboxWorkspace(source))
    assert caught.value.code == "CODE_REPOSITORY_FILTERS_UNSUPPORTED"
    assert runner.requests == [], "Reject unsupported source transforms before a model request"
    assert service.events == [] and not (source.scratch / "review.patch").exists()


@pytest.mark.asyncio
async def test_configured_process_filter_is_rejected_even_without_any_active_attributes(source):
    source.git("config", "filter.disabled.process", "an-authored-test-filter-that-is-never-executed")
    with pytest.raises(CodeRunnerError) as caught:
        await SandboxWorkspace(source).source_state()
    assert caught.value.code == "CODE_REPOSITORY_FILTERS_UNSUPPORTED"


@pytest.mark.asyncio
async def test_removing_a_still_present_ignored_source_from_index_cannot_forge_a_deletion_patch(source):
    (source.root / ".gitignore").write_text("calc.py\n", encoding="utf-8")
    source.git("add", ".gitignore")
    source.git("-c", "commit.gpgsign=false", "commit", "--quiet", "--no-verify", "-m", "Tracked ignored-source fixture")
    workspace = SandboxWorkspace(source)
    await workspace.source_state()
    source.git("rm", "--cached", "calc.py")
    assert (source.root / "calc.py").is_file() and "deleted file mode" in source.git("diff", "HEAD")
    with pytest.raises(CodeRunnerError, match="complete source"):
        await workspace.source_state()


@pytest.mark.asyncio
async def test_complete_untracked_inventory_and_file_count_are_bounded_without_truncation(source):
    workspace = SandboxWorkspace(source)
    await workspace.source_state()
    for index in range(code_runner.MAX_CHANGED_FILES + 1):
        (source.root / f"new_{index}.py").write_text("VALUE = 1\n", encoding="utf-8")
    with pytest.raises(CodeRunnerError, match="complete source"):
        await workspace.source_state()


@pytest.mark.asyncio
async def test_deleted_explicit_syntax_target_is_replaced_by_real_deletion_diff_check(source):
    runner = Turns(Service(), [tool("compile", "run_verification", command="python3", args=["-m", "py_compile", "obsolete.py"]),
        tool("delete", "delete_file", path="obsolete.py"), final()])
    workspace = SandboxWorkspace(source)
    result = await runner.run_in_workspace(dict(TASK), workspace)
    assert result["status"] == "completed"
    assert "deleted file mode" in result["result_patch"]
    assert not any("py_compile obsolete.py" in row["command"] for row in result["verification"])
    assert any(row["command"].startswith("git diff --check ") and row["returnCode"] == 0 for row in result["verification"])
    assert sum(row["command"] == "python3 -m py_compile obsolete.py" for row in workspace.verification) == 1


@pytest.mark.asyncio
async def test_deleting_a_behavioral_test_never_retires_its_requested_check(source):
    # A deleted unittest module must still be rerun and fail import; deletion
    # retirement applies exclusively to explicit all-deleted syntax targets.
    (source.root / "calc.py").write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")
    runner = Turns(Service(), [tool("test", "run_verification", command="python3", args=["-m", "unittest", "-q", "test_calc"]),
        tool("delete", "delete_file", path="test_calc.py"), final()], max_steps=3)
    workspace = SandboxWorkspace(source)
    result = await runner.run_in_workspace(dict(TASK), workspace)
    assert result["status"] == "failed" and result["failure_code"] == "CODE_VERIFICATION_FAILED"
    checks = [row for row in workspace.verification if row["command"] == "python3 -m unittest -q test_calc"]
    assert [row["returnCode"] for row in checks] == [0, 1]


@pytest.mark.asyncio
async def test_controlled_helpers_and_automatic_compile_ignore_repo_standard_library_impersonators(source):
    (source.root / "pathlib.py").write_text("raise RuntimeError('repository module must not control helpers')\n", encoding="utf-8")
    (source.root / "py_compile.py").write_text("print('FAKE_GREEN')\n", encoding="utf-8")
    (source.root / "calc.py").write_text("def invalid(:\n", encoding="utf-8")
    workspace = SandboxWorkspace(source)
    assert "def invalid(:" in await workspace.read_file("calc.py")
    await workspace.syntax_verify(["calc.py"])
    receipt = workspace.verification[-1]
    assert receipt["command"].startswith("python3 -I -X pycache_prefix=/tmp/crump-code-pycache -m py_compile ")
    assert receipt["returnCode"] != 0 and "SyntaxError" in receipt["stderr"]
    assert "FAKE_GREEN" not in receipt["stdout"]
    assert not list(source.root.rglob("*.pyc"))


@pytest.mark.asyncio
async def test_cancellation_after_failed_final_check_prevents_next_repair_model_call(source):
    service = Service(cancel_on_repair=True)
    runner = Turns(service, [tool("broken", "write_file", path="calc.py", content="def broken(:\n"), final()])
    with pytest.raises(CodeRunnerError) as caught:
        await runner.run_in_workspace(dict(TASK), SandboxWorkspace(source))
    assert caught.value.code == "CODE_TASK_CANCELLED"
    assert len(runner.requests) == 2
    assert service.task["status"] == "cancelled"


@pytest.mark.asyncio
async def test_one_session_deadline_covers_repair_wait_and_never_completes(monkeypatch):
    service = Service()
    runner = CrumpCodeRunner(SimpleNamespace(code_max_agent_steps=8), service)
    calls, deadlines = [], []
    cancelled = asyncio.Event()

    async def request(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return final()
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    class Workspace:
        verification = [{"command": "fixture check", "returnCode": 1, "stderr": "actual failure"}]
        async def base_revision(self): return "authored-fixture"
        async def list_files(self, _prefix): return "notes.txt"
        async def changed_paths(self): return ["notes.txt"]
        async def syntax_verify(self, _paths): pass

    original_timeout = asyncio.timeout
    def fast_timeout(seconds):
        deadlines.append(seconds)
        return original_timeout(.02)

    runner._request_turn = request
    monkeypatch.setattr(code_runner.asyncio, "timeout", fast_timeout)
    with pytest.raises(CodeRunnerError) as caught:
        await runner.run_in_workspace({**TASK, "max_duration_seconds": 30}, Workspace())
    assert caught.value.code == "CODE_DEADLINE"
    assert deadlines == [55] and len(calls) == 2
    assert cancelled.is_set()
    assert service.task["status"] == "running"
    assert not any(kind == "task.completed" for kind, _ in service.events)


@pytest.mark.asyncio
async def test_exact_edits_refuse_ambiguous_stale_and_protected_paths_and_preserve_other_bytes(source):
    (source.root / "windows.txt").write_bytes(b"alpha\r\nword word\r\nomega\r\n")
    source.git("add", "windows.txt")
    workspace = SandboxWorkspace(source)
    for old in ("word", "does not exist"):
        with pytest.raises(ValueError, match="matches exactly once"):
            await workspace.edit_file("windows.txt", old, "replacement")
    assert workspace.mutation_revision == 0
    await workspace.edit_file("windows.txt", "alpha", "first")
    assert (source.root / "windows.txt").read_bytes() == b"first\r\nword word\r\nomega\r\n"
    assert workspace.mutation_revision == 1
    await workspace.edit_file("windows.txt", "first", "first")
    assert workspace.mutation_revision == 1, "No-op edits do not invalidate passing checks"
    for path in ("../escape.py", "/etc/escape.py", "C:/escape.py", ".git/config", "nested/.git/config", "config/.env.production.json"):
        with pytest.raises(ValueError):
            normalize_workspace_path(path)
    with pytest.raises(ValueError):
        await Turns(Service(), [])._execute_tool(workspace, name="edit_file", arguments={"path": "calc.py", "old": "len", "new": "sum"}, mode="plan")


@pytest.mark.asyncio
async def test_single_source_deletion_is_reviewable_and_automatic_syntax_skips_missing_file(source):
    workspace = SandboxWorkspace(source)
    await workspace.delete_file("obsolete.py")
    assert not (source.root / "obsolete.py").exists()
    assert workspace.mutation_revision == 1
    await workspace.syntax_verify(["obsolete.py"])
    patch = await workspace.patch()
    assert "deleted file mode" in patch and "-OLD = True" in patch
    with pytest.raises(ValueError):
        await workspace.delete_file("obsolete.py")
    with pytest.raises(ValueError):
        await workspace.delete_file(".")


@pytest.mark.asyncio
async def test_bounded_read_ranges_can_inspect_and_exactly_edit_later_source(source):
    path = source.root / "large.py"
    path.write_text("".join(f"VALUE_{i} = {i}\n" for i in range(600)), encoding="utf-8")
    workspace = SandboxWorkspace(source)
    first = await workspace.read_file("large.py")
    assert "VALUE_0 = 0" in first and "VALUE_500 = 500" not in first
    later = await workspace.read_file("large.py", start_line=499, max_lines=5)
    assert "VALUE_500 = 500" in later and "VALUE_0 = 0" not in later
    await workspace.edit_file("large.py", "VALUE_500 = 500", "VALUE_500 = 501")
    assert "VALUE_500 = 501" in path.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        await workspace.read_file("large.py", start_line=True)


def test_context_compaction_preserves_objective_recent_tool_pair_and_bounds_bytes():
    messages = [{"role": "user", "content": "Original exact objective"}]
    for i in range(8):
        messages.extend([
            {"role": "assistant", "content": [{"type": "tool_use", "id": f"tool-{i}", "name": "write_file", "input": {"content": "x" * 40_000}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"tool-{i}", "content": "actual diagnostic " + "x" * 40_000}]},
        ])
    bounded = bounded_messages(messages, limit=12_000)
    assert bounded[0]["content"].startswith("Original exact objective")
    assert len(json.dumps(bounded, ensure_ascii=False, separators=(",", ":")).encode()) <= 12_000
    assert bounded[-2]["content"][0]["id"] == bounded[-1]["content"][0]["tool_use_id"] == "tool-7"
    assert "actual diagnostic" in bounded[-1]["content"][0]["content"]
    assert len(messages[-2]["content"][0]["input"]["content"]) == 40_000
    with pytest.raises(CodeRunnerError) as caught:
        bounded_messages([{"role": "user", "content": "x" * 2000}], limit=1000)
    assert caught.value.code == "CODE_CONTEXT_LIMIT"
