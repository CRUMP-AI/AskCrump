from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app as app_module
from backend.routes import media as media_routes
from backend.video_service import VideoService


CLIENT = TestClient(app_module.app)
CRON_SECRET = "video-cron-test-secret"


class SweepDB:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, bool]] = []
        self.select_calls: list[tuple[str, dict]] = []

    async def rpc(self, function_name, payload, *, retry_transient=False):
        self.calls.append((function_name, dict(payload), retry_transient))
        if function_name == "claim_video_reconciliation_batch":
            return []
        return [
            {
                "outcome": "completed",
                "scanned": 7,
                "released": 2,
                "completed": 1,
                "failed": 3,
                "refunded": 2,
                "errors": 1,
                # The service-to-route boundary must never expose row-level
                # identifiers or content even if an RPC accidentally adds it.
                "user_id": "private-user-id",
                "job_id": "private-job-id",
                "prompt": "private customer content",
            }
        ]

    async def select(self, table, **kwargs):
        self.select_calls.append((table, dict(kwargs)))
        return []


@pytest.fixture
def cron_context(monkeypatch):
    database = SweepDB()
    service = VideoService(SimpleNamespace(), database, SimpleNamespace())
    monkeypatch.setattr(
        media_routes,
        "settings",
        SimpleNamespace(cron_secret=CRON_SECRET),
    )
    monkeypatch.setattr(media_routes, "video", service)
    return database


def test_video_lease_cron_rejects_missing_bearer_secret(cron_context) -> None:
    response = CLIENT.get("/api/cron/videos")

    assert response.status_code == 401
    assert response.json() == {"success": False, "error": "Unauthorized."}
    assert cron_context.calls == []


def test_video_lease_cron_rejects_wrong_bearer_secret(cron_context) -> None:
    response = CLIENT.get(
        "/api/cron/videos",
        headers={"Authorization": "Bearer definitely-wrong"},
    )

    assert response.status_code == 401
    assert response.json() == {"success": False, "error": "Unauthorized."}
    assert cron_context.calls == []


def test_video_lease_cron_rejects_when_server_secret_is_unconfigured(
    cron_context,
    monkeypatch,
) -> None:
    monkeypatch.setattr(media_routes, "settings", SimpleNamespace(cron_secret=""))

    response = CLIENT.get(
        "/api/cron/videos",
        headers={"Authorization": f"Bearer {CRON_SECRET}"},
    )

    assert response.status_code == 401
    assert cron_context.calls == []


