"""Real temporary Git repositories exercise review-artifact boundaries offline."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.code_runner import CodeRunnerError, CrumpCodeRunner, SandboxWorkspace


class LocalRepository:
    def __init__(self, root: Path, scratch: Path):
        self.root = root
        self.scratch = scratch
        self.commands = []
        self.fs = SimpleNamespace(mkdir=self.mkdir, write_text=self.write_text)
        self.environment = {key: os.environ[key] for key in ("SystemRoot", "WINDIR", "TEMP", "TMP", "PATH")
                            if key in os.environ}
        self.environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                                 "GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "Offline fixture",
                                 "GIT_AUTHOR_EMAIL": "offline@example.invalid", "GIT_COMMITTER_NAME": "Offline fixture",
                                 "GIT_COMMITTER_EMAIL": "offline@example.invalid", "PYTHONDONTWRITEBYTECODE": "1",
                                 "PYTHONPYCACHEPREFIX": str(scratch / "pycache"),
                                 "PYTEST_ADDOPTS": "-p no:cacheprovider"})
        self.git_executable = shutil.which("git")
        assert self.git_executable, "Offline Git is required to verify actual artifact semantics"

    async def mkdir(self, path, *, recursive):
        (self.root / path).mkdir(parents=recursive, exist_ok=True)

    async def write_text(self, path, content):
        (self.root / path).write_text(content, encoding="utf-8")

    def git(self, *args):
        result = subprocess.run([self.git_executable, *args], cwd=self.root, env=self.environment,
                                capture_output=True, text=True, timeout=10, check=False)
        assert result.returncode == 0, result.stderr
        return result.stdout

    async def run_process(self, command, args, *, kill_after, capture_output):
        assert capture_output is True
        self.commands.append([command, *args])
        executable = sys.executable if command == "python3" else self.git_executable
        assert command in {"python3", "git"}, "This fixture executes no other programs"
        patch_path = str(self.scratch / "review.patch")
        actual_args = ["pycache_prefix=" + str(self.scratch / "pycache") if value == "pycache_prefix=/tmp/crump-code-pycache" else
                       patch_path if value == "/tmp/crump-code.patch" else
                       "--output=" + patch_path if value == "--output=/tmp/crump-code.patch" else value
                       for value in args]
        process = await asyncio.create_subprocess_exec(
            executable, *actual_args, cwd=self.root, env=self.environment,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=kill_after)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.communicate()
            raise
        return SimpleNamespace(returncode=process.returncode,
                               stdout=stdout.decode("utf-8", errors="replace"),
                               stderr=stderr.decode("utf-8", errors="replace"))


@pytest.fixture
def repository(tmp_path):
    # Keep native Windows cache paths below MAX_PATH: py_compile embeds the
    # absolute source path below its otherwise isolated cache prefix.
    root = tmp_path / "r"
    root.mkdir()
    scratch = tmp_path / "s"
    scratch.mkdir()
    repo = LocalRepository(root, scratch)
    repo.git("init", "--quiet")
    (root / ".gitignore").write_text("generated/\ntracked.py\n", encoding="utf-8")
    (root / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / ".env").write_text("Public filename-protection fixture only\n", encoding="utf-8")
    repo.git("add", "--force", ".gitignore", "tracked.py", ".env")
    repo.git("-c", "commit.gpgsign=false", "commit", "--quiet", "--no-verify", "-m", "Offline fixture")
    return repo


@pytest.mark.asyncio
async def test_ignored_write_is_rejected_before_any_directory_or_file_is_created(repository):
    workspace = SandboxWorkspace(repository)
    with pytest.raises(ValueError, match="ignored by Git"):
        await workspace.write_file("generated/helper.py", "VALUE = 2\n")
    assert not (repository.root / "generated").exists()
    assert workspace.changed_files == set()
    assert await workspace.changed_paths() == []
    assert await workspace.patch() == ""


@pytest.mark.asyncio
async def test_tracked_file_matching_ignore_rules_is_editable_and_included_in_patch(repository):
    workspace = SandboxWorkspace(repository)
    assert "Wrote tracked.py" in await workspace.write_file("tracked.py", "VALUE = 2\n")
    assert await workspace.changed_paths() == ["tracked.py"]
    patch = await workspace.patch()
    assert "diff --git a/tracked.py b/tracked.py" in patch
    assert "-VALUE = 1" in patch and "+VALUE = 2" in patch


@pytest.mark.asyncio
async def test_source_filename_with_spaces_survives_real_status_syntax_and_patch(repository):
    workspace = SandboxWorkspace(repository)
    path = "helper with spaces.py"
    await workspace.write_file(path, "def answer():\n    return 42\n")
    assert await workspace.changed_paths() == [path]
    await workspace.syntax_verify([path])
    assert workspace.verification[0]["returnCode"] == 0, workspace.verification[0]
    assert await workspace.changed_paths() == [path]
    patch = await workspace.patch()
    assert path in patch and "+    return 42" in patch
    assert not list(repository.root.rglob("*.pyc"))


@pytest.mark.asyncio
async def test_safe_rename_lists_both_actual_source_and_destination(repository):
    repository.git("mv", "tracked.py", "renamed safely.py")
    assert await SandboxWorkspace(repository).changed_paths() == ["renamed safely.py", "tracked.py"]


@pytest.mark.asyncio
async def test_real_rename_cannot_hide_a_protected_source_behind_a_safe_destination(repository):
    repository.git("mv", ".env", "public.txt")
    with pytest.raises(CodeRunnerError) as caught:
        await SandboxWorkspace(repository).changed_paths()
    assert caught.value.code == "CODE_RESULT_INCOMPLETE"


@pytest.mark.asyncio
async def test_write_then_exact_revert_reports_no_actual_changes_or_patch(repository):
    workspace = SandboxWorkspace(repository)
    await workspace.write_file("tracked.py", "VALUE = 2\n")
    await workspace.write_file("tracked.py", "VALUE = 1\n")
    assert "tracked.py" in workspace.changed_files
    assert await workspace.changed_paths() == []
    assert await workspace.patch() == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("output", [" M notes.txt", "R  safe.txt\0", "bad\0", "\0",
                                      "?? ../escape.py\0", "?? leading.py \0"])
async def test_malformed_truncated_or_ambiguous_nul_inventory_fails_closed(output):
    sandbox = SimpleNamespace(run_process=AsyncMock(return_value=SimpleNamespace(returncode=0, stdout=output)))
    with pytest.raises(CodeRunnerError) as caught:
        await SandboxWorkspace(sandbox).changed_paths()
    assert caught.value.code == "CODE_RESULT_INCOMPLETE"


@pytest.mark.asyncio
async def test_failed_intent_to_add_stops_before_diff_or_partial_patch_read():
    sandbox = SimpleNamespace(run_process=AsyncMock(return_value=SimpleNamespace(returncode=128, stdout="")))
    with pytest.raises(CodeRunnerError) as caught:
        await SandboxWorkspace(sandbox).patch()
    assert caught.value.code == "CODE_RESULT_INCOMPLETE"
    assert sandbox.run_process.await_count == 1
    assert sandbox.run_process.await_args.args[:2] == ("git", ["add", "-N", "--", "."])


@pytest.mark.asyncio
async def test_uncertain_ignore_lookup_fails_before_any_file_write():
    fs = SimpleNamespace(mkdir=AsyncMock(), write_text=AsyncMock())
    sandbox = SimpleNamespace(fs=fs, run_process=AsyncMock(side_effect=[
        SimpleNamespace(returncode=0, stdout=""), SimpleNamespace(returncode=128, stdout="")]))
    with pytest.raises(CodeRunnerError) as caught:
        await SandboxWorkspace(sandbox).write_file("helper.py", "VALUE = 2\n")
    assert caught.value.code == "CODE_RESULT_INCOMPLETE"
    fs.mkdir.assert_not_called()
    fs.write_text.assert_not_called()


@pytest.mark.asyncio
async def test_verification_side_effect_is_rescanned_before_patch_or_completion(repository):
    class Workspace(SandboxWorkspace):
        async def syntax_verify(self, paths):
            await super().syntax_verify(paths)
            (repository.root / "unexpected.bin").write_bytes(b"unreviewable verification side effect")

    row = {"id": "offline-task", "user_id": "offline-user", "status": "provisioning", "mode": "implement"}
    transitions = []

    async def current(**_kwargs): return dict(row)

    async def transition(_task, status, **kwargs):
        transitions.append(status)
        row.update(kwargs.get("changes", {}), status=status)
        return dict(row)

    service = SimpleNamespace(get=current, transition=transition, append_event=AsyncMock())
    workspace = Workspace(repository)
    runner = CrumpCodeRunner(SimpleNamespace(), service)

    async def agent_loop(**_kwargs):
        await workspace.write_file("helper.py", "VALUE = 2\n")
        return "Offline fixture"

    runner._agent_loop = agent_loop
    with pytest.raises(CodeRunnerError) as caught:
        await runner._run_in_workspace(dict(row), workspace)
    assert caught.value.code == "CODE_RESULT_INCOMPLETE"
    assert workspace.verification[0]["returnCode"] == 0
    assert transitions == ["running", "verifying"]
    assert not (repository.scratch / "review.patch").exists()
