"""Server-authoritative, content-free in-product lifecycle decisions."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi import Request

from .product_analytics import environment_for_request, platform_for_request


MESSAGE_KEYS = frozenset({
    "starter-assist",
    "first-value-assist",
    "continuity-assist",
    "artifact-assist",
    "referral-ask",
})
INTENTS = frozenset({"document", "presentation", "resume", "video", "projects"})
ARTIFACT_INTENTS = frozenset({"document", "presentation", "resume"})
SURFACES = frozenset({"workspace-inline", "composer-inline", "post-response-inline"})
CURRENT_SURFACES = frozenset({"ask", "projects", "create", "other"})
SUPPRESSION_REASONS = frozenset({
    "account-ineligible", "channel-disabled", "quiet-hours", "unanswered-checkin",
    "target-completed", "already-shown", "frequency-cap", "session-collision",
    "active-work", "recovery-surface", "no-safe-intent", "recent-activity",
    "user-dismissed",
})
TERMINAL_SUPPRESSIONS = frozenset({
    "account-ineligible", "frequency-cap", "session-collision", "active-work",
    "recovery-surface", "recent-activity",
})


def _safe_intent(value: Any) -> str | None:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in INTENTS else None


def _safe_current_surface(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    return candidate if candidate in CURRENT_SURFACES else "other"


def _rpc_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def session_hash(auth_session_id: Any, client_session_id: str) -> str:
    """Return a one-way, content-free page-session key for database caps."""
    material = f"{str(auth_session_id or '')}:{client_session_id}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def candidate_sequence(
    facts: dict[str, Any],
    requested_intent: str | None = None,
) -> list[dict[str, str | None]]:
    """Order eligible message families without using customer content."""
    if not bool(facts.get("accountEligible")):
        return []

    intent = _safe_intent(requested_intent) or _safe_intent(facts.get("acquisitionIntent"))
    activation = bool(facts.get("hasActivation"))
    aha = bool(facts.get("hasAha"))
    project = bool(facts.get("hasProject"))
    artifact = bool(facts.get("hasArtifact"))
    first_request = bool(facts.get("hasFirstRequest"))
    recent_work = bool(facts.get("hasRecentWork"))
    latest_feedback = str(facts.get("latestFeedback") or "").strip().lower()
    account_age_seconds = max(0, int(facts.get("accountAgeSeconds") or 0))

    candidates: list[dict[str, str | None]] = []
    if activation and not aha:
        candidates.append({
            "messageKey": "continuity-assist",
            "intent": "projects",
            "surface": "post-response-inline",
        })
    if (activation or project) and not artifact and intent in ARTIFACT_INTENTS:
        candidates.append({
            "messageKey": "artifact-assist",
            "intent": intent,
            "surface": "workspace-inline",
        })
    referral_signal = (aha and latest_feedback == "useful") or recent_work
    if referral_signal and latest_feedback != "needs_work":
        candidates.append({
            "messageKey": "referral-ask",
            "intent": None,
            "surface": "post-response-inline",
        })
    if not activation and not first_request:
        candidates.append({
            "messageKey": "starter-assist",
            "intent": intent,
            "surface": "workspace-inline",
        })
    if not activation and account_age_seconds >= 60:
        candidates.append({
            "messageKey": "first-value-assist",
            "intent": None,
            "surface": "composer-inline",
        })
    return candidates


async def request_lifecycle_decision(
    database: Any,
    *,
    user_id: str,
    session_key: str,
    request: Request,
    requested_intent: str | None,
    active_work: bool,
    recovery_surface: bool,
    current_surface: str,
) -> dict[str, Any]:
    environment = environment_for_request(request)
    platform = platform_for_request(request)
    facts = _rpc_object(await database.rpc("lifecycle_prompt_facts", {
        "p_user_id": user_id,
        "p_environment": environment,
    }))
    for candidate in candidate_sequence(facts, requested_intent):
        result = _rpc_object(await database.rpc("claim_lifecycle_prompt", {
            "p_user_id": user_id,
            "p_session_hash": session_key,
            "p_environment": environment,
            "p_client_platform": platform,
            "p_message_key": candidate["messageKey"],
            "p_intent": candidate["intent"],
            "p_surface": candidate["surface"],
            "p_active_work": bool(active_work),
            "p_recovery_surface": bool(recovery_surface),
            "p_current_surface": _safe_current_surface(current_surface),
        }))
        if result.get("eligible") is True:
            return {
                "eligible": True,
                "messageKey": result.get("messageKey"),
                "intent": result.get("intent"),
                "surface": result.get("surface"),
                "decisionId": result.get("decisionId"),
            }
        reason = str(result.get("suppressionReason") or "")
        if result.get("terminal") is True or reason in TERMINAL_SUPPRESSIONS:
            break
    return {"eligible": False}


async def record_lifecycle_action(
    database: Any,
    *,
    user_id: str,
    session_key: str,
    request: Request,
    decision_id: str,
    action: str,
    active_work: bool,
    recovery_surface: bool,
    current_surface: str,
    suppression_reason: str | None = None,
) -> dict[str, Any]:
    safe_reason = str(suppression_reason or "").strip().lower()
    if safe_reason not in SUPPRESSION_REASONS:
        safe_reason = None
    result = _rpc_object(await database.rpc("record_lifecycle_prompt_action", {
        "p_user_id": user_id,
        "p_decision_id": decision_id,
        "p_action": action,
        "p_session_hash": session_key,
        "p_environment": environment_for_request(request),
        "p_client_platform": platform_for_request(request),
        "p_active_work": bool(active_work),
        "p_recovery_surface": bool(recovery_surface),
        "p_current_surface": _safe_current_surface(current_surface),
        "p_suppression_reason": safe_reason,
    }))
    reason = str(result.get("suppressionReason") or "")
    return {
        "recorded": result.get("recorded") is True,
        "suppressionReason": reason if reason in SUPPRESSION_REASONS else None,
    }