def test_video_lease_cron_runs_bounded_sweep_and_returns_only_aggregate_counts(
    cron_context,
) -> None:
    response = CLIENT.get(
        "/api/cron/videos",
        headers={"Authorization": f"Bearer {CRON_SECRET}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "outcome": "completed",
        "scanned": 7,
        "released": 2,
        "completed": 1,
        "failed": 3,
        "refunded": 2,
        "errors": 1,
        "providerReconciliation": {
            "scanned": 0,
            "processing": 0,
            "ready": 0,
            "failed": 0,
            "retryable": 0,
            "errors": 0,
        },
    }
    assert cron_context.calls == [
        ("sweep_expired_video_leases", {"p_limit": 100}, True),
        (
            "claim_video_reconciliation_batch",
            {
                "p_limit": 10,
                "p_stale_seconds": 120,
                "p_backoff_seconds": 600,
            },
            True,
        ),
    ]
    assert cron_context.select_calls == []


class ProcessingDB:
    def __init__(self, rows, *, finalizing_rows=None):
        self.rows = list(rows)
        self.finalizing_rows = list(finalizing_rows or [])
        self.calls = []
        self.select_calls = []

    async def rpc(self, function_name, payload, *, retry_transient=False):
        self.calls.append((function_name, dict(payload), retry_transient))
        assert function_name == "claim_video_reconciliation_batch"
        limit = int(payload.get("p_limit") or 0)
        return [*self.finalizing_rows, *self.rows][:limit]

    async def select(self, table, **kwargs):
        self.select_calls.append((table, dict(kwargs)))
        return list(self.rows)[: int(kwargs.get("limit") or 0)]


@pytest.mark.asyncio
async def test_processing_reconciliation_is_bounded_and_isolates_provider_failures():
    database = ProcessingDB([
        {
            "id": "00000000-0000-0000-0000-000000000011",
            "user_id": "owner-a",
            "video_phase": "processing",
            "lease_token": None,
        },
        {
            "id": "00000000-0000-0000-0000-000000000012",
            "user_id": "owner-b",
            "video_phase": "processing",
            "lease_token": None,
        },
        {
            "id": "00000000-0000-0000-0000-000000000013",
            "user_id": "owner-c",
            "video_phase": "processing",
            "lease_token": None,
        },
    ])
    service = VideoService(SimpleNamespace(), database, SimpleNamespace())
    seen = []

    async def fake_poll(*, user_id, job_id):
        seen.append((user_id, job_id))
        if user_id == "owner-b":
            raise media_routes.VideoServiceError(
                "provider busy",
                "VIDEO_PROVIDER_BUSY",
                503,
                True,
                False,
            )
        return {"status": "ready" if user_id == "owner-a" else "failed"}

    service.poll = fake_poll
    summary = await service.reconcile_stale_processing(limit=99, stale_seconds=1)

    assert summary == {
        "scanned": 3,
        "processing": 0,
        "ready": 1,
        "failed": 1,
        "retryable": 1,
        "errors": 1,
    }
    assert seen == [
        ("owner-a", "00000000-0000-0000-0000-000000000011"),
        ("owner-b", "00000000-0000-0000-0000-000000000012"),
        ("owner-c", "00000000-0000-0000-0000-000000000013"),
    ]
    assert database.calls == [
        (
            "claim_video_reconciliation_batch",
            {
                "p_limit": 25,
                "p_stale_seconds": 60,
                "p_backoff_seconds": 600,
            },
            True,
        )
    ]


@pytest.mark.asyncio
async def test_expired_finalization_is_retried_in_background_after_user_leaves():
    job_id = "00000000-0000-0000-0000-000000000021"
    database = ProcessingDB(
        [],
        finalizing_rows=[
            {
                "id": job_id,
                "user_id": "owner-away",
                "video_phase": "finalizing",
                "lease_token": "00000000-0000-0000-0000-000000000099",
            }
        ],
    )
    service = VideoService(SimpleNamespace(), database, SimpleNamespace())
    seen = []

    async def fake_poll(*, user_id, job_id):
        seen.append((user_id, job_id))
        return {"status": "ready"}

    service.poll = fake_poll
    summary = await service.reconcile_stale_processing(limit=10, stale_seconds=120)

    assert seen == [("owner-away", job_id)]
    assert summary == {
        "scanned": 1,
        "processing": 0,
        "ready": 1,
        "failed": 0,
        "retryable": 0,
        "errors": 0,
    }
    assert database.calls == [
        (
            "claim_video_reconciliation_batch",
            {
                "p_limit": 10,
                "p_stale_seconds": 120,
                "p_backoff_seconds": 600,
            },
            True,
        )
    ]


@pytest.mark.asyncio
async def test_nonterminal_processing_jobs_are_claimed_with_durable_backoff():
    job_id = "00000000-0000-0000-0000-000000000031"
    database = ProcessingDB([
        {
            "id": job_id,
            "user_id": "owner-long-running",
            "video_phase": "processing",
            "lease_token": None,
        }
    ])
    service = VideoService(SimpleNamespace(), database, SimpleNamespace())

    async def fake_poll(*, user_id, job_id):
        return {"status": "processing"}

    service.poll = fake_poll
    summary = await service.reconcile_stale_processing(limit=10, stale_seconds=120)

    assert summary["processing"] == 1
    assert summary["errors"] == 0
    assert database.calls[0][0] == "claim_video_reconciliation_batch"
    assert database.calls[0][1]["p_backoff_seconds"] == 600


@pytest.mark.asyncio
async def test_overdue_provider_and_finalization_rows_do_not_block_capacity():
    database = ProcessingDB([
        {
            "id": "expired-provider",
            "user_id": "owner-capacity",
            "status": "processing",
            "provider_job_id": "provider-old",
            "video_phase": "processing",
            "provider_started_at": "2000-01-01T00:00:00+00:00",
        },
        {
            "id": "expired-finalization",
            "user_id": "owner-capacity",
            "status": "processing",
            "provider_job_id": "provider-finalizing",
            "video_phase": "finalizing",
            "finalization_started_at": "2000-01-01T00:00:00+00:00",
        },
        {
            "id": "active-provider",
            "user_id": "owner-capacity",
            "status": "processing",
            "provider_job_id": "provider-current",
            "video_phase": "processing",
            "provider_started_at": "2099-01-01T00:00:00+00:00",
        },
    ])
    service = VideoService(SimpleNamespace(), database, SimpleNamespace())

    assert await service.active_count(user_id="owner-capacity") == 1


@pytest.mark.asyncio
async def test_customer_poll_settles_exact_overdue_job_before_provider_call():
    job_id = "00000000-0000-0000-0000-000000000041"

    class HorizonDB:
        def __init__(self):
            self.row = {
                "id": job_id,
                "user_id": "owner-horizon",
                "kind": "video",
                "status": "processing",
                "provider": "gemini",
                "provider_job_id": "provider-too-old",
                "video_phase": "processing",
                "provider_started_at": "2000-01-01T00:00:00+00:00",
            }
            self.calls = []

        async def select_one(self, table, *, filters):
            return dict(self.row)

        async def rpc(self, function_name, payload, *, retry_transient=False):
            self.calls.append((function_name, dict(payload), retry_transient))
            self.row = {**self.row, "status": "failed", "video_phase": "failed"}
            return [{"outcome": "completed", "scanned": 1, "failed": 1}]

    database = HorizonDB()
    service = VideoService(SimpleNamespace(), database, SimpleNamespace())

    row = await service.poll(user_id="owner-horizon", job_id=job_id)

    assert row["status"] == "failed"
    assert database.calls == [
        (
            "sweep_expired_video_leases",
            {
                "p_limit": 1,
                "p_user_id": "owner-horizon",
                "p_job_id": job_id,
            },
            True,
        )
    ]


def test_absolute_horizon_boundary_is_inclusive_for_both_processing_phases():
    service = VideoService(SimpleNamespace(), ProcessingDB([]), SimpleNamespace())
    now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)

    assert service._past_absolute_horizon(
        {
            "video_phase": "processing",
            "provider_started_at": "2026-09-23T12:00:00+00:00",
        },
        now=now,
    )
    assert not service._past_absolute_horizon(
        {
            "video_phase": "processing",
            "provider_started_at": "2026-09-23T12:00:00.000001+00:00",
        },
        now=now,
    )
    assert service._past_absolute_horizon(
        {
            "video_phase": "finalizing",
            "finalization_started_at": "2026-09-24T11:00:00+00:00",
        },
        now=now,
    )
    assert not service._past_absolute_horizon(
        {
            "video_phase": "finalizing",
            "finalization_started_at": "2026-09-24T11:00:00.000001+00:00",
        },
        now=now,
    )


