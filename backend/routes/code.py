"""Authenticated Crump Code task and approval endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from uuid import uuid4

from ..auth_service import authenticate_request
from ..code_service import (
    CodeTaskConflictError,
    CodeTaskError,
    CodeTaskService,
)
from ..feature_service import FeatureAccessError
from ..project_service import ProjectNotFoundError
from ..runtime import code_tasks, db, features, settings

router = APIRouter(tags=["code"])


def _error(message: str, code: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": message, "code": code},
    )


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
    )


def _task_error(exc: CodeTaskError) -> JSONResponse:
    return _error(str(exc), exc.code, exc.status_code)


def _configured(request: Request) -> bool:
    oidc_token = str(
        request.headers.get("x-vercel-oidc-token") or settings.vercel_oidc_token or ""
    ).strip()
    return bool(
        settings.code_workspace_enabled
        and settings.anthropic_api_key
        and oidc_token
    )


@router.get("/api/projects/{project_id}/code/tasks")
async def list_code_tasks(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        items = await code_tasks.list(user_id=auth.user["id"], project_id=project_id)
        return {
            "success": True,
            "configured": _configured(request),
            "tasks": [CodeTaskService.public_task(item) for item in items],
        }
    except ProjectNotFoundError:
        return _error("Project not found.", "PROJECT_NOT_FOUND", 404)


@router.post("/api/projects/{project_id}/code/tasks")
async def create_code_task(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    if not _configured(request):
        return _error("Crump Code is not enabled yet.", "CODE_WORKSPACE_NOT_CONFIGURED", 503)
    try:
        await features.require_tier(auth.user, "code_workspace")
    except FeatureAccessError as exc:
        return _feature_error(exc)
    payload = await request.json()
    if not isinstance(payload, dict):
        return _error("Invalid Crump Code request.", "INVALID_CODE_TASK", 400)
    try:
        task = await code_tasks.create(
            user_id=auth.user["id"],
            project_id=project_id,
            objective=str(payload.get("objective") or ""),
            mode=str(payload.get("mode") or "plan"),
            repo_url=str(payload.get("repositoryUrl") or ""),
            revision=str(payload.get("revision") or "").strip() or None,
            max_duration_seconds=min(
                int(payload.get("maxDurationSeconds") or settings.code_max_duration_seconds),
                settings.code_max_duration_seconds,
            ),
        )
        return {"success": True, "task": CodeTaskService.public_task(task)}
    except ProjectNotFoundError:
        return _error("Project not found.", "PROJECT_NOT_FOUND", 404)
    except (TypeError, ValueError) as exc:
        return _error(str(exc), "INVALID_CODE_TASK", 400)


@router.get("/api/code/tasks/{task_id}")
async def get_code_task(task_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        task = await code_tasks.get(
            user_id=auth.user["id"], task_id=task_id, include_history=True
        )
        return {"success": True, "task": CodeTaskService.public_task(task)}
    except CodeTaskError as exc:
        return _task_error(exc)


@router.post("/api/code/tasks/{task_id}/run")
async def run_code_task(task_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    if not _configured(request):
        return _error("Crump Code is not enabled yet.", "CODE_WORKSPACE_NOT_CONFIGURED", 503)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict) or payload.get("confirmed") is not True:
        return _error(
            "Review the task and confirm the isolated run before it starts.",
            "RUN_CONFIRMATION_REQUIRED",
            400,
        )
    try:
        task = await code_tasks.get(user_id=auth.user["id"], task_id=task_id)
        task = await code_tasks.ensure_not_expired(task)
        await features.require_tier(auth.user, "code_workspace")
    except FeatureAccessError as exc:
        return _feature_error(exc)
    except CodeTaskError as exc:
        return _task_error(exc)

    try:
        receipt = await features.consume(
            auth.user,
            "code_workspace",
            {"route": "code_task", "mode": task.get("mode")},
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)

    dispatch_token = str(uuid4())
    try:
        claimed = await code_tasks.dispatch(
            task,
            receipt=receipt,
            dispatch_token=dispatch_token,
        )
    except CodeTaskError as exc:
        await features.refund(auth.user["id"], receipt)
        return _task_error(exc)
    except Exception:
        current = await code_tasks.get(user_id=auth.user["id"], task_id=task_id)
        if str(current.get("dispatch_token") or "") == dispatch_token:
            claimed = current
        else:
            await features.refund(auth.user["id"], receipt)
            raise

    return JSONResponse(
        status_code=202,
        content={
            "success": True,
            "accepted": True,
            "task": CodeTaskService.public_task(claimed),
        },
    )


@router.post("/api/code/tasks/{task_id}/cancel")
async def cancel_code_task(task_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        task = await code_tasks.get(user_id=auth.user["id"], task_id=task_id)
        cancelled = await code_tasks.cancel(task)
        return {"success": True, "task": CodeTaskService.public_task(cancelled)}
    except CodeTaskError as exc:
        return _task_error(exc)


@router.post("/api/code/tasks/{task_id}/approvals/{approval_id}")
async def decide_code_approval(task_id: str, approval_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    if not isinstance(payload, dict):
        return _error("Invalid approval decision.", "INVALID_APPROVAL", 400)
    try:
        task = await code_tasks.get(user_id=auth.user["id"], task_id=task_id)
        if task.get("status") != "awaiting_approval":
            raise CodeTaskConflictError("This task is not awaiting approval.")
        decision = str(payload.get("decision") or "")
        approval = await code_tasks.decide_approval(
            task=task, approval_id=approval_id, decision=decision
        )
        if approval.get("status") == "approved":
            task = await code_tasks.transition(
                task,
                "queued",
                event_type="task.requeued",
                event_payload={"status": "queued"},
            )
        else:
            task = await code_tasks.cancel(task)
        return {
            "success": True,
            "approval": approval,
            "task": CodeTaskService.public_task(task),
        }
    except (TypeError, ValueError) as exc:
        return _error(str(exc), "INVALID_APPROVAL", 400)
    except CodeTaskError as exc:
        return _task_error(exc)
