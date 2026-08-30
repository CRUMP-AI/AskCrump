"""Privacy-safe in-product lifecycle decision and action endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from ..auth_service import authenticate_request
from ..lifecycle_service import record_lifecycle_action, request_lifecycle_decision, session_hash
from ..runtime import db, settings
from ..schemas import LifecycleActionRequest, LifecycleDecisionRequest

logger = logging.getLogger("askcrump.lifecycle")
router = APIRouter(prefix="/api/lifecycle", tags=["lifecycle"])


@router.post("/decision")
async def lifecycle_decision(payload: LifecycleDecisionRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    key = session_hash(auth.session.get("id"), payload.sessionId)
    try:
        decision = await request_lifecycle_decision(
            db,
            user_id=auth.user["id"],
            session_key=key,
            request=request,
            requested_intent=payload.intent,
            active_work=payload.activeWork,
            recovery_surface=payload.recoverySurface,
            current_surface=payload.currentSurface,
        )
    except Exception:
        logger.warning("Lifecycle decision unavailable", exc_info=True)
        decision = {"eligible": False}
    return {"success": True, **decision}


@router.post("/actions")
async def lifecycle_action(payload: LifecycleActionRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    key = session_hash(auth.session.get("id"), payload.sessionId)
    try:
        result = await record_lifecycle_action(
            db,
            user_id=auth.user["id"],
            session_key=key,
            request=request,
            decision_id=payload.decisionId,
            action=payload.action,
            active_work=payload.activeWork,
            recovery_surface=payload.recoverySurface,
            current_surface=payload.currentSurface,
            suppression_reason=payload.suppressionReason,
        )
    except Exception:
        logger.warning("Lifecycle action unavailable action=%s", payload.action, exc_info=True)
        result = {"recorded": False, "suppressionReason": None}
    return {"success": True, **result}
