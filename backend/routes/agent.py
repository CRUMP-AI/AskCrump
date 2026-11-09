"""Agent capability registry, run ledger, and approval endpoints.

The client fetches the registry at session start and renders task,
approval, artifact, connection, and brief cards from it. Runs are
created only for registered capabilities — unknown ids fail closed
with ``CAPABILITY_NOT_FOUND`` — and every run, step, and approval
decision is recorded in the durable ledger behind these routes.
Queued runs execute through the agent executor, and the Today brief
is composed from the same ledger and connection state.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..agent_executor import AgentExecutor, build_today_brief
from ..agent_registry import get_capability, public_catalog
from ..agent_run_service import AgentRunError
from ..auth_service import authenticate_request
from ..google_connector import GoogleConnector
from ..google_vault import GoogleVault
from ..runtime import agent_runs, db, settings

router = APIRouter(prefix='/api/agent', tags=['agent'])


def _google_connector() -> GoogleConnector:
    return GoogleConnector(settings=settings, db=db, vault=GoogleVault())


def _executor() -> AgentExecutor:
    return AgentExecutor(agent_runs, google_connector=_google_connector())


def _error(exc: AgentRunError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={'success': False, 'error': exc.message, 'code': exc.code},
        headers={'Cache-Control': 'private, no-store'},
    )


def _private(payload: dict) -> JSONResponse:
    return JSONResponse(
        content=payload,
        headers={'Cache-Control': 'private, no-store'},
    )


async def _auth(request: Request):
    return await authenticate_request(
        request,
        db,
        settings,
        require_account=True,
        require_expected_owner_header=True,
    )


@router.get('/capabilities')
async def list_capabilities(request: Request):
    await _auth(request)
    return _private({'success': True, **public_catalog()})


@router.get('/capabilities/{capability_id}')
async def describe_capability(capability_id: str, request: Request):
    await _auth(request)
    item = get_capability(capability_id)
    if item is None:
        return _error(
            AgentRunError('That capability is not available.', 404, 'CAPABILITY_NOT_FOUND')
        )
    return _private({'success': True, 'capability': item.public_dict()})


@router.get('/today')
async def today_brief(request: Request):
    auth = await _auth(request)
    brief = await build_today_brief(
        auth.user['id'],
        run_service=agent_runs,
        google_connector=_google_connector(),
    )
    return _private({'success': True, 'brief': brief})


@router.post('/runs')
async def create_run(request: Request):
    auth = await _auth(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return _error(AgentRunError('Invalid run request.', 400, 'INVALID_RUN_INPUT'))
    try:
        run = await agent_runs.create_run(
            user_id=auth.user['id'],
            capability_id=str(payload.get('capabilityId') or ''),
            payload=payload.get('input') or {},
            conversation_id=payload.get('conversationId'),
            project_id=payload.get('projectId'),
        )
        return JSONResponse(
            status_code=201,
            content={'success': True, 'run': run},
            headers={'Cache-Control': 'private, no-store'},
        )
    except AgentRunError as exc:
        return _error(exc)


@router.get('/runs')
async def list_runs(request: Request):
    auth = await _auth(request)
    try:
        runs = await agent_runs.list_runs(
            user_id=auth.user['id'],
            status=request.query_params.get('status'),
        )
        return _private({'success': True, 'runs': runs})
    except AgentRunError as exc:
        return _error(exc)


@router.get('/runs/{run_id}')
async def get_run(run_id: str, request: Request):
    auth = await _auth(request)
    try:
        run = await agent_runs.get_run(user_id=auth.user['id'], run_id=run_id)
        return _private({'success': True, 'run': run})
    except AgentRunError as exc:
        return _error(exc)


@router.post('/runs/{run_id}/execute')
async def execute_run(run_id: str, request: Request):
    auth = await _auth(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    run_input = payload.get('input')
    try:
        run = await _executor().execute_run(
            user_id=auth.user['id'],
            run_id=run_id,
            payload=run_input if isinstance(run_input, dict) else None,
        )
        return _private({'success': True, 'run': run})
    except AgentRunError as exc:
        return _error(exc)


@router.post('/runs/{run_id}/cancel')
async def cancel_run(run_id: str, request: Request):
    auth = await _auth(request)
    try:
        run = await agent_runs.cancel_run(user_id=auth.user['id'], run_id=run_id)
        return _private({'success': True, 'run': run})
    except AgentRunError as exc:
        return _error(exc)


@router.get('/approvals')
async def list_approvals(request: Request):
    auth = await _auth(request)
    approvals = await agent_runs.list_approvals(user_id=auth.user['id'])
    return _private({'success': True, 'approvals': approvals})


@router.post('/approvals/{action_id}/decision')
async def decide_approval(action_id: str, request: Request):
    auth = await _auth(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return _error(AgentRunError('Invalid approval decision.', 400, 'INVALID_APPROVAL'))
    try:
        result = await agent_runs.decide_approval(
            user_id=auth.user['id'],
            action_id=action_id,
            decision=str(payload.get('decision') or ''),
            edited_payload=payload.get('payload'),
        )
    except AgentRunError as exc:
        return _error(exc)
    # An approved action leaves its run queued with the exact payload
    # frozen on the action; execute it inline so the approval is the
    # last step the user takes. Executor failures are recorded on the
    # run itself and never fail the decision response.
    action = result.get('action') or {}
    run = result.get('run') or {}
    if action.get('status') == 'approved' and run.get('status') == 'queued':
        try:
            executed = await _executor().execute_run(
                user_id=auth.user['id'],
                run_id=str(run.get('id') or ''),
                payload=action.get('payload'),
            )
            result = {**result, 'run': executed}
        except Exception:
            pass
    return _private({'success': True, **result})
