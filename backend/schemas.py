"""Validated request models for the public API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


CURRENT_TERMS_VERSION = "2026-08-01"


class APIModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    deviceName: str | None = Field(default=None, max_length=160)
    platform: str | None = Field(default=None, max_length=80)


class RegisterRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    fullName: str | None = Field(default=None, max_length=160)
    source: str | None = Field(default=None, max_length=32)
    placement: str | None = Field(default=None, max_length=32)
    campaign: str | None = Field(default=None, max_length=32)
    creative: str | None = Field(default=None, max_length=32)
    intent: str | None = Field(default=None, max_length=32)
    termsAccepted: bool = False
    termsVersion: Literal["2026-08-01"] | None = None


class EmailRequest(APIModel):
    email: EmailStr


class ResetPasswordRequest(APIModel):
    token: str = Field(min_length=20, max_length=500)
    newPassword: str = Field(min_length=1, max_length=256)


class DeleteAccountRequest(APIModel):
    password: str = Field(min_length=1, max_length=256)
    confirmation: str = Field(default="DELETE", max_length=40)


class ProfileUpdateRequest(APIModel):
    fullName: str = Field(min_length=1, max_length=160)


class TermsAcceptanceRequest(APIModel):
    version: Literal["2026-08-01"] = CURRENT_TERMS_VERSION


class AIContentReportRequest(APIModel):
    chatId: str = Field(min_length=1, max_length=120)
    messageId: str | None = Field(default=None, max_length=120)
    category: Literal[
        "hate_or_harassment",
        "sexual_content",
        "violence_or_danger",
        "self_harm",
        "deception_or_fraud",
        "privacy",
        "copyright",
        "other",
    ]
    comment: str = Field(default="", max_length=2000)
    response: str = Field(min_length=1, max_length=30_000)


class RevokeDeviceRequest(APIModel):
    sessionId: str = Field(min_length=1, max_length=100)


class CheckoutRequest(APIModel):
    tier: str = Field(default="professional", max_length=30)


class ProductEventRequest(APIModel):
    eventName: Literal[
        "WorkspaceOpened",
        "StarterIntentReached",
        "ActivationReached",
        "OutcomeFeedbackSubmitted",
        "RecentWorkResumed",
        "PlanCenterViewed",
        "PlanIntentReached",
        "ResponseShared",
    ]
    eventKey: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$",
    )
    source: str | None = Field(default=None, max_length=32)
    plan: Literal["professional", "enterprise"] | None = None


class ChatAckRequest(APIModel):
    chatId: str = Field(min_length=1, max_length=120)
    messageId: str = Field(min_length=1, max_length=120)
    message: str = Field(default="", max_length=100_000)
    fileTypes: list[str] = Field(default_factory=list, max_length=4)


class PresencePreferencesRequest(APIModel):
    enabled: bool = False
    frequency: str = Field(default="balanced", max_length=20)
    quiet_start: int = Field(default=21, ge=0, le=23)
    quiet_end: int = Field(default=8, ge=0, le=23)
    timezone: str = Field(default="America/New_York", max_length=100)
    notifications_enabled: bool = False
    haptics_enabled: bool = True
    allow_followups: bool = True
    allow_reminders: bool = True
    allow_goals: bool = True
    allow_encouragement: bool = False


class PushTokenRequest(APIModel):
    token: str = Field(min_length=20, max_length=5000)
    platform: str = Field(min_length=3, max_length=20)
    installationId: str = Field(min_length=8, max_length=200)


class LifecycleDecisionRequest(APIModel):
    sessionId: str = Field(
        min_length=16,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{15,99}$",
    )
    intent: str | None = Field(default=None, max_length=32)
    activeWork: bool = False
    recoverySurface: bool = False
    currentSurface: str = Field(default="other", max_length=20)


class LifecycleActionRequest(APIModel):
    sessionId: str = Field(
        min_length=16,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{15,99}$",
    )
    decisionId: str = Field(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    )
    action: Literal["shown", "dismissed", "acted", "suppressed"]
    activeWork: bool = False
    recoverySurface: bool = False
    currentSurface: str = Field(default="other", max_length=20)
    suppressionReason: str | None = Field(default=None, max_length=32)
