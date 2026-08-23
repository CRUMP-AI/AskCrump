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
    "ActivationReached",
    "AhaReached",
    "PlanIntentReached",
    "ResponseShared",
    "SubscriptionCheckoutOpened",
    "SubscriptionCheckoutCompleted",
    "BillingPortalOpened",
    "SubscriptionStatusChanged",
})
CLIENT_EVENT_NAMES = frozenset({
    "WorkspaceOpened",
    "ActivationReached",
    "PlanIntentReached",
    "ResponseShared",
})
PAID_PLANS = frozenset({"professional", "enterprise"})
ARTIFACT_TYPES = frozenset({
    "document", "image", "video", "manuscript", "code",
    "spreadsheet", "presentation", "pdf", "project", "file",
})
SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
SAFE_SOURCE_RE = re.compile(r"^[a-z0-9_-]{1,32}$")


def environment_for_request(request: Request | None) -> str:
    host = str(request.url.hostname or "").lower() if request else ""
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


def normalize_plan(value: str | None) -> str | None:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in PAID_PLANS else None


def artifact_type_for_result(result: dict[str, Any]) -> str | None:
    if result.get("manuscriptWorkspace"):
        return "manuscript"
    if result.get("imageFile") or result.get("imageUrl"):
        return "image"
    artifact = result.get("artifact")
    if not isinstance(artifact, dict):
        return None
    format_name = str(artifact.get("format") or artifact.get("extension") or "").lower().lstrip(".")
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
