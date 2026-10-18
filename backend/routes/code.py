"""Authenticated Crump Code task and approval endpoints."""
from __future__ import annotations

import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from uuid import uuid4

from ..auth_service import authenticate_request
from ..code_observability import code_log
from ..code_budget import CodeBudgetError, CodeBudgetPolicy
from ..code_identity import CodeIdentityError, code_identity_token, verify_code_identity
from ..code_service import (
    CodeTaskConflictError,
    CodeTaskError,
    CodeTaskService,
)
from ..feature_service import FeatureAccessError
from ..project_service import ProjectNotFoundError
from ..runtime import code_tasks, db, features, settings

router = APIRouter(tags=["code"])
logger = logging.getLogger("askcrump.code")


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
            "creditQuote": exc.quote,
        },
    )


def _task_error(exc: CodeTaskError) -> JSONResponse:
    return _error(str(exc), exc.code, exc.status_code)


async def _configured(request: Request) -> bool:
    if not settings.code_workspace_enabled or not settings.anthropic_api_key:
        return False
    try:
        await verify_code_identity(code_identity_token(settings, request.headers), settings)
        policy = CodeBudgetPolicy.from_env()
        if policy.model != settings.anthropic_model:
            return False
    except (CodeIdentityError, CodeBudgetError):
        return False
    return True


@router.get("/api/code/activity")
async def list_code_activity(request: Request):
    auth = await authenticate_request(request, db, settings)
    activity = await code_tasks.list_activity(user_id=auth.user["id"])
    return {"success": True, "activity": activity}


@router.get("/api/projects/{project_id}/code/tasks")
async def list_code_tasks(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    try:
        items = await code_tasks.list(user_id=auth.user["id"], project_id=project_id)
        return {
            "success": True,
            "configured": await _configured(request),
            "tasks": [CodeTaskService.public_task(item) for item in items],
        }
    except ProjectNotFoundError:
        return _error("Project not found.", "PROJECT_NOT_FOUND", 404)


@router.post("/api/projects/{project_id}/code/tasks")
async def create_code_task(project_id: str, request: Request):
    auth = await authenticate_request(request, db, settings)
    if not await _configured(request):
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
    if not await _configured(request):
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

    dispatch_token = str(uuid4())
    recovered = False
    try:
        claimed = await code_tasks.dispatch_authorized(
            task, user=auth.user, features=features,
            confirmation=payload.get("creditConfirmation"),
            dispatch_token=dispatch_token, budget_policy=CodeBudgetPolicy.from_env(),
        )
    except FeatureAccessError as exc:
        return _feature_error(exc)
    except CodeBudgetError as exc:
        return _error(str(exc), exc.code, exc.status_code)
    except CodeTaskError as exc:
        code_log(
            logger,
            logging.WARNING,
            "dispatch_rejected",
            failure_code=exc.code,
            outcome="not_dispatched",
        )
        return _task_error(exc)
    except Exception as exc:
        current = await code_tasks.get(user_id=auth.user["id"], task_id=task_id)
        if current.get("usage_receipt") and current.get("payment_source") and current.get("dispatch_token"):
            claimed = current
            recovered = True
        else:
            code_log(
                logger,
                logging.ERROR,
                "dispatch_rejected",
                error_type=type(exc).__name__,
                outcome="unconfirmed",
            )
            raise

    code_log(
        logger,
        logging.INFO,
        "dispatch_recovered" if recovered else "dispatch_accepted",
        mode=str(claimed.get("mode") or ""),
        status=str(claimed.get("status") or ""),
        payment_source=str(claimed.get("payment_source") or ""),
        credits_spent=int(claimed.get("credits_spent") or 0),
    )
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
        code_log(
            logger,
            logging.INFO,
            "cancellation_recorded",
            status=str(cancelled.get("status") or ""),
            refund_pending=cancelled.get("payment_source") == "refund_pending",
        )
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
