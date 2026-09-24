from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend import video_providers
from backend.video_service import VideoService
from backend.video_providers import GeminiVeoProvider, ProviderError, RunwayProvider


def iso_box(box_type: bytes, payload: bytes) -> bytes:
    return (len(payload) + 8).to_bytes(4, "big") + box_type + payload


def movie_box(
    *,
    handler_type: bytes = b"vide",
    timescale: int = 1000,
    version: int = 0,
) -> bytes:
    movie_header = bytearray(112 if version == 1 else 100)
    movie_header[0] = version
    timescale_start = 20 if version == 1 else 12
    movie_header[timescale_start : timescale_start + 4] = timescale.to_bytes(4, "big")
    handler = bytearray(24)
    handler[8:12] = handler_type
    media = iso_box(b"mdia", iso_box(b"hdlr", bytes(handler)))
    return iso_box(
        b"moov",
        iso_box(b"mvhd", bytes(movie_header)) + iso_box(b"trak", media),
    )


FTYP = iso_box(b"ftyp", b"isom\x00\x00\x02\x00isommp42")
MOOV = movie_box()
MDAT = iso_box(b"mdat", b"data")
VALID_MP4 = FTYP + MOOV + MDAT


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
        second: StreamResponse(chunks=[VALID_MP4[:19], VALID_MP4[19:]]),
    }
    monkeypatch.setattr(video_providers, "_safe_resolved_https_url", allow_public)
    monkeypatch.setattr(video_providers.httpx, "AsyncClient", StreamClient)
    provider = GeminiVeoProvider(SimpleNamespace(
        gemini_api_key="private-key",
        video_generation_enabled=True,
    ))

    data = await provider.download(first, max_bytes=len(VALID_MP4))

    assert data == VALID_MP4
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


def test_generated_video_requires_complete_mp4_structure():
    assert VideoService._valid_generated_video(VALID_MP4)
    assert not VideoService._valid_generated_video(
        b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isommp42"
    )


def test_generated_video_rejects_truncated_or_overlapping_boxes():
    truncated = VALID_MP4[:-1]
    oversized_moov = (
        FTYP
        + b"\x00\x00\x10\x00"
        + MOOV[4:]
        + MDAT
    )

    assert not VideoService._valid_generated_video(truncated)
    assert not VideoService._valid_generated_video(oversized_moov)


def test_generated_video_accepts_mdat_before_moov_and_extended_box_size():
    extended_mdat = b"\x00\x00\x00\x01mdat\x00\x00\x00\x00\x00\x00\x00\x14data"
    reordered = FTYP + extended_mdat + MOOV

    assert VideoService._valid_generated_video(reordered)


def test_generated_video_accepts_v1_movie_header_and_heavily_fragmented_output():
    fragment = iso_box(b"moof", iso_box(b"mfhd", b"\x00" * 8)) + iso_box(b"mdat", b"x")
    candidate = FTYP + movie_box(version=1) + (fragment * 5000)

    assert VideoService._valid_generated_video(candidate)


def test_generated_video_accepts_provider_brand_changes_but_rejects_empty_media_data():
    unknown_brand = VALID_MP4.replace(b"isom", b"zzzz").replace(b"mp42", b"yyyy")
    empty_mdat = FTYP + MOOV + iso_box(b"mdat", b"")

    assert VideoService._valid_generated_video(unknown_brand)
    assert not VideoService._valid_generated_video(empty_mdat)


def test_generated_video_accepts_terminal_media_data_and_uuid_boxes():
    uuid_box = b"\x00\x00\x00\x1cuuid" + (b"\x01" * 16) + b"data"
    terminal_mdat = b"\x00\x00\x00\x00mdatdata"
    candidate = FTYP + uuid_box + MOOV + terminal_mdat

    assert VideoService._valid_generated_video(candidate)


def test_generated_video_rejects_duplicate_or_malformed_movie_boxes():
    duplicate_moov = FTYP + MOOV + MOOV + MDAT
    empty_moov = FTYP + iso_box(b"moov", b"") + MDAT

    assert not VideoService._valid_generated_video(duplicate_moov)
    assert not VideoService._valid_generated_video(empty_moov)


def test_generated_video_rejects_truncated_uuid_and_box_count_exhaustion():
    truncated_uuid = FTYP + b"\x00\x00\x00\x08uuid" + MOOV + MDAT
    too_many_boxes = (
        FTYP
        + (b"\x00\x00\x00\x08free" * 16_384)
        + MOOV
        + MDAT
    )

    assert not VideoService._valid_generated_video(truncated_uuid)
    assert not VideoService._valid_generated_video(too_many_boxes)


def test_generated_video_rejects_forged_movie_header_and_audio_only_container():
    forged_movie = iso_box(b"moov", iso_box(b"free", b""))
    audio_movie = movie_box(handler_type=b"soun")

    assert not VideoService._valid_generated_video(FTYP + forged_movie + MDAT)
    assert not VideoService._valid_generated_video(FTYP + audio_movie + MDAT)


def test_generated_video_rejects_zero_timescale_and_nested_zero_sized_box():
    zero_timescale = movie_box(timescale=0)
    nested_zero_size = iso_box(b"moov", b"\x00\x00\x00\x00free")

    assert not VideoService._valid_generated_video(FTYP + zero_timescale + MDAT)
    assert not VideoService._valid_generated_video(FTYP + nested_zero_size + MDAT)


def test_generated_video_rejects_short_or_unknown_movie_header_and_nested_overrun():
    short_header = iso_box(
        b"moov",
        iso_box(b"mvhd", b"\x00" * 20)
        + iso_box(b"trak", iso_box(b"mdia", iso_box(b"hdlr", b"\x00" * 24))),
    )
    unknown_version = bytearray(100)
    unknown_version[0] = 2
    unknown_version_movie = iso_box(
        b"moov",
        iso_box(b"mvhd", bytes(unknown_version))
        + iso_box(b"trak", iso_box(b"mdia", iso_box(b"hdlr", b"\x00" * 24))),
    )
    nested_overrun = iso_box(b"moov", b"\x00\x00\x10\x00mvhd\x00\x00\x00\x00")

    assert not VideoService._valid_generated_video(FTYP + short_header + MDAT)
    assert not VideoService._valid_generated_video(FTYP + unknown_version_movie + MDAT)
    assert not VideoService._valid_generated_video(FTYP + nested_overrun + MDAT)
