"""Feature availability, plan requirements, and cost guard metadata."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..feature_service import FeatureAccessError
from ..runtime import db, features, settings, video, voice

router = APIRouter(prefix="/api/features", tags=["features"])


def _feature_error(exc: FeatureAccessError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "code": exc.code,
            "upgradeRequired": exc.code == "SUBSCRIPTION_REQUIRED",
            "requiredTier": exc.required_tier,
            "creditsRequired": exc.credit_cost,
            "creditBalance": exc.credit_balance,
            "creditQuote": exc.quote,
        },
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("")
async def feature_status(request: Request):
    auth = await authenticate_request(request, db, settings)
    status = await features.status(auth.user)
    engines = video.engine_status
    sandbox_configured = bool(
        request.headers.get("x-vercel-oidc-token") or settings.vercel_oidc_token
    )
    configured = {
        "think_longer": bool(settings.anthropic_api_key),
        "research": bool((settings.brave_api_key and settings.web_search_enabled) or settings.openweather_api_key),
        "image": bool(settings.openai_api_key and settings.image_generation_enabled),
        "image_edit": bool(settings.openai_api_key and settings.image_generation_enabled),
        "visual_analysis": bool(settings.openai_api_key),
        "video": bool(engines["quick"]["configured"]),
        "video_hd": bool(engines["quick"]["configured"]),
        "video_extendable": bool(engines["extendable"]["configured"]),
        "video_continue": bool(engines["extendable"]["configured"]),
        "video_cinematic_5": bool(engines["cinematic"]["configured"]),
        "video_cinematic_10": bool(engines["cinematic"]["configured"]),
        "manuscript_draft": bool(settings.anthropic_api_key and settings.manuscript_generation_enabled),
        "manuscript_blueprint": bool(settings.anthropic_api_key and settings.manuscript_generation_enabled),
        "kdp_export": settings.manuscript_generation_enabled,
        "code_workspace": bool(
            settings.code_workspace_enabled
            and settings.anthropic_api_key
            and sandbox_configured
        ),
        "premium_voice": voice.configured,
    }
    for code, item in status["features"].items():
        item["configured"] = configured.get(code, True)
    status["providers"] = {
        "chat": {
            "free": {
                "configured": bool(
                    settings.ai_gateway_enabled
                    and (settings.ai_gateway_api_key or settings.vercel_oidc_token)
                ),
                "provider": "vercel-ai-gateway",
                "model": settings.ai_gateway_free_model,
            },
            "paid": {
                "configured": bool(settings.anthropic_api_key),
                "provider": "anthropic",
                "model": settings.anthropic_model,
            },
        },
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
        "code": {
            "configured": configured["code_workspace"],
            "provider": "anthropic+vercel-sandbox",
            "model": settings.anthropic_model,
            "networkPolicy": "deny_all",
            "maxDurationSeconds": settings.code_max_duration_seconds,
        },
        "voice": {
            "configured": configured["premium_voice"],
            "provider": "elevenlabs",
            "model": settings.elevenlabs_model_id,
            "maxCharacters": settings.elevenlabs_max_chars,
            "storage": "ephemeral",
        },
    }
    status["videoEngines"] = engines
    return {"success": True, **status}


@router.post("/quote")
async def feature_quote(request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    try:
        raw = payload.get("components")
        if isinstance(raw, list):
            components = {
                str(item.get("code") or ""): int(item.get("quantity") or 1)
                for item in raw
                if isinstance(item, dict)
            }
        else:
            components = {
                str(payload.get("code") or ""): int(payload.get("quantity") or 1)
            }
        quote = await features.quote(
            auth.user,
            components,
            scope={"route": "feature_quote", "components": components},
        )
        quote.pop("token", None)
        quote.pop("actionKey", None)
        return {"success": True, "quote": quote}
    except (TypeError, ValueError):
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "Invalid quote request.",
                "code": "INVALID_CREDIT_QUOTE",
            },
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)
