import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.feature_service import (
    POLICIES,
    CreditAuthorization,
    FeatureAccessError,
    FeatureService,
)
from backend.project_service import ProjectNotFoundError
from backend.routes import media as media_routes
from backend.video_service import VideoService, VideoServiceError


USER_ID = "00000000-0000-0000-0000-000000000001"
JOB_ID = "00000000-0000-0000-0000-000000000002"
PROJECT_ID = "00000000-0000-0000-0000-000000000003"


class JsonRequest:
    def __init__(self, payload, *, idempotency_key=None):
        self._payload = payload
        self.headers = (
            {}
            if idempotency_key is None
            else {"X-Idempotency-Key": idempotency_key}
        )

    async def json(self):
        return self._payload


def response_body(response):
    return json.loads(response.body)


def guarded_services():
    return {
        "existing": AsyncMock(return_value=None),
        "features": SimpleNamespace(
            consume=AsyncMock(return_value={"eventId": "included-fixture"}),
            consume_video_reservation=AsyncMock(
                return_value={"eventId": "included-fixture"}
            ),
            refund=AsyncMock(),
        ),
        "projects": SimpleNamespace(get=AsyncMock(return_value={"id": PROJECT_ID})),
        "video": SimpleNamespace(
            EXTENDABLE="extendable",
            normalize_request=Mock(return_value=("quick", "720p", 8)),
            validate_prompt=Mock(
                side_effect=lambda value, **_kwargs: " ".join(str(value).split())
            ),
            validate_aspect_ratio=Mock(
                side_effect=lambda value: str(value or "16:9").strip()
            ),
            normalize_reference_plan=Mock(return_value=[]),
            feature_code=Mock(return_value="video_quick_720p"),
            prepare_reference_images=AsyncMock(return_value=[]),
            prepare_provider_prompt=Mock(
                return_value=("prompt", "guarded prompt", [], "initial-frame")
            ),
            provider_cost_cents=Mock(return_value=10),
            provider_for_engine=Mock(return_value="gemini"),
            guard_provider_budget=AsyncMock(),
            authorize_reservation_capacity=AsyncMock(
                side_effect=lambda **kwargs: kwargs["row"]
            ),
            start=AsyncMock(return_value={"id": JOB_ID}),
            public_job=AsyncMock(return_value={"id": JOB_ID, "status": "queued"}),
            validate_continuation_parent=AsyncMock(),
            continue_video=AsyncMock(return_value={"id": JOB_ID}),
            release_unbilled_reservation=AsyncMock(return_value=True),
            reconcile_pending=AsyncMock(side_effect=lambda **kwargs: kwargs["row"]),
        ),
    }


