import asyncio
from types import SimpleNamespace

import pytest

from backend.video_service import VideoService, VideoServiceError


USER_ID = "00000000-0000-0000-0000-000000000001"
JOB_A = "00000000-0000-0000-0000-000000000011"
JOB_B = "00000000-0000-0000-0000-000000000012"
TOKEN_A = "00000000-0000-0000-0000-000000000021"
TOKEN_B = "00000000-0000-0000-0000-000000000022"
FINGERPRINT_A = "a" * 64
FINGERPRINT_B = "b" * 64
HISTORICAL_KEY = "h" * 160


def valid_video_bytes() -> bytes:
    def box(box_type: bytes, payload: bytes) -> bytes:
        return (len(payload) + 8).to_bytes(4, "big") + box_type + payload

    movie_header = bytearray(100)
    movie_header[12:16] = (1000).to_bytes(4, "big")
    handler = bytearray(24)
    handler[8:12] = b"vide"
    movie = box(
        b"moov",
        box(b"mvhd", bytes(movie_header))
        + box(b"trak", box(b"mdia", box(b"hdlr", bytes(handler)))),
    )
    return (
        box(b"ftyp", b"isom\x00\x00\x02\x00isommp42")
        + movie
        + box(b"mdat", b"data")
    )


def settings(**overrides):
    values = {
        "gemini_api_key": "gemini-test",
        "gemini_video_model": "veo-3.1-lite-generate-preview",
        "gemini_video_extend_model": "veo-3.1-fast-generate-preview",
        "runway_api_secret": "runway-test",
        "runway_video_model": "gen4.5",
        "runway_api_version": "2024-11-06",
        "video_generation_enabled": True,
        "max_active_video_jobs_per_user": 1,
        "max_generated_video_bytes": 90 * 1024 * 1024,
        "video_daily_provider_budget_cents": 10_000,
        "video_user_daily_provider_budget_cents": 2_000,
        "runway_monthly_provider_budget_cents": 50_000,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def reserved_row(job_id, key, fingerprint, token, *, cost=40):
    return {
        "id": job_id,
        "user_id": USER_ID,
        "kind": "video",
        "status": "queued",
        "provider": "gemini",
        "provider_job_id": f"pending:{job_id}",
        "idempotency_key": key,
        "request_fingerprint": fingerprint,
        "video_phase": "reserved_unbilled",
        "lease_token": token,
        "lease_expires_at": "2999-01-01T00:00:00+00:00",
        "billing_receipt": {},
        "billing_refunded": False,
        "estimated_provider_cost_cents": cost,
        "metadata": {"billingPending": True},
    }


class AtomicCapacityDB:
    """Small executable model of the migration's serialized DB decision."""

    def __init__(self):
        self.rows = {
            JOB_A: reserved_row(JOB_A, "capacity-a", FINGERPRINT_A, TOKEN_A),
            JOB_B: reserved_row(JOB_B, "capacity-b", FINGERPRINT_B, TOKEN_B),
        }
        self.lock = asyncio.Lock()
        self.calls = []
        self.sweep_calls = []
        self.events = []

    async def rpc(self, name, payload, *, retry_transient=False):
        assert retry_transient is True
        if name == "sweep_expired_video_leases":
            self.sweep_calls.append(dict(payload))
            self.events.append(("sweep", payload.get("p_user_id")))
            return [{"outcome": "completed", "scanned": 0, "errors": 0}]
        assert name == "authorize_video_reservation_capacity"
        async with self.lock:
            self.events.append(("capacity", payload["p_job_id"]))
            self.calls.append(dict(payload))
            row = self.rows[payload["p_job_id"]]
            assert row["user_id"] == payload["p_user_id"]
            assert row["idempotency_key"] == payload["p_idempotency_key"]
            assert row["request_fingerprint"] == payload["p_request_fingerprint"]
            assert row["lease_token"] == payload["p_reservation_token"]
            active = sum(
                candidate["user_id"] == payload["p_user_id"]
                and candidate["video_phase"] in {
                    "reserved_unbilled",
                    "ready_to_launch",
                    "launching",
                    "processing",
                    "finalizing",
                }
                for candidate in self.rows.values()
            )
            if active > payload["p_max_active_jobs"]:
                removed = self.rows.pop(payload["p_job_id"])
                return [{"outcome": "concurrency_limit", "job": dict(removed)}]
            row["metadata"] = {
                **row["metadata"],
                "capacityAuthorized": True,
                "capacityPolicy": "serialized-v1",
            }
            return [{"outcome": "authorized", "job": dict(row)}]


class HistoricalIdentityDB:
    """Record every existing-row RPC identity without emulating its state machine."""

    OUTCOMES = {
        "authorize_video_reservation_capacity": "authorized",
        "release_video_reservation": "released",
        "claim_video_provider_launch": "claimed",
        "complete_video_provider_launch": "completed",
        "fail_video_provider_launch": "failed",
        "claim_video_finalization": "claimed",
        "complete_video_finalization": "completed",
        "fail_video_finalization": "failed",
    }

    def __init__(self, row):
        self.row = dict(row)
        self.calls = []
        self.sweep_calls = []

    async def rpc(self, name, payload, *, retry_transient=False):
        assert retry_transient is True
        if name == "sweep_expired_video_leases":
            self.sweep_calls.append(dict(payload))
            return [{"outcome": "completed", "scanned": 0, "errors": 0}]
        assert name in self.OUTCOMES
        assert payload["p_idempotency_key"] == HISTORICAL_KEY
        self.calls.append((name, dict(payload)))
        return [{"outcome": self.OUTCOMES[name], "job": dict(self.row)}]


@pytest.mark.asyncio
async def test_different_keys_share_one_atomic_capacity_slot_before_billing():
    database = AtomicCapacityDB()
    service = VideoService(settings(), database, SimpleNamespace())

    results = await asyncio.gather(
        service.authorize_reservation_capacity(
            user_id=USER_ID,
            row=database.rows[JOB_A],
            reservation_token=TOKEN_A,
        ),
        service.authorize_reservation_capacity(
            user_id=USER_ID,
            row=database.rows[JOB_B],
            reservation_token=TOKEN_B,
        ),
        return_exceptions=True,
    )

    authorized = [item for item in results if isinstance(item, dict)]
    denied = [item for item in results if isinstance(item, VideoServiceError)]
    assert len(authorized) == 1
    assert len(denied) == 1
    assert denied[0].code == "VIDEO_CONCURRENCY_LIMIT"
    assert len(database.rows) == 1
    remaining = next(iter(database.rows.values()))
    assert remaining["metadata"]["capacityAuthorized"] is True
    assert {call["p_idempotency_key"] for call in database.calls} == {
        "capacity-a",
        "capacity-b",
    }
    assert database.sweep_calls == [
        {"p_limit": 500, "p_user_id": USER_ID},
        {"p_limit": 500, "p_user_id": USER_ID},
    ]


class PrebillingSettlementDB:
    def __init__(self, summary=None, *, sweep_error=None):
        self.row = reserved_row(JOB_A, "prebilling", FINGERPRINT_A, TOKEN_A)
        self.summary = summary or {
            "outcome": "completed",
            "scanned": 1,
            "errors": 0,
        }
        self.sweep_error = sweep_error
        self.calls = []

    async def rpc(self, name, payload, *, retry_transient=False):
        assert retry_transient is True
        self.calls.append((name, dict(payload)))
        if name == "sweep_expired_video_leases":
            if self.sweep_error:
                raise self.sweep_error
            return [dict(self.summary)]
        if name == "release_video_reservation":
            return [{"outcome": "released", "job": dict(self.row)}]
        assert name == "authorize_video_reservation_capacity"
        return [{"outcome": "authorized", "job": dict(self.row)}]


@pytest.mark.asyncio
async def test_owner_settlement_precedes_the_serialized_capacity_decision():
    database = PrebillingSettlementDB()
    service = VideoService(settings(), database, SimpleNamespace())

    current = await service.authorize_reservation_capacity(
        user_id=USER_ID,
        row=database.row,
        reservation_token=TOKEN_A,
    )

    assert current["id"] == JOB_A
    assert [name for name, _ in database.calls] == [
        "sweep_expired_video_leases",
        "authorize_video_reservation_capacity",
    ]
    assert database.calls[0][1] == {"p_limit": 500, "p_user_id": USER_ID}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("summary", "sweep_error"),
    [
        ({"outcome": "busy", "scanned": 0, "errors": 0}, None),
        ({"outcome": "completed", "scanned": 1, "errors": 1}, None),
        ({"outcome": "completed", "scanned": 500, "errors": 0}, None),
        (None, RuntimeError("database transport unavailable")),
    ],
)
async def test_unsettled_owner_billing_fails_closed_and_releases_reservation(
    summary,
    sweep_error,
):
    database = PrebillingSettlementDB(summary, sweep_error=sweep_error)
    service = VideoService(settings(), database, SimpleNamespace())

    with pytest.raises(VideoServiceError) as error:
        await service.authorize_reservation_capacity(
            user_id=USER_ID,
            row=database.row,
            reservation_token=TOKEN_A,
        )

    assert error.value.code == "VIDEO_PREBILLING_SETTLEMENT_PENDING"
    assert error.value.status_code == 503
    assert error.value.retryable is True
    assert [name for name, _ in database.calls] == [
        "sweep_expired_video_leases",
        "release_video_reservation",
    ]


