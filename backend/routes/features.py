"""Feature availability, plan requirements, and cost guard metadata."""
from __future__ import annotations

from fastapi import APIRouter, Request

from ..auth_service import authenticate_request
from ..runtime import db, features, settings, video

router = APIRouter(prefix="/api/features", tags=["features"])


@router.get("")
async def feature_status(request: Request):
    auth = await authenticate_request(request, db, settings)
    status = await features.status(auth.user)
    configured = {
        "research": bool((settings.brave_api_key and settings.web_search_enabled) or settings.openweather_api_key),
        "image": bool(settings.openai_api_key and settings.image_generation_enabled),
        "image_edit": bool(settings.openai_api_key and settings.image_generation_enabled),
        "video": video.enabled,
        "video_hd": video.enabled,
        "manuscript_draft": bool(settings.anthropic_api_key and settings.manuscript_generation_enabled),
        "manuscript_blueprint": bool(settings.anthropic_api_key and settings.manuscript_generation_enabled),
        "kdp_export": settings.manuscript_generation_enabled,
    }
    for code, item in status["features"].items():
        item["configured"] = configured.get(code, True)
    return {"success": True, **status}