def install_services(monkeypatch, services):
    monkeypatch.setattr(
        media_routes,
        "authenticate_request",
        AsyncMock(return_value=SimpleNamespace(user={"id": USER_ID})),
    )
    monkeypatch.setattr(media_routes, "_existing_job", services["existing"])
    monkeypatch.setattr(media_routes, "features", services["features"])
    monkeypatch.setattr(media_routes, "projects", services["projects"])
    monkeypatch.setattr(media_routes, "video", services["video"])


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["create", "continue"])
@pytest.mark.parametrize("idempotency_key", [None, "   ", "x" * 121])
async def test_video_posts_reject_missing_or_unbounded_idempotency_before_work(
    monkeypatch,
    endpoint,
    idempotency_key,
):
    services = guarded_services()
    install_services(monkeypatch, services)
    request = JsonRequest(
        {"prompt": "A careful credit-safety fixture."},
        idempotency_key=idempotency_key,
    )

    response = (
        await media_routes.create_video(request)
        if endpoint == "create"
        else await media_routes.continue_video(JOB_ID, request)
    )

    assert response.status_code == 400
    assert response_body(response) == {
        "success": False,
        "error": "Provide a nonblank video idempotency key of at most 120 characters.",
        "code": "VIDEO_IDEMPOTENCY_REQUIRED",
        "shouldRetry": False,
    }
    services["existing"].assert_not_awaited()
    services["features"].consume_video_reservation.assert_not_awaited()
    services["projects"].get.assert_not_awaited()
    services["video"].prepare_reference_images.assert_not_awaited()
    services["video"].guard_provider_budget.assert_not_awaited()
    services["video"].start.assert_not_awaited()
    services["video"].validate_continuation_parent.assert_not_awaited()
    services["video"].continue_video.assert_not_awaited()
    services["video"].normalize_request.assert_not_called()
    services["video"].validate_prompt.assert_not_called()
    services["video"].validate_aspect_ratio.assert_not_called()
    services["video"].normalize_reference_plan.assert_not_called()
    services["video"].feature_code.assert_not_called()
    services["video"].prepare_provider_prompt.assert_not_called()
    services["video"].provider_cost_cents.assert_not_called()
    services["video"].provider_for_engine.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("confirmation", "expected_code"),
    [
        (None, "VIDEO_REFERENCE_CONFIRMATION_REQUIRED"),
        (
            {
                "version": "video-reference-plan-v0",
                "confirmed": True,
                "engine": "quick",
                "capability": {
                    "provider": "gemini",
                    "mode": "initial-frame",
                    "fidelity": "starting-frame-not-pixel-locked",
                },
                "fileIds": ["00000000-0000-0000-0000-000000000011"],
                "referencePlan": [
                    {
                        "fileId": "00000000-0000-0000-0000-000000000011",
                        "role": "logo",
                    }
                ],
            },
            "VIDEO_REFERENCE_CONFIRMATION_STALE",
        ),
    ],
    ids=["unconfirmed", "stale-version"],
)
async def test_reference_contract_rejection_happens_before_reservation_or_charge(
    monkeypatch,
    confirmation,
    expected_code,
):
    services = guarded_services()
    services["video"].normalize_reference_plan.side_effect = (
        VideoService.normalize_reference_plan
    )
    install_services(monkeypatch, services)
    reference_id = "00000000-0000-0000-0000-000000000011"

    response = await media_routes.create_video(
        JsonRequest(
            {
                "prompt": "Animate this exact approved logo without substituting its design.",
                "engine": "quick",
                "referenceFileIds": [reference_id],
                "referencePlan": [{"fileId": reference_id, "role": "logo"}],
                "referencePlanConfirmation": confirmation,
            },
            idempotency_key=f"reference-contract-{expected_code.lower()}",
        )
    )

    assert response.status_code == 409
    body = response_body(response)
    assert body["code"] == expected_code
    assert body["shouldRetry"] is False
    assert "No credits were used" in body["error"]
    services["existing"].assert_not_awaited()
    services["projects"].get.assert_not_awaited()
    services["video"].prepare_reference_images.assert_not_awaited()
    services["video"].guard_provider_budget.assert_not_awaited()
    services["video"].start.assert_not_awaited()
    services["video"].authorize_reservation_capacity.assert_not_awaited()
    services["features"].consume_video_reservation.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_video_reserves_before_one_charge_and_launch(monkeypatch):
    services = guarded_services()
    events = []

    async def reserve_or_launch(**kwargs):
        if kwargs.get("reserve_only"):
            events.append("reserve")
            return {
                "id": JOB_ID,
                "status": "queued",
                "provider_job_id": f"pending:{JOB_ID}",
                "idempotency_key": kwargs["idempotency_key"],
                "request_fingerprint": kwargs["request_fingerprint"],
                "video_phase": "reserved_unbilled",
                "lease_token": kwargs["reservation_token"],
                "metadata": {"billingPending": True},
            }
        events.append("launch")
        assert kwargs["reserved_job_id"] == JOB_ID
        assert kwargs["reservation_token"]
        return {"id": JOB_ID, "status": "processing"}

    async def consume(*_args, **_kwargs):
        events.append("charge")
        return {"eventId": "included-fixture"}

    async def authorize(**kwargs):
        events.append("capacity")
        return kwargs["row"]

    services["video"].start.side_effect = reserve_or_launch
    services["video"].authorize_reservation_capacity.side_effect = authorize
    services["features"].consume_video_reservation.side_effect = consume
    install_services(monkeypatch, services)

    response = await media_routes.create_video(
        JsonRequest(
            {
                "prompt": "A careful atomic video billing fixture.",
                "engine": "quick",
                "resolution": "720p",
                "durationSeconds": 8,
            },
            idempotency_key="atomic-video-fixture",
        )
    )

    assert response["success"] is True
    assert events == ["reserve", "capacity", "charge", "launch"]
    assert services["features"].consume_video_reservation.await_count == 1
    assert services["video"].start.await_count == 2


