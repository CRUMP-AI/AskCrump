from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.routes import voice as voice_routes
from backend.voice_service import (
    ElevenLabsVoiceService,
    VoiceServiceError,
    prepare_speech_text,
)


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def settings(**changes):
    values = {
        "voice_generation_enabled": True,
        "elevenlabs_api_key": "server-secret-key",
        "elevenlabs_voice_id": "JBFqnCBsd6RMkjVDRZzb",
        "elevenlabs_model_id": "eleven_flash_v2_5",
        "elevenlabs_max_chars": 4000,
    }
    values.update(changes)
    return SimpleNamespace(**values)


def test_speech_text_is_bounded_and_removes_markdown_noise():
    prepared = prepare_speech_text(
        "# Result\nRead [the guide](https://private.example/path). ```python\nsecret = 1\n```",
        max_chars=4000,
    )
    assert prepared == "Result Read the guide. Code sample omitted."
    assert "private.example" not in prepared
    assert "secret" not in prepared
    with pytest.raises(VoiceServiceError) as raised:
        prepare_speech_text("x" * 401, max_chars=400)
    assert raised.value.code == "VOICE_TEXT_TOO_LONG"


def test_voice_is_disabled_without_every_server_side_gate():
    assert ElevenLabsVoiceService(settings()).configured is True
    assert ElevenLabsVoiceService(settings(voice_generation_enabled=False)).configured is False
    assert ElevenLabsVoiceService(settings(elevenlabs_api_key=None)).configured is False
    assert ElevenLabsVoiceService(settings(elevenlabs_voice_id="")).configured is False
    assert ElevenLabsVoiceService(settings(elevenlabs_model_id="arbitrary-model")).configured is False


@pytest.mark.asyncio
async def test_elevenlabs_request_is_server_authenticated_bounded_and_ephemeral():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, headers={"Content-Type": "audio/mpeg"}, content=b"ID3audio")

    service = ElevenLabsVoiceService(settings(), transport=httpx.MockTransport(handler))
    audio = await service.synthesize_prepared("A concise response.")
    assert audio == b"ID3audio"
    request = captured["request"]
    assert request.headers["xi-api-key"] == "server-secret-key"
    assert request.url.params["output_format"] == "mp3_44100_128"
    assert request.url.path.endswith("/JBFqnCBsd6RMkjVDRZzb")
    assert b'"model_id":"eleven_flash_v2_5"' in request.content


@pytest.mark.asyncio
async def test_provider_details_are_not_leaked_in_errors():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "sensitive provider account detail"})

    service = ElevenLabsVoiceService(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(VoiceServiceError) as raised:
        await service.synthesize_prepared("Hello")
    assert raised.value.code == "VOICE_PROVIDER_AUTH_FAILED"
    assert "sensitive provider" not in str(raised.value)


def test_voice_route_feature_and_browser_fallback_contract():
    route = read("backend/routes/voice.py")
    application = read("backend/application.py")
    policy = read("backend/feature_service.py")
    config = read("backend/config.py")
    example = read(".env.example")
    browser = read("public/app.js")

    assert 'features.consume(' in route and '"premium_voice"' in route
    assert 'await features.refund' in route
    assert 'Cache-Control": "private, no-store"' in route
    assert "application.include_router(voice.router)" in application
    assert '"premium_voice": FeaturePolicy' in policy
    assert '"professional": 10' in policy and '"enterprise": 30' in policy
    assert "elevenlabs_api_key" in config and "CRUMP_ENABLE_PREMIUM_VOICE" in config
    assert "ELEVENLABS_API_KEY=" in example and "ELEVENLABS_VOICE_ID=" in example
    assert '"premium_voice": voice.configured' in read("backend/routes/features.py")
    assert "/api/voice/synthesize" in browser
    assert "data?.features?.premium_voice" in browser
    assert "feature.configured && feature.entitled" in browser
    assert "speakWithDeviceVoice" in browser
    assert "URL.revokeObjectURL" in browser
    assert "ELEVENLABS_API_KEY" not in browser


@pytest.mark.asyncio
async def test_voice_route_returns_private_ephemeral_audio_and_usage_receipt(monkeypatch):
    calls = []

    async def authenticate(_request, _database, _settings):
        return SimpleNamespace(user={
            "id": "00000000-0000-0000-0000-000000000001",
            "subscription_tier": "professional",
            "subscription_status": "active",
        })

    async def rate_limit(_database, **values):
        calls.append(("rate", values))

    class FakeVoice:
        configured = True

        @staticmethod
        def prepare(value):
            assert value == "Read this response."
            return value

        @staticmethod
        async def synthesize_prepared(value):
            assert value == "Read this response."
            return b"ID3private-audio"

    class FakeFeatures:
        async def consume(self, user, code, metadata):
            calls.append(("consume", user["id"], code, metadata))
            return {"paymentSource": "included", "creditsSpent": 0}

        async def refund(self, _user_id, _receipt):
            raise AssertionError("successful synthesis must not be refunded")

    class FakeRequest:
        async def json(self):
            return {"text": "Read this response."}

    monkeypatch.setattr(voice_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(voice_routes, "enforce_user_rate_limit", rate_limit)
    monkeypatch.setattr(voice_routes, "voice", FakeVoice())
    monkeypatch.setattr(voice_routes, "features", FakeFeatures())
    monkeypatch.setattr(
        voice_routes,
        "settings",
        SimpleNamespace(elevenlabs_model_id="eleven_flash_v2_5"),
    )

    response = await voice_routes.synthesize(FakeRequest())
    assert response.status_code == 200
    assert response.media_type == "audio/mpeg"
    assert response.body == b"ID3private-audio"
    assert response.headers["cache-control"] == "private, no-store"
    assert calls[1] == (
        "consume",
        "00000000-0000-0000-0000-000000000001",
        "premium_voice",
        {"characters": 19, "model": "eleven_flash_v2_5"},
    )


@pytest.mark.asyncio
async def test_voice_route_refunds_usage_when_provider_fails(monkeypatch):
    refunds = []

    async def authenticate(_request, _database, _settings):
        return SimpleNamespace(user={"id": "00000000-0000-0000-0000-000000000001"})

    async def rate_limit(_database, **_values):
        return None

    class FakeVoice:
        configured = True

        @staticmethod
        def prepare(value):
            return str(value)

        @staticmethod
        async def synthesize_prepared(_value):
            raise VoiceServiceError("Provider failed.", 502, "VOICE_PROVIDER_FAILED")

    class FakeFeatures:
        async def consume(self, _user, _code, _metadata):
            return {"paymentSource": "included", "eventId": "event-1"}

        async def refund(self, user_id, receipt):
            refunds.append((user_id, receipt))

    class FakeRequest:
        async def json(self):
            return {"text": "Hello"}

    monkeypatch.setattr(voice_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(voice_routes, "enforce_user_rate_limit", rate_limit)
    monkeypatch.setattr(voice_routes, "voice", FakeVoice())
    monkeypatch.setattr(voice_routes, "features", FakeFeatures())
    monkeypatch.setattr(
        voice_routes,
        "settings",
        SimpleNamespace(elevenlabs_model_id="eleven_flash_v2_5"),
    )

    response = await voice_routes.synthesize(FakeRequest())
    assert response.status_code == 502
    assert b"Provider failed" in response.body
    assert refunds == [(
        "00000000-0000-0000-0000-000000000001",
        {"paymentSource": "included", "eventId": "event-1"},
    )]
