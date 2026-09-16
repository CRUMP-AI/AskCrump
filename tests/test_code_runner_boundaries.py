from __future__ import annotations

from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend import code_runner
from backend.code_runner import (
    CodeRunnerError,
    CrumpCodeRunner,
    SandboxWorkspace,
    normalize_workspace_path,
    validate_verification_command,
)
from scripts.run_crump_code_offline_benchmark import _LocalSandbox


def _git(root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=text,
    )


def _write(root: Path, relative: str, content: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _commit(root: Path, message: str = "fixture") -> None:
    _git(root, "add", "--all")
    _git(root, "commit", "-q", "-m", message)


@pytest.fixture
def local_repository(tmp_path: Path) -> tuple[Path, SandboxWorkspace]:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "fixture@example.test")
    _git(tmp_path, "config", "user.name", "Autonomous Crump fixture")
    _write(tmp_path, "src/app.py", "value = 1\n")
    _write(tmp_path, "src/other.py", "other = 1\n")
    _commit(tmp_path)
    return tmp_path, SandboxWorkspace(_LocalSandbox(tmp_path))


@pytest.mark.asyncio
async def test_patch_round_trips_exact_utf8_bytes_without_redaction(
    local_repository: tuple[Path, SandboxWorkspace],
):
    root, workspace = local_repository
    _write(root, "src/app.py", 'import os\nvalue = "placeholder"\n')
    _commit(root, "credential reference baseline")

    await workspace.read_file("src/app.py")
    await workspace.write_file(
        "src/app.py",
        'import os\nvalue = os.environ["API_KEY"]\nmessage = "café"\n',
    )

    patch = await workspace.patch()
    expected = _git(
        root,
        "diff",
        "--binary",
        "--no-ext-diff",
        "--no-textconv",
        "--",
        ".",
        text=False,
    ).stdout.decode("utf-8")

    assert patch.encode("utf-8") == expected.encode("utf-8")
    assert '["API_KEY"]' in patch
    assert "café" in patch
    assert "[REDACTED]" not in patch


@pytest.mark.asyncio
async def test_patch_over_limit_fails_without_returning_a_prefix(
    local_repository: tuple[Path, SandboxWorkspace], monkeypatch: pytest.MonkeyPatch
):
    _, workspace = local_repository
    monkeypatch.setattr(code_runner, "MAX_PATCH", 120)
    if hasattr(code_runner, "MAX_PATCH_BYTES"):
        monkeypatch.setattr(code_runner, "MAX_PATCH_BYTES", 120)

    await workspace.read_file("src/app.py")
    await workspace.write_file("src/app.py", f'value = "{"x" * 512}"\n')

    with pytest.raises(CodeRunnerError) as exc:
        await workspace.patch()

    assert exc.value.code == "PATCH_TOO_LARGE"


@pytest.mark.asyncio
async def test_patch_with_high_confidence_secret_fails_instead_of_rewriting(
    local_repository: tuple[Path, SandboxWorkspace],
):
    _, workspace = local_repository
    await workspace.read_file("src/app.py")
    await workspace.write_file(
        "src/app.py",
        f'STRIPE_KEY = "sk_live_{"A" * 32}"\n',
    )

    with pytest.raises(CodeRunnerError) as exc:
        await workspace.patch()

    assert exc.value.code == "PATCH_SENSITIVE_CONTENT"


@pytest.mark.asyncio
async def test_truncated_read_is_explicit_and_blocks_same_path_write(
    local_repository: tuple[Path, SandboxWorkspace], monkeypatch: pytest.MonkeyPatch
):
    root, workspace = local_repository
    _write(root, "src/large.py", "x" * 256)
    _commit(root, "large source")
    monkeypatch.setattr(code_runner, "MAX_FILE_READ", 32)
    if hasattr(code_runner, "MAX_FILE_READ_BYTES"):
        monkeypatch.setattr(code_runner, "MAX_FILE_READ_BYTES", 32)

    output = await workspace.read_file("src/large.py")

    assert "UNTRUSTED" in output.upper()
    assert "TRUNCATED" in output.upper()
    with pytest.raises((ValueError, CodeRunnerError), match="(?i)complete|truncat"):
        await workspace.write_file("src/large.py", "replacement = True\n")


