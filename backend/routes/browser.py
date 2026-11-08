"""Fail-closed public boundary for the Ask Crump Browser workspace.

The complete provider-neutral runtime is integrated separately. Until its
source release, schema, isolated provider, cleanup, and device gates all pass,
this route exposes only an authenticated content-free availability result.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..config import browser_workspace_environment_released
from ..runtime import db, settings


router = APIRouter(tags=["browser"])
browser_workspace_service = None


def _runtime_ready() -> bool:
    """Require an atomically composed runtime, never only a feature switch."""

    service = browser_workspace_service
    return bool(service is not None and getattr(service, "ready", False) is True)


def _unreleased() -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={
            "success": False,
            "error": "Browser workspace is not released.",
            "code": "BROWSER_NOT_RELEASED",
        },
        headers={"Cache-Control": "private, no-store"},
    )


async def _account(request: Request):
    return await authenticate_request(
        request,
        db,
        settings,
        require_account=True,
        require_expected_owner_header=True,
    )


@router.get("/api/browser/status")
async def browser_status(request: Request):
    await _account(request)
    return JSONResponse(
        content={
            "success": True,
            "released": (
                browser_workspace_environment_released()
                and _runtime_ready()
            ),
        },
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/api/browser/tasks")
async def list_browser_tasks(request: Request):
    await _account(request)
    return _unreleased()


@router.get("/api/browser/requests/{request_id}")
async def read_browser_request(request_id: str, request: Request):
    del request_id
    await _account(request)
    return _unreleased()


@router.post("/api/browser/tasks")
async def create_browser_task(request: Request):
    await _account(request)
    return _unreleased()


@router.post("/api/browser/tasks/{task_id}/{command}")
async def control_browser_task(task_id: str, command: str, request: Request):
    del task_id, command
    await _account(request)
    return _unreleased()


@router.post("/api/browser/tasks/{task_id}/approvals/{approval_id}")
async def decide_browser_approval(task_id: str, approval_id: str, request: Request):
    del task_id, approval_id
    await _account(request)
    return _unreleased()