@pytest.mark.asyncio
async def test_atomic_capacity_denial_stops_before_charge_or_provider_launch(
    monkeypatch,
):
    services = guarded_services()

    async def reserve(**kwargs):
        assert kwargs.get("reserve_only") is True
        return {
            "id": JOB_ID,
            "status": "queued",
            "provider_job_id": f"pending:{JOB_ID}",
            "idempotency_key": kwargs["idempotency_key"],
            "request_fingerprint": kwargs["request_fingerprint"],
            "video_phase": "reserved_unbilled",
            "lease_token": kwargs["reservation_token"],
            "metadata": {"billingPending": True},
        }

    services["video"].start.side_effect = reserve
    services["video"].authorize_reservation_capacity.side_effect = (
        VideoServiceError(
            "Wait for the current video job to finish before starting another.",
            "VIDEO_CONCURRENCY_LIMIT",
            429,
            True,
            False,
            JOB_ID,
        )
    )
    install_services(monkeypatch, services)

    response = await media_routes.create_video(
        JsonRequest(
            {
                "prompt": "A capacity denial must happen before money or provider work.",
                "engine": "quick",
                "resolution": "720p",
                "durationSeconds": 8,
            },
            idempotency_key="atomic-capacity-denied",
        )
    )

    assert response.status_code == 429
    assert response_body(response)["code"] == "VIDEO_CONCURRENCY_LIMIT"
    assert response_body(response)["shouldRetry"] is True
    services["video"].authorize_reservation_capacity.assert_awaited_once()
    services["features"].consume_video_reservation.assert_not_awaited()
    assert services["video"].start.await_count == 1


@pytest.mark.asyncio
async def test_losing_same_key_reservation_race_never_consumes_or_launches(monkeypatch):
    services = guarded_services()

    async def lose_reservation_race(**kwargs):
        assert kwargs.get("reserve_only") is True
        return {
            "id": JOB_ID,
            "status": "queued",
            "provider_job_id": f"pending:{JOB_ID}",
            "idempotency_key": kwargs["idempotency_key"],
            "request_fingerprint": kwargs["request_fingerprint"],
            "video_phase": "reserved_unbilled",
            "lease_token": "00000000-0000-0000-0000-000000000099",
            "metadata": {"billingPending": True},
        }

    services["video"].start.side_effect = lose_reservation_race
    install_services(monkeypatch, services)

    response = await media_routes.create_video(
        JsonRequest(
            {
                "prompt": "A careful duplicate video request fixture.",
                "engine": "quick",
                "resolution": "720p",
                "durationSeconds": 8,
            },
            idempotency_key="same-key-route-race",
        )
    )

    assert response.status_code == 409
    assert response_body(response)["code"] == "VIDEO_REQUEST_IN_PROGRESS"
    assert response_body(response)["shouldRetry"] is True
    services["features"].consume_video_reservation.assert_not_awaited()
    assert services["video"].start.await_count == 1
    services["video"].public_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_continue_video_reserves_before_one_charge_and_launch(monkeypatch):
    services = guarded_services()
    events = []

    async def reserve_or_launch(**kwargs):
        if kwargs.get("reserve_only"):
            events.append("reserve")
            return {
                "id": JOB_ID,
                "status": "queued",
                "provider_job_id": f"pending:{JOB_ID}",
                "idempotency_key": kwargs["idempotency_key"],
                "request_fingerprint": kwargs["request_fingerprint"],
                "video_phase": "reserved_unbilled",
                "lease_token": kwargs["reservation_token"],
                "metadata": {"billingPending": True},
            }
        events.append("launch")
        assert kwargs["reserved_job_id"] == JOB_ID
        return {"id": JOB_ID, "status": "processing"}

    async def consume(*_args, **_kwargs):
        events.append("charge")
        return {"eventId": "included-continuation-fixture"}

    async def authorize(**kwargs):
        events.append("capacity")
        return kwargs["row"]

    services["video"].continue_video.side_effect = reserve_or_launch
    services["video"].authorize_reservation_capacity.side_effect = authorize
    services["features"].consume_video_reservation.side_effect = consume
    install_services(monkeypatch, services)

    response = await media_routes.continue_video(
        JOB_ID,
        JsonRequest(
            {"prompt": "Continue the scene while preserving every visible detail."},
            idempotency_key="atomic-continuation-fixture",
        ),
    )

    assert response["success"] is True
    assert events == ["reserve", "capacity", "charge", "launch"]
    assert services["features"].consume_video_reservation.await_count == 1
    assert services["video"].continue_video.await_count == 2


