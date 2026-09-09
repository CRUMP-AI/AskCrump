"""Exercise Crump Code's production orchestration against fixed local fixtures.

This harness deliberately uses no network, provider credential, Vercel Sandbox, user
content, or production task. Scripted model turns make orchestration regressions
deterministic; the separate receipt evaluator remains responsible for scoring.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.code_runner import (  # noqa: E402
    CrumpCodeRunner,
    SandboxWorkspace,
    redact_sensitive_text,
)
from scripts.evaluate_crump_code_benchmark import (  # noqa: E402
    DEFAULT_MANIFEST,
    evaluate_benchmark,
    validate_manifest,
)


OUTPUT_ROOT = (ROOT / "output" / "crump-code-benchmark").resolve()
FIXTURE_ROOT = ROOT / "benchmarks" / "crump_code" / "fixtures"

PYTHON_BOUNDARY = '''"""Small numeric range helpers."""


def clamp(value: int, lower: int, upper: int) -> int:
    """Return value constrained to the inclusive lower/upper range."""
    if lower > upper:
        raise ValueError("lower must not exceed upper")
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value
'''

JAVASCRIPT_SLUG = '''export function slugify(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\\s_-]+/g, "-")
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}
'''

SECURITY_HEADERS = '''"""Header logging boundary for the benchmark fixture."""


SENSITIVE_HEADERS = {"authorization", "x-api-key", "cookie"}


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy safe for diagnostic logging."""
    return {
        name: "[REDACTED]" if name.lower() in SENSITIVE_HEADERS else value
        for name, value in headers.items()
    }
