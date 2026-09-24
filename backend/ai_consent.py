"""Server-authoritative permission for sharing user content with third-party AI."""

from __future__ import annotations

from typing import Any


CURRENT_AI_DATA_SHARING_CONSENT_VERSION = "2026-09-17"
AI_DATA_SHARING_PROVIDERS = (
    "Anthropic",
    "OpenAI",
    "Vercel AI Gateway and Groq",
    "Google Gemini and Veo",
    "Runway",
    "ElevenLabs",
    "Brave Search",
    "OpenWeather",
    "Vercel Sandbox",
)
AI_DATA_SHARING_CATEGORIES = (
    "prompts and relevant conversation context",
    "files and images selected for the request",
    "text selected for voice generation",
    "video prompts, settings, and references",
    "Autonomous Crump task and repository content",
)


class AIDataSharingConsentRequired(RuntimeError):
    """Raised before any user content can reach a third-party AI provider."""

    def __init__(self) -> None:
        self.message = (
            "Allow AI data sharing before Ask Crump sends your prompt or selected files "
            "to the provider needed for this feature."
        )
        self.status_code = 428
        self.code = "AI_DATA_SHARING_CONSENT_REQUIRED"
        super().__init__(self.message)


def has_current_ai_data_sharing_consent(user: dict[str, Any] | None) -> bool:
    if not isinstance(user, dict):
        return False
    return bool(
        user.get("ai_data_sharing_consent_at")
        and user.get("ai_data_sharing_consent_version")
        == CURRENT_AI_DATA_SHARING_CONSENT_VERSION
        and not user.get("ai_data_sharing_consent_revoked_at")
        and not user.get("deleted_at")
    )


def require_ai_data_sharing_consent(user: dict[str, Any] | None) -> None:
    if not has_current_ai_data_sharing_consent(user):
        raise AIDataSharingConsentRequired()
