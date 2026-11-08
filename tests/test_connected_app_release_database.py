from __future__ import annotations

import json

import pytest

from backend import config
from backend.connected_app_release_database import (
    ConnectedReleasePreviewDatabaseError,
    ConnectedReleasePreviewProductionDatabase,
)


class Response:
    def __init__(self, chunks: list[bytes], *, status: int = 200) -> None:
        self._chunks = chunks
        self.status_code = status
        self.headers = {"content-type": "application/json"}

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class Stream:
    def __init__(self, response: Response) -> None:
        self.response = response

    async def __aenter__(self) -> Response:
        return self.response

    async def __aexit__(self, *_args) -> None:
        return None


class Client:
    constructed: list[dict[str, object]] = []
    response = Response([b"true"])
    request: tuple[object, ...] | None = None

    def __init__(self, **kwargs) -> None:
        type(self).constructed.append(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    def stream(self, method, url, **kwargs) -> Stream:
        type(self).request = (method, url, kwargs)
        return Stream(type(self).response)


@pytest.fixture(autouse=True)
def production_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SUPABASE_URL", config.PRODUCTION_SUPABASE_ORIGIN)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-role-" + "s" * 40)
    Client.constructed.clear()
    Client.response = Response([b"true"])
    Client.request = None


@pytest.mark.asyncio
async def test_fixed_origin_no_proxy_no_redirect_and_strict_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.connected_app_release_database.httpx.AsyncClient",
        Client,
    )
    database = ConnectedReleasePreviewProductionDatabase()
    value = await database.rpc(
        "claim_ai_gateway_cost_receipt",
        {"p_receipt_id": "content-free"},
    )
    assert value is True
    assert Client.constructed[0]["trust_env"] is False
    assert Client.constructed[0]["follow_redirects"] is False
    assert Client.request is not None
    assert Client.request[0] == "POST"
    assert Client.request[1] == (
        config.PRODUCTION_SUPABASE_ORIGIN
        + "/rest/v1/rpc/claim_ai_gateway_cost_receipt"
    )
    headers = Client.request[2]["headers"]
    assert headers["Authorization"].startswith("Bearer service-role-")
    assert ("service-role-" + "s" * 40) not in repr(database)


@pytest.mark.asyncio
async def test_chunked_oversize_aborts_before_allocating_unbounded_body(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "backend.connected_app_release_database.httpx.AsyncClient",
        Client,
    )
    Client.response = Response([b"x" * 524_288, b"y" * 524_289])
    with pytest.raises(ConnectedReleasePreviewDatabaseError):
        await ConnectedReleasePreviewProductionDatabase().rpc(
            "connected_app_release_preview_status_v1",
            {"p_invocation_id": "11111111-1111-4111-8111-111111111111"},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("APP_ENV", "preview"),
        ("SUPABASE_URL", "https://attacker.invalid"),
        ("SUPABASE_SERVICE_KEY", "short"),
    ),
)
async def test_wrong_environment_origin_or_service_authority_fails_before_io(
    monkeypatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        "backend.connected_app_release_database.httpx.AsyncClient",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("network reached")),
    )
    with pytest.raises(ConnectedReleasePreviewDatabaseError):
        await ConnectedReleasePreviewProductionDatabase().rpc(
            "connected_app_release_preview_status_v1",
            {"p_invocation_id": "11111111-1111-4111-8111-111111111111"},
        )


@pytest.mark.asyncio
async def test_duplicate_json_and_unapproved_function_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.connected_app_release_database.httpx.AsyncClient",
        Client,
    )
    Client.response = Response([b'{"x":1,"x":2}'])
    with pytest.raises(ConnectedReleasePreviewDatabaseError):
        await ConnectedReleasePreviewProductionDatabase().rpc(
            "connected_app_release_preview_status_v1",
            {"p_invocation_id": "11111111-1111-4111-8111-111111111111"},
        )
    with pytest.raises(ConnectedReleasePreviewDatabaseError):
        await ConnectedReleasePreviewProductionDatabase().rpc(
            "delete_user_account",
            {},
        )


def test_body_fixture_is_valid_json() -> None:
    assert json.loads(b"true") is True
