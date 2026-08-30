"""Privacy-minimized, server-authoritative product milestone recording."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from fastapi import Request

logger = logging.getLogger("askcrump.product_analytics")

EVENT_NAMES = frozenset({
    "AccountCreated",
    "OnboardingCompleted",
    "WorkspaceOpened",
    "StarterIntentReached",
    "ActivationReached",
    "AhaReached",
    "OutcomeFeedbackSubmitted",
    "RecentWorkResumed",
    "PlanCenterViewed",
    "PlanIntentReached",
    "ResponseShared",
    "ArtifactRequested",
    "ArtifactPackaged",
    "ArtifactPackagingFailed",
    "ArtifactDownloaded",
    "SubscriptionCheckoutOpened",
    "SubscriptionCheckoutCompleted",
    "CreditCheckoutOpened",
    "CreditCheckoutCompleted",
    "BillingPortalOpened",
    "SubscriptionStatusChanged",
})
CLIENT_EVENT_NAMES = frozenset({
    "WorkspaceOpened",
    "StarterIntentReached",
    "ActivationReached",
    "OutcomeFeedbackSubmitted",
    "RecentWorkResumed",
    "PlanCenterViewed",
    "PlanIntentReached",
    "ResponseShared",
})
OUTCOME_FEEDBACK_SOURCES = frozenset({"useful", "needs_work"})
RESPONSE_SHARE_SOURCES = frozenset({
    "native_share",
    "clipboard",
    "useful_prompt_native",
    "useful_prompt_clipboard",
})
RECENT_WORK_SOURCES = frozenset({"launchpad", "project"})
PLAN_CENTER_SOURCES = frozenset({
    "settings",
    "plan_intent",
    "upgrade_prompt",
    "recovery_credits",
    "recovery_subscription",
    "recovery_feature",
    "recovery_project",
    "recovery_usage",
})
PAID_PLANS = frozenset({"professional", "enterprise"})
ARTIFACT_TYPES = frozenset({
    "document", "image", "video", "manuscript", "code",
    "spreadsheet", "presentation", "pdf", "project", "file",
})
SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
SAFE_SOURCE_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
ATTRIBUTION_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
ATTRIBUTION_ACQUISITIONS = frozenset({
    "direct", "instagram", "facebook", "facebook-pinned", "linkedin",
    "tiktok", "youtube", "x", "referral", "organic", "organic-search",
    "clevercrump", "founder-outreach",
})
ATTRIBUTION_PLACEMENTS = frozenset({
    "response-share", "profile-link", "workflow-guide", "organic-social",
    "creator-cohort",
})
ATTRIBUTION_INTENTS = frozenset({
    "document", "presentation", "resume", "video", "projects",
})
ATTRIBUTION_CAMPAIGNS = {
    "presentation-proof-current": {
        "intent": "presentation",
        "acquisitions": frozenset({"facebook", "instagram"}),
        "placements": frozenset({"profile-link", "organic-social"}),
        "creatives": frozenset({"fb-static", "ig-feed", "ig-story"}),
    },
    "real-product-continuity": {
        "intent": "projects",
        "acquisitions": frozenset({"facebook", "instagram"}),
        "placements": frozenset({"profile-link", "organic-social"}),
        "creatives": frozenset({"continuity-feed", "continuity-story"}),
    },
    "rough-idea-launch-plan": {
        "intent": "projects",
        "acquisitions": frozenset({"organic-search"}),
        "placements": frozenset({"workflow-guide"}),
        "creatives": frozenset({"search-article"}),
    },
    "project-memory-boundaries": {
        "intent": "projects",
        "acquisitions": frozenset({"organic-search", "facebook", "instagram"}),
        "placements": frozenset({"workflow-guide", "organic-social"}),
        "creatives": frozenset({
            "search-article", "project-memory-feed", "project-memory-story",
        }),
    },
    "editable-powerpoint-review": {
        "intent": "presentation",
        "acquisitions": frozenset({"organic-search", "facebook", "instagram"}),
        "placements": frozenset({"workflow-guide", "organic-social"}),
        "creatives": frozenset({
            "search-article", "presentation-feed", "presentation-story",
        }),
    },
    "creator-cohort-01": {
        "intent": "projects",
        "acquisitions": frozenset({"founder-outreach"}),
        "placements": frozenset({"creator-cohort"}),
        "creatives": frozenset({"personal-invite"}),
    },
}


def environment_for_request(request: Request | None) -> str:
    request_url = getattr(request, "url", None) if request else None
    host = str(getattr(request_url, "hostname", "") or "").lower()
    if host == "askcrump.com" or host.endswith(".askcrump.com"):
        return "production"
    if host.endswith(".vercel.app"):
        return "preview"
    return "development"


def platform_for_request(request: Request | None) -> str:
    if not request:
        return "web"
    platform = str(request.headers.get("x-crump-platform") or "").strip().lower()
    if platform in {"ios", "android"}:
        return platform
    return "web"


def normalize_event_key(value: str) -> str:
    candidate = str(value or "").strip()
    if SAFE_KEY_RE.fullmatch(candidate):
        return candidate
    return f"sha256:{hashlib.sha256(candidate.encode('utf-8')).hexdigest()}"


def normalize_source(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip().lower()
    return candidate if SAFE_SOURCE_RE.fullmatch(candidate) else "direct"


def _attribution_token(value: str | None) -> str | None:
    candidate = str(value or "").strip().lower()
    return candidate if ATTRIBUTION_TOKEN_RE.fullmatch(candidate) else None


def normalize_attribution(
    *,
    acquisition: str | None,
    placement: str | None,
    campaign: str | None,
    creative: str | None,
    intent: str | None,
) -> dict[str, str | None]:
    """Return only the registered, content-free first-touch tuple."""
    safe_acquisition = _attribution_token(acquisition)
    if safe_acquisition not in ATTRIBUTION_ACQUISITIONS:
        safe_acquisition = None
    safe_placement = _attribution_token(placement)
    if safe_placement not in ATTRIBUTION_PLACEMENTS:
        safe_placement = None
    safe_intent = _attribution_token(intent)
    if safe_intent not in ATTRIBUTION_INTENTS:
        safe_intent = None

    safe_campaign = _attribution_token(campaign)
    specification = ATTRIBUTION_CAMPAIGNS.get(safe_campaign or "")
    if not specification or (
        safe_acquisition not in specification["acquisitions"]
        or safe_placement not in specification["placements"]
        or safe_intent != specification["intent"]
    ):
        safe_campaign = None
        specification = None

    safe_creative = _attribution_token(creative)
    if not specification or safe_creative not in specification["creatives"]:
        safe_creative = None

    return {
        "acquisition": safe_acquisition,
        "placement": safe_placement,
        "campaign": safe_campaign,
        "creative": safe_creative,
        "intent": safe_intent,
    }


def normalize_plan(value: str | None) -> str | None:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in PAID_PLANS else None


def artifact_type_for_format(value: Any) -> str:
    """Reduce a file format to an allowlisted category without retaining its name."""
    format_name = str(value or "").strip().lower().lstrip(".")
    if format_name == "pdf":
        return "pdf"
    if format_name in {"xlsx", "csv", "tsv"}:
        return "spreadsheet"
    if format_name in {"pptx", "ppt"}:
        return "presentation"
    if format_name in {"py", "js", "ts", "tsx", "jsx", "html", "css"}:
        return "code"
    if format_name in {"docx", "rtf", "txt", "md", "epub"}:
        return "document"
    return "file"


def artifact_type_for_file(row: dict[str, Any]) -> str:
    """Classify a private file row while returning no filename or other content."""
    if str(row.get("kind") or "").strip().lower() == "manuscript_export":
        return "manuscript"
    metadata = row.get("metadata")
    if isinstance(metadata, dict) and metadata.get("format"):
        return artifact_type_for_format(metadata["format"])
    mime_type = str(row.get("mime_type") or "").strip().lower()
    mime_formats = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
        "application/vnd.ms-powerpoint": "ppt",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "text/csv": "csv",
        "text/tab-separated-values": "tsv",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "application/rtf": "rtf",
        "application/epub+zip": "epub",
        "text/markdown": "md",
        "text/plain": "txt",
    }
    if mime_type in mime_formats:
        return artifact_type_for_format(mime_formats[mime_type])
    file_name = str(row.get("file_name") or "")
    extension = file_name.rsplit(".", 1)[-1] if "." in file_name else ""
    return artifact_type_for_format(extension)


def artifact_type_for_result(result: dict[str, Any]) -> str | None:
    if result.get("manuscriptWorkspace"):
        return "manuscript"
    if result.get("imageFile") or result.get("imageUrl"):
        return "image"
    artifact = result.get("artifact")
    if not isinstance(artifact, dict):
        return None
    return artifact_type_for_format(artifact.get("format") or artifact.get("extension"))


async def record_product_event(
    database: Any,
    *,
    user_id: str,
    event_name: str,
    event_key: str,
    request: Request | None = None,
    source: str | None = None,
    plan: str | None = None,
    artifact_type: str | None = None,
) -> bool:
    """Record one allowlisted event; analytics must never break the product flow."""
    if event_name not in EVENT_NAMES:
        return False
    normalized_artifact = str(artifact_type or "").lower() or None
    if normalized_artifact not in ARTIFACT_TYPES:
        normalized_artifact = None
    try:
        result = await database.rpc("record_product_event", {
            "p_user_id": user_id,
            "p_event_name": event_name,
            "p_event_key": normalize_event_key(event_key),
            "p_environment": environment_for_request(request),
            "p_client_platform": platform_for_request(request),
            "p_source": normalize_source(source),
            "p_plan": normalize_plan(plan),
            "p_artifact_type": normalized_artifact,
        })
        if isinstance(result, list):
            return bool(result[0]) if result else False
        return bool(result)
    except Exception:
        logger.warning("Product analytics write failed event=%s", event_name, exc_info=True)
        return False


async def record_account_created_event(
    database: Any,
    *,
    user_id: str,
    request: Request | None = None,
    acquisition: str | None = None,
    placement: str | None = None,
    campaign: str | None = None,
    creative: str | None = None,
    intent: str | None = None,
) -> bool:
    """Record one server-authoritative, content-free first-touch attribution row."""
    attribution = normalize_attribution(
        acquisition=acquisition,
        placement=placement,
        campaign=campaign,
        creative=creative,
        intent=intent,
    )
    try:
        result = await database.rpc("record_account_created_event", {
            "p_user_id": user_id,
            "p_event_key": "account-created",
            "p_environment": environment_for_request(request),
            "p_client_platform": platform_for_request(request),
            "p_acquisition": attribution["acquisition"],
            "p_placement": attribution["placement"],
            "p_campaign": attribution["campaign"],
            "p_creative": attribution["creative"],
            "p_intent": attribution["intent"],
        })
        if isinstance(result, list):
            return bool(result[0]) if result else False
        return bool(result)
    except Exception:
        logger.warning("Account attribution write failed", exc_info=True)
        return False
