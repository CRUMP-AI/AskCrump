"""Authenticated, allowlisted product milestone intake."""

from fastapi import APIRouter, HTTPException, Request

from ..auth_service import authenticate_request
from ..product_analytics import (
    CLIENT_EVENT_NAMES,
    OUTCOME_FEEDBACK_SOURCES,
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
        event_key=payload.eventKey,
        request=request,
        source=payload.source,
        plan=payload.plan,
    )
    return {"success": True, "recorded": recorded}
