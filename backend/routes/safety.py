"""In-app generative-AI content reporting and moderation intake."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from ..auth_service import authenticate_request
from ..db import eq
from ..rate_limit import enforce_user_rate_limit
from ..runtime import db, settings
from ..schemas import AIContentReportRequest
from ..security import iso_now, new_uuid, normalize_chat_id

router = APIRouter(prefix="/api/safety", tags=["safety"])


def _server_context(messages: Any, message_id: str | None) -> tuple[str, str]:
    if not isinstance(messages, list) or not message_id:
        return "", ""
    for index, item in enumerate(messages):
        if not isinstance(item, dict):
            continue
        if str(item.get("id") or "") != message_id or item.get("role") != "assistant":
            continue
        response = str(item.get("content") or "").strip()[:30_000]
        prompt = ""
        for prior in reversed(messages[:index]):
            if isinstance(prior, dict) and prior.get("role") == "user":
                prompt = str(prior.get("content") or "").strip()[:5000]
                break
        return response, prompt
    return "", ""


@router.post("/reports", status_code=201)
async def report_ai_content(payload: AIContentReportRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    await enforce_user_rate_limit(
        db,
        user_id=auth.user["id"],
        action="ai-content-report",
        limit=20,
        window_seconds=86_400,
    )

    chat_id = normalize_chat_id(payload.chatId)
    chat = await db.select_one(
        "user_chats",
        columns="messages",
        filters={"user_id": eq(auth.user["id"]), "chat_id": eq(chat_id)},
    )
    response, prompt = _server_context((chat or {}).get("messages"), payload.messageId)
    # A just-rendered response can be reported before background chat sync reaches
    # the database. Preserve that report while preferring server-owned history.
    response = response or payload.response.strip()[:30_000]

    report_id = new_uuid()
    created_at = iso_now()
    await db.insert("ai_content_reports", {
        "id": report_id,
        "user_id": auth.user["id"],
        "chat_id": chat_id,
        "message_id": (payload.messageId or "").strip(),
        "category": payload.category,
        "comment": payload.comment.strip(),
        "reported_output": response,
        "prompt_context": prompt,
        "client_platform": request.headers.get("x-crump-platform", "web")[:40],
        "status": "new",
        "created_at": created_at,
        "updated_at": created_at,
    })
    return {
        "success": True,
        "reportId": report_id,
        "message": "Thanks. This response was sent for safety review.",
    }
