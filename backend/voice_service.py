"""Bounded, server-side ElevenLabs text-to-speech for explicit playback requests."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings


ALLOWED_MODELS = frozenset({
    "eleven_flash_v2_5",
    "eleven_multilingual_v2",
    "eleven_v3",
})
VOICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,80}$")
MAX_AUDIO_BYTES = 15 * 1024 * 1024


@dataclass(slots=True)
class VoiceServiceError(RuntimeError):
    message: str
    status_code: int = 400
    code: str = "VOICE_ERROR"

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message)


def prepare_speech_text(value: Any, *, max_chars: int) -> str:
    """Turn response Markdown into speech without retaining or logging its content."""
    text = str(value or "").strip()
    if not text:
        raise VoiceServiceError("Choose a response with text to read aloud.", 400, "VOICE_TEXT_REQUIRED")
    # Long code blocks and raw URLs are especially unpleasant when spoken.
    text = re.sub(r"```[\s\S]*?```", " Code sample omitted. ", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+", " link ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[`*_>#~|]", " ", text)
    text = re.sub(r"(?m)^\s*[-+]\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise VoiceServiceError("That response has no readable text.", 400, "VOICE_TEXT_REQUIRED")
    if len(text) > max_chars:
        raise VoiceServiceError(
            f"Premium voice supports up to {max_chars:,} characters at a time.",
            413,
            "VOICE_TEXT_TOO_LONG",
        )
    return text


class ElevenLabsVoiceService:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.voice_generation_enabled
            and self.settings.elevenlabs_api_key
            and VOICE_ID_RE.fullmatch(self.settings.elevenlabs_voice_id or "")
            and self.settings.elevenlabs_model_id in ALLOWED_MODELS
        )

    def prepare(self, value: Any) -> str:
        return prepare_speech_text(value, max_chars=self.settings.elevenlabs_max_chars)

    async def synthesize_prepared(self, text: str) -> bytes:
        if not self.configured:
            raise VoiceServiceError(
                "Premium voice is not configured yet.",
                503,
                "VOICE_NOT_CONFIGURED",
            )
        voice_id = quote(self.settings.elevenlabs_voice_id, safe="")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": str(self.settings.elevenlabs_api_key),
        }
        payload = {
            "text": text,
            "model_id": self.settings.elevenlabs_model_id,
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(45.0, connect=10.0),
                transport=self.transport,
            ) as client:
                response = await client.post(
                    url,
                    params={"output_format": "mp3_44100_128"},
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise VoiceServiceError(
                "Premium voice took too long to respond.",
                504,
                "VOICE_TIMEOUT",
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceServiceError(
                "Premium voice is temporarily unavailable.",
                502,
                "VOICE_PROVIDER_UNAVAILABLE",
            ) from exc
        if response.status_code == 429:
            raise VoiceServiceError(
                "Premium voice is busy. Try again shortly.",
                429,
                "VOICE_PROVIDER_BUSY",
            )
        if response.status_code in {401, 403}:
            raise VoiceServiceError(
                "Premium voice is not configured correctly.",
                503,
                "VOICE_PROVIDER_AUTH_FAILED",
            )
        if response.status_code >= 400:
            raise VoiceServiceError(
                "Premium voice could not create that audio.",
                502,
                "VOICE_PROVIDER_FAILED",
            )
        content_type = str(response.headers.get("content-type") or "").lower()
        if "audio" not in content_type or not response.content:
            raise VoiceServiceError(
                "Premium voice returned an invalid audio response.",
                502,
                "VOICE_INVALID_RESPONSE",
            )
        if len(response.content) > MAX_AUDIO_BYTES:
            raise VoiceServiceError(
                "Premium voice returned an audio file that was too large.",
                502,
                "VOICE_AUDIO_TOO_LARGE",
            )
        return response.content