@pytest.mark.asyncio
async def test_billing_rejection_releases_owned_reservation_before_response(monkeypatch):
    services = guarded_services()

    async def reserve(**kwargs):
        assert kwargs.get("reserve_only") is True
        return {
            "id": JOB_ID,
            "status": "queued",
            "provider_job_id": f"pending:{JOB_ID}",
            "idempotency_key": kwargs["idempotency_key"],
            "request_fingerprint": kwargs["request_fingerprint"],
            "video_phase": "reserved_unbilled",
            "lease_token": kwargs["reservation_token"],
            "metadata": {"billingPending": True},
        }

    services["video"].start.side_effect = reserve
    services["features"].consume_video_reservation.side_effect = FeatureAccessError(
        "Video needs one Crump Credit.",
        "CREDITS_REQUIRED",
        402,
        "free",
        1,
        0,
    )
    install_services(monkeypatch, services)

    response = await media_routes.create_video(
        JsonRequest(
            {
                "prompt": "A careful unpaid reservation cleanup fixture.",
                "engine": "quick",
                "resolution": "720p",
                "durationSeconds": 8,
            },
            idempotency_key="unpaid-reservation-fixture",
        )
    )

    assert response.status_code == 402
    services["video"].release_unbilled_reservation.assert_awaited_once()
    assert services["video"].start.await_count == 1


@pytest.mark.asyncio
async def test_request_status_recovers_owned_job_by_idempotency_key(monkeypatch):
    services = guarded_services()
    services["existing"].return_value = {
        "id": JOB_ID,
        "status": "processing",
        "provider_job_id": "provider-job-1",
        "metadata": {"billingPending": False},
    }
    install_services(monkeypatch, services)

    response = await media_routes.video_request_status(
        JsonRequest({}, idempotency_key="recover-video-request")
    )

    assert response["success"] is True
    assert response["idempotentReplay"] is True
    services["existing"].assert_awaited_once_with(USER_ID, "recover-video-request")
    services["video"].public_job.assert_awaited_once()
    services["features"].consume_video_reservation.assert_not_awaited()


def test_video_idempotency_key_normalizes_and_enforces_the_bound():
    bounded = "x" * media_routes.VIDEO_IDEMPOTENCY_KEY_MAX_LENGTH

    assert media_routes._idempotency_key(
        JsonRequest({}, idempotency_key=f"  {bounded}  "),
        {},
    ) == bounded
    assert media_routes._idempotency_key(
        JsonRequest({}, idempotency_key=f"{bounded}x"),
        {},
    ) is None


@pytest.mark.asyncio
async def test_atomic_feature_call_passes_every_database_fence_and_returns_receipt():
    class AtomicDB:
        def __init__(self):
            self.calls = []

        async def rpc(self, name, payload, *, retry_transient=False):
            self.calls.append((name, payload, retry_transient))
            return [
                {
                    "outcome": "bound",
                    "receipt": {
                        "feature": "video",
                        "eventId": "credit:fixture",
                        "paymentSource": "credits",
                    },
                    "balance": 9,
                }
            ]

    database = AtomicDB()
    service = FeatureService(database)
    service.require_tier = AsyncMock(return_value=POLICIES["video"])
    service.authorize = AsyncMock(
        return_value=CreditAuthorization(
            user_id=USER_ID,
            action_key="approved-action",
            max_by_code={"video": 60},
            quantities={"video": 1},
            confirmed_credits=60,
        )
    )

    receipt = await service.consume_video_reservation(
        {"id": USER_ID, "subscription_tier": "free"},
        "video",
        media_job_id=JOB_ID,
        idempotency_key="atomic-rpc-fences",
        request_fingerprint="a" * 64,
        reservation_token="00000000-0000-0000-0000-000000000099",
        instance_key="atomic-rpc-fences",
    )

    assert receipt["eventId"] == "credit:fixture"
    name, rpc_payload, retry_transient = database.calls[0]
    assert name == "consume_video_reservation"
    assert retry_transient is True
    assert rpc_payload["p_user_id"] == USER_ID
    assert rpc_payload["p_job_id"] == JOB_ID
    assert rpc_payload["p_idempotency_key"] == "atomic-rpc-fences"
    assert rpc_payload["p_request_fingerprint"] == "a" * 64
    assert rpc_payload["p_reservation_token"].endswith("0099")
    assert media_routes._idempotency_key(
        JsonRequest({}),
        {"idempotencyKey": "  body-key  "},
    ) == "body-key"
    assert media_routes._idempotency_key(
        JsonRequest({}),
        {"idempotencyKey": {"not": "a string"}},
    ) is None


