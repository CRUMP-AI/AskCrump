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
from ..agent_run_service import AgentRunConflictError, AgentRunError
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


# Run-creation failures with these codes are properties of the
# stored automation and the registry, not of the moment: the same
# creation would fail identically on every later pass, so the row is
# terminally invalid and is disabled instead of retried forever.
# Everything else (a paused executor, an entitlement or balance
# change, a provider or database outage) is transient and leaves the
# automation due.
TERMINAL_RUN_ERROR_CODES = frozenset(
    {'CAPABILITY_NOT_FOUND', 'CAPABILITY_NOT_LIVE', 'INVALID_RUN_INPUT'}
)


async def process_due_automations() -> dict:
    """Create + execute a morning-brief run for every due automation.

    Shared by the internal run-due endpoint and the manuscripts cron
    lane: the repo reuses its existing Vercel cron slots instead of
    registering new ones, so due automations ride the minutely
    manuscripts cron. Each automation is isolated - one failure leaves
    that automation due for the next pass and never blocks the rest.

    One outstanding run per occurrence is the invariant. Each
    occurrence's run is filed under a deterministic conversation id,
    and the schedule advances only once the run exists:

    - a terminally invalid row (see
      ``AgentAutomationService.terminal_invalid_reason``) is disabled
      on sight, so it leaves the due scan for good;
    - a row whose occurrence already has a run — an earlier pass
      created it and died before confirming, or execution is paused
      and the run waits queued — is confirmed forward, never
      duplicated;
    - otherwise the pass leases the row (the lease never advances
      the schedule), creates the run, and only then confirms the
      schedule forward. A crash between lease and creation leaves
      the occurrence due behind an expiring lease; a crash between
      creation and confirmation is recovered by the rule above.
      The confirmation is fenced on the lease: a pass whose lease
      expired mid-creation, and whose confirmation therefore
      reports the fence lost to a takeover pass, retires its own
      run instead of executing it — the occurrence keeps exactly
      one live run.

    Runs are created held, in a waiting state the execution claim
    refuses, and the pass whose confirmation advances the schedule
    releases its run to the queue immediately before executing it.
    A duplicate minted by a lease-losing pass therefore cannot
    execute at all — its retirement is cleanup, retried by a sweep
    on this lane until it lands, not a safety mechanism.
    """
    service = _automations()
    now = datetime.now(timezone.utc)
    due = await service.due_automations(now)
    triggered: list[dict] = []
    errors = 0
    disabled = 0
    for row in due:
        reason = AgentAutomationService.terminal_invalid_reason(row)
        if reason is not None:
            try:
                if await service.disable_automation(row, reason=reason):
                    disabled += 1
                else:
                    errors += 1
            except Exception:
                errors += 1
            continue
        conversation_id = AgentAutomationService.occurrence_conversation_id(row)
        try:
            existing = await agent_runs.find_run_by_conversation_id(
                user_id=row['user_id'],
                conversation_id=conversation_id,
            )
        except Exception:
            errors += 1
            continue
        if existing is not None:
            # The occurrence already has its run; an earlier pass
            # died after creating it (or execution is still pending
            # on it). Confirm the schedule forward and, if the run
            # still waits queued, give it its execution attempt —
            # never a second run.
            status = existing.get('status')
            if status == 'waiting_user':
                # The run is still held: its creating pass died
                # before confirming it. Adopt it — confirm the
                # occurrence under this pass, then release the run
                # to the queue. When the confirmation reports the
                # schedule already advanced under a winning pass,
                # the held run is that takeover's loser: retire it
                # instead, and never release it.
                confirmed = None
                try:
                    confirmed = await service.confirm_existing_run(
                        row, ran_at=now
                    )
                except Exception:
                    confirmed = None
                if confirmed is None:
                    try:
                        await agent_runs.cancel_run(
                            user_id=row['user_id'],
                            run_id=str(existing['id']),
                        )
                    except Exception:
                        pass
                    continue
                try:
                    existing = await agent_runs.release_held_run(existing)
                except AgentRunConflictError:
                    continue
                status = 'queued'
            else:
                try:
                    await service.confirm_existing_run(row, ran_at=now)
                except Exception:
                    pass
            if status == 'queued':
                try:
                    executed = await _executor().execute_run(
                        user_id=row['user_id'],
                        run_id=str(existing['id']),
                    )
                    status = executed.get('status')
                except AgentRunConflictError:
                    # Another pass is executing this run right now.
                    status = 'running'
                except Exception:
                    errors += 1
                    continue
            triggered.append(
                {
                    'automationId': row['id'],
                    'runId': existing['id'],
                    'status': status,
                }
            )
            continue
        claimed = None
        created_id = None
        try:
            # Lease before creating anything: the lease is a
            # compare-and-swap, so a concurrent pass over the same
            # due automation gets no lease and skips it instead of
            # firing it a second time. The lease does not advance
            # the schedule — confirmation below does, once the run
            # exists.
            claimed = await service.claim_due_automation(row, ran_at=now)
            if claimed is None:
                continue
            # Re-check under the lease: a competitor whose lease
            # expired may have created the occurrence's run after
            # the pre-claim check above read, and this pass's claim
            # is the takeover, not the first arrival. If the run
            # exists now, the occurrence is already handled —
            # confirm the schedule forward under this pass's claim
            # fence and treat the run exactly like the pre-claim
            # existing-run case instead of minting a second one.
            try:
                existing = await agent_runs.find_run_by_conversation_id(
                    user_id=row['user_id'],
                    conversation_id=conversation_id,
                )
            except Exception:
                errors += 1
                try:
                    await service.release_claim(row, claimed)
                except Exception:
                    pass
                continue
            if existing is not None:
                status = existing.get('status')
                if status == 'waiting_user':
                    # A held run an earlier claimant left for this
                    # occurrence (it died after creating, before
                    # confirming). This pass's claim owns the
                    # occurrence now: confirm under the claim and
                    # release the run — or retire it when the fence
                    # reports a winner already advanced the
                    # schedule. It is never executed while held.
                    confirmed = None
                    try:
                        confirmed = await service.confirm_run_created(
                            row, claimed, ran_at=now
                        )
                    except Exception:
                        confirmed = None
                    if confirmed is None:
                        try:
                            await agent_runs.cancel_run(
                                user_id=row['user_id'],
                                run_id=str(existing['id']),
                            )
                        except Exception:
                            pass
                        continue
                    try:
                        existing = await agent_runs.release_held_run(
                            existing
                        )
                    except AgentRunConflictError:
                        continue
                    status = 'queued'
                else:
                    try:
                        await service.confirm_run_created(
                            row, claimed, ran_at=now
                        )
                    except Exception:
                        pass
                if status == 'queued':
                    try:
                        executed = await _executor().execute_run(
                            user_id=row['user_id'],
                            run_id=str(existing['id']),
                        )
                        status = executed.get('status')
                    except AgentRunConflictError:
                        status = 'running'
                    except Exception:
                        errors += 1
                        continue
                triggered.append(
                    {
                        'automationId': row['id'],
                        'runId': existing['id'],
                        'status': status,
                    }
                )
                continue
            run_payload = AgentAutomationService.run_payload_for(row)
            try:
                created = await agent_runs.create_run(
                    user_id=row['user_id'],
                    capability_id=row['capability_id'],
                    payload=run_payload,
                    conversation_id=conversation_id,
                    held=True,
                )
            except AgentRunError as exc:
                if exc.code in TERMINAL_RUN_ERROR_CODES:
                    # Creation itself proved the row terminal (for
                    # example the stored payload fails the capability
                    # schema): disable it instead of retrying forever.
                    if await service.disable_automation(row, reason=exc.code):
                        disabled += 1
                    else:
                        errors += 1
                    continue
                raise
            created_id = str(created['id'])
            # The run exists, so the occurrence is consumed: confirm
            # the schedule forward under the lease before executing.
            # Execution outcomes never roll this back — the run's
            # outcome lives in the ledger, even when the run failed
            # or execution is paused and it waits queued.
            confirmed = await service.confirm_run_created(
                row, claimed, ran_at=now
            )
            if confirmed is None:
                # The fence is lost: this pass's lease expired while
                # it was creating, and a takeover pass already
                # advanced the schedule and owns the occurrence. The
                # run created here is a duplicate — but it was
                # created held, so it cannot execute whether or not
                # retirement lands. Retire it through the
                # compare-and-swap cancellation as cleanup; the
                # lane's sweep retries the retirement until it
                # lands, and the occurrence keeps exactly one live
                # run either way: the winning pass's.
                try:
                    await agent_runs.cancel_run(
                        user_id=row['user_id'], run_id=created_id
                    )
                except Exception:
                    pass
                continue
            # The confirmation advanced the schedule under this
            # pass's claim, so this pass owns the run: release it
            # from held to queued and execute it. (The run executes
            # its stored creation payload, stored by create_run
            # above.) A release conflict means the run moved while
            # held — cancelled by its owner, for example — and the
            # occurrence is consumed either way; there is nothing
            # to execute.
            try:
                held_row = await agent_runs._get_owned_run(
                    user_id=row['user_id'], run_id=created_id
                )
                await agent_runs.release_held_run(held_row)
            except AgentRunConflictError:
                continue
            run = await _executor().execute_run(
                user_id=row['user_id'],
                run_id=created_id,
            )
            triggered.append(
                {
                    'automationId': row['id'],
                    'runId': created['id'],
                    'status': run.get('status'),
                }
            )
        except AgentRunConflictError:
            # The run was claimed for execution by a concurrent pass
            # between creation and execution here; the occurrence
            # has exactly one run and it is being handled.
            if created_id is not None:
                triggered.append(
                    {
                        'automationId': row['id'],
                        'runId': created_id,
                        'status': 'running',
                    }
                )
            else:
                errors += 1
        except Exception:
            # One bad automation must not block the rest of the pass.
            # A failure before the run exists hands the lease back so
            # the occurrence stays due and is retried on the next
            # trigger; the release is best effort and never masks the
            # original failure. (A BaseException — a crash — is not
            # caught here at all: the lease is simply left to expire.)
            errors += 1
            if claimed is not None and created_id is None:
                try:
                    await service.release_claim(row, claimed)
                except Exception:
                    pass
    # Credit recovery rides the same lane: settle reservations a
    # crashed or failed execution left stranded on terminal runs.
    # The sweep is bounded and best effort — it never fails the pass.
    credits_reconciled = 0
    try:
        credits_reconciled = await agent_runs.reconcile_terminal_run_credits()
    except Exception:
        credits_reconciled = 0
    # Held-run retirement rides the same lane: a takeover loser's
    # inline cancellation can fail, so the sweep retries it pass
    # after pass until it lands. Best effort — a held run cannot
    # execute either way, so a failure here never fails the pass.
    held_retired = 0
    try:
        held_retired = await agent_runs.retire_unconfirmed_automation_runs()
    except Exception:
        held_retired = 0
    return {
        'success': True,
        'due': len(due),
        'triggered': len(triggered),
        'errors': errors,
        'disabled': disabled,
        'creditsReconciled': credits_reconciled,
        'retiredHeldRuns': held_retired,
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

