from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from backend import config
from backend.connected_app_background import ConnectedBackgroundCycle
from backend.routes import connected_apps


CRON_SECRET = "connected-worker-cron-secret"
ROOT = Path(__file__).resolve().parents[1]


class Worker:
    def __init__(
        self,
        *,
        cycle: ConnectedBackgroundCycle | object | None = None,
        fail: bool = False,
        block: bool = False,
        external_wake: bool = True,
        running: bool = True,
    ) -> None:
        self.external_wake = external_wake
        self.running = running
        self.fail = fail
        self.block = block
        self.calls = 0
        self.cancelled = False
        self.cycle = cycle or ConnectedBackgroundCycle(
            dispatch_owners_scanned=2,
            dispatch_actions_considered=3,
            dispatch_actions_invoked=1,
            dispatch_terminal_count=1,
            schedule_completion_count=4,
            dispatch_failed=False,
            scheduler_failed=False,
        )

    async def run_cycle(self):
        self.calls += 1
        try:
            if self.block:
                await asyncio.Event().wait()
            if self.fail:
                raise RuntimeError("private provider detail")
            return self.cycle
        except asyncio.CancelledError:
            self.cancelled = True
            raise


def app() -> FastAPI:
    value = FastAPI()
    value.include_router(connected_apps.cron_router)
    return value


@pytest.fixture(autouse=True)
def reset_worker_route(monkeypatch):
    connected_apps.connected_background_worker = None
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", False)
    monkeypatch.setattr(config, "CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED", True)
    monkeypatch.setattr(config, "CONNECTED_MULTI_STEP_SOURCE_RELEASED", True)
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(
            cron_secret=CRON_SECRET,
            connected_apps_enabled=False,
            is_production=True,
        ),
    )
    yield
    connected_apps.connected_background_worker = None


async def request(*, authorization: str | None = None, method: str = "GET"):
    headers = {} if authorization is None else {"Authorization": authorization}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app()),
        base_url="http://testserver",
    ) as client:
        return await client.request(
            method,
            "/api/cron/connected-apps",
            headers=headers,
        )


@pytest.mark.asyncio
async def test_cron_authentication_uses_exact_constant_time_bearer_comparison(monkeypatch):
    calls: list[tuple[str, str]] = []
    activation_calls: list[str] = []

    def compare(left: str, right: str) -> bool:
        calls.append((left, right))
        return False

    async def forbidden_activation(_assertion_source):
        activation_calls.append("activation")
        raise AssertionError("unauthorized cron must fail before activation")

    monkeypatch.setattr(connected_apps.hmac, "compare_digest", compare)
    monkeypatch.setattr(
        connected_apps,
        "_acquire_request_activation",
        forbidden_activation,
    )
    response = await request(authorization="Bearer wrong")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "success": False,
        "code": "CONNECTED_WORKER_UNAUTHORIZED",
        "retryable": False,
    }
    assert calls == [("Bearer wrong", f"Bearer {CRON_SECRET}")]
    assert activation_calls == []


@pytest.mark.asyncio
async def test_missing_cron_secret_fails_closed_without_a_worker_call(monkeypatch):
    worker = Worker()
    connected_apps.connected_background_worker = worker  # type: ignore[assignment]
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(
            cron_secret="",
            connected_apps_enabled=True,
            is_production=True,
        ),
    )

    response = await request(authorization=f"Bearer {CRON_SECRET}")

    assert response.status_code == 401
    assert worker.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_released", "runtime_enabled", "is_production"),
    (
        (False, True, True),
        (True, False, True),
        (True, True, False),
    ),
)
async def test_every_release_and_host_gate_is_required(
    monkeypatch,
    source_released,
    runtime_enabled,
    is_production,
):
    worker = Worker()
    connected_apps.connected_background_worker = worker  # type: ignore[assignment]
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", source_released)
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(
            cron_secret=CRON_SECRET,
            connected_apps_enabled=runtime_enabled,
            is_production=is_production,
        ),
    )

    response = await request(authorization=f"Bearer {CRON_SECRET}")

    assert response.status_code == 404
    assert response.json()["code"] == "CONNECTED_APPS_NOT_RELEASED"
    assert worker.calls == 0


