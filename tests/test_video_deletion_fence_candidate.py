"""Source-only video deletion-fence races. Providers and Supabase are always fakes."""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.video_providers import GeminiVeoProvider, ProviderError, RunwayProvider
from backend.video_service import VideoService, VideoServiceError
import backend.video_providers as provider_module
from backend.routes import manuscripts as manuscript_routes
from backend.routes.media import _video_error


ROOT = Path(__file__).resolve().parents[1]
OWNER = "00000000-0000-0000-0000-000000000001"
PARENT_ID = "00000000-0000-0000-0000-000000000002"
DELETE_TOKEN = "00000000-0000-0000-0000-000000000003"


def settings(**overrides):
    values = dict(
        gemini_api_key="fake-only",
        gemini_video_model="fake-veo",
        gemini_video_extend_model="fake-veo-extend",
        runway_api_secret="fake-only",
        runway_video_model="fake-runway",
        runway_api_version="2024-11-06",
        video_generation_enabled=True,
        max_active_video_jobs_per_user=1,
        max_generated_video_bytes=90 * 1024 * 1024,
        video_daily_provider_budget_cents=10_000,
        video_user_daily_provider_budget_cents=2_000,
        runway_monthly_provider_budget_cents=50_000,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class RaceDB:
    """In-memory atomic RPC model; a real Postgres lock test is still required."""

    def __init__(self):
        self.user_exists = True
        self.deletion_fenced = False
        self.deletion_token = None
        self.deleted = False
        self.claims = {}
        self.rows = {}
        self.lock = asyncio.Lock()
        self.provider_acceptance_calls = 0

    async def select(self, table, **_kwargs):
        assert table == "media_jobs"
        return [
            {"id": row["id"], "status": row["status"]}
            for row in self.rows.values()
        ]

    async def select_one(self, table, *, filters=None, **_kwargs):
        assert table in {"media_jobs", "video_provider_start_claims"}
        if not filters:
            return None
        if table == "video_provider_start_claims":
            job_id = str(filters["job_id"]).removeprefix("eq.")
            return self.claims.get(job_id)
        if "id" in filters:
            return self.rows.get(str(filters["id"]).removeprefix("eq."))
        if "idempotency_key" in filters:
            key = str(filters["idempotency_key"]).removeprefix("eq.")
            return next(
                (row for row in self.rows.values() if row.get("idempotency_key") == key),
                None,
            )
        return None

    async def insert(self, table, payload):
        assert table == "media_jobs"
        async with self.lock:
            if not self.user_exists:
                raise RuntimeError("FK: user was deleted")
            self.rows[payload["id"]] = dict(payload)
            return [dict(payload)]

    async def update(self, table, payload, *, filters, **_kwargs):
        assert table == "media_jobs"
        async with self.lock:
            job_id = str(filters["id"]).removeprefix("eq.")
            row = self.rows.get(job_id)
            if not row:
                return []
            row.update(payload)
            return [dict(row)]

    async def rpc(self, name, payload, **_kwargs):
        async with self.lock:
            job_id = payload.get("p_job_id")
            if name == "reserve_video_provider_claim":
                if not self.user_exists or self.deletion_fenced:
                    return {"status": "account_deleting"}
                unresolved = next(
                    (claim for claim in self.claims.values()
                     if claim["state"] in {"dispatching", "unknown"}
                     and not claim["provider_job_id"]),
                    None,
                )
                if unresolved:
                    return {"status": "start_unknown", "jobId": unresolved["job_id"]}
                self.claims[job_id] = {
                    "job_id": job_id,
                    "user_id": payload["p_user_id"],
                    "provider": payload["p_provider"],
                    "operation_type": payload["p_operation_type"],
                    "state": "reserved",
                    "provider_job_id": None,
                }
                return {"status": "reserved"}
            if name == "begin_video_provider_dispatch":
                claim = self.claims[job_id]
                if not self.user_exists or self.deletion_fenced:
                    claim["state"] = "rejected"
                    return False
                if claim["state"] != "reserved" or job_id not in self.rows:
                    return False
                claim["state"] = "dispatching"
                claim["dispatch_token"] = payload["p_dispatch_token"]
                return True
            if name == "record_video_provider_acceptance":
                self.provider_acceptance_calls += 1
                claim = self.claims[job_id]
                claim["state"] = "accepted"
                claim["provider_job_id"] = payload["p_provider_job_id"]
                row = self.rows.get(job_id)
                if not row:
                    return False
                row["provider_job_id"] = payload["p_provider_job_id"]
                row["status"] = "processing"
                row["metadata"] = {**row.get("metadata", {}), "providerAccepted": True}
                return True
            if name == "finish_video_provider_claim":
                claim = self.claims[job_id]
                if (
                    claim["state"] in {"reserved", "dispatching"}
                    or (
                        claim["state"] == "unknown"
                        and payload["p_outcome"] == "rejected"
                        and not claim["provider_job_id"]
                    )
                ):
                    claim["state"] = payload["p_outcome"]
                return None
            if name == "begin_video_account_deletion":
                if not self.user_exists:
                    return False
                if any(
                    claim["state"] == "reserved" for claim in self.claims.values()
                ):
                    return False
                token = payload["p_operation_token"]
                if self.deletion_fenced and self.deletion_token != token:
                    return False
                self.deletion_fenced = True
                self.deletion_token = token
                return True
            if name == "release_video_account_deletion_fence":
                if not self.user_exists:
                    return "user_deleted"
                if not self.deletion_fenced or self.deletion_token != payload["p_operation_token"]:
                    return "not_owner"
                self.deletion_fenced = False
                self.deletion_token = None
                return "released"
            if name == "claim_deleted_video_provider_reconciliation":
                for claim in self.claims.values():
                    if (
                        self.deleted
                        and claim["state"] in {"dispatching", "accepted", "unknown"}
                        and not claim.get("reconcile_lease_token")
                        and claim.get("reconcile_due", True)
                    ):
                        claim["reconcile_lease_token"] = payload["p_lease_token"]
                        return [dict(claim)]
                return []
            if name == "release_deleted_video_provider_reconciliation":
                claim = self.claims[payload["p_job_id"]]
                if claim.get("reconcile_lease_token") != payload["p_lease_token"]:
                    return False
                claim["state"] = payload["p_next_state"]
                claim["reconcile_lease_token"] = None
                claim["reconcile_due"] = False
                return True
            raise AssertionError(name)

    async def delete_user_after_fence(self):
        assert self.deletion_fenced
        assert not any(claim["state"] == "reserved" for claim in self.claims.values())
        async with self.lock:
            self.user_exists = False
            self.deleted = True
            self.rows.clear()  # media_jobs ON DELETE CASCADE


def service(db):
    return VideoService(settings(), db, SimpleNamespace())


@pytest.mark.asyncio
async def test_deletion_first_denies_new_claim_before_provider_or_charge():
    db = RaceDB()
    video = service(db)
    provider_calls = 0

    async def fake_provider(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return "provider-task-should-not-exist"

    video.runway.start = fake_provider
    assert await db.rpc("begin_video_account_deletion", {"p_user_id": OWNER, "p_operation_token": DELETE_TOKEN})
    await db.delete_user_after_fence()
    with pytest.raises(VideoServiceError) as exc:
        await video.reserve_provider_claim(
            user_id=OWNER, provider="runway", operation_type="generate",
        )
    assert exc.value.code == "ACCOUNT_DELETION_IN_PROGRESS"
    assert provider_calls == 0
    assert db.claims == {}


@pytest.mark.asyncio
async def test_accepted_video_start_survives_account_delete_without_content():
    db = RaceDB()
    video = service(db)
    claim_id = await video.reserve_provider_claim(
        user_id=OWNER, provider="runway", operation_type="generate",
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def held_provider(**_kwargs):
        entered.set()
        await release.wait()
        return "runway-task-after-delete"

    video.runway.start = held_provider
    pending = asyncio.create_task(video.start(
        user_id=OWNER,
        prompt="Private creative request that must not survive account deletion.",
        engine="cinematic",
        aspect_ratio="16:9",
        resolution="720p",
        duration_seconds=5,
        claimed_job_id=claim_id,
        charge_receipt={"eventId": "credit:fake"},
    ))
    await asyncio.wait_for(entered.wait(), timeout=2)
    assert await db.rpc("begin_video_account_deletion", {"p_user_id": OWNER, "p_operation_token": DELETE_TOKEN})
    await db.delete_user_after_fence()
    release.set()
    with pytest.raises(VideoServiceError) as exc:
        await pending
    assert exc.value.code == "VIDEO_JOB_TRACKING_FAILED"
    assert exc.value.refund_eligible is False
    assert db.provider_acceptance_calls == 1
    assert db.rows == {}
    assert db.claims[claim_id]["state"] == "accepted"
    assert db.claims[claim_id]["provider_job_id"] == "runway-task-after-delete"
    assert "prompt" not in db.claims[claim_id]
    assert "billing_receipt" not in db.claims[claim_id]


@pytest.mark.asyncio
async def test_definitive_rejection_after_deletion_poll_clears_temporary_unknown():
    db = RaceDB()
    video = service(db)
    claim_id = await video.reserve_provider_claim(
        user_id=OWNER, provider="runway", operation_type="generate",
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def held_rejection(**_kwargs):
        entered.set()
        await release.wait()
        raise ProviderError("Provider rejected the request.", "VIDEO_PROVIDER_REJECTED")

    video.runway.start = held_rejection
    pending = asyncio.create_task(video.start(
        user_id=OWNER,
        prompt="A delayed but definitive provider rejection.",
        engine="cinematic",
        aspect_ratio="16:9",
        resolution="720p",
        duration_seconds=5,
        claimed_job_id=claim_id,
    ))
    await asyncio.wait_for(entered.wait(), timeout=2)
    assert await db.rpc("begin_video_account_deletion", {"p_user_id": OWNER, "p_operation_token": DELETE_TOKEN})
    await db.delete_user_after_fence()
    assert await video.reconcile_deleted_provider_claim_once() == {
        "handled": True, "result": "needs_review",
    }
    assert db.claims[claim_id]["state"] == "unknown"
    release.set()
    with pytest.raises(VideoServiceError) as exc:
        await pending
    assert exc.value.refund_eligible is True
    assert db.claims[claim_id]["state"] == "rejected"


@pytest.mark.asyncio
async def test_reserved_claim_conflict_leaves_no_fence_then_retry_succeeds():
    db = RaceDB()
    video = service(db)
    claim_id = await video.reserve_provider_claim(
        user_id=OWNER, provider="runway", operation_type="generate",
    )
    assert not await db.rpc("begin_video_account_deletion", {"p_user_id": OWNER, "p_operation_token": DELETE_TOKEN})
    assert db.user_exists
    assert db.deletion_fenced is False

    async def fake_provider(**_kwargs):
        return "runway-task-after-conflict"

    video.runway.start = fake_provider
    row = await video.start(
        user_id=OWNER,
        prompt="This request can settle before deletion is retried.",
        engine="cinematic",
        aspect_ratio="16:9",
        resolution="720p",
        duration_seconds=5,
        claimed_job_id=claim_id,
    )
    assert row["status"] == "processing"
    assert db.claims[claim_id]["state"] == "accepted"
    assert await db.rpc("begin_video_account_deletion", {"p_user_id": OWNER, "p_operation_token": DELETE_TOKEN})
    await db.delete_user_after_fence()


@pytest.mark.asyncio
async def test_accepted_continuation_survives_account_delete():
    db = RaceDB()
    db.rows[PARENT_ID] = {
        "id": PARENT_ID,
        "user_id": OWNER,
        "status": "ready",
        "engine": "extendable",
        "provider": "gemini",
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "provider_asset_reference": "https://generativelanguage.googleapis.com/v1beta/files/fake",
        "provider_asset_expires_at": "2999-01-01T00:00:00+00:00",
        "sequence_index": 0,
        "duration_seconds": 8,
        "metadata": {"storedBytes": 1024},
    }
    video = service(db)
    claim_id = await video.reserve_provider_claim(
        user_id=OWNER, provider="gemini", operation_type="extend",
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def held_provider(**_kwargs):
        entered.set()
        await release.wait()
        return "gemini-continuation-after-delete"

    video.gemini.start = held_provider
    pending = asyncio.create_task(video.continue_video(
        user_id=OWNER,
        parent_job_id=PARENT_ID,
        prompt="Private continuation details.",
        claimed_job_id=claim_id,
        charge_receipt={"eventId": "credit:fake"},
    ))
    await asyncio.wait_for(entered.wait(), timeout=2)
    assert await db.rpc("begin_video_account_deletion", {"p_user_id": OWNER, "p_operation_token": DELETE_TOKEN})
    await db.delete_user_after_fence()
    release.set()
    with pytest.raises(VideoServiceError) as exc:
        await pending
    assert exc.value.refund_eligible is False
    assert db.claims[claim_id]["provider_job_id"] == "gemini-continuation-after-delete"
    assert db.claims[claim_id]["operation_type"] == "extend"
    assert db.rows == {}


@pytest.mark.asyncio
async def test_ambiguous_provider_outcome_is_not_refunded_or_redispatched():
    db = RaceDB()
    video = service(db)
    claim_id = await video.reserve_provider_claim(
        user_id=OWNER, provider="runway", operation_type="generate",
    )
    provider_calls = 0

    async def ambiguous_provider(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise ProviderError(
            "The provider response was lost.", "VIDEO_START_OUTCOME_UNKNOWN",
            503, False, "PROVIDER_START_OUTCOME_UNKNOWN", False,
        )

    video.runway.start = ambiguous_provider
    with pytest.raises(VideoServiceError) as exc:
        await video.start(
            user_id=OWNER,
            prompt="A video whose provider acceptance cannot be proven.",
            engine="cinematic",
            aspect_ratio="16:9",
            resolution="720p",
            duration_seconds=5,
            idempotency_key="same-request",
            claimed_job_id=claim_id,
        )
    assert exc.value.refund_eligible is False
    assert db.claims[claim_id]["state"] == "unknown"
    assert db.rows[claim_id]["status"] == "failed"
    assert db.rows[claim_id]["metadata"]["providerStartOutcomeUnknown"] is True
    assert await video._idempotent(user_id=OWNER, key="same-request")
    assert provider_calls == 1


@pytest.mark.asyncio
async def test_unknown_claim_blocks_new_paid_start_and_status_stays_pending():
    db = RaceDB()
    video = service(db)
    job_id = await video.reserve_provider_claim(
        user_id=OWNER, provider="runway", operation_type="generate",
    )
    db.claims[job_id]["state"] = "unknown"
    db.rows[job_id] = {
        "id": job_id, "user_id": OWNER, "kind": "video",
        "status": "failed", "provider": "runway",
        "provider_job_id": f"pending:{job_id}",
        "metadata": {"providerStartOutcomeUnknown": True},
    }

    with pytest.raises(VideoServiceError) as exc:
        await video.reserve_provider_claim(
            user_id=OWNER, provider="runway", operation_type="generate",
        )
    assert exc.value.code == "VIDEO_START_RECONCILIATION_PENDING"
    assert exc.value.failed_job_id == job_id
    response = _video_error(exc.value, stage="reservation")
    assert response.status_code == 409
    assert json.loads(response.body) == {
        "success": False,
        "error": exc.value.message,
        "code": "VIDEO_START_RECONCILIATION_PENDING",
        "shouldRetry": False,
        "jobId": job_id,
        "reconciliationPending": True,
    }
    assert len(db.claims) == 1
    public = await video.public_job(user_id=OWNER, row=db.rows[job_id])
    assert public["status"] == "failed"
    assert public["reconciliationPending"] is True

    # Operator/provider reconciliation can definitively reject the start;
    # only then does the terminal status release a fresh generation.
    await video.finish_provider_claim(user_id=OWNER, job_id=job_id, outcome="rejected")
    public = await video.public_job(user_id=OWNER, row=db.rows[job_id])
    assert public["reconciliationPending"] is False
    next_job = await video.reserve_provider_claim(
        user_id=OWNER, provider="runway", operation_type="generate",
    )
    assert next_job != job_id


@pytest.mark.asyncio
async def test_accepted_claim_repairs_local_pending_handle_before_provider_poll():
    db = RaceDB()
    video = service(db)
    job_id = await video.reserve_provider_claim(
        user_id=OWNER, provider="runway", operation_type="generate",
    )
    db.claims[job_id].update(state="accepted", provider_job_id="runway-real-id")
    db.rows[job_id] = {
        "id": job_id, "user_id": OWNER, "kind": "video",
        "status": "queued", "provider": "runway",
        "provider_job_id": f"pending:{job_id}", "metadata": {},
    }
    polled = []

    async def fake_poll(value):
        polled.append(value)
        return {"status": "processing"}

    video.runway.poll = fake_poll
    row = await video.poll(user_id=OWNER, job_id=job_id)
    assert polled == ["runway-real-id"]
    assert row["provider_job_id"] == "runway-real-id"
    public = await video.public_job(user_id=OWNER, row=row)
    assert public["reconciliationPending"] is False


@pytest.mark.asyncio
async def test_same_key_replay_settles_new_reserved_claim_without_provider_call():
    db = RaceDB()
    video = service(db)
    existing_id = "00000000-0000-0000-0000-000000000005"
    db.rows[existing_id] = {
        "id": existing_id, "user_id": OWNER, "kind": "video",
        "status": "ready", "idempotency_key": "replay-key",
        "provider_job_id": "already-finished", "metadata": {},
    }
    new_claim = await video.reserve_provider_claim(
        user_id=OWNER, provider="runway", operation_type="generate",
    )
    result = await video.start(
        user_id=OWNER,
        prompt="This should replay an existing video job.",
        engine="cinematic",
        duration_seconds=5,
        idempotency_key="replay-key",
        claimed_job_id=new_claim,
    )
    assert result["id"] == existing_id
    assert db.claims[new_claim]["state"] == "rejected"

    continuation_claim = await video.reserve_provider_claim(
        user_id=OWNER, provider="gemini", operation_type="extend",
    )
    result = await video.continue_video(
        user_id=OWNER, parent_job_id=existing_id,
        prompt="This should replay without a provider continuation.",
        idempotency_key="replay-key", claimed_job_id=continuation_claim,
    )
    assert result["id"] == existing_id
    assert db.claims[continuation_claim]["state"] == "rejected"


@pytest.mark.asyncio
async def test_deleted_provider_claim_is_polled_and_output_discarded():
    db = RaceDB()
    video = service(db)
    job_id = await video.reserve_provider_claim(
        user_id=OWNER, provider="runway", operation_type="generate",
    )
    db.claims[job_id].update(
        state="accepted", provider_job_id="runway-ready-after-delete",
    )
    assert await db.rpc("begin_video_account_deletion", {"p_user_id": OWNER, "p_operation_token": DELETE_TOKEN})
    await db.delete_user_after_fence()
    polls = []

    async def fake_poll(provider_job_id):
        polls.append(provider_job_id)
        return {
            "status": "ready",
            "outputUrl": "https://provider.example/private-output.mp4",
        }

    async def forbidden_download(*_args, **_kwargs):
        raise AssertionError("Deleted output must never be downloaded")

    video.runway.poll = fake_poll
    video.runway.download = forbidden_download
    result = await video.reconcile_deleted_provider_claim_once()
    assert result == {"handled": True, "result": "settled"}
    assert polls == ["runway-ready-after-delete"]
    assert db.claims[job_id]["state"] == "settled"
    assert db.rows == {}
    assert "outputUrl" not in str(db.claims[job_id])
    assert await video.reconcile_deleted_provider_claim_once() == {"handled": False}


@pytest.mark.asyncio
async def test_disabled_new_generation_still_reconciles_accepted_deleted_job():
    db = RaceDB()
    video = VideoService(settings(video_generation_enabled=False), db, SimpleNamespace())
    job_id = await video.reserve_provider_claim(
        user_id=OWNER, provider="gemini", operation_type="generate",
    )
    db.claims[job_id].update(state="accepted", provider_job_id="gemini-existing")
    assert await db.rpc("begin_video_account_deletion", {"p_user_id": OWNER, "p_operation_token": DELETE_TOKEN})
    await db.delete_user_after_fence()
    polls = []

    async def fake_poll(job):
        polls.append(job)
        return {"status": "processing"}

    video.gemini.poll = fake_poll
    result = await video.reconcile_deleted_provider_claim_once()
    assert result == {"handled": True, "result": "processing"}
    assert polls == ["gemini-existing"]


@pytest.mark.asyncio
async def test_deleted_ambiguous_claim_without_provider_id_needs_review():
    db = RaceDB()
    video = service(db)
    job_id = await video.reserve_provider_claim(
        user_id=OWNER, provider="gemini", operation_type="extend",
    )
    db.claims[job_id]["state"] = "unknown"
    assert await db.rpc("begin_video_account_deletion", {"p_user_id": OWNER, "p_operation_token": DELETE_TOKEN})
    await db.delete_user_after_fence()

    async def forbidden_poll(_provider_job_id):
        raise AssertionError("An unknown start cannot be polled without a provider ID")

    video.gemini.poll = forbidden_poll
    result = await video.reconcile_deleted_provider_claim_once()
    assert result == {"handled": True, "result": "needs_review"}
    assert db.claims[job_id]["state"] == "unknown"
    assert db.claims[job_id]["reconcile_due"] is False


@pytest.mark.asyncio
async def test_existing_cron_reconciles_deleted_video_before_other_workers(monkeypatch):
    class VideoWorker:
        async def reconcile_deleted_provider_claim_once(self):
            return {"handled": True, "result": "settled"}

    class ForbiddenWorker:
        async def process_next(self, **_kwargs):
            raise AssertionError("Only one claimed worker runs per cron invocation")

    monkeypatch.setattr(manuscript_routes, "settings", SimpleNamespace(
        cron_secret="fixture-secret", vercel_oidc_token="",
    ))
    monkeypatch.setattr(manuscript_routes, "video", VideoWorker())
    monkeypatch.setattr(manuscript_routes, "code_worker", ForbiddenWorker())
    monkeypatch.setattr(manuscript_routes, "_cron_priority_slot", lambda: 0)
    response = await manuscript_routes.manuscript_cron(SimpleNamespace(
        headers={"authorization": "Bearer fixture-secret"},
    ))
    assert response == {
        "success": True, "worker": "video_deletion",
        "handled": True, "result": "settled",
    }


@pytest.mark.asyncio
async def test_video_reconciliation_outage_does_not_starve_code_cron(monkeypatch):
    class BrokenVideoWorker:
        async def reconcile_deleted_provider_claim_once(self):
            raise RuntimeError("fixture database outage")

    class CodeWorker:
        async def process_next(self, **_kwargs):
            return {"handled": True, "result": "completed"}

    monkeypatch.setattr(manuscript_routes, "settings", SimpleNamespace(
        cron_secret="fixture-secret", vercel_oidc_token="",
    ))
    monkeypatch.setattr(manuscript_routes, "video", BrokenVideoWorker())
    monkeypatch.setattr(manuscript_routes, "code_worker", CodeWorker())
    monkeypatch.setattr(manuscript_routes, "_cron_priority_slot", lambda: 0)
    response = await manuscript_routes.manuscript_cron(SimpleNamespace(
        headers={"authorization": "Bearer fixture-secret"},
    ))
    assert response["worker"] == "code"
    assert response["result"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("slot", "first_worker"),
    [(0, "video_deletion"), (1, "code"), (2, "manuscripts")],
)
async def test_shared_minute_cron_rotates_first_claim_fairly(
    monkeypatch, slot, first_worker,
):
    invoked = []

    class VideoWorker:
        async def reconcile_deleted_provider_claim_once(self):
            invoked.append("video_deletion")
            return {"handled": True}

    class CodeWorker:
        async def process_next(self, **_kwargs):
            invoked.append("code")
            return {"handled": True}

    class ManuscriptWorker:
        async def process_next_run(self):
            invoked.append("manuscripts")
            return {"handled": True}

    monkeypatch.setattr(manuscript_routes, "settings", SimpleNamespace(
        cron_secret="fixture-secret", vercel_oidc_token="",
    ))
    monkeypatch.setattr(manuscript_routes, "video", VideoWorker())
    monkeypatch.setattr(manuscript_routes, "code_worker", CodeWorker())
    monkeypatch.setattr(manuscript_routes, "manuscripts", ManuscriptWorker())
    monkeypatch.setattr(manuscript_routes, "_cron_priority_slot", lambda: slot)
    response = await manuscript_routes.manuscript_cron(SimpleNamespace(
        headers={"authorization": "Bearer fixture-secret"},
    ))
    assert response["worker"] == first_worker
    assert invoked == [first_worker]


def test_provider_poll_errors_never_log_response_body(caplog):
    secret = "private generation details must not enter logs"
    caplog.set_level(logging.ERROR, logger="askcrump.video.providers")
    gemini = httpx.Response(
        400,
        headers={"x-request-id": secret},
        json={"error": {"status": "FAILED_PRECONDITION", "message": secret}},
    )
    runway = httpx.Response(400, headers={"x-request-id": secret}, json={"error": secret})
    GeminiVeoProvider._exception(gemini, checking=True)
    RunwayProvider._exception(runway, checking=True)
    assert secret not in caplog.text


@pytest.mark.parametrize(
    "code", ["VIDEO_START_OUTCOME_UNKNOWN", "VIDEO_JOB_TRACKING_FAILED"],
)
def test_ambiguous_start_error_includes_owner_job_handle(code):
    job_id = "00000000-0000-0000-0000-000000000007"
    response = _video_error(
        VideoServiceError(
            "Video start needs reconciliation.", code, 503, False, False, job_id,
        ),
        stage="generation",
    )
    body = json.loads(response.body)
    assert response.status_code == 503
    assert body["code"] == code
    assert body["jobId"] == job_id
    assert body["reconciliationPending"] is True
    assert body["shouldRetry"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["gemini", "runway"])
@pytest.mark.parametrize("outcome", ["http_500", "read_timeout", "connect_timeout"])
async def test_provider_start_outcome_classification_without_network(
    monkeypatch, provider_name, outcome,
):
    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, **_kwargs):
            if outcome == "read_timeout":
                raise httpx.ReadTimeout("simulated")
            if outcome == "connect_timeout":
                raise httpx.ConnectTimeout("simulated")
            return httpx.Response(500, request=httpx.Request("POST", url))

    monkeypatch.setattr(provider_module.httpx, "AsyncClient", FakeClient)
    if provider_name == "runway":
        provider = RunwayProvider(settings())
        arguments = {
            "model": "fake-runway", "prompt": "A no-network test video.",
            "aspect_ratio": "16:9", "duration_seconds": 5,
        }
    else:
        provider = GeminiVeoProvider(settings())
        arguments = {
            "model": "fake-veo", "prompt": "A no-network test video.",
            "aspect_ratio": "16:9", "resolution": "720p",
        }
    with pytest.raises(ProviderError) as exc:
        await provider.start(**arguments)
    if outcome == "connect_timeout":
        assert exc.value.refund_eligible is True
        assert exc.value.code == "VIDEO_PROVIDER_UNAVAILABLE"
    else:
        assert exc.value.refund_eligible is False
        assert exc.value.code == "VIDEO_START_OUTCOME_UNKNOWN"


def test_sql_candidate_is_content_free_service_only_and_guards_user_cascade():
    sql = (ROOT / "staging/video_provider_deletion_fence.sql").read_text(encoding="utf-8").lower()
    claim_table = sql.split("create table if not exists public.video_provider_start_claims", 1)[1].split(");", 1)[0]
    for private_field in ("prompt", "image", "filename", "file_id", "billing_receipt", "metadata"):
        assert private_field not in claim_table
    assert "user_id uuid not null" in claim_table and "references public.users" not in claim_table
    assert "alter table public.video_provider_start_claims enable row level security" in sql
    assert "grant select, insert, update, delete on table public.video_provider_start_claims to service_role" in sql
    assert "for update" in sql
    assert "before delete on public.users" in sql
    assert "record_video_provider_acceptance" in sql
    assert "for update skip locked" in sql
    assert "deleted_at is not null" in sql