@pytest.mark.asyncio
async def test_historical_160_character_key_is_preserved_at_every_rpc_boundary():
    row = reserved_row(JOB_A, HISTORICAL_KEY, FINGERPRINT_A, TOKEN_A)
    database = HistoricalIdentityDB(row)
    service = VideoService(settings(), database, SimpleNamespace())

    await service.authorize_reservation_capacity(
        user_id=USER_ID,
        row=row,
        reservation_token=TOKEN_A,
    )
    assert await service.release_unbilled_reservation(
        user_id=USER_ID,
        job_id=JOB_A,
        idempotency_key=HISTORICAL_KEY,
        request_fingerprint=FINGERPRINT_A,
        reservation_token=TOKEN_A,
    )
    _, _, launch_token = await service._claim_provider_launch(
        user_id=USER_ID,
        row=row,
        claim_ready=True,
    )
    assert launch_token
    await service._complete_provider_launch(
        user_id=USER_ID,
        row=row,
        launch_token=launch_token,
        provider_job_id="historical-provider-job",
    )
    await service._fail_provider_launch(
        user_id=USER_ID,
        row=row,
        launch_token=launch_token,
        exc=VideoServiceError("Provider rejected the historical request."),
        acceptance="rejected",
    )
    _, _, finalization_token = await service._claim_finalization(
        user_id=USER_ID,
        row=row,
        terminal_outcome="ready",
    )
    assert finalization_token
    await service._complete_finalization(
        user_id=USER_ID,
        row=row,
        finalization_token=finalization_token,
        file_id=JOB_A,
        provider_asset_reference=None,
        provider_asset_expires_at=None,
        stored_bytes=100,
        file_metadata={},
    )
    await service._fail_finalization(
        user_id=USER_ID,
        row=row,
        finalization_token=finalization_token,
        message="Historical finalization failed.",
        failure_code="HISTORICAL_FINALIZATION_FAILED",
    )

    assert [name for name, _ in database.calls] == list(
        HistoricalIdentityDB.OUTCOMES
    )