@pytest.mark.asyncio
async def test_exact_external_worker_runs_one_bounded_content_free_cycle(monkeypatch):
    worker = Worker()
    connected_apps.connected_background_worker = worker  # type: ignore[assignment]
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(
            cron_secret=CRON_SECRET,
            connected_apps_enabled=True,
            is_production=True,
        ),
    )

    response = await request(authorization=f"Bearer {CRON_SECRET}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "success": True,
        "dispatchOwnersScanned": 2,
        "dispatchActionsConsidered": 3,
        "dispatchActionsInvoked": 1,
        "dispatchTerminalCount": 1,
        "scheduleCompletionCount": 4,
        "cleanupAttempts": 0,
        "cleanupTerminalCount": 0,
        "expiredOAuthFlowCount": 0,
        "expiredOAuthProvisionalCount": 0,
        "continuationCandidatesConsidered": 0,
        "continuationClaimsAcquired": 0,
        "continuationTerminalCount": 0,
        "continuationFailedCount": 0,
        "expiredPayloadsPurged": 0,
        "expiredPlansPurged": 0,
        "expiredLoopEnvelopesPurged": 0,
        "dispatchFailed": False,
        "schedulerFailed": False,
        "cleanupFailed": False,
        "oauthExpiryFailed": False,
        "reconciliationFailed": False,
        "continuationFailed": False,
        "retentionFailed": False,
    }
    assert worker.calls == 1
    assert "provider" not in response.text.casefold()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("worker", "expected_calls"),
    (
        (None, 0),
        (Worker(external_wake=False), 0),
        (Worker(running=False), 0),
    ),
)
async def test_cron_refuses_missing_continuous_or_inactive_workers(
    monkeypatch,
    worker,
    expected_calls,
):
    connected_apps.connected_background_worker = worker  # type: ignore[assignment]
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(
            cron_secret=CRON_SECRET,
            connected_apps_enabled=True,
            is_production=True,
        ),
    )

    response = await request(authorization=f"Bearer {CRON_SECRET}")

    assert response.status_code == 503
    assert response.json()["code"] == "CONNECTED_BACKGROUND_NOT_READY"
    if worker is not None:
        assert worker.calls == expected_calls


@pytest.mark.asyncio
async def test_partial_cycle_returns_retryable_503_with_only_bounded_counts(monkeypatch):
    cycle = ConnectedBackgroundCycle(
        dispatch_owners_scanned=1,
        dispatch_actions_considered=1,
        dispatch_actions_invoked=0,
        dispatch_terminal_count=0,
        schedule_completion_count=2,
        dispatch_failed=True,
        scheduler_failed=False,
    )
    connected_apps.connected_background_worker = Worker(cycle=cycle)  # type: ignore[assignment]
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(
            cron_secret=CRON_SECRET,
            connected_apps_enabled=True,
            is_production=True,
        ),
    )

    response = await request(authorization=f"Bearer {CRON_SECRET}")

    assert response.status_code == 503
    assert response.json()["success"] is False
    assert response.json()["dispatchFailed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ("continuation_failed", "retention_failed"))
async def test_continuation_or_retention_failure_is_visible_and_returns_503(
    monkeypatch, failure
):
    values = {
        "dispatch_owners_scanned": 1,
        "dispatch_actions_considered": 0,
        "dispatch_actions_invoked": 0,
        "dispatch_terminal_count": 0,
        "schedule_completion_count": 0,
        "dispatch_failed": False,
        "scheduler_failed": False,
        "continuation_candidates_considered": 3,
        "continuation_claims_acquired": 2,
        "continuation_terminal_count": 1,
        "continuation_failed_count": 1,
        "expired_payloads_purged": 4,
        "expired_plans_purged": 5,
        "expired_loop_envelopes_purged": 6,
        failure: True,
    }
    cycle = ConnectedBackgroundCycle(**values)
    connected_apps.connected_background_worker = Worker(cycle=cycle)  # type: ignore[assignment]
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(
            cron_secret=CRON_SECRET,
            connected_apps_enabled=True,
            is_production=True,
        ),
    )

    response = await request(authorization=f"Bearer {CRON_SECRET}")

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
    assert body["continuationCandidatesConsidered"] == 3
    assert body["continuationClaimsAcquired"] == 2
    assert body["continuationTerminalCount"] == 1
    assert body["continuationFailedCount"] == 1
    assert body["expiredPayloadsPurged"] == 4
    assert body["expiredPlansPurged"] == 5
    assert body["expiredLoopEnvelopesPurged"] == 6
    assert body["continuationFailed"] is (failure == "continuation_failed")
    assert body["retentionFailed"] is (failure == "retention_failed")


@pytest.mark.asyncio
async def test_cron_timeout_cancels_request_work_and_returns_content_free_retry(monkeypatch):
    worker = Worker(block=True)
    connected_apps.connected_background_worker = worker  # type: ignore[assignment]
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    monkeypatch.setattr(connected_apps, "_CRON_CYCLE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        connected_apps,
        "settings",
        SimpleNamespace(
            cron_secret=CRON_SECRET,
            connected_apps_enabled=True,
            is_production=True,
        ),
    )

    response = await request(authorization=f"Bearer {CRON_SECRET}")

    assert response.status_code == 503
    assert response.json()["code"] == "CONNECTED_BACKGROUND_TIMEOUT"
    assert worker.cancelled is True
    assert "private" not in response.text.casefold()


@pytest.mark.asyncio
async def test_cron_is_get_only(monkeypatch):
    monkeypatch.setattr(config, "CONNECTED_APPS_PUBLIC_RELEASED", True)
    response = await request(
        authorization=f"Bearer {CRON_SECRET}",
        method="POST",
    )
    assert response.status_code == 405


def test_vercel_cron_wakes_the_exact_get_route_with_bounded_function_headroom() -> None:
    deployment = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    matching = [
        item
        for item in deployment["crons"]
        if item["path"] == "/api/cron/connected-apps"
    ]

    assert matching == [
        {
            "path": "/api/cron/connected-apps",
            "schedule": "* * * * *",
        }
    ]
    assert len({item["path"] for item in deployment["crons"]}) == len(
        deployment["crons"]
    )
    assert deployment["functions"]["api/index.py"]["maxDuration"] == 300
    assert connected_apps._CRON_CYCLE_TIMEOUT_SECONDS < 300
