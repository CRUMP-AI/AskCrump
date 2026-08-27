"""Explicit, authenticated premium voice playback."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ..auth_service import authenticate_request
from ..feature_service import FeatureAccessError
from ..rate_limit import enforce_user_rate_limit
from ..runtime import db, features, settings, voice
from ..voice_service import VoiceServiceError

router = APIRouter(prefix="/api/voice", tags=["voice"])


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
        },
        headers={"Cache-Control": "private, no-store"},
    )


def _voice_error(exc: VoiceServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": exc.message, "code": exc.code},
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/synthesize")
async def synthesize(request: Request):
    """Create ephemeral audio only after a signed-in user explicitly requests it."""
    auth = await authenticate_request(request, db, settings)
    if not voice.configured:
        return _voice_error(VoiceServiceError(
            "Premium voice is not configured yet.", 503, "VOICE_NOT_CONFIGURED"
        ))
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    try:
        text = voice.prepare(payload.get("text"))
    except VoiceServiceError as exc:
        return _voice_error(exc)
    await enforce_user_rate_limit(
        db,
        user_id=auth.user["id"],
        action="premium-voice",
        limit=30,
        window_seconds=3600,
    )
    try:
        receipt = await features.consume(
            auth.user,
            "premium_voice",
            {"characters": len(text), "model": settings.elevenlabs_model_id},
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)
    try:
        audio = await voice.synthesize_prepared(text)
    except VoiceServiceError as exc:
        await features.refund(auth.user["id"], receipt)
        return _voice_error(exc)
    except Exception:
        await features.refund(auth.user["id"], receipt)
        return _voice_error(VoiceServiceError(
            "Premium voice is temporarily unavailable.",
            502,
            "VOICE_PROVIDER_UNAVAILABLE",
        ))
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'inline; filename="ask-crump-voice.mp3"',
            "X-Content-Type-Options": "nosniff",
            "X-Crump-Payment-Source": str(receipt.get("paymentSource") or ""),
            "X-Crump-Credits-Spent": str(int(receipt.get("creditsSpent") or 0)),
        },
    )