@pytest.mark.asyncio
async def test_missing_project_is_rejected_before_allowance_credit_or_provider_work(
    monkeypatch,
):
    services = guarded_services()
    services["projects"].get.side_effect = ProjectNotFoundError("Project not found.")
    install_services(monkeypatch, services)
    request = JsonRequest(
        {
            "prompt": "A careful project-order fixture.",
            "engine": "quick",
            "resolution": "720p",
            "durationSeconds": 8,
            "projectId": PROJECT_ID,
        },
        idempotency_key="video-project-order-fixture",
    )

    response = await media_routes.create_video(request)

    assert response.status_code == 404
    assert response_body(response) == {
        "success": False,
        "error": "Project not found.",
        "code": "PROJECT_NOT_FOUND",
    }
    services["projects"].get.assert_awaited_once_with(USER_ID, PROJECT_ID)
    services["features"].consume_video_reservation.assert_not_awaited()
    services["features"].refund.assert_not_awaited()
    services["video"].prepare_reference_images.assert_not_awaited()
    services["video"].guard_provider_budget.assert_not_awaited()
    services["video"].start.assert_not_awaited()
    services["video"].prepare_provider_prompt.assert_not_called()
    services["video"].provider_cost_cents.assert_not_called()
    services["video"].provider_for_engine.assert_not_called()


@pytest.mark.asyncio
async def test_same_key_with_changed_request_is_rejected_before_reconcile_or_charge(
    monkeypatch,
):
    services = guarded_services()
    services["existing"].return_value = {
        "id": JOB_ID,
        "status": "queued",
        "provider_job_id": f"pending:{JOB_ID}",
        "idempotency_key": "fingerprint-conflict",
        "request_fingerprint": "f" * 64,
        "video_phase": "reserved_unbilled",
    }
    install_services(monkeypatch, services)

    response = await media_routes.create_video(
        JsonRequest(
            {"prompt": "A different normalized request for this key."},
            idempotency_key="fingerprint-conflict",
        )
    )

    assert response.status_code == 409
    assert response_body(response)["code"] == "VIDEO_IDEMPOTENCY_CONFLICT"
    services["video"].reconcile_pending.assert_not_awaited()
    services["features"].consume_video_reservation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["create", "continue"])
async def test_pre_atomic_same_key_mismatch_replays_existing_job_without_new_launch(
    monkeypatch,
    endpoint,
):
    services = guarded_services()
    existing = {
        "id": JOB_ID,
        "status": "processing",
        "provider_job_id": "legacy-provider-job",
        "idempotency_key": "pre-atomic-replay",
        "request_fingerprint": "f" * 64,
        "video_phase": "processing",
        "metadata": {"compatibilityOrigin": "pre-atomic"},
    }
    services["existing"].return_value = existing
    services["video"].reconcile_pending.return_value = existing
    install_services(monkeypatch, services)

    request = JsonRequest(
        {"prompt": "A different canonical payload than the synthetic legacy fingerprint."},
        idempotency_key="pre-atomic-replay",
    )
    response = (
        await media_routes.create_video(request)
        if endpoint == "create"
        else await media_routes.continue_video(JOB_ID, request)
    )

    assert response["success"] is True
    assert response["idempotentReplay"] is True
    services["video"].reconcile_pending.assert_awaited_once_with(
        user_id=USER_ID,
        row=existing,
        launch_ready=True,
    )
    services["video"].public_job.assert_awaited_once_with(
        user_id=USER_ID,
        row=existing,
    )
    services["features"].consume_video_reservation.assert_not_awaited()
    services["video"].prepare_reference_images.assert_not_awaited()
    services["video"].guard_provider_budget.assert_not_awaited()
    services["video"].start.assert_not_awaited()
    services["video"].validate_continuation_parent.assert_not_awaited()
    services["video"].continue_video.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_billing_response_reads_bound_receipt_and_never_cleans_up(
    monkeypatch,
):
    services = guarded_services()
    payload = {
        "prompt": "A protected billing response-loss recovery fixture.",
        "engine": "quick",
        "resolution": "720p",
        "durationSeconds": 8,
    }
    install_services(monkeypatch, services)
    _, _, _, _, fingerprint = media_routes._normalized_creation_identity(
        payload,
        engine="quick",
        resolution="720p",
        duration=8,
    )

    async def reserve_or_launch(**kwargs):
        if kwargs.get("reserve_only"):
            return {
                "id": JOB_ID,
                "status": "queued",
                "provider_job_id": f"pending:{JOB_ID}",
                "idempotency_key": kwargs["idempotency_key"],
                "request_fingerprint": kwargs["request_fingerprint"],
                "video_phase": "reserved_unbilled",
                "lease_token": kwargs["reservation_token"],
            }
        return {"id": JOB_ID, "status": "processing"}

    services["video"].start.side_effect = reserve_or_launch
    services["features"].consume_video_reservation.side_effect = RuntimeError(
        "response lost after commit"
    )
    services["existing"].side_effect = [
        None,
        {
            "id": JOB_ID,
            "status": "queued",
            "provider_job_id": f"pending:{JOB_ID}",
            "idempotency_key": "ambiguous-billing",
            "request_fingerprint": fingerprint,
            "video_phase": "ready_to_launch",
            "lease_token": None,
            "billing_receipt": {"eventId": "included:committed"},
        },
    ]

    response = await media_routes.create_video(
        JsonRequest(payload, idempotency_key="ambiguous-billing")
    )

    assert response["success"] is True
    assert services["video"].start.await_count == 2
    services["video"].release_unbilled_reservation.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_billing_receipt_remains_recoverable_during_finalization(
    monkeypatch,
):
    receipt = {
        "eventId": "credit:00000000-0000-0000-0000-000000000099",
        "paymentSource": "credits",
    }
    monkeypatch.setattr(
        media_routes,
        "_existing_job",
        AsyncMock(
            return_value={
                "id": JOB_ID,
                "user_id": USER_ID,
                "idempotency_key": "finalizing-billing-recovery",
                "request_fingerprint": "f" * 64,
                "status": "processing",
                "video_phase": "finalizing",
                "billing_receipt": receipt,
            }
        ),
    )

    row, recovered = await media_routes._read_bound_video_receipt(
        user_id=USER_ID,
        idempotency_key="finalizing-billing-recovery",
        request_fingerprint="f" * 64,
    )

    assert row["video_phase"] == "finalizing"
    assert recovered == receipt


