from pathlib import Path

import pytest

from backend.routes import media as media_routes


ROOT = Path(__file__).resolve().parents[1]
USER_ID = "00000000-0000-0000-0000-000000000001"
JOB_ID = "00000000-0000-0000-0000-000000000002"


class RefundFeatures:
    def __init__(self):
        self.calls = []

    async def refund(self, user_id, receipt):
        self.calls.append((user_id, receipt))


class RefundDB:
    def __init__(self, *, fail_update=False):
        self.fail_update = fail_update
        self.calls = []

    async def update(self, table, payload, *, filters):
        self.calls.append((table, payload, filters))
        if self.fail_update:
            raise RuntimeError("private database diagnostic")
        return [{"id": JOB_ID, **payload}]


@pytest.mark.asyncio
async def test_pre_acceptance_refund_marks_the_exact_private_job_reconciled(monkeypatch):
    feature_service = RefundFeatures()
    database = RefundDB()
    receipt = {"eventId": "credit:ledger-fixture"}
    monkeypatch.setattr(media_routes, "features", feature_service)
    monkeypatch.setattr(media_routes, "db", database)

    await media_routes._refund_failed_video_charge(
        user_id=USER_ID,
        receipt=receipt,
        job_id=JOB_ID,
    )

    assert feature_service.calls == [(USER_ID, receipt)]
    assert database.calls == [(
        "media_jobs",
        {"billing_refunded": True},
        {"id": f"eq.{JOB_ID}", "user_id": f"eq.{USER_ID}"},
    )]


@pytest.mark.asyncio
async def test_refund_without_a_reserved_job_does_not_guess_a_database_target(monkeypatch):
    feature_service = RefundFeatures()
    database = RefundDB()
    monkeypatch.setattr(media_routes, "features", feature_service)
    monkeypatch.setattr(media_routes, "db", database)

    await media_routes._refund_failed_video_charge(
        user_id=USER_ID,
        receipt={"eventId": "included-fixture"},
        job_id=None,
    )

    assert len(feature_service.calls) == 1
    assert database.calls == []


@pytest.mark.asyncio
async def test_refund_state_write_failure_keeps_the_idempotent_status_recovery_open(monkeypatch, caplog):
    feature_service = RefundFeatures()
    database = RefundDB(fail_update=True)
    monkeypatch.setattr(media_routes, "features", feature_service)
    monkeypatch.setattr(media_routes, "db", database)

    await media_routes._refund_failed_video_charge(
        user_id=USER_ID,
        receipt={"eventId": "credit:ledger-fixture"},
        job_id=JOB_ID,
    )

    assert len(feature_service.calls) == 1
    assert len(database.calls) == 1
    assert "Video refund state update needs a retry." in caplog.text
    assert "private database diagnostic" not in caplog.text


def test_failed_job_identity_is_private_and_both_start_paths_reconcile_once():
    service = (ROOT / "backend" / "video_service.py").read_text(encoding="utf-8")
    route = (ROOT / "backend" / "routes" / "media.py").read_text(encoding="utf-8")

    assert service.count("mapped.failed_job_id = job_id") == 2
    assert route.count("job_id=exc.failed_job_id") == 2
    assert '"failedJobId"' not in route
    assert "exc.failed_job_id" not in route.split("def _video_error", 1)[1].split(
        "def _idempotency_key", 1
    )[0]