def test_rpc_key_window_does_not_expand_the_new_request_limit():
    assert VideoService.IDEMPOTENCY_KEY_MAX_LENGTH == 120
    assert VideoService.HISTORICAL_IDEMPOTENCY_KEY_MAX_LENGTH == 160
    assert VideoService.normalize_rpc_idempotency_key(" x ") == "x"
    assert VideoService.normalize_rpc_idempotency_key(HISTORICAL_KEY) == HISTORICAL_KEY

    with pytest.raises(VideoServiceError) as error:
        VideoService.normalize_rpc_idempotency_key("x" * 161)

    assert error.value.code == "VIDEO_REQUEST_IDENTITY_INVALID"
    assert error.value.status_code == 409
    assert error.value.retryable is False


def processing_row(*, job_id=JOB_A):
    return {
        "id": job_id,
        "user_id": USER_ID,
        "kind": "video",
        "status": "processing",
        "provider": "gemini",
        "provider_job_id": "operations/provider-video-1",
        "idempotency_key": "terminal-video",
        "request_fingerprint": FINGERPRINT_A,
        "video_phase": "processing",
        "lease_token": None,
        "lease_expires_at": None,
        "billing_receipt": {
            "eventId": "credit:00000000-0000-0000-0000-000000000099",
            "paymentSource": "credits",
        },
        "billing_refunded": False,
        "estimated_provider_cost_cents": 40,
        "prompt": "A stable branded product scene.",
        "engine": "quick",
        "operation_type": "generate",
        "model": "veo-test",
        "aspect_ratio": "16:9",
        "resolution": "720p",
        "duration_seconds": 8,
        "sequence_index": 0,
        "metadata": {"refundEligible": True, "videoPhase": "processing"},
    }


