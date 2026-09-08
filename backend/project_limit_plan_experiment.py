"""Dormant, server-authoritative Project-limit value-to-plan experiment."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from fastapi import Request

from .product_analytics import environment_for_request, platform_for_request

logger = logging.getLogger("askcrump.project_limit_plan_experiment")

EXPERIMENT_KEY = "project-limit-plan-copy"
EVENT_NAME = "ProjectLimitPlanMessageShown"
EVENT_KEY = "project-limit-plan-message-shown"
CONTROL = "control"
TREATMENT = "value-specific"
VARIANTS = frozenset({CONTROL, TREATMENT})
CONTROL_DETAIL = (
    "Compare monthly plans below before creating another Project. "
    "Nothing changes until you choose and confirm."
)
TREATMENT_DETAIL = (
    "Your two Free Projects stay available. Professional raises the active Project "
    "limit to 25 for $20/month. You can keep using Free or review the plan before deciding."
)


def _rpc_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def session_hash(auth_session_id: Any) -> str:
    """Return a one-way, content-free device-session key for concurrency control."""
    return hashlib.sha256(str(auth_session_id or "").encode("utf-8")).hexdigest()


async def claim_project_limit_plan_message(
    database: Any,
    *,
    user_id: str,
    auth_session_id: Any,
    request: Request,
    enabled: bool,
) -> dict[str, Any] | None:
    """Claim one eligible exposure; fail closed without affecting Project recovery.

    The RPC owns account checks, durable assignment, prompt priority, multi-device
    concurrency, and 30-day suppression. The Python boundary deliberately returns
    only fixed, allowlisted copy and never accepts copy or customer content.
    """
    if not enabled:
        return None
    try:
        result = _rpc_object(await database.rpc("claim_project_limit_plan_message", {
            "p_user_id": user_id,
            "p_environment": environment_for_request(request),
            "p_client_platform": platform_for_request(request),
            "p_session_hash": session_hash(auth_session_id),
            "p_project_limit_code": "PROJECT_LIMIT_REACHED",
            "p_feature_enabled": True,
        }))
    except Exception:
        logger.warning("Project-limit plan experiment unavailable", exc_info=True)
        return None
    variant = str(result.get("variant") or "").strip().lower()
    decision_id = str(result.get("decisionId") or "").strip()
    if result.get("eligible") is not True or variant not in VARIANTS or not decision_id:
        return None
    return {
        "eligible": True,
        "experiment": EXPERIMENT_KEY,
        "decisionId": decision_id,
        "variant": variant,
    }


async def record_project_limit_plan_message_shown(
    database: Any,
    *,
    user_id: str,
    auth_session_id: Any,
    decision_id: str,
    request: Request,
    enabled: bool,
) -> dict[str, Any] | None:
    """Atomically recheck and record the fixed-field exposure before rendering."""
    if not enabled:
        return None
    try:
        result = _rpc_object(await database.rpc("record_project_limit_plan_message_shown", {
            "p_user_id": user_id,
            "p_decision_id": decision_id,
            "p_environment": environment_for_request(request),
            "p_client_platform": platform_for_request(request),
            "p_session_hash": session_hash(auth_session_id),
            "p_feature_enabled": True,
        }))
    except Exception:
        logger.warning("Project-limit plan exposure unavailable", exc_info=True)
        return None
    variant = str(result.get("variant") or "").strip().lower()
    if result.get("recorded") is not True or variant not in VARIANTS:
        return None
    return {
        "eligible": True,
        "experiment": EXPERIMENT_KEY,
        "eventName": EVENT_NAME,
        "eventKey": EVENT_KEY,
        "decisionId": decision_id,
        "variant": variant,
        "detail": TREATMENT_DETAIL if variant == TREATMENT else CONTROL_DETAIL,
        "source": "recovery_project",
        "plan": "professional",
    }
