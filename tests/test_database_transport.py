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

    assert len(calls) == 4
    assert sleeps == [0.25, 0.75, 1.5]
    assert captured.value.status_code == 503
    assert captured.value.retryable is True
    assert captured.value.retry_after == 2
    assert captured.value.attempts == 4
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
