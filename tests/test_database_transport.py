from types import SimpleNamespace

import httpx
import pytest

from backend.db import DatabaseError, SupabaseDB


def db_settings() -> SimpleNamespace:
    return SimpleNamespace(
        supabase_url="https://project.supabase.co",
        supabase_service_key="service-test-key",
    )


@pytest.mark.asyncio
async def test_transient_read_status_retries_with_bounded_backoff_and_retry_header():
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503, json={"code": "PGRST001"})
        return httpx.Response(200, json=[{"id": "row-1"}])

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client, sleep=fake_sleep)
        rows = await database.select("records", filters={"user_id": "eq.user-1"})

    assert rows == [{"id": "row-1"}]
    assert len(calls) == 3
    assert calls[0].headers.get("x-retry-count") is None
    assert calls[1].headers["x-retry-count"] == "1"
    assert calls[2].headers["x-retry-count"] == "2"
    assert sleeps == [0.25, 0.75]


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [500, 502])
async def test_transient_database_gateway_failures_retry_safe_reads(status_code):
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(status_code, json={"code": "UPSTREAM_UNAVAILABLE"})
        return httpx.Response(200, json=[])

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client, sleep=fake_sleep)
        rows = await database.select("scheduled_work", columns="status")

    assert rows == []
    assert len(calls) == 2
    assert calls[0].headers.get("x-retry-count") is None
    assert calls[1].headers["x-retry-count"] == "1"
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_transient_read_transport_failure_exhausts_without_leaking_request_details():
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError(
            "private-filter=eq.secret-value",
            request=request,
        )

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client, sleep=fake_sleep)
        with pytest.raises(DatabaseError) as captured:
            await database.select_one(
                "sessions",
                filters={"token_hash": "eq.private-session-hash"},
            )

    assert len(calls) == 5
    assert sleeps == [0.25, 0.75, 1.5, 3.0]
    assert captured.value.status_code == 503
    assert captured.value.retryable is True
    assert captured.value.retry_after == 2
    assert captured.value.attempts == 5
    assert captured.value.details == {"error_type": "ConnectError"}
    assert "private" not in str(captured.value.details)


@pytest.mark.asyncio
async def test_non_idempotent_write_is_never_retried_after_transient_status():
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503, json={"code": "PGRST001"})

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client, sleep=fake_sleep)
        with pytest.raises(DatabaseError) as captured:
            await database.insert("records", {"id": "write-1"})

    assert len(calls) == 1
    assert sleeps == []
    assert captured.value.retryable is False
    assert captured.value.attempts == 1


@pytest.mark.asyncio
async def test_transient_gateway_timeout_can_recover_on_final_bounded_read_attempt():
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 5:
            return httpx.Response(504, json={"code": "UPSTREAM_TIMEOUT"})
        return httpx.Response(200, json=[{"status": "ready"}])

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client, sleep=fake_sleep)
        rows = await database.select("scheduled_work", columns="status")

    assert rows == [{"status": "ready"}]
    assert len(calls) == 5
    assert [request.headers.get("x-retry-count") for request in calls] == [
        None,
        "1",
        "2",
        "3",
        "4",
    ]
    assert sleeps == [0.25, 0.75, 1.5, 3.0]


