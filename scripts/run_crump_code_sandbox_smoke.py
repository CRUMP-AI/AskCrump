"""Fail-closed live Sandbox smoke proof for the disabled Crump Code runtime.

The default dry run performs no network request and provisions no Sandbox. A live run
requires an exact source acknowledgement, an exact one-cent maximum-cost acknowledgement,
the Ask Crump project OIDC identity, and the public feature flag to remain disabled.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from time import monotonic
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.code_runner import (
    CodeRunnerError,
    decode_sandbox_identity,
    provision_code_sandbox,
)


EXPECTED_PROJECT_ID = "prj_aG1X6SVzWMa2YE6MOTafsfCjghil"
EXPECTED_TEAM_ID = "team_ibBiyZIVAOTJMggxbRAHsGO5"
FIXTURE_NAME = "octocat-hello-world-pinned"
FIXTURE_REPOSITORY = "https://github.com/octocat/Hello-World"
FIXTURE_REVISION = "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"
SOURCE_ACKNOWLEDGEMENT = "public-no-secret-fixture"
MAX_ACKNOWLEDGED_COST_CENTS = 1
SMOKE_DURATION_SECONDS = 30
SMOKE_DEADLINE_SECONDS = 60
TRUTHY = frozenset({"1", "true", "yes", "on"})


class SmokeGateError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _is_true(value: Any) -> bool:
    return str(value or "").strip().lower() in TRUTHY


def smoke_plan() -> dict[str, Any]:
    return {
        "success": True,
        "mode": "dry-run",
        "fixture": FIXTURE_NAME,
        "revision": FIXTURE_REVISION,
        "wouldProvisionSandboxes": 1,
        "maxDurationSeconds": SMOKE_DURATION_SECONDS,
        "requestedVcpus": 2,
        "requestedMemoryMb": 4096,
        "networkPolicy": "deny-all",
        "persistent": False,
        "destroy": True,
        "injectedEnvironmentVariables": 0,
        "modelCalls": 0,
        "databaseWrites": 0,
        "customerData": False,
        "publicFeatureMustRemainDisabled": True,
        "liveRunAuthorized": False,
    }


def validate_live_gate(
    *,
    confirmed_cost_cents: int | None,
    confirmed_source: str | None,
    environment: Mapping[str, str],
) -> str:
    if confirmed_cost_cents != MAX_ACKNOWLEDGED_COST_CENTS:
        raise SmokeGateError("CODE_SMOKE_COST_ACK_REQUIRED")
    if confirmed_source != SOURCE_ACKNOWLEDGEMENT:
        raise SmokeGateError("CODE_SMOKE_SOURCE_ACK_REQUIRED")
    if _is_true(environment.get("CRUMP_ENABLE_CODE_WORKSPACE")):
        raise SmokeGateError("CODE_SMOKE_PUBLIC_FEATURE_MUST_BE_DISABLED")

    token = str(environment.get("VERCEL_OIDC_TOKEN") or "").strip()
    if not token:
        raise SmokeGateError("CODE_SMOKE_OIDC_REQUIRED")
    try:
        project_id, team_id = decode_sandbox_identity(token)
    except CodeRunnerError as exc:
        raise SmokeGateError("CODE_SMOKE_OIDC_INVALID") from exc
    if project_id != EXPECTED_PROJECT_ID or team_id != EXPECTED_TEAM_ID:
        raise SmokeGateError("CODE_SMOKE_OIDC_SCOPE_MISMATCH")
    return token


async def _run(
    sandbox: Any,
    command: str,
    args: list[str],
    *,
    kill_after: int = 8,
) -> Any:
    return await sandbox.run_process(
        command,
        args,
        capture_output=True,
        kill_after=kill_after,
    )


async def run_live_smoke(oidc_token: str) -> dict[str, Any]:
    task = {
        "id": "operator-smoke",
        "source_repo_url": FIXTURE_REPOSITORY,
        "source_ref": FIXTURE_REVISION,
        "max_duration_seconds": SMOKE_DURATION_SECONDS,
    }
    started = monotonic()
    cleanup_completed = False

    try:
        async with asyncio.timeout(SMOKE_DEADLINE_SECONDS):
            async with provision_code_sandbox(task, oidc_token=oidc_token) as sandbox:
                revision = await _run(sandbox, "git", ["rev-parse", "HEAD"])
                write_read = await _run(
                    sandbox,
                    "python3",
                    [
                        "-c",
                        "from pathlib import Path; p=Path('.crump-code-smoke'); "
                        "p.write_text('ok', encoding='utf-8'); print(p.read_text(encoding='utf-8')); "
                        "p.unlink()",
                    ],
                )
                clean = await _run(sandbox, "git", ["status", "--porcelain"])
                secret_names = await _run(
                    sandbox,
                    "python3",
                    [
                        "-c",
                        "import os; names={'ANTHROPIC_API_KEY','OPENAI_API_KEY',"
                        "'SUPABASE_SERVICE_KEY','STRIPE_SECRET_KEY','RESEND_API_KEY',"
                        "'VERCEL_OIDC_TOKEN','CRON_SECRET','GEMINI_API_KEY',"
                        "'RUNWAYML_API_SECRET','ELEVENLABS_API_KEY','BRAVE_API_KEY'}; "
                        "print(sum(name in os.environ for name in names))",
                    ],
                )
                network = await _run(
                    sandbox,
                    "python3",
                    [
                        "-c",
                        "import socket; socket.create_connection(('example.com', 443), 2)",
                    ],
                    kill_after=5,
                )
                reported_policy = str(
                    getattr(getattr(sandbox, "network_policy", None), "mode", "")
                )
        cleanup_completed = True
    except TimeoutError as exc:
        raise SmokeGateError("CODE_SMOKE_DEADLINE") from exc
    except SmokeGateError:
        raise
    except Exception as exc:
        if isinstance(exc, CodeRunnerError):
            raise SmokeGateError(str(exc.code or "CODE_SMOKE_RUNTIME_FAILED")) from exc
        raise SmokeGateError("CODE_SMOKE_RUNTIME_FAILED") from exc

    try:
        observed_secret_names = int(str(secret_names.stdout or "").strip())
    except (TypeError, ValueError) as exc:
        raise SmokeGateError("CODE_SMOKE_ENVIRONMENT_PROOF_INVALID") from exc

    checks = {
        "revisionPinned": revision.returncode == 0
        and str(revision.stdout or "").strip() == FIXTURE_REVISION,
        "workspaceWritable": write_read.returncode == 0
        and str(write_read.stdout or "").strip() == "ok",
        "repositoryCleanAfterProbe": clean.returncode == 0
        and not str(clean.stdout or "").strip(),
        "sensitiveEnvironmentNames": observed_secret_names,
        "networkDenied": network.returncode != 0,
        "reportedNetworkPolicy": reported_policy,
        "cleanupCompleted": cleanup_completed,
    }
    if not checks["revisionPinned"]:
        raise SmokeGateError("CODE_SMOKE_REVISION_MISMATCH")
    if not checks["workspaceWritable"] or not checks["repositoryCleanAfterProbe"]:
        raise SmokeGateError("CODE_SMOKE_WORKSPACE_FAILED")
    if checks["sensitiveEnvironmentNames"] != 0:
        raise SmokeGateError("CODE_SMOKE_ENVIRONMENT_EXPOSED")
    if not checks["networkDenied"] or checks["reportedNetworkPolicy"] != "deny-all":
        raise SmokeGateError("CODE_SMOKE_NETWORK_NOT_DENIED")
    if not checks["cleanupCompleted"]:
        raise SmokeGateError("CODE_SMOKE_CLEANUP_UNCONFIRMED")

    return {
        "success": True,
        "mode": "live",
        "fixture": FIXTURE_NAME,
        "maxAcknowledgedCostCents": MAX_ACKNOWLEDGED_COST_CENTS,
        "maxDurationSeconds": SMOKE_DURATION_SECONDS,
        "requestedVcpus": 2,
        "requestedMemoryMb": 4096,
        "modelCalls": 0,
        "databaseWrites": 0,
        "customerData": False,
        "checks": checks,
        "durationMs": int((monotonic() - started) * 1000),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-max-cost-cents", type=int)
    parser.add_argument("--confirm-source")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        print(json.dumps(smoke_plan(), sort_keys=True))
        return 0

    try:
        oidc_token = validate_live_gate(
            confirmed_cost_cents=args.confirm_max_cost_cents,
            confirmed_source=args.confirm_source,
            environment=os.environ,
        )
        receipt = asyncio.run(run_live_smoke(oidc_token))
    except SmokeGateError as exc:
        print(json.dumps({"success": False, "code": exc.code}, sort_keys=True))
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
