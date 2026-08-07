"""User-facing controls for Ask Crump's intelligence layer."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..runtime import db, intelligence, settings
from ..security import normalize_chat_id


router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/status")
async def intelligence_status(request: Request):
    auth = await authenticate_request(request, db, settings)
    status = await intelligence.status(auth.user["id"])
    return {"success": True, **status}


@router.get("/preferences")
async def get_preferences(request: Request):
    auth = await authenticate_request(request, db, settings)
    preferences = await intelligence.get_preferences(auth.user["id"])
    return {
        "success": True,
        "preferences": {
            "intelligenceMode": preferences["intelligence_mode"],
            "memoryEnabled": preferences["memory_enabled"],
            "autoLearn": preferences["auto_learn"],
            "autoTools": preferences["auto_tools"],
            "verificationLevel": preferences["verification_level"],
        },
    }


@router.patch("/preferences")
async def update_preferences(request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid preferences payload."},
        )
    preferences = await intelligence.update_preferences(auth.user["id"], payload)
    return {"success": True, "preferences": preferences}


@router.get("/memories")
async def list_memories(request: Request, limit: int = 50):
    auth = await authenticate_request(request, db, settings)
    memories = await intelligence.list_memories(auth.user["id"], limit=max(1, min(100, limit)))
    return {"success": True, "memories": memories, "count": len(memories)}


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        normalized_id = normalize_chat_id(memory_id)
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "Invalid memory identifier."},
        )
    deleted = await intelligence.delete_memory(auth.user["id"], normalized_id)
    if not deleted:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Memory not found."},
        )
    return {"success": True}


@router.delete("/memories")
async def clear_memories(request: Request):
    auth = await authenticate_request(request, db, settings)
    count = await intelligence.clear_memories(auth.user["id"])
    return {"success": True, "deleted": count}