@pytest.mark.asyncio
async def test_failed_compatibility_row_recovers_interrupted_refund_on_poll():
    job_id = "00000000-0000-0000-0000-000000000051"

    class CompatibilityRefundDB:
        def __init__(self):
            self.row = {
                "id": job_id,
                "user_id": "owner-refund",
                "kind": "video",
                "status": "failed",
                "video_phase": "failed",
                "billing_refunded": False,
                "billing_receipt": {
                    "paymentSource": "credits",
                    "eventId": "credit:00000000-0000-4000-8000-000000000052",
                },
                "metadata": {"compatibilityOrigin": "pre-atomic"},
            }
            self.calls = []

        async def select_one(self, table, *, filters):
            return dict(self.row)

        async def rpc(self, function_name, payload, *, retry_transient=False):
            self.calls.append((function_name, dict(payload), retry_transient))
            self.row = {**self.row, "billing_refunded": True}
            return [
                {
                    "outcome": "completed",
                    "scanned": 1,
                    "failed": 1,
                    "refunded": 1,
                }
            ]

    database = CompatibilityRefundDB()
    service = VideoService(SimpleNamespace(), database, SimpleNamespace())

    row = await service.poll(user_id="owner-refund", job_id=job_id)

    assert row["status"] == "failed"
    assert row["billing_refunded"] is True
    assert database.calls == [
        (
            "sweep_expired_video_leases",
            {
                "p_limit": 1,
                "p_user_id": "owner-refund",
                "p_job_id": job_id,
            },
            True,
        )
    ]


@pytest.mark.parametrize(
    "summary",
    [
        {"outcome": "busy", "scanned": 0, "errors": 0},
        {"outcome": "completed", "scanned": 1, "errors": 1},
        {"outcome": "completed", "scanned": 0, "errors": 0},
    ],
)
@pytest.mark.asyncio
async def test_customer_poll_fails_closed_while_exact_refund_is_unsettled(summary):
    job_id = "00000000-0000-0000-0000-000000000061"

    class UnsettledRefundDB:
        def __init__(self):
            self.row = {
                "id": job_id,
                "user_id": "owner-unsettled",
                "kind": "video",
                "status": "failed",
                "video_phase": "failed",
                "billing_refunded": False,
                "billing_receipt": {
                    "paymentSource": "credits",
                    "eventId": "credit:00000000-0000-4000-8000-000000000062",
                },
                "metadata": {
                    "compatibilityOrigin": "pre-atomic",
                    "refundEligible": True,
                },
            }

        async def select_one(self, table, *, filters):
            return dict(self.row)

        async def rpc(self, function_name, payload, *, retry_transient=False):
            assert function_name == "sweep_expired_video_leases"
            return [dict(summary)]

    service = VideoService(
        SimpleNamespace(), UnsettledRefundDB(), SimpleNamespace()
    )

    with pytest.raises(media_routes.VideoServiceError) as error:
        await service.poll(user_id="owner-unsettled", job_id=job_id)

    assert error.value.code == "VIDEO_SETTLEMENT_PENDING"
    assert error.value.retryable is True


@pytest.mark.asyncio
async def test_recent_video_rows_are_owner_scoped_and_capped():
    database = ProcessingDB([])
    service = VideoService(SimpleNamespace(), database, SimpleNamespace())

    rows = await service.list_recent(user_id="private-owner", limit=500)

    assert rows == []
    table, query = database.select_calls[0]
    assert table == "media_jobs"
    assert query["filters"] == {
        "user_id": "eq.private-owner",
        "kind": "eq.video",
    }
    assert query["order"] == "created_at.desc"
    assert query["limit"] == 20
