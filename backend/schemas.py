"""Validated request models for the public API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


LEGACY_TERMS_VERSION = "2026-08-01"
CURRENT_TERMS_VERSION = LEGACY_TERMS_VERSION
CURRENT_POLICY_BUNDLE_ID = "ask-crump-legal-2026-08-01-a44e8c36"
CURRENT_POLICY_BUNDLE_HASH = "a44e8c3637047ccfda406e35310312b4ea068bed73244a753fee5c4f2173a83a"

_POLICY_ATTESTATION_FIELDS = (
    "termsAccepted",
    "privacyNoticeAcknowledged",
    "age17PlusAttested",
    "aiProviderTransmissionAuthorized",
)


def _validate_current_policy_payload(value, *, version_field: str):
    """Require four literal booleans only when the exact new bundle is used.

    The legacy contract remains intentionally unchanged during this transition.
    A legacy version, even with extra truthy fields, never becomes an exact
    current-bundle acceptance.
    """
    if not isinstance(value, dict) or value.get(version_field) != CURRENT_POLICY_BUNDLE_ID:
        return value
    for field in _POLICY_ATTESTATION_FIELDS:
        if field not in value or type(value[field]) is not bool or value[field] is not True:
            raise ValueError(
                "The exact current policy bundle requires four explicit boolean true attestations."
            )
    return value


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
    intent: Literal["document", "image", "presentation", "resume", "video", "projects"] | None = None
    plan: Literal["professional", "enterprise"] | None = None
    termsAccepted: bool = False
    privacyNoticeAcknowledged: bool | None = None
    age17PlusAttested: bool | None = None
    aiProviderTransmissionAuthorized: bool | None = None
    termsVersion: Literal[
        "2026-08-01",
        "ask-crump-legal-2026-08-01-a44e8c36",
    ] | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_policy_contract(cls, value):
        return _validate_current_policy_payload(value, version_field="termsVersion")

    @property
    def accepts_current_policy_bundle(self) -> bool:
        return (
            self.termsVersion == CURRENT_POLICY_BUNDLE_ID
            and self.termsAccepted is True
            and self.privacyNoticeAcknowledged is True
            and self.age17PlusAttested is True
            and self.aiProviderTransmissionAuthorized is True
        )


class EmailRequest(APIModel):
    email: EmailStr


class ResendVerificationRequest(EmailRequest):
    intent: Literal["document", "image", "presentation", "resume", "video", "projects"] | None = None
    plan: Literal["professional", "enterprise"] | None = None


class ResetPasswordRequest(APIModel):
    token: str = Field(min_length=20, max_length=500)
    newPassword: str = Field(min_length=1, max_length=256)


class CompletePasswordSetupRequest(APIModel):
    newPassword: str = Field(min_length=1, max_length=256)


class DeleteAccountRequest(APIModel):
    password: str = Field(min_length=1, max_length=256)
    confirmation: str = Field(default="DELETE", max_length=40)


class ProfileUpdateRequest(APIModel):
    fullName: str = Field(min_length=1, max_length=160)


class TermsAcceptanceRequest(APIModel):
    version: Literal[
        "2026-08-01",
        "ask-crump-legal-2026-08-01-a44e8c36",
    ] = CURRENT_TERMS_VERSION
    termsAccepted: bool | None = None
    privacyNoticeAcknowledged: bool | None = None
    age17PlusAttested: bool | None = None
    aiProviderTransmissionAuthorized: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_policy_contract(cls, value):
        return _validate_current_policy_payload(value, version_field="version")

    @property
    def accepts_current_policy_bundle(self) -> bool:
        return (
            self.version == CURRENT_POLICY_BUNDLE_ID
            and self.termsAccepted is True
            and self.privacyNoticeAcknowledged is True
            and self.age17PlusAttested is True
            and self.aiProviderTransmissionAuthorized is True
        )


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
    attemptId: str | None = Field(
        default=None,
        min_length=16,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{15,99}$",
    )


class ProductEventRequest(APIModel):
    eventName: Literal[
        "WorkspaceOpened",
        "NavigationDestinationSelected",
        "StarterIntentReached",
        "ProjectSaveOfferShown",
        "ProjectSaveIntentReached",
        "ActivationReached",
        "OutcomeFeedbackSubmitted",
        "OutcomeIssueCategorized",
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


class ProjectLimitPlanShownRequest(APIModel):
    decisionId: str = Field(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
    )
