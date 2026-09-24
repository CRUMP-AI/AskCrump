from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend import video_providers
from backend.video_providers import GeminiVeoProvider, ProviderError, RunwayProvider


class StreamResponse:
    def __init__(self, *, status=200, headers=None, chunks=()):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = list(chunks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class StreamClient:
    responses = {}
    requests = []

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def stream(self, method, url, *, headers):
        self.requests.append((method, url, dict(headers)))
        return self.responses[url]


async def allow_public(uri, *, provider):
    return video_providers._safe_https_url(uri, provider=provider)


@pytest.mark.asyncio
async def test_gemini_redirect_is_revalidated_and_drops_api_key_cross_origin(monkeypatch):
    first = "https://generativelanguage.googleapis.com/v1beta/files/one:download"
    second = "https://media.googleusercontent.com/video.mp4"
    StreamClient.requests = []
    StreamClient.responses = {
        first: StreamResponse(status=302, headers={"location": second}),
        second: StreamResponse(chunks=[b"\x00\x00\x00\x18ftyp", b"mp42video"]),
    }
    monkeypatch.setattr(video_providers, "_safe_resolved_https_url", allow_public)
    monkeypatch.setattr(video_providers.httpx, "AsyncClient", StreamClient)
    provider = GeminiVeoProvider(SimpleNamespace(
        gemini_api_key="private-key",
        video_generation_enabled=True,
    ))

    data = await provider.download(first, max_bytes=100)

    assert data.startswith(b"\x00\x00\x00\x18ftyp")
    assert StreamClient.requests[0][2] == {"x-goog-api-key": "private-key"}
    assert StreamClient.requests[1][2] == {}


@pytest.mark.asyncio
async def test_runway_download_stops_when_stream_crosses_limit(monkeypatch):
    uri = "https://cdn.runway.example/video.mp4"
    StreamClient.requests = []
    StreamClient.responses = {
        uri: StreamResponse(chunks=[b"1234", b"5678"]),
    }
    monkeypatch.setattr(video_providers, "_safe_resolved_https_url", allow_public)
    monkeypatch.setattr(video_providers.httpx, "AsyncClient", StreamClient)
    provider = RunwayProvider(SimpleNamespace(
        runway_api_secret="private-key",
        runway_api_version="2024-11-06",
        video_generation_enabled=True,
    ))

    with pytest.raises(ProviderError) as error:
        await provider.download(uri, max_bytes=6)

    assert error.value.code == "VIDEO_FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_dns_resolution_rejects_private_provider_target(monkeypatch):
    monkeypatch.setattr(
        video_providers.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )

    with pytest.raises(ProviderError) as error:
        await video_providers._safe_resolved_https_url(
            "https://cdn.runway.example/video.mp4",
            provider="runway",
        )

    assert error.value.code == "UNSAFE_VIDEO_URI"


def test_provider_url_rejects_nonstandard_https_ports():
    with pytest.raises(ProviderError) as error:
        video_providers._safe_https_url(
            "https://cdn.runway.example:8443/video.mp4",
            provider="runway",
        )

    assert error.value.code == "UNSAFE_VIDEO_URI"


@pytest.mark.asyncio
async def test_credentialed_download_rejects_malformed_port_without_raw_value_error():
    with pytest.raises(ProviderError) as error:
        await video_providers._bounded_provider_download(
            "https://generativelanguage.googleapis.com:invalid/video.mp4",
            provider="Gemini",
            max_bytes=1024,
            credential_headers={"x-goog-api-key": "secret"},
        )

    assert error.value.code == "UNSAFE_VIDEO_URI"


def test_provider_rejection_logs_never_include_upstream_message(caplog):
    class Response:
        status_code = 400
        headers = {"x-request-id": "request-safe"}
        text = "private customer prompt should never be logged"

        @staticmethod
        def json():
            return {"error": {"status": "INVALID_ARGUMENT", "message": Response.text}}

    with caplog.at_level("ERROR", logger="askcrump.video.providers"):
        GeminiVeoProvider._exception(Response())

    assert "INVALID_ARGUMENT" in caplog.text
    assert "request-safe" in caplog.text
    assert "private customer prompt" not in caplog.text