@pytest.mark.asyncio
async def test_explicitly_idempotent_rpc_retries_with_the_same_payload():
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, json={"code": "PGRST001"})
        return httpx.Response(200, json=[])

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    payload = {
        "p_lease_seconds": 420,
        "p_claim_token": "00000000-0000-4000-8000-000000000001",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client, sleep=fake_sleep)
        result = await database.rpc(
            "claim_manuscript_run",
            payload,
            retry_transient=True,
        )

    assert result == []
    assert len(calls) == 2
    assert calls[0].content == calls[1].content
    assert calls[0].headers.get("x-retry-count") is None
    assert calls[1].headers["x-retry-count"] == "1"
    assert sleeps == [0.25]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rpc_name", "payload", "duplicate_response"),
    [
        (
            "consume_usage_event_v2",
            {
                "p_user_id": "00000000-0000-4000-8000-000000000001",
                "p_event_type": "messages",
                "p_limit": 10,
                "p_metadata": {"usageIdempotencyKey": "message-1"},
            },
            [{
                "event_id": "00000000-0000-4000-8000-000000000101",
                "used": 1,
                "allowed": True,
                "duplicate": True,
            }],
        ),
        (
            "spend_credits_confirmed_v2",
            {
                "p_user_id": "00000000-0000-4000-8000-000000000001",
                "p_amount": 10,
                "p_reason": "feature_image_edit",
                "p_action_key": "quote-1",
                "p_component": "message-1:image-edit",
                "p_confirmed_max": 10,
                "p_usage_event_type": "feature:image_edit",
                "p_usage_idempotency_key": "message-1:image-edit",
                "p_metadata": {},
            },
            [{
                "ledger_id": "00000000-0000-4000-8000-000000000201",
                "balance": 90,
                "allowed": True,
                "duplicate": True,
                "limit_exceeded": False,
            }],
        ),
    ],
)
async def test_keyed_billing_rpc_retries_after_commit_response_is_lost(
    rpc_name: str,
    payload: dict,
    duplicate_response: list[dict],
):
    calls: list[httpx.Request] = []
    sleeps: list[float] = []
    committed = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal committed
        calls.append(request)
        if len(calls) == 1:
            # The database transaction committed, but the response disappeared
            # before the application could own its receipt.
            committed = True
            raise httpx.ReadError("response lost after commit", request=request)
        assert committed is True
        return httpx.Response(200, json=duplicate_response)

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client, sleep=fake_sleep)
        result = await database.rpc(
            rpc_name,
            payload,
            retry_transient=True,
        )

    assert result == duplicate_response
    assert len(calls) == 2
    assert calls[0].content == calls[1].content
    assert calls[0].headers.get("x-retry-count") is None
    assert calls[1].headers["x-retry-count"] == "1"
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_explicitly_idempotent_rpc_retries_after_bad_gateway():
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(502, json={"code": "UPSTREAM_UNAVAILABLE"})
        return httpx.Response(200, json=[])

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    payload = {
        "p_lease_seconds": 420,
        "p_claim_token": "00000000-0000-4000-8000-000000000002",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client, sleep=fake_sleep)
        result = await database.rpc(
            "claim_manuscript_run",
            payload,
            retry_transient=True,
        )

    assert result == []
    assert len(calls) == 2
    assert calls[0].content == calls[1].content
    assert calls[1].headers["x-retry-count"] == "1"
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_explicitly_idempotent_rpc_does_not_retry_database_internal_error():
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500, json={"code": "P0001"})

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client, sleep=fake_sleep)
        with pytest.raises(DatabaseError) as captured:
            await database.rpc(
                "claim_manuscript_run",
                {
                    "p_lease_seconds": 420,
                    "p_claim_token": "00000000-0000-4000-8000-000000000003",
                },
                retry_transient=True,
            )

    assert len(calls) == 1
    assert sleeps == []
    assert captured.value.status_code == 500
    assert captured.value.retryable is False
    assert captured.value.attempts == 1


@pytest.mark.asyncio
async def test_explicitly_idempotent_upsert_retries_with_the_same_payload():
    calls: list[httpx.Request] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(504, json={"code": "UPSTREAM_TIMEOUT"})
        return httpx.Response(200, json=[{"user_id": "user-1"}])

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    payload = {
        "user_id": "user-1",
        "assistant_name": "Crump",
        "updated_at": "2026-09-14T00:05:00+00:00",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client, sleep=fake_sleep)
        result = await database.upsert(
            "user_settings",
            payload,
            on_conflict="user_id",
            retry_transient=True,
        )

    assert result == [{"user_id": "user-1"}]
    assert len(calls) == 2
    assert calls[0].content == calls[1].content
    assert calls[0].headers.get("x-retry-count") is None
    assert calls[1].headers["x-retry-count"] == "1"
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_non_transient_read_error_is_not_retried():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, json={"code": "PGRST100"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        database = SupabaseDB(db_settings(), client=client)
        with pytest.raises(DatabaseError) as captured:
            await database.select("records")

    assert len(calls) == 1
    assert captured.value.status_code == 400
    assert captured.value.retryable is False
