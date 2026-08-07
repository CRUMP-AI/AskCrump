"""Message acknowledgement and AI response endpoints."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..ai_service import AIServiceError
from ..auth_service import authenticate_request
from ..checkin_service import mark_check_in_responded
from ..db import eq
from ..runtime import ai, db, intelligence, settings
from ..schemas import ChatAckRequest
from ..security import iso_now, normalize_chat_id
from ..usage_service import UsageLimitError, consume_usage, refund_usage

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/ack")
async def chat_ack(payload: ChatAckRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    chat_id = normalize_chat_id(payload.chatId)
    message_id = normalize_chat_id(payload.messageId)
    now = iso_now()
    activity = ai.activity_for(payload.message, payload.fileTypes)
    await db.upsert(
        "message_receipts",
        {
            "user_id": auth.user["id"],
            "chat_id": chat_id,
            "message_id": message_id,
            "delivered_at": now,
            "seen_at": now,
            "activity": activity,
            "updated_at": now,
        },
        on_conflict="user_id,message_id",
    )
    return {
        "success": True,
        "chatId": chat_id,
        "messageId": message_id,
        "deliveredAt": now,
        "seenAt": now,
        "activity": activity,
    }


@router.post("")
async def chat(request: Request):
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    request_payload = dict(payload) if isinstance(payload, dict) else {}

    raw_chat_id = str(request_payload.get("chatId") or "").strip()
    raw_message_id = str(request_payload.get("messageId") or "").strip()
    chat_id = normalize_chat_id(raw_chat_id) if raw_chat_id else None
    message_id = normalize_chat_id(raw_message_id) if raw_message_id else None
    prepared = None
    verifier_used = False

    if chat_id and message_id:
        claim_result = await db.rpc(
            "claim_chat_job",
            {
                "p_user_id": auth.user["id"],
                "p_chat_id": chat_id,
                "p_message_id": message_id,
            },
        )
        claim = (
            claim_result[0]
            if isinstance(claim_result, list) and claim_result
            else (claim_result or {})
        )
        state = claim.get("job_state") or "claimed"
        if state == "completed" and isinstance(claim.get("response_data"), dict):
            return {"success": True, **claim["response_data"], "cached": True}
        if state == "busy":
            return JSONResponse(
                status_code=409,
                content={
                    "success": False,
                    "error": "Crump is already replying to this message.",
                    "message": "Crump is already replying to this message.",
                    "code": "REPLY_IN_PROGRESS",
                    "shouldRetry": True,
                    "retryAfter": 3,
                },
            )

    try:
        usage = await consume_usage(
            db,
            auth.user,
            settings,
            "messages",
            {"route": "chat", "messageId": message_id},
        )
    except UsageLimitError as exc:
        if message_id:
            await db.update(
                "chat_jobs",
                {
                    "status": "failed",
                    "error_code": "USAGE_LIMIT",
                    "updated_at": iso_now(),
                },
                filters={"user_id": eq(auth.user["id"]), "message_id": eq(message_id)},
            )
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "error": "Daily message limit reached.",
                "code": "USAGE_LIMIT",
                "upgradeRequired": True,
                "usage": {"used": exc.used, "limit": exc.limit, "remaining": 0},
            },
        )

    user_settings = (
        await db.select_one(
            "user_settings",
            filters={"user_id": eq(auth.user["id"])},
        )
        or {}
    )
    request_payload["assistantName"] = user_settings.get("assistant_name") or "Crump"
    request_payload["workMode"] = "work" if user_settings.get("work_mode") else "companion"
    request_payload["user"] = {
        "id": auth.user["id"],
        "email": auth.user.get("email"),
        "name": (
            auth.user.get("full_name")
            or str(auth.user.get("email") or "").split("@")[0]
            or "the user"
        ),
    }

    # 4.4 intelligence layer: retrieve durable context, select a route, and
    # optionally create a concise execution checklist before the primary call.
    prepared = await intelligence.prepare(auth.user["id"], request_payload)
    request_payload = prepared.payload

    await mark_check_in_responded(
        db,
        auth.user["id"],
        str(request_payload.get("replyToCheckInId") or "") or None,
    )

    try:
        result = await ai.chat(request_payload)
    except AIServiceError as exc:
        await refund_usage(db, auth.user["id"], usage.get("eventId"))
        if message_id:
            await db.update(
                "chat_jobs",
                {
                    "status": "failed",
                    "error_code": exc.code,
                    "updated_at": iso_now(),
                },
                filters={"user_id": eq(auth.user["id"]), "message_id": eq(message_id)},
            )
        await intelligence.record_trace(
            user_id=auth.user["id"],
            request_id=request_id,
            chat_id=chat_id,
            message_id=message_id,
            prepared=prepared,
            model=None,
            latency_ms=int((time.perf_counter() - started) * 1000),
            status="error",
            error_code=exc.code,
            verifier_used=False,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "error": exc.message,
                "message": exc.message,
                "code": exc.code,
                "shouldRetry": exc.retryable,
                "retryAfter": exc.retry_after,
            },
        )

    result = dict(result or {})
    result, verifier_used = await intelligence.verify_answer(
        prepared=prepared,
        question=str(request_payload.get("message") or ""),
        result=result,
    )

    # The API, not an individual browser tab, owns persistence of the AI reply.
    # This keeps the shared Supabase conversation authoritative across devices.
    if chat_id and message_id:
        reply_time = iso_now()
        user_message = {
            "id": message_id,
            "role": "user",
            "content": str(request_payload.get("message") or "")[:100_000],
            "timestamp": reply_time,  # DB preserves an existing user's original timestamp.
            "deliveryStatus": "seen",
            "replyStatus": "replied",
            "deliveryUpdatedAt": reply_time,
            "seenAt": reply_time,
        }
        assistant_message = {
            "id": str(uuid4()),
            "role": "assistant",
            "content": str(result.get("response") or "")[:100_000],
            "timestamp": reply_time,
            "origin": "reply",
            "inReplyTo": message_id,
        }
        if result.get("imageUrl"):
            assistant_message["imageUrl"] = result["imageUrl"]
        if result.get("imagePrompt"):
            assistant_message["imagePrompt"] = str(result["imagePrompt"])[:4_000]

        try:
            persisted = await db.rpc(
                "persist_chat_reply",
                {
                    "p_user_id": auth.user["id"],
                    "p_chat_id": chat_id,
                    "p_title": None,
                    "p_user_message": user_message,
                    "p_assistant_message": assistant_message,
                },
            )
            result["assistantMessage"] = assistant_message
            if isinstance(persisted, list) and persisted:
                result["conversationRevision"] = persisted[0].get("resulting_revision")
                result["conversationUpdatedAt"] = persisted[0].get("resulting_updated_at")
        except Exception:
            await refund_usage(db, auth.user["id"], usage.get("eventId"))
            await db.update(
                "chat_jobs",
                {
                    "status": "failed",
                    "error_code": "CHAT_PERSISTENCE",
                    "updated_at": iso_now(),
                },
                filters={"user_id": eq(auth.user["id"]), "message_id": eq(message_id)},
            )
            await intelligence.record_trace(
                user_id=auth.user["id"],
                request_id=request_id,
                chat_id=chat_id,
                message_id=message_id,
                prepared=prepared,
                model=result.get("model"),
                latency_ms=int((time.perf_counter() - started) * 1000),
                status="persistence_error",
                error_code="CHAT_PERSISTENCE",
                verifier_used=verifier_used,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": "Crump generated a reply but could not save the shared conversation.",
                    "message": (
                        "Crump generated a reply but could not save the shared "
                        "conversation. Please retry."
                    ),
                    "code": "CHAT_PERSISTENCE",
                    "shouldRetry": True,
                    "retryAfter": 2,
                },
            )

    memories_saved = await intelligence.learn_explicit(
        user_id=auth.user["id"],
        chat_id=chat_id,
        message_id=message_id,
        message=str(request_payload.get("message") or ""),
        enabled=prepared.auto_learn,
    )

    result["intelligence"] = {
        "mode": prepared.effective_mode,
        "requestedMode": prepared.requested_mode,
        "route": prepared.route,
        "plannerUsed": prepared.planner_used,
        "verifierUsed": verifier_used,
        "memoryCount": prepared.memory_count,
        "memoriesSaved": memories_saved,
        "privateChat": prepared.private_chat,
    }

    if message_id:
        await db.update(
            "chat_jobs",
            {
                "status": "completed",
                "response_data": result,
                "error_code": None,
                "updated_at": iso_now(),
            },
            filters={"user_id": eq(auth.user["id"]), "message_id": eq(message_id)},
        )

    await intelligence.record_trace(
        user_id=auth.user["id"],
        request_id=request_id,
        chat_id=chat_id,
        message_id=message_id,
        prepared=prepared,
        model=result.get("model"),
        latency_ms=int((time.perf_counter() - started) * 1000),
        status="success",
        verifier_used=verifier_used,
    )
    return {"success": True, **result, "dailyUsage": usage}