class FinalizationDB:
    def __init__(self, row=None):
        row = row or processing_row()
        self.row = dict(row)
        self.lock = asyncio.Lock()
        self.claim_payloads = []
        self.complete_payloads = []
        self.fail_payloads = []

    async def select_one(self, table, *, filters=None, **_kwargs):
        assert table == "media_jobs"
        filters = filters or {}
        wanted = str(filters.get("id") or "").removeprefix("eq.")
        owner = str(filters.get("user_id") or "").removeprefix("eq.")
        if wanted == self.row["id"] and owner == self.row["user_id"]:
            return dict(self.row)
        return None

    async def update(self, table, payload, *, filters):
        assert table == "media_jobs"
        if (
            str(filters.get("id") or "").removeprefix("eq.") == self.row["id"]
            and str(filters.get("user_id") or "").removeprefix("eq.")
            == self.row["user_id"]
            and str(filters.get("status") or "").removeprefix("eq.")
            == self.row["status"]
            and str(filters.get("video_phase") or "").removeprefix("eq.")
            == self.row["video_phase"]
        ):
            self.row.update(payload)
            return [dict(self.row)]
        return []

    def _assert_identity(self, payload):
        assert payload["p_user_id"] == self.row["user_id"]
        assert payload["p_job_id"] == self.row["id"]
        assert payload["p_idempotency_key"] == self.row["idempotency_key"]
        assert payload["p_request_fingerprint"] == self.row["request_fingerprint"]

    async def rpc(self, name, payload, *, retry_transient=False):
        assert retry_transient is True
        async with self.lock:
            self._assert_identity(payload)
            if name == "claim_video_finalization":
                self.claim_payloads.append(dict(payload))
                if self.row["status"] in {"ready", "failed"}:
                    return [{"outcome": "current", "job": dict(self.row)}]
                if self.row["video_phase"] == "finalizing":
                    return [{"outcome": "in_progress", "job": dict(self.row)}]
                assert self.row["video_phase"] == "processing"
                self.row.update(
                    {
                        "video_phase": "finalizing",
                        "lease_token": payload["p_finalization_token"],
                        "lease_expires_at": "2999-01-01T00:00:00+00:00",
                        "metadata": {
                            **self.row["metadata"],
                            "videoPhase": "finalizing",
                            "finalizationOutcome": payload["p_terminal_outcome"],
                            "finalizationRefundEligible": payload[
                                "p_refund_eligible"
                            ],
                        },
                    }
                )
                return [{"outcome": "claimed", "job": dict(self.row)}]

            if name == "complete_video_finalization":
                self.complete_payloads.append(dict(payload))
                if (
                    self.row["video_phase"] != "finalizing"
                    or self.row["lease_token"] != payload["p_finalization_token"]
                    or payload["p_file_id"] != self.row["id"]
                ):
                    return [
                        {"outcome": "finalization_conflict", "job": dict(self.row)}
                    ]
                self.row.update(
                    {
                        "status": "ready",
                        "video_phase": "ready",
                        "lease_token": None,
                        "lease_expires_at": None,
                        "file_id": payload["p_file_id"],
                        "metadata": {
                            **self.row["metadata"],
                            "videoPhase": "ready",
                            "refundEligible": False,
                        },
                    }
                )
                return [{"outcome": "completed", "job": dict(self.row)}]

            if name == "fail_video_finalization":
                self.fail_payloads.append(dict(payload))
                if (
                    self.row["video_phase"] != "finalizing"
                    or self.row["lease_token"] != payload["p_finalization_token"]
                ):
                    return [
                        {"outcome": "finalization_conflict", "job": dict(self.row)}
                    ]
                refund_allowed = bool(
                    self.row["metadata"].get("finalizationRefundEligible", True)
                    and payload["p_refund_eligible"]
                )
                self.row.update(
                    {
                        "status": "failed",
                        "video_phase": "failed",
                        "lease_token": None,
                        "lease_expires_at": None,
                        "billing_refunded": (
                            self.row["billing_refunded"] or refund_allowed
                        ),
                        "error_message": payload["p_message"],
                        "metadata": {
                            **self.row["metadata"],
                            "videoPhase": "failed",
                            "refundEligible": False,
                        },
                    }
                )
                return [{"outcome": "failed", "job": dict(self.row)}]

            raise AssertionError(f"Unexpected RPC: {name}")