@pytest.mark.asyncio
async def test_complete_read_larger_than_tool_default_reaches_model_without_second_cut(
    local_repository: tuple[Path, SandboxWorkspace],
):
    root, workspace = local_repository
    tail = "COMPLETE_READ_TAIL_MARKER"
    _write(root, "src/large.py", ("x" * 30_000) + tail)
    _commit(root, "bounded complete source")

    class RecordingService:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict]] = []

        async def get(self, **_kwargs):
            return {"status": "running"}

        async def append_event(self, _task, event_type, payload):
            self.events.append((event_type, payload))

    service = RecordingService()
    runner = CrumpCodeRunner(SimpleNamespace(code_max_agent_steps=2), service)
    runner._anthropic_turn = AsyncMock(
        side_effect=[
            {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "read-large",
                        "name": "read_file",
                        "input": {"path": "src/large.py"},
                    }
                ]
            },
            {"content": [{"type": "text", "text": "Review complete."}]},
        ]
    )

    result = await runner._agent_loop(
        task={
            "id": "task-id",
            "user_id": "user-id",
            "mode": "plan",
            "objective": "Review src/large.py.",
        },
        workspace=workspace,
        inventory="",
    )

    second_messages = runner._anthropic_turn.await_args_list[1].kwargs["messages"]
    tool_content = second_messages[-1]["content"][0]["content"]
    assert result == "Review complete."
    assert tail in tool_content
    assert "TRUNCATED" not in tool_content.upper()


@pytest.mark.asyncio
async def test_truncated_search_is_explicit_and_blocks_writes_in_scope(
    local_repository: tuple[Path, SandboxWorkspace],
):
    root, workspace = local_repository
    _write(
        root,
        "src/matches.py",
        "\n".join(f"needle = {index}" for index in range(205)) + "\n",
    )
    _commit(root, "many matches")

    await workspace.read_file("src/matches.py")
    output = await workspace.search("needle", "src")

    assert "UNTRUSTED" in output.upper()
    assert "TRUNCATED" in output.upper()
    with pytest.raises((ValueError, CodeRunnerError), match="(?i)complete|truncat"):
        await workspace.write_file("src/matches.py", "needle = 1\n")


@pytest.mark.asyncio
async def test_truncated_list_requires_complete_parent_before_new_file(
    local_repository: tuple[Path, SandboxWorkspace],
):
    root, workspace = local_repository
    for index in range(1001):
        _write(root, f"bulk/f{index:04d}.py", f"value = {index}\n")
    _commit(root, "large inventory")

    output = await workspace.list_files("")
    assert "UNTRUSTED" in output.upper()
    assert "TRUNCATED" in output.upper()

    with pytest.raises((ValueError, CodeRunnerError), match="(?i)complete|list"):
        await workspace.write_file("fresh/new.py", "value = 1\n")

    narrower = await workspace.list_files("fresh")
    assert "COMPLETE" in narrower.upper()
    result = await workspace.write_file("fresh/new.py", "value = 1\n")
    assert "fresh/new.py" in result


@pytest.mark.asyncio
async def test_existing_write_requires_complete_unredacted_read(
    local_repository: tuple[Path, SandboxWorkspace],
):
    _, workspace = local_repository

    with pytest.raises((ValueError, CodeRunnerError), match="(?i)read|complete"):
        await workspace.write_file("src/app.py", "value = 2\n")

    complete = await workspace.read_file("src/app.py")
    assert "COMPLETE" in complete.upper()
    result = await workspace.write_file("src/app.py", "value = 2\n")
    assert "src/app.py" in result


@pytest.mark.parametrize(
    "unsafe",
    (
        "/tmp/escape.py",
        "C:/escape.py",
        "~/escape.py",
        "src//escape.py",
        "src/\nignore.py",
        "src/.git/hooks/check.py",
        ".env.production",
        "config/secrets.yml",
    ),
)
def test_sensitive_noncanonical_and_control_character_paths_are_rejected(unsafe: str):
    with pytest.raises(ValueError):
        normalize_workspace_path(unsafe)


