"""Authenticated, allowlisted product milestone intake."""

from fastapi import APIRouter, Request

from ..auth_service import authenticate_request
from ..product_analytics import CLIENT_EVENT_NAMES, record_product_event
from ..rate_limit import enforce_user_rate_limit
from ..runtime import db, settings
from ..schemas import ProductEventRequest

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("/events")
async def create_product_event(payload: ProductEventRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    if payload.eventName not in CLIENT_EVENT_NAMES:
        return {"success": False, "recorded": False}
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
