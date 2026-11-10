"""Agent capability registry, run ledger, and approval endpoints.

The client fetches the registry at session start and renders task,
approval, artifact, connection, and brief cards from it. Runs are
created only for registered capabilities — unknown ids fail closed
with ``CAPABILITY_NOT_FOUND`` — and every run, step, and approval
decision is recorded in the durable ledger behind these routes.
Queued runs execute through the agent executor, and the Today brief
is composed from the same ledger and connection state. Users can
also save automations (standing daily schedules) for schedulable
capabilities; the internal trigger endpoint runs the ones that are
due and stamps their schedules forward.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..agent_automation_service import (
    AgentAutomationError,
    AgentAutomationService,
)
from ..agent_executor import AgentExecutor, build_today_brief
from ..agent_registry import get_capability, public_catalog
from ..agent_run_service import AgentRunError
from ..auth_service import authenticate_request
from ..google_connector import GoogleConnector
from ..google_vault import GoogleVault
from ..runtime import agent_runs, db, settings

router = APIRouter(prefix='/api/agent', tags=['agent'])
internal_router = APIRouter(prefix='/api/internal/agent', tags=['agent-internal'])


def _google_connector() -> GoogleConnector:
    return GoogleConnector(settings=settings, db=db, vault=GoogleVault())


def _executor() -> AgentExecutor:
    return AgentExecutor(agent_runs, google_connector=_google_connector())


def _automations() -> AgentAutomationService:
    return AgentAutomationService(db)


def _error(exc: AgentRunError | AgentAutomationError) -> JSONResponse:
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
    await _auth(request)
    # Emergency pause: run execution is closed until the payload-of-record
    # + CAS execution fix lands. This endpoint accepted caller input that
    # could substitute the approved payload, so it fails closed for every
    # run — no body parsing, no executor call.
    return _error(
        AgentRunError(
            'Agent execution is paused while a safety fix is completed. '
            'No run was executed.',
            503,
            'AGENT_EXECUTION_PAUSED',
        )
    )


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
            # No payload is passed: the executor resolves the approved
            # action's frozen exact payload from the run's own record.
            executed = await _executor().execute_run(
                user_id=auth.user['id'],
                run_id=str(run.get('id') or ''),
            )
            result = {**result, 'run': executed}
        except Exception:
            pass
    return _private({'success': True, **result})


@router.get('/automations')
async def list_automations(request: Request):
    auth = await _auth(request)
    automations = await _automations().list_automations(user_id=auth.user['id'])
    return _private({'success': True, 'automations': automations})


@router.post('/automations')
async def create_automation(request: Request):
    auth = await _auth(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        return _error(
            AgentAutomationError(
                'Invalid automation request.', 400, 'INVALID_AUTOMATION_INPUT'
            )
        )
    enabled = payload.get('enabled')
    try:
        automation = await _automations().create_automation(
            user_id=auth.user['id'],
            capability_id=str(payload.get('capabilityId') or ''),
            schedule=payload.get('schedule'),
            payload=payload.get('payload', payload.get('input')),
            enabled=True if enabled is None else bool(enabled),
        )
        return JSONResponse(
            status_code=201,
            content={'success': True, 'automation': automation},
            headers={'Cache-Control': 'private, no-store'},
        )
    except AgentAutomationError as exc:
        return _error(exc)


@router.delete('/automations/{automation_id}')
async def delete_automation(automation_id: str, request: Request):
    auth = await _auth(request)
    try:
        automation = await _automations().delete_automation(
            user_id=auth.user['id'], automation_id=automation_id
        )
        return _private({'success': True, 'automation': automation})
    except AgentAutomationError as exc:
        return _error(exc)


async def process_due_automations() -> dict:
    """Create + execute a morning-brief run for every due automation.

    Shared by the internal run-due endpoint and the manuscripts cron
    lane: the repo reuses its existing Vercel cron slots instead of
    registering new ones, so due automations ride the minutely
    manuscripts cron. Each automation is isolated - one failure leaves
    that automation due for the next pass and never blocks the rest.
    """
    service = _automations()
    now = datetime.now(timezone.utc)
    due = await service.due_automations(now)
    triggered: list[dict] = []
    errors = 0
    for row in due:
        claimed = None
        try:
            # Claim before creating anything: the claim is a
            # compare-and-swap on the row's observed next_run_at, so
            # a concurrent pass over the same due automation gets no
            # claim and skips it instead of firing it a second time.
            claimed = await service.claim_due_automation(row, ran_at=now)
            if claimed is None:
                continue
            run_payload = AgentAutomationService.run_payload_for(row)
            created = await agent_runs.create_run(
                user_id=row['user_id'],
                capability_id=row['capability_id'],
                payload=run_payload,
            )
            run = created
            if created.get('status') == 'queued':
                # The run executes its stored creation payload (the
                # automation's payload, stored by create_run above).
                run = await _executor().execute_run(
                    user_id=row['user_id'],
                    run_id=str(created['id']),
                )
            # The claim already advanced the schedule: the run
            # happened (its outcome lives in the ledger), even when
            # the run itself failed.
            triggered.append(
                {
                    'automationId': row['id'],
                    'runId': created['id'],
                    'status': run.get('status'),
                }
            )
        except Exception:
            # One bad automation must not block the rest of the pass.
            # Hand the claim back so it stays due and is retried on
            # the next trigger; the release is best effort and never
            # masks the original failure.
            errors += 1
            if claimed is not None:
                try:
                    await service.release_claim(row, claimed)
                except Exception:
                    pass
    return {
        'success': True,
        'due': len(due),
        'triggered': len(triggered),
        'errors': errors,
        'runs': triggered,
    }


@internal_router.api_route('/automations/run-due', methods=['GET', 'POST'])
async def run_due_automations(request: Request):
    # Same cron authentication as the other internal cron endpoints:
    # the configured secret arrives as a bearer credential, and the
    # endpoint fails closed when no secret is configured. GET is
    # accepted alongside POST because Vercel Cron issues GET requests.
    expected = settings.cron_secret
    authorization = request.headers.get('authorization', '')
    if not expected or not hmac.compare_digest(
        authorization, f'Bearer {expected}'
    ):
        return JSONResponse(
            status_code=401,
            content={'success': False, 'error': 'Unauthorized.'},
        )
    return _private(await process_due_automations())