'''


def _tool(identifier: str, name: str, **arguments: Any) -> dict[str, Any]:
    return {"type": "tool_use", "id": identifier, "name": name, "input": arguments}


def _scripted_turns(case: dict[str, Any]) -> list[dict[str, Any]]:
    case_id = case["id"]
    if case_id == "python-boundary-001":
        target = "benchmarks/crump_code/fixtures/python_boundary/range_utils.py"
        acceptance = "benchmarks/crump_code/fixtures/python_boundary/acceptance_range_utils.py"
        content = PYTHON_BOUNDARY
        summary = "range_utils.py now uses each nearest inclusive boundary; pytest passed."
    elif case_id == "javascript-slug-001":
        target = "benchmarks/crump_code/fixtures/javascript_slug/slug.js"
        acceptance = "benchmarks/crump_code/fixtures/javascript_slug/acceptance_slug.py"
        content = JAVASCRIPT_SLUG
        summary = "slug.js now normalizes every separator; pytest passed."
    elif case_id == "security-headers-001":
        target = "benchmarks/crump_code/fixtures/security_headers/header_redaction.py"
        acceptance = "benchmarks/crump_code/fixtures/security_headers/acceptance_header_redaction.py"
        content = SECURITY_HEADERS
        summary = "header_redaction.py now compares names case-insensitively; pytest passed."
    elif case_id == "atomic-plan-001":
        reads = [
            _tool("read-api", "read_file", path="benchmarks/crump_code/fixtures/atomic_plan/api.py"),
            _tool(
                "read-store", "read_file", path="benchmarks/crump_code/fixtures/atomic_plan/store.py"
            ),
            _tool(
                "read-acceptance",
                "read_file",
                path="benchmarks/crump_code/fixtures/atomic_plan/acceptance_atomic_plan.md",
            ),
        ]
        return [
            {"content": reads},
            {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "In store.py, replace the separate read_count/write_count boundary with "
                            "one atomic increment-if-below-limit operation implemented by the store. "
                            "In api.py, await that atomic operation and preserve allow_request's boolean "
                            "contract. Add a concurrent test that releases more simultaneous calls than "
                            "the configured limit and proves exactly the limit succeed."
                        ),
                    }
                ]
            },
        ]
    else:  # pragma: no cover - the manifest validator and parity test guard this path
        raise ValueError("The fixed benchmark contains an unsupported case.")

    command = case["required_verifications"][0].split(" ")
    return [
        {
            "content": [
                _tool("read-target", "read_file", path=target),
                _tool("read-acceptance", "read_file", path=acceptance),
            ]
        },
        {
            "content": [
                _tool("write-target", "write_file", path=target, content=content),
                _tool("verify", "run_verification", command=command[0], args=command[1:]),
            ]
        },
        {"content": [{"type": "text", "text": summary}]},
    ]


class _LocalFs:
    def __init__(self, root: Path) -> None:
        self.root = root

    async def mkdir(self, path: str, *, recursive: bool) -> None:
        (self.root / path).mkdir(parents=recursive, exist_ok=True)

    async def write_text(self, path: str, content: str) -> None:
        (self.root / path).write_text(content, encoding="utf-8")


class _LocalSandbox:
    """Minimal deny-network stand-in for SandboxWorkspace's process and file APIs."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.fs = _LocalFs(root)
        bundled_node = (
            Path(sys.executable).resolve().parent.parent / "node" / "bin" / "node.exe"
        )
        self.node = (
            os.environ.get("ASKCRUMP_NODE_EXECUTABLE")
            or os.environ.get("CRUMP_BENCHMARK_NODE")
            or shutil.which("node")
            or (str(bundled_node) if bundled_node.is_file() else "node")
        )

    async def run_process(
        self,
        command: str,
        args: list[str],
        *,
        kill_after: int,
        capture_output: bool,
    ) -> SimpleNamespace:
        executable = sys.executable if command in {"python", "python3"} else command
        if command == "node":
            executable = self.node
        environment = os.environ.copy()
        environment["CRUMP_BENCHMARK_NODE"] = self.node
        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                *args,
                cwd=self.root,
                env=environment,
                stdout=asyncio.subprocess.PIPE if capture_output else None,
                stderr=asyncio.subprocess.PIPE if capture_output else None,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=kill_after)
        except (OSError, asyncio.TimeoutError):
            if "process" in locals() and process.returncode is None:
                process.kill()
                await process.communicate()
            return SimpleNamespace(returncode=124, stdout="", stderr="process unavailable")
        return SimpleNamespace(
            returncode=int(process.returncode or 0),
            stdout=(stdout or b"").decode("utf-8", errors="replace"),
            stderr=(stderr or b"").decode("utf-8", errors="replace"),
        )


class _BenchmarkWorkspace(SandboxWorkspace):
    def __init__(self, root: Path, revision: str) -> None:
        super().__init__(_LocalSandbox(root))
        self.revision = revision

    async def base_revision(self) -> str:
        return self.revision

    async def patch(self) -> str:
        result = await self._run(
            "git", ["diff", "--binary", "--no-ext-diff", "--", "."], kill_after=30
        )
        if result.returncode != 0:
            raise RuntimeError("The offline fixture patch could not be packaged.")
        return redact_sensitive_text(result.stdout, limit=200_000)


class _MemoryTaskService:
    def __init__(self, task: dict[str, Any]) -> None:
        self.task = dict(task)
        self.events: list[dict[str, Any]] = []

    async def get(self, **_kwargs: Any) -> dict[str, Any]:
        return dict(self.task)

    async def append_event(
        self, _task: dict[str, Any], event_type: str, payload: dict[str, Any]
    ) -> None:
        self.events.append({"type": event_type, "payload": dict(payload)})

    async def transition(
        self,
        _task: dict[str, Any],
        status: str,
        *,
        changes: dict[str, Any] | None = None,
        event_type: str,
        event_payload: dict[str, Any],
    ) -> dict[str, Any]:
        self.task = {**self.task, **(changes or {}), "status": status}
        await self.append_event(self.task, event_type, event_payload)
        return dict(self.task)


class _ScriptedRunner(CrumpCodeRunner):
    def __init__(self, service: _MemoryTaskService, turns: list[dict[str, Any]]) -> None:
        super().__init__(SimpleNamespace(code_max_agent_steps=6), service)
        self.turns = list(turns)

    async def _anthropic_turn(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        del messages, tools
        if not self.turns:
            raise RuntimeError("The scripted provider exhausted its fixed turns.")
        return self.turns.pop(0)


def _initialize_fixture_repository(root: Path) -> None:
    destination = root / "benchmarks" / "crump_code" / "fixtures"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(FIXTURE_ROOT, destination)
    commands = (
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "benchmark@localhost.invalid"],
        ["git", "config", "user.name", "Crump Code Offline Benchmark"],
        ["git", "add", "--", "."],
        ["git", "commit", "--quiet", "-m", "fixed benchmark fixture"],
    )
    for command in commands:
        subprocess.run(command, cwd=root, check=True, capture_output=True)  # noqa: S603


async def run_offline_benchmark(manifest_path: Path = DEFAULT_MANIFEST) -> tuple[dict, dict]:
    manifest = validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))
    runs: list[dict[str, Any]] = []
    for case in manifest["cases"]:
        started = time.monotonic()
        with TemporaryDirectory(prefix="crump-code-benchmark-") as directory:
            root = Path(directory)
            _initialize_fixture_repository(root)
            task = {
                "id": f"offline-{case['id']}",
                "user_id": "offline-benchmark",
                "mode": case["mode"],
                "objective": case["objective"],
                "status": "provisioning",
                "lease_token": "offline-fixed-lease",
            }
            service = _MemoryTaskService(task)
            runner = _ScriptedRunner(service, _scripted_turns(case))
            workspace = _BenchmarkWorkspace(root, manifest["source"]["revision"])
            result = await runner._run_in_workspace(task, workspace)
            duration_ms = max(1, round((time.monotonic() - started) * 1000))
            runs.append(
                {
                    "case_id": case["id"],
                    "mode": case["mode"],
                    "status": result["status"],
                    "base_revision": result["base_revision"],
                    "result_summary": result["result_summary"],
                    "result_patch": result["result_patch"],
                    "verification": result["verification"],
                    "duration_ms": duration_ms,
                    "attempt_count": 1,
                }
            )
    artifact = {
        "suite_id": manifest["suite_id"],
        "source_revision": manifest["source"]["revision"],
        "runs": runs,
    }
    return artifact, evaluate_benchmark(manifest, artifact)


def _output_path(name: str) -> Path:
    target = (OUTPUT_ROOT / name).resolve()
    if target.parent != OUTPUT_ROOT:
        raise ValueError("Offline benchmark output must stay in its private output directory.")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", default="offline-artifact.json")
    parser.add_argument("--report", default="offline-report.json")
    args = parser.parse_args()
    artifact, report = asyncio.run(run_offline_benchmark())
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    _output_path(args.artifact).write_text(
        json.dumps(artifact, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    _output_path(args.report).write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
