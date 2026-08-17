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
    engines = video.engine_status
    configured = {
        "research": bool((settings.brave_api_key and settings.web_search_enabled) or settings.openweather_api_key),
        "image": bool(settings.openai_api_key and settings.image_generation_enabled),
        "image_edit": bool(settings.openai_api_key and settings.image_generation_enabled),
        "video": bool(engines["quick"]["configured"]),
        "video_hd": bool(engines["quick"]["configured"]),
        "video_extendable": bool(engines["extendable"]["configured"]),
        "video_continue": bool(engines["extendable"]["configured"]),
        "video_cinematic_5": bool(engines["cinematic"]["configured"]),
        "video_cinematic_10": bool(engines["cinematic"]["configured"]),
        "manuscript_draft": bool(settings.anthropic_api_key and settings.manuscript_generation_enabled),
        "manuscript_blueprint": bool(settings.anthropic_api_key and settings.manuscript_generation_enabled),
        "kdp_export": settings.manuscript_generation_enabled,
    }
    for code, item in status["features"].items():
        item["configured"] = configured.get(code, True)
    status["providers"] = {
        "image": {
            "configured": configured["image"],
            "provider": "openai",
            "model": settings.openai_image_model,
        },
        "video": {
            "configured": video.enabled,
            "provider": "multi-engine",
            "engines": engines,
        },
        "manuscript": {
            "configured": configured["manuscript_draft"],
            "provider": "anthropic",
            "model": settings.anthropic_model,
        },
    }
    status["videoEngines"] = engines
    return {"success": True, **status}