@pytest.mark.asyncio
async def test_ambiguous_billing_without_bound_receipt_is_retryable_and_not_released(
    monkeypatch,
):
    services = guarded_services()
    payload = {
        "prompt": "A protected unresolved billing transport fixture.",
        "engine": "quick",
        "resolution": "720p",
        "durationSeconds": 8,
    }
    install_services(monkeypatch, services)
    _, _, _, _, fingerprint = media_routes._normalized_creation_identity(
        payload,
        engine="quick",
        resolution="720p",
        duration=8,
    )
    reserved = {
        "id": JOB_ID,
        "status": "queued",
        "provider_job_id": f"pending:{JOB_ID}",
        "idempotency_key": "ambiguous-unbound",
        "request_fingerprint": fingerprint,
        "video_phase": "reserved_unbilled",
        "lease_token": "00000000-0000-0000-0000-000000000099",
        "billing_receipt": {},
    }

    async def reserve(**kwargs):
        return {
            **reserved,
            "lease_token": kwargs["reservation_token"],
        }

    services["video"].start.side_effect = reserve
    services["features"].consume_video_reservation.side_effect = RuntimeError(
        "billing transport unavailable"
    )
    services["existing"].side_effect = [None, reserved]

    response = await media_routes.create_video(
        JsonRequest(payload, idempotency_key="ambiguous-unbound")
    )

    assert response.status_code == 503
    assert response_body(response)["code"] == "VIDEO_BILLING_STATE_UNAVAILABLE"
    assert response_body(response)["shouldRetry"] is True
    assert services["video"].start.await_count == 1
    services["video"].release_unbilled_reservation.assert_not_awaited()


@pytest.mark.asyncio
async def test_status_never_bypasses_quarantined_compatibility_refund_validation(
    monkeypatch,
):
    services = guarded_services()
    services["video"].poll = AsyncMock(
        return_value={
            "id": JOB_ID,
            "user_id": USER_ID,
            "kind": "video",
            "status": "failed",
            "video_phase": "failed",
            "billing_refunded": False,
            "billing_receipt": {
                "eventId": "credit:00000000-0000-4000-8000-000000000099",
                "paymentSource": "poisoned-source",
            },
            "metadata": {
                "compatibilityOrigin": "pre-atomic",
                "refundEligible": True,
                "sweepNeedsReview": True,
            },
        }
    )
    install_services(monkeypatch, services)

    response = await media_routes.video_status(JOB_ID, SimpleNamespace())

    assert response["success"] is True
    assert response["job"]["status"] == "queued"
    services["features"].refund.assert_not_awaited()