@pytest.mark.asyncio
async def test_search_never_returns_matches_from_protected_files(
    local_repository: tuple[Path, SandboxWorkspace],
):
    root, workspace = local_repository
    marker = "DO_NOT_RETURN_PROTECTED_VALUE"
    _write(root, ".env", f"PRIVATE_TOKEN={marker}\n")
    _write(root, "src/safe.py", "safe = True\n")
    _commit(root, "protected search fixture")

    output = await workspace.search(marker)

    assert marker not in output
    assert ".env" not in output


@pytest.mark.asyncio
async def test_same_workspace_symlink_cannot_be_read_as_a_regular_source_file(
    local_repository: tuple[Path, SandboxWorkspace],
):
    root, workspace = local_repository
    _write(root, "private.py", "PRIVATE_TOKEN = 'not-for-the-agent'\n")
    alias = root / "src" / "alias.py"
    try:
        alias.symlink_to(Path("..") / "private.py")
    except (OSError, NotImplementedError):
        pytest.skip("This host cannot create an unprivileged symlink fixture.")
    _commit(root, "symlink fixture")

    with pytest.raises((ValueError, CodeRunnerError), match="(?i)symlink|safely|read"):
        await workspace.read_file("src/alias.py")


@pytest.mark.parametrize(
    ("command", "args"),
    (
        ("git", ["show", "HEAD:.env"]),
        ("git", ["diff", "HEAD~1"]),
        ("git", ["diff", "--no-index", ".env", "README.md"]),
        ("git", ["rev-parse", "--git-dir"]),
        ("git", ["ls-files", ".env"]),
        ("npm", ["run", "send-secrets"]),
        ("python3", ["-m", "pytest", "-p", "malicious_plugin"]),
        ("pytest", ["--rootdir=/tmp", "tests"]),
    ),
)
def test_verification_grammar_rejects_history_protected_paths_and_arbitrary_scripts(
    command: str, args: list[str]
):
    with pytest.raises(ValueError):
        validate_verification_command(command, args)


@pytest.mark.parametrize(
    ("command", "args"),
    (
        ("git", ["status", "--short"]),
        ("git", ["diff", "--check"]),
        ("git", ["diff", "--stat"]),
        ("git", ["rev-parse", "HEAD"]),
        ("python3", ["-m", "pytest", "-q", "tests/test_safe.py"]),
        ("npm", ["run", "lint"]),
    ),
)
def test_verification_grammar_preserves_bounded_useful_checks(
    command: str, args: list[str]
):
    executable, canonical = validate_verification_command(command, args)
    assert executable == command
    assert canonical


def test_verification_argument_overflow_is_rejected_instead_of_silently_dropped():
    with pytest.raises(ValueError):
        validate_verification_command(
            "python3",
            ["-m", "py_compile", *[f"src/f{index}.py" for index in range(24)]],
        )


@pytest.mark.asyncio
async def test_malicious_verification_mutation_taints_workspace_and_blocks_patch(
    local_repository: tuple[Path, SandboxWorkspace],
):
    root, workspace = local_repository
    _write(
        root,
        "tests/test_mutator.py",
        (
            "from pathlib import Path\n\n"
            "def test_mutate_an_unapproved_file():\n"
            "    Path('src/other.py').write_text('tampered = True\\n', encoding='utf-8')\n"
        ),
    )
    _commit(root, "malicious verification fixture")

    await workspace.read_file("src/app.py")
    await workspace.write_file("src/app.py", "value = 2\n")

    with pytest.raises(CodeRunnerError) as exc:
        await workspace.run_verification(
            "python3", ["-m", "pytest", "-q", "tests/test_mutator.py"]
        )
    assert exc.value.code == "WORKSPACE_UNAUTHORIZED_MUTATION"

    with pytest.raises(CodeRunnerError) as patch_exc:
        await workspace.patch()
    assert patch_exc.value.code == "WORKSPACE_UNAUTHORIZED_MUTATION"
