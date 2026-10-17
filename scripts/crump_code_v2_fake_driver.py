"""Deterministic fake-provider driver for the Autonomous Crump verification loop.

PLUMBING EVIDENCE ONLY. This module replaces ONLY the model-provider call
(CrumpCodeRunner._request_turn) with a deterministic, seeded fake. The REAL
tool, repair, cancellation, limit, verification, and artifact-packaging
lifecycle is preserved end-to-end: the fake answers provider turns, everything
else runs for real.

Nothing here evaluates model capability. No model is called. No paid
infrastructure is used. Per-case labels remain "Not evaluated (model
evaluation not run)"; fake execution proves the loop runs, nothing more.
Evaluator-owned oracle isolation is separately open and is not claimed here.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

FIXED_EPOCH = "2026-01-01T00:00:00+00:00"
PROVIDER_NAME = "deterministic-fake"
SUPPORTED_OBSERVATION_CONTRACTS = ("rename-boundary", "workspace-paths", "image-size")

# Same lifecycle vocabulary as backend/code_service.py (mirrored, not imported,
# so this driver has no database dependency).
TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"provisioning", "cancelled"}),
    "provisioning": frozenset({"running", "queued", "failed", "cancelled"}),
    "running": frozenset({"verifying", "awaiting_approval", "failed", "cancelled"}),
    "awaiting_approval": frozenset({"queued", "failed", "cancelled"}),
    "verifying": frozenset({"completed", "failed", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}
EVENT_TYPES = frozenset(
    {
        "task.created",
        "task.claimed",
        "sandbox.provisioned",
        "agent.started",
        "tool.requested",
        "tool.completed",
        "verification.started",
        "verification.completed",
        "approval.requested",
        "approval.decided",
        "task.completed",
        "task.failed",
        "task.cancelled",
        "task.requeued",
    }
)


def _text_response(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


def _tool_response(text: str, name: str, input_: dict[str, Any]) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    if text:
        blocks.append({"type": "text", "text": text})
    blocks.append({"type": "tool_use", "name": name, "input": input_})
    return {"content": blocks}


class DeterministicFakeProvider:
    """Drop-in provider replacement: deterministic, seeded, no network.

    Subclass CrumpCodeRunner and override ONLY _request_turn, exactly the seam
    the production code documents for independently authorized adapters. The
    tool, repair, cancellation, limit, verification, and packaging lifecycle is
    inherited unchanged.
    """

    def __init__(
        self,
        runner_cls,
        settings,
        service,
        *,
        seed: str,
        script: list[dict[str, Any]] | None = None,
        cancel_after_turns: int | None = None,
    ) -> None:
        # runner_cls is backend.code_runner.CrumpCodeRunner; passed in so this
        # module never imports backend at module scope (keeps unit-test
        # collection light).
        self._runner = runner_cls(settings, service)
        self.settings = settings
        self.service = service
        self.seed = seed
        self.script = script if script is not None else []
        self.cancel_after_turns = cancel_after_turns
        self.turn_log: list[dict[str, Any]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._runner, name)

    async def _request_turn(
        self,
        *,
        task: dict[str, Any],
        call_key: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        step = len(self.turn_log)
        entry = self.script[min(step, len(self.script) - 1)]
        payload = copy.deepcopy(entry)
        for index, block in enumerate(payload.get("content", [])):
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and not block.get("id")
            ):
                block["id"] = f"toolu_fake_{self.seed}_{step}_{index}"
        saw_repair_feedback = any(
            isinstance(m, dict)
            and m.get("role") == "user"
            and "Final verification requires repair" in json.dumps(m.get("content", ""))
            for m in messages
        )
        self.turn_log.append(
            {
                "call_key": call_key,
                "step": step,
                "message_count": len(messages),
                "saw_repair_feedback": saw_repair_feedback,
            }
        )
        if self.cancel_after_turns is not None and step + 1 >= self.cancel_after_turns:
            # Simulate an external cancellation landing between provider turns.
            self.service.cancel_requested = True
        return payload

    async def run_in_workspace(
        self, task: dict[str, Any], workspace: Any
    ) -> dict[str, Any]:
        # Route through the REAL production loop; only _request_turn is fake.
        original = self._runner._request_turn
        self._runner._request_turn = self._request_turn  # type: ignore[method-assign]
        try:
            return await self._runner.run_in_workspace(task, workspace)
        finally:
            self._runner._request_turn = original


class FakeCodeTaskService:
    """In-memory task service mirroring the production lifecycle vocabulary."""

    def __init__(self, task: dict[str, Any]) -> None:
        self.task = dict(task)
        self.events: list[dict[str, Any]] = []
        self._clock = 0
        self.cancel_requested = False

    def _tick(self) -> str:
        self._clock += 1
        return f"2026-01-01T00:00:{self._clock:02d}+00:00"

    async def get(
        self, *, user_id: str, task_id: str, include_history: bool = False
    ) -> dict[str, Any]:
        task = dict(self.task)
        if self.cancel_requested:
            task["status"] = "cancelled"
        return task

    async def append_event(
        self,
        task: dict[str, Any],
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if event_type not in EVENT_TYPES:
            raise ValueError("Unknown Crump Code event type.")
        self.events.append(
            {
                "t": self._tick(),
                "event_type": event_type,
                "payload": copy.deepcopy(payload),
            }
        )

    async def transition(
        self,
        task: dict[str, Any],
        target: str,
        *,
        changes: dict[str, Any] | None = None,
        event_type: str | None = None,
        event_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        current = str(task.get("status") or "")
        if target not in TRANSITIONS.get(current, frozenset()):
            raise ValueError(f"Crump Code task cannot move from {current} to {target}.")
        updated = dict(task)
        updated["status"] = target
        updated.update(changes or {})
        self.task = updated
        if event_type:
            await self.append_event(updated, event_type, event_payload)
        return dict(updated)


def _hermetic_git_env() -> dict[str, str]:
    """Fixed timestamps plus a hermetic git config.

    The runner rejects repositories with clean/process filters; CI runner
    images configure Git LFS globally, which is host noise, not a repository
    filter. Ignoring system/global config keeps the temp repos hermetic.
    """
    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = FIXED_EPOCH
    env["GIT_COMMITTER_DATE"] = FIXED_EPOCH
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    return env


class LocalSandbox:
    """Runs workspace commands as local subprocesses. No paid infrastructure."""

    def __init__(self, root: str) -> None:
        self.root = root
        self.commands: list[dict[str, Any]] = []

    async def run_process(
        self,
        command: str,
        args: list[str],
        *,
        kill_after: int = 40,
        capture_output: bool = True,
    ) -> Any:
        env = _hermetic_git_env()
        self.commands.append({"command": command, "args": list(args)})
        proc = await asyncio.create_subprocess_exec(
            command,
            *args,
            cwd=self.root,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=kill_after
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return SimpleNamespace(returncode=124, stdout="", stderr="timed out")
        return SimpleNamespace(
            returncode=proc.returncode,
            stdout=stdout.decode("utf-8", "replace"),
            stderr=stderr.decode("utf-8", "replace"),
        )


def prepare_workspace(case_id: str, corpus_root: Path, dest: Path) -> None:
    """Copy a case workspace into a fresh git repo with fixed timestamps."""
    src = corpus_root / "cases" / case_id / "workspace"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    # Real target repositories ignore build/test caches; without this, the
    # runner's own source-integrity accounting rejects pytest's __pycache__.
    (dest / ".gitignore").write_text(
        "__pycache__/\n*.pyc\n.pytest_cache/\n", encoding="utf-8"
    )
    env = _hermetic_git_env()

    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=dest,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    git("init", "-q")
    git("config", "user.email", "fake-driver@example.invalid")
    git("config", "user.name", "fake-driver")
    git("config", "init.defaultBranch", "main")
    git("add", "-A")
    git("commit", "-q", "-m", f"fake-driver base for {case_id}")


def default_script(case: Any) -> list[dict[str, Any]]:
    """Inspect, read one required file, run visible checks, summarize."""
    steps = [
        _tool_response(
            "Inspecting the workspace inventory.", "list_files", {"path": ""}
        ),
    ]
    first_py = sorted(p for p in case.required_paths if p.endswith(".py"))
    target = first_py[0] if first_py else sorted(case.required_paths)[0]
    steps.append(
        _tool_response(
            f"Reading {target}.",
            "read_file",
            {"path": target, "start_line": 1, "max_lines": 250},
        )
    )
    if "tests/test_visible.py" in case.workspace:
        steps.append(
            _tool_response(
                "Running the visible checks.",
                "run_verification",
                {
                    "command": "python3",
                    "args": ["-m", "pytest", "tests/test_visible.py", "-q"],
                },
            )
        )
    steps.append(
        _text_response("Inspection and checks complete. No source changes were needed.")
    )
    return steps


def _canonicalize(value: Any) -> Any:
    """Strip wall-clock noise so two runs compare byte-identically."""
    if isinstance(value, dict):
        return {k: _canonicalize(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\"']*", "<ts>", value)
        value = re.sub(r" in \d+\.\d+s", " in <dur>s", value)
        value = re.sub(r"\d+\.\d+s\b", "<dur>s", value)
        return value
    return value


def _tool_calls_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls = []
    for event in events:
        if event["event_type"] == "tool.requested":
            payload = event["payload"] or {}
            calls.append(
                {k: payload[k] for k in ("tool", "path", "command") if k in payload}
            )
    return calls


def _receipts_summary(receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"command": r.get("command"), "returnCode": r.get("returnCode")}
        for r in receipts
    ]


async def drive_case(
    case: Any,
    *,
    corpus_root: Path,
    work_root: Path,
    runner_cls: Any,
    settings: Any,
    script: list[dict[str, Any]] | None = None,
    seed: str | None = None,
    cancel_after_turns: int | None = None,
    adapter_support: str = "supported",
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    """Drive one corpus case through the REAL production loop with a fake provider.

    Returns a plumbing-only record. The honest per-case label is unchanged:
    "Not evaluated (model evaluation not run)".
    """
    seed = seed or f"{case.id}-v1"
    dest = work_root / f"ws-{case.id}"
    prepare_workspace(case.id, corpus_root, dest)

    from backend.code_runner import (  # local import: heavy deps
        CodeRunnerError,
        SandboxWorkspace,
    )

    task = {
        "id": f"fake-{case.id}",
        "user_id": "fake-user",
        "project_id": "fake-project",
        "status": "provisioning",
        "mode": "implement",
        "objective": case.objective,
        "provider_budget_policy": {"max_input_bytes": 112_000},
        "lease_token": None,
        "failure_code": None,
    }
    service = FakeCodeTaskService(task)
    provider = DeterministicFakeProvider(
        runner_cls,
        settings,
        service,
        seed=seed,
        script=script if script is not None else default_script(case),
        cancel_after_turns=cancel_after_turns,
    )
    workspace = SandboxWorkspace(LocalSandbox(str(dest)))
    outcome = {"final_status": None, "failure_code": None, "error": None}
    try:
        result = await provider.run_in_workspace(task, workspace)
        outcome["final_status"] = result.get("status")
        outcome["failure_code"] = result.get("failure_code")
        outcome["result_patch_bytes"] = len(result.get("result_patch") or "")
        outcome["verification"] = _receipts_summary(result.get("verification") or [])
    except CodeRunnerError as exc:
        if exc.code == "CODE_TASK_CANCELLED":
            cancelled = await service.transition(
                service.task,
                "cancelled",
                event_type="task.cancelled",
                event_payload={"status": "cancelled", "failureCode": exc.code},
            )
            outcome["final_status"] = cancelled.get("status")
            outcome["failure_code"] = exc.code
        else:
            outcome["final_status"] = "error"
            outcome["error"] = {"code": exc.code, "message": str(exc)[:200]}
    repair_rounds = sum(
        1
        for e in service.events
        if e["event_type"] == "verification.completed"
        and (e["payload"] or {}).get("status") == "repair_required"
    )
    record = {
        "id": case.id,
        "stratum": case.stratum,
        "adapter_support": adapter_support,
        "blocked_reason": blocked_reason,
        "honest_label": "Not evaluated",
        "honest_reason": "model evaluation not run",
        "plumbing_only": True,
        "driver": {
            "provider": PROVIDER_NAME,
            "seed": seed,
            "model_calls": 0,
            "paid_sandbox_used": False,
            "provider_turns": len(provider.turn_log),
            "tool_calls": _tool_calls_from_events(service.events),
            "repair_rounds_observed": repair_rounds,
            "events": [
                (e["event_type"], (e["payload"] or {}).get("status"))
                for e in service.events
            ],
            **outcome,
        },
    }
    return record


async def drive_all(
    corpus_root: Path,
    work_root: Path,
    runner_cls: Any,
    settings: Any,
    *,
    seed: str = "v1",
) -> dict[str, Any]:
    """Drive all 20 corpus cases. Blocked cases are driven AND marked blocked."""
    from scripts.evaluate_crump_code_v2 import load_suite  # local import: heavy deps

    suite = load_suite(corpus_root)
    # Integrity: workspace files must match the frozen manifest before driving.
    for case in suite.cases:
        for rel, expected in sorted(
            _manifest_files(corpus_root).get(case.id, {}).items()
        ):
            if not rel.startswith("workspace/"):
                continue
            data = (corpus_root / "cases" / case.id / rel).read_bytes()
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                raise ValueError(f"Corpus integrity failure for {case.id}/{rel}")
    cases = []
    for case in suite.cases:
        supported = case.id in SUPPORTED_OBSERVATION_CONTRACTS
        record = await drive_case(
            case,
            corpus_root=corpus_root,
            work_root=work_root,
            runner_cls=runner_cls,
            settings=settings,
            seed=f"{case.id}-{seed}",
            adapter_support="supported" if supported else "blocked",
            blocked_reason=None if supported else "missing trusted adapter",
        )
        cases.append(record)
    return {
        "report": "crump_code_v2_fake_driver",
        "plumbing_evidence_only": True,
        "capability_claims": "none",
        "aggregate": "Model evaluation not run; 0 cases evaluated; fix rate unavailable",
        "fix_rate": None,
        "provider": PROVIDER_NAME,
        "model_calls": 0,
        "paid_sandbox_used": False,
        "cases": cases,
    }


def _manifest_files(corpus_root: Path) -> dict[str, dict[str, str]]:
    manifest = json.loads((corpus_root / "manifest.json").read_text())
    by_case: dict[str, dict[str, str]] = {}
    for case in manifest["cases"]:
        by_case[case["id"]] = dict(case["files"])
    return by_case


def canonical_report(report: dict[str, Any]) -> str:
    return json.dumps(_canonicalize(report), sort_keys=True, ensure_ascii=False)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Deterministic fake-provider driver (plumbing only)."
    )
    parser.add_argument("--corpus-root", default="benchmarks/crump_code/real_tasks_v2")
    parser.add_argument("--work-root", default="/tmp/crump-code-v2-fake-driver")
    parser.add_argument("--out", default="fake_driver_report.json")
    parser.add_argument("--seed", default="v1")
    args = parser.parse_args()

    import sys
    from types import SimpleNamespace

    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from backend.code_runner import CrumpCodeRunner

    settings = SimpleNamespace(
        code_max_agent_steps=8, anthropic_api_key=None, anthropic_model="fake-provider"
    )
    work_root = Path(args.work_root)
    report = asyncio.run(
        drive_all(
            Path(args.corpus_root), work_root, CrumpCodeRunner, settings, seed=args.seed
        )
    )
    # Determinism self-check: run twice, compare canonical form.
    work_root2 = Path(str(work_root) + "-second")
    report2 = asyncio.run(
        drive_all(
            Path(args.corpus_root),
            work_root2,
            CrumpCodeRunner,
            settings,
            seed=args.seed,
        )
    )
    identical = canonical_report(report) == canonical_report(report2)
    report["determinism"] = {"runs": 2, "canonical_identical": identical}
    if not identical:
        raise SystemExit("FAIL: two driver runs were not canonically identical")
    Path(args.out).write_text(canonical_report(report), encoding="utf-8")
    n = len(report["cases"])
    blocked = sum(1 for c in report["cases"] if c["adapter_support"] == "blocked")
    print(
        f"drove {n} cases ({blocked} blocked, all represented); "
        f"determinism check passed; report -> {args.out}"
    )


if __name__ == "__main__":
    main()