class StableFiles:
    def __init__(self):
        self.calls = []
        self.discard_calls = []

    async def store_bytes(self, **kwargs):
        self.calls.append(dict(kwargs))
        await asyncio.sleep(0)
        return {
            "id": kwargs["file_id"],
            "user_id": kwargs["user_id"],
            "kind": kwargs["kind"],
            "status": "ready",
            "size_bytes": len(kwargs["data"]),
            "metadata": kwargs["metadata"],
        }

    async def discard_generated_file(self, **kwargs):
        self.discard_calls.append(dict(kwargs))


class DeadlineWinsDB(FinalizationDB):
    async def rpc(self, name, payload, *, retry_transient=False):
        if name == "sweep_expired_video_leases":
            return [
                {
                    "outcome": "completed",
                    "scanned": 1,
                    "failed": 1,
                    "refunded": 1,
                    "errors": 0,
                }
            ]
        if name == "complete_video_finalization":
            assert retry_transient is True
            self._assert_identity(payload)
            self.complete_payloads.append(dict(payload))
            self.row.update(
                {
                    "status": "failed",
                    "video_phase": "failed",
                    "lease_token": None,
                    "lease_expires_at": None,
                    "billing_refunded": True,
                    "file_id": None,
                    "metadata": {
                        **self.row["metadata"],
                        "videoPhase": "failed",
                        "refundEligible": False,
                    },
                }
            )
            return [{"outcome": "expired", "job": dict(self.row)}]
        return await super().rpc(name, payload, retry_transient=retry_transient)


class ReadyPollBarrier:
    def __init__(self):
        self.count = 0
        self.both_arrived = asyncio.Event()

    async def poll(self, _provider_job_id):
        self.count += 1
        if self.count >= 2:
            self.both_arrived.set()
        await self.both_arrived.wait()
        return {
            "status": "ready",
            "outputUrl": "https://provider.invalid/output.mp4",
        }

    @staticmethod
    async def download(_output_url, *, max_bytes):
        assert max_bytes > 0
        return valid_video_bytes()


@pytest.mark.asyncio
async def test_concurrent_terminal_polls_store_and_complete_exactly_one_file():
    database = FinalizationDB()
    files = StableFiles()
    service = VideoService(settings(), database, files)
    provider = ReadyPollBarrier()
    service.gemini.poll = provider.poll
    service.gemini.download = provider.download

    first, second = await asyncio.gather(
        service.poll(user_id=USER_ID, job_id=JOB_A),
        service.poll(user_id=USER_ID, job_id=JOB_A),
    )

    assert provider.count == 2
    assert len(database.claim_payloads) == 2
    assert len(files.calls) == 1
    assert files.calls[0]["file_id"] == JOB_A
    assert files.calls[0]["persist_metadata"] is False
    assert len(database.complete_payloads) == 1
    assert database.complete_payloads[0]["p_file_metadata"] == files.calls[0]["metadata"]
    assert database.row["status"] == "ready"
    assert database.row["file_id"] == JOB_A
    assert {first["video_phase"], second["video_phase"]} == {
        "finalizing",
        "ready",
    }


