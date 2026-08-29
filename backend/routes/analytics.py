"""Authenticated, allowlisted product milestone intake."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from ..auth_service import authenticate_request
from ..product_analytics import (
    CLIENT_EVENT_NAMES,
    OUTCOME_FEEDBACK_SOURCES,
    PLAN_CENTER_SOURCES,
    RECENT_WORK_SOURCES,
    RESPONSE_SHARE_SOURCES,
    record_product_event,
)
from ..rate_limit import enforce_user_rate_limit
from ..runtime import db, settings
from ..schemas import ProductEventRequest

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("/events")
async def create_product_event(payload: ProductEventRequest, request: Request):
    if payload.eventName not in CLIENT_EVENT_NAMES:
        return {"success": False, "recorded": False}
    if payload.eventName == "OutcomeFeedbackSubmitted" and (
        payload.source not in OUTCOME_FEEDBACK_SOURCES
        or not payload.eventKey.startswith("outcome-feedback:")
    ):
        raise HTTPException(status_code=422, detail="Invalid outcome feedback event.")
    if payload.eventName == "ResponseShared" and (
        payload.source not in RESPONSE_SHARE_SOURCES
        or not payload.eventKey.startswith("response-share:")
    ):
        raise HTTPException(status_code=422, detail="Invalid response share event.")
    if payload.eventName == "RecentWorkResumed" and (
        payload.source not in RECENT_WORK_SOURCES
        or payload.eventKey != "recent-work-resumed"
    ):
        raise HTTPException(status_code=422, detail="Invalid recent work event.")
    if payload.eventName == "PlanCenterViewed" and (
        payload.source not in PLAN_CENTER_SOURCES
        or payload.eventKey != "plan-center-viewed"
        or payload.plan is not None
    ):
        raise HTTPException(status_code=422, detail="Invalid plan center event.")
    event_key = payload.eventKey
    if payload.eventName == "RecentWorkResumed":
        server_day = datetime.now(timezone.utc).date().isoformat()
        event_key = f"recent-work-resumed:{server_day}"
    if payload.eventName == "PlanCenterViewed":
        server_day = datetime.now(timezone.utc).date().isoformat()
        event_key = f"plan-center-viewed:{server_day}"
    auth = await authenticate_request(request, db, settings)
    await enforce_user_rate_limit(
        db,
        user_id=auth.user["id"],
        action="product-event",
        limit=240,
        window_seconds=3600,
    )
    recorded = await record_product_event(
        db,
        user_id=auth.user["id"],
        event_name=payload.eventName,
        event_key=event_key,
        request=request,
        source=payload.source,
        plan=payload.plan,
    )
    return {"success": True, "recorded": recorded}
