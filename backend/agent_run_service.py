"""Durable agent run ledger and approval service.

A run is one user outcome requested through a registered capability.
Steps are append-only: the Tasks view and the audit trail read from the
ledger, never from chat text. Capabilities that require an approval
card create a pending action holding the exact payload; approving it
executes that stored payload exactly, so the payload is frozen here at
creation and can only change through an explicit user edit, which
re-validates against the capability schema's required fields.

Execution adapters (Gmail, Calendar, browser, and the other registry
connectors) claim queued runs in a later increment. This service owns
the lifecycle every adapter shares: queued, waiting_approval,
waiting_user, running, succeeded, failed, cancelled.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any

from .agent_registry import Capability, get_capability
from .db import SupabaseDB, eq
from .security import iso_now, new_uuid

RUN_STATUSES = frozenset(
    {
        'queued', 'planning', 'running', 'waiting_approval',
        'waiting_user', 'succeeded', 'failed', 'cancelled',
    }
)
TERMINAL_STATUSES = frozenset({'succeeded', 'failed', 'cancelled'})
APPROVAL_TTL = timedelta(hours=24)
MAX_PAYLOAD_BYTES = 16000


class AgentRunError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400, code: str = 'AGENT_RUN_ERROR'):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class AgentRunNotFoundError(AgentRunError):
    def __init__(self, message: str = 'Run not found.'):
        super().__init__(message, 404, 'AGENT_RUN_NOT_FOUND')


class AgentActionNotFoundError(AgentRunError):
    def __init__(self, message: str = 'That action is no longer waiting.'):
        super().__init__(message, 404, 'AGENT_ACTION_NOT_FOUND')


class AgentRunConflictError(AgentRunError):
    def __init__(self, message: str):
        super().__init__(message, 409, 'AGENT_RUN_CONFLICT')


def _summarize_input(payload: dict[str, Any]) -> dict[str, Any]:
    """Redacted step/ledger summary: field names and sizes, never values
    that look like message bodies or credentials."""
    summary: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            summary[key] = {'type': 'string', 'length': len(value)}
        elif isinstance(value, list):
            summary[key] = {'type': 'array', 'length': len(value)}
        elif isinstance(value, dict):
            summary[key] = {'type': 'object', 'keys': sorted(value)[:20]}
        elif isinstance(value, bool) or value is None or isinstance(value, (int, float)):
            summary[key] = value
        else:
            summary[key] = {'type': type(value).__name__}
    return summary


def _validate_payload(capability: Capability, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AgentRunError('Run input must be an object.', 400, 'INVALID_RUN_INPUT')
    if len(json.dumps(payload, default=str).encode()) > MAX_PAYLOAD_BYTES:
        raise AgentRunError('Run input is too large.', 400, 'INVALID_RUN_INPUT')
    required = capability.input_schema.get('required') or []
    missing = [name for name in required if payload.get(name) in (None, '')]
    if missing:
        raise AgentRunError(
            f"Missing required input: {', '.join(missing)}.",
            400,
            'INVALID_RUN_INPUT',
        )
    return payload


class AgentRunService:
    def __init__(self, db: SupabaseDB) -> None:
        self.db = db

    # -- shape ------------------------------------------------------------
    @staticmethod
    def public_run(row: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': row.get('id'),
            'capabilityId': row.get('capability_id'),
            'status': row.get('status'),
            'projectId': row.get('project_id'),
            'conversationId': row.get('conversation_id'),
            'inputSummary': row.get('input_summary') or {},
            'resultSummary': row.get('result_summary'),
            'creditCost': row.get('credit_cost'),
            'createdAt': row.get('created_at'),
            'updatedAt': row.get('updated_at'),
        }

    @staticmethod
    def public_action(row: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': row.get('id'),
            'runId': row.get('run_id'),
            'capabilityId': row.get('capability_id'),
            'summary': row.get('rendered_summary'),
            'payload': row.get('exact_payload') or {},
            'creditCost': row.get('credit_cost'),
            'status': row.get('status'),
            'expiresAt': row.get('expires_at'),
            'decidedAt': row.get('decided_at'),
            'createdAt': row.get('created_at'),
        }

    @staticmethod
    def public_step(row: dict[str, Any]) -> dict[str, Any]:
        return {
            'id': row.get('id'),
            'capabilityId': row.get('capability_id'),
            'type': row.get('step_type'),
            'payload': row.get('payload') or {},
            'createdAt': row.get('created_at'),
        }

    # -- internals ----------------------------------------------------------
    async def _record_step(
        self,
        *,
        run: dict[str, Any],
        step_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self.db.insert(
            'agent_run_steps',
            {
                'run_id': run['id'],
                'user_id': run['user_id'],
                'capability_id': run['capability_id'],
                'step_type': step_type,
                'payload': payload or {},
            },
        )

    async def _set_status(self, run: dict[str, Any], status: str) -> dict[str, Any]:
        if status not in RUN_STATUSES:
            raise AgentRunError(f'Unknown run status: {status}', 500, 'AGENT_RUN_ERROR')
        updated = await self.db.update(
            'agent_runs',
            {'status': status, 'updated_at': iso_now()},
            filters={'id': eq(run['id']), 'user_id': eq(run['user_id'])},
        )
        row = updated[0] if isinstance(updated, list) and updated else {**run, 'status': status}
        return row

    async def _get_owned_run(self, *, user_id: str, run_id: str) -> dict[str, Any]:
        row = await self.db.select_one(
            'agent_runs',
            filters={'id': eq(str(run_id)), 'user_id': eq(user_id)},
        )
        if not row:
            raise AgentRunNotFoundError()
        return row

    # -- runs ---------------------------------------------------------------
    async def create_run(
        self,
        *,
        user_id: str,
        capability_id: str,
        payload: Any,
        conversation_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        capability = get_capability(capability_id)
        if capability is None:
            raise AgentRunError(
                'That capability is not available.', 404, 'CAPABILITY_NOT_FOUND'
            )
        payload = _validate_payload(capability, payload)
        needs_approval = capability.approval in {'card', 'card_with_cost'}
        now = iso_now()
        run = {
            'id': new_uuid(),
            'user_id': user_id,
            'project_id': project_id or None,
            'conversation_id': (str(conversation_id)[:160] if conversation_id else None),
            'capability_id': capability.id,
            'status': 'waiting_approval' if needs_approval else 'queued',
            'input_summary': _summarize_input(payload),
            'result_summary': None,
            'credit_cost': capability.credit_cost,
            'created_at': now,
            'updated_at': now,
        }
        await self.db.insert('agent_runs', run)
        await self._record_step(run=run, step_type='run.created')
        action = None
        if needs_approval:
            expires = datetime.now(timezone.utc) + APPROVAL_TTL
            action = {
                'id': new_uuid(),
                'run_id': run['id'],
                'user_id': user_id,
                'capability_id': capability.id,
                'exact_payload': payload,
                'rendered_summary': f'{capability.title} — {capability.verb_phrase}',
                'credit_cost': capability.credit_cost,
                'status': 'pending',
                'expires_at': expires.isoformat(),
                'decided_at': None,
                'created_at': now,
                'updated_at': now,
            }
            await self.db.insert('agent_pending_actions', action)
            await self._record_step(run=run, step_type='approval.requested')
        else:
            await self._record_step(run=run, step_type='run.queued')
        result = self.public_run(run)
        if action is not None:
            result['pendingAction'] = self.public_action(action)
        return result

    async def list_runs(
        self, *, user_id: str, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {'user_id': eq(user_id)}
        if status:
            if status not in RUN_STATUSES:
                raise AgentRunError('Unknown run status filter.', 400, 'INVALID_RUN_STATUS')
            filters['status'] = eq(status)
        rows = await self.db.select(
            'agent_runs',
            filters=filters,
            order='created_at.desc',
            limit=max(1, min(int(limit or 100), 250)),
        )
        return [self.public_run(row) for row in rows]

    async def get_run(self, *, user_id: str, run_id: str) -> dict[str, Any]:
        run = await self._get_owned_run(user_id=user_id, run_id=run_id)
        steps = await self.db.select(
            'agent_run_steps',
            filters={'run_id': eq(run['id']), 'user_id': eq(user_id)},
            order='id.asc',
            limit=500,
        )
        actions = await self.db.select(
            'agent_pending_actions',
            filters={'run_id': eq(run['id']), 'user_id': eq(user_id)},
            order='created_at.desc',
            limit=50,
        )
        result = self.public_run(run)
        result['steps'] = [self.public_step(step) for step in steps]
        result['pendingActions'] = [self.public_action(item) for item in actions]
        return result

    async def cancel_run(self, *, user_id: str, run_id: str) -> dict[str, Any]:
        run = await self._get_owned_run(user_id=user_id, run_id=run_id)
        if run['status'] in TERMINAL_STATUSES:
            raise AgentRunConflictError('This run has already finished.')
        pending = await self.db.select(
            'agent_pending_actions',
            filters={
                'run_id': eq(run['id']),
                'user_id': eq(user_id),
                'status': eq('pending'),
            },
            limit=50,
        )
        for action in pending:
            await self.db.update(
                'agent_pending_actions',
                {'status': 'cancelled', 'updated_at': iso_now()},
                filters={'id': eq(action['id']), 'user_id': eq(user_id)},
            )
        run = await self._set_status(run, 'cancelled')
        await self._record_step(run=run, step_type='run.cancelled')
        return self.public_run(run)

    # -- approvals ------------------------------------------------------------
    async def list_approvals(self, *, user_id: str) -> list[dict[str, Any]]:
        rows = await self.db.select(
            'agent_pending_actions',
            filters={'user_id': eq(user_id), 'status': eq('pending')},
            order='created_at.desc',
            limit=100,
        )
        return [self.public_action(row) for row in rows]

    async def decide_approval(
        self,
        *,
        user_id: str,
        action_id: str,
        decision: str,
        edited_payload: Any = None,
    ) -> dict[str, Any]:
        normalized = str(decision or '').strip().lower()
        if normalized not in {'approved', 'denied'}:
            raise AgentRunError('Invalid approval decision.', 400, 'INVALID_APPROVAL')
        action = await self.db.select_one(
            'agent_pending_actions',
            filters={'id': eq(str(action_id)), 'user_id': eq(user_id)},
        )
        if not action:
            raise AgentActionNotFoundError()
        if action['status'] != 'pending':
            raise AgentRunConflictError('This action has already been decided.')
        expires_at = str(action.get('expires_at') or '')
        if expires_at and expires_at <= iso_now():
            await self.db.update(
                'agent_pending_actions',
                {'status': 'expired', 'updated_at': iso_now()},
                filters={'id': eq(action['id']), 'user_id': eq(user_id)},
            )
            raise AgentRunConflictError('This approval has expired.')
        run = await self._get_owned_run(user_id=user_id, run_id=str(action['run_id']))
        payload = action.get('exact_payload') or {}
        if normalized == 'approved' and edited_payload is not None:
            capability = get_capability(str(action['capability_id']))
            if capability is None:
                raise AgentRunError(
                    'That capability is not available.', 404, 'CAPABILITY_NOT_FOUND'
                )
            payload = _validate_payload(capability, edited_payload)
        now = iso_now()
        await self.db.update(
            'agent_pending_actions',
            {
                'status': normalized,
                'exact_payload': payload,
                'decided_at': now,
                'updated_at': now,
            },
            filters={'id': eq(action['id']), 'user_id': eq(user_id)},
        )
        decided = {**action, 'status': normalized, 'exact_payload': payload, 'decided_at': now}
        if normalized == 'approved':
            run = await self._set_status(run, 'queued')
            await self._record_step(
                run=run,
                step_type='approval.decided',
                payload={'decision': 'approved', 'actionId': action['id']},
            )
            await self._record_step(run=run, step_type='run.queued')
        else:
            run = await self._set_status(run, 'cancelled')
            await self._record_step(
                run=run,
                step_type='approval.decided',
                payload={'decision': 'denied', 'actionId': action['id']},
            )
            await self._record_step(run=run, step_type='run.cancelled')
        return {'action': self.public_action(decided), 'run': self.public_run(run)}