@pytest.mark.asyncio
async def test_deadline_winning_after_upload_discards_unbound_video_object():
    database = DeadlineWinsDB()
    files = StableFiles()
    service = VideoService(settings(), database, files)

    async def ready_poll(_provider_job_id):
        return {
            "status": "ready",
            "outputUrl": "https://provider.invalid/output.mp4",
        }

    async def good_download(_output_url, *, max_bytes):
        assert max_bytes > 0
        return valid_video_bytes()

    service.gemini.poll = ready_poll
    service.gemini.download = good_download

    failed = await service.poll(user_id=USER_ID, job_id=JOB_A)

    assert failed["status"] == "failed"
    assert failed["file_id"] is None
    assert files.calls[0]["persist_metadata"] is False
    assert len(database.complete_payloads) == 1
    assert database.complete_payloads[0]["p_file_metadata"] == files.calls[0]["metadata"]
    assert files.discard_calls == [
        {
            "user_id": USER_ID,
            "file_id": JOB_A,
            "filename": f"crump-video-{JOB_A}.mp4",
        }
    ]


@pytest.mark.asyncio
async def test_invalid_provider_video_bytes_fail_before_storage():
    database = FinalizationDB()
    files = StableFiles()
    service = VideoService(settings(), database, files)

    async def ready_poll(_provider_job_id):
        return {
            "status": "ready",
            "outputUrl": "https://provider.invalid/output.mp4",
        }

    async def bad_download(_output_url, *, max_bytes):
        assert max_bytes > 0
        return b"<html>not video</html>"

    service.gemini.poll = ready_poll
    service.gemini.download = bad_download
    failed = await service.poll(user_id=USER_ID, job_id=JOB_A)

    assert files.calls == []
    assert database.fail_payloads[0]["p_failure_code"] == "VIDEO_PROVIDER_OUTPUT_INVALID"
    assert failed["status"] == "failed"
    assert failed["billing_refunded"] is True


@pytest.mark.asyncio
async def test_complete_and_fail_reject_a_stale_finalization_token():
    row = processing_row()
    row.update(
        {
            "video_phase": "finalizing",
            "lease_token": TOKEN_A,
            "lease_expires_at": "2999-01-01T00:00:00+00:00",
            "metadata": {
                **row["metadata"],
                "finalizationOutcome": "ready",
                "finalizationRefundEligible": True,
            },
        }
    )
    database = FinalizationDB(row)
    service = VideoService(settings(), database, SimpleNamespace())

    with pytest.raises(VideoServiceError) as complete_error:
        await service._complete_finalization(
            user_id=USER_ID,
            row=dict(database.row),
            finalization_token=TOKEN_B,
            file_id=JOB_A,
            provider_asset_reference=None,
            provider_asset_expires_at=None,
            stored_bytes=100,
            file_metadata={},
        )
    with pytest.raises(VideoServiceError) as fail_error:
        await service._fail_finalization(
            user_id=USER_ID,
            row=dict(database.row),
            finalization_token=TOKEN_B,
            message="stale worker",
            failure_code="STALE_FINALIZER",
            refund_eligible=True,
        )

    assert complete_error.value.code == "VIDEO_FINALIZATION_STATE_UNAVAILABLE"
    assert fail_error.value.code == "VIDEO_FINALIZATION_STATE_UNAVAILABLE"
    assert database.row["video_phase"] == "finalizing"
    assert database.row["lease_token"] == TOKEN_A
    assert database.row["billing_refunded"] is False


@pytest.mark.asyncio
async def test_nonrefundable_provider_failure_stays_nonrefundable_end_to_end():
    database = FinalizationDB()
    service = VideoService(settings(), database, SimpleNamespace())

    async def failed_poll(_provider_job_id):
        return {
            "status": "failed",
            "failureMessage": "The provider blocked this request.",
            "failureCode": "SAFETY.INPUT.TEXT",
            "refundEligible": False,
        }

    service.gemini.poll = failed_poll
    failed = await service.poll(user_id=USER_ID, job_id=JOB_A)

    assert database.claim_payloads[0]["p_refund_eligible"] is False
    assert database.fail_payloads[0]["p_refund_eligible"] is False
    assert failed["status"] == "failed"
    assert failed["billing_refunded"] is False
    assert failed["metadata"]["refundEligible"] is False
    assert VideoService.refund_eligible(failed) is False
