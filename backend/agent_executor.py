"""Agent run executor and the Today brief composer.

The run ledger (``agent_run_service``) owns lifecycle state; this module
owns doing the work. An executor claims a queued run, moves it through
``running`` to a terminal status, and appends every transition to the
ledger through the run service's own step/status methods, so the Tasks
view and the audit trail keep reading from one store.

Adapters are deliberately narrow. ``gmail.search`` and ``calendar.list``
run against the signed-in user's Google connection and fail honestly
with ``CONNECTION_REQUIRED`` when there is none. ``agent.today_brief``
composes the Today brief from real service calls only. ``browser.read``
dispatches to the browser agent's guarded page fetch, and the Gmail
write capabilities (``gmail.draft``, ``gmail.send``) dispatch to the
Gmail write adapter, which re-checks the granted scopes before any
provider call. Every other registered capability fails with
``EXECUTOR_NOT_AVAILABLE`` rather than pretending to have run — an
adapter lands here capability by capability.
No adapter charges credits: the capabilities wired here are registered
with a ``none`` credit cost.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import json
from typing import Any

from . import agent_gmail_write, browser_agent
from .agent_run_service import AgentRunConflictError, AgentRunService
from .browser_agent import BrowserAgentError
from .db import eq
from .google_connector import ConnectionRequiredError, GoogleConnectorError
from .security import iso_now

# Result summaries land in a length-capped text column and step payloads
# in a capped jsonb column, so both are fenced well below the limits.
MAX_RESULT_SUMMARY_CHARS = 8000
MAX_STEP_PAYLOAD_CHARS = 4000
MAX_SUMMARY_ITEMS = 10
MAX_SUMMARY_FIELD_CHARS = 300

EXECUTOR_NOT_AVAILABLE = 'EXECUTOR_NOT_AVAILABLE'
CONNECTION_REQUIRED = 'CONNECTION_REQUIRED'
# The ledger stores a fenced result summary, not full page bodies; the
# browser adapter's complete text stays available to the run caller via
# the adapter itself, and the summary keeps a bounded excerpt.
MAX_BROWSER_TEXT_CHARS = 3000


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_SUMMARY_FIELD_CHARS:
        return value[:MAX_SUMMARY_FIELD_CHARS]
    return value


def _fence_summary_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fenced: list[dict[str, Any]] = []
    for item in items[:MAX_SUMMARY_ITEMS]:
        fenced.append({str(key): _truncate(val) for key, val in item.items()})
    return fenced


def _result_summary_text(summary: dict[str, Any]) -> str:
    """Serialize a result summary for the ledger's text column.

    Only counts, ids, and provider summary fields are stored — never
    message bodies, tokens, or other credential-shaped values.
    """
    text = json.dumps(summary, default=str)
    if len(text) <= MAX_RESULT_SUMMARY_CHARS:
        return text
    trimmed = dict(summary)
    for key in ('messages', 'events'):
        if isinstance(trimmed.get(key), list):
            trimmed[key] = trimmed[key][:3]
    trimmed['truncated'] = True
    text = json.dumps(trimmed, default=str)
    return text[:MAX_RESULT_SUMMARY_CHARS]


def _step_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(payload, default=str)) <= MAX_STEP_PAYLOAD_CHARS:
        return payload
    return {'truncated': True, 'keys': sorted(payload)[:20]}


def _unavailable(reason: str) -> str:
    return f'unavailable: {reason}'


def _default_google_connector() -> Any | None:
    """Build the Google connector the same way connected_apps does."""
    try:
        from .google_connector import GoogleConnector
        from .google_vault import GoogleVault
        from .runtime import db, settings

        return GoogleConnector(settings=settings, db=db, vault=GoogleVault())
    except Exception:
        return None


async def build_today_brief(
    user_id: str,
    *,
    run_service: AgentRunService | None = None,
    google_connector: Any | None = None,
) -> dict[str, Any]:
    """Compose the Today brief from real service calls only.

    Approvals and recent runs come from the run ledger. Calendar and
    inbox highlights come from the user's Google connection when one is
    connected; each source that cannot be read degrades to an explicit
    ``unavailable: ...`` reason string instead of fabricated data.
    """
    if run_service is None:
        from .runtime import agent_runs

        run_service = agent_runs
    connector = google_connector
    if connector is None:
        connector = _default_google_connector()

    pending_approvals = await run_service.list_approvals(user_id=user_id)
    recent_runs = await run_service.list_runs(user_id=user_id, limit=10)

    google_status: dict[str, Any] = {
        'status': 'unavailable',
        'connected': False,
        'accounts': [],
    }
    calendar: Any = _unavailable('Google connection status is unavailable.')
    inbox_highlights: Any = _unavailable('Google connection status is unavailable.')
    access_token: str | None = None
    if connector is not None:
        if getattr(connector, 'oauth_configured', True) is False:
            google_status = {
                'status': 'not_configured',
                'connected': False,
                'accounts': [],
            }
            calendar = _unavailable('Google connections are not configured yet.')
            inbox_highlights = calendar
        else:
            try:
                status = await connector.status(user_id)
            except Exception:
                status = None
            if status is not None:
                connected = bool(status.get('connected'))
                google_status = {
                    'status': 'connected' if connected else 'not_connected',
                    'connected': connected,
                    'accounts': status.get('accounts') or [],
                }
                if not connected:
                    reason = 'Google is not connected for this account.'
                    calendar = _unavailable(reason)
                    inbox_highlights = _unavailable(reason)
                else:
                    try:
                        access_token = await connector.access_token_for(user_id)
                    except ConnectionRequiredError:
                        reason = 'Connect Google to use this capability.'
                        calendar = _unavailable(reason)
                        inbox_highlights = _unavailable(reason)
                    except GoogleConnectorError as exc:
                        calendar = _unavailable(exc.message)
                        inbox_highlights = _unavailable(exc.message)

    if access_token is not None and connector is not None:
        today = datetime.now(timezone.utc).date()
        time_min = datetime.combine(today, time.min, tzinfo=timezone.utc).isoformat()
        time_max = datetime.combine(
            today + timedelta(days=1), time.min, tzinfo=timezone.utc
        ).isoformat()
        try:
            calendar = await connector.list_events(
                access_token, time_min=time_min, time_max=time_max
            )
        except ConnectionRequiredError:
            calendar = _unavailable('Connect Google to use this capability.')
        except GoogleConnectorError as exc:
            calendar = _unavailable(exc.message)
        except Exception:
            calendar = _unavailable('Calendar could not be read.')
        try:
            inbox_highlights = await connector.search_messages(
                access_token, 'in:inbox', 5
            )
        except ConnectionRequiredError:
            inbox_highlights = _unavailable('Connect Google to use this capability.')
        except GoogleConnectorError as exc:
            inbox_highlights = _unavailable(exc.message)
        except Exception:
            inbox_highlights = _unavailable('Inbox could not be read.')

    return {
        'generatedAt': iso_now(),
        'pendingApprovals': pending_approvals,
        'recentRuns': recent_runs,
        'connections': {'google': google_status},
        'calendar': calendar,
        'inboxHighlights': inbox_highlights,
    }


class AgentExecutor:
    """Dispatches queued runs to capability adapters."""

    def __init__(
        self,
        run_service: AgentRunService,
        google_connector: Any | None = None,
    ) -> None:
        self.run_service = run_service
        self.google_connector = google_connector

    # -- connector ------------------------------------------------------

    def _connector(self) -> Any | None:
        if self.google_connector is not None:
            return self.google_connector
        self.google_connector = _default_google_connector()
        return self.google_connector

    async def _access_token(self, user_id: str) -> str:
        connector = self._connector()
        if connector is None:
            raise ConnectionRequiredError()
        return await connector.access_token_for(user_id)

    # -- ledger helpers ---------------------------------------------------

    async def _record_step(
        self, run: dict[str, Any], step_type: str, payload: dict[str, Any] | None = None
    ) -> None:
        await self.run_service._record_step(
            run=run, step_type=step_type, payload=_step_payload(payload or {})
        )

    async def _finish(
        self,
        run: dict[str, Any],
        status: str,
        summary: dict[str, Any],
        step_type: str,
        step_payload: dict[str, Any],
    ) -> dict[str, Any]:
        run = await self.run_service._set_status(run, status)
        summary_text = _result_summary_text(summary)
        await self.run_service.db.update(
            'agent_runs',
            {'result_summary': summary_text, 'updated_at': iso_now()},
            filters={'id': eq(run['id']), 'user_id': eq(run['user_id'])},
        )
        run = {**run, 'result_summary': summary_text}
        await self._record_step(run, step_type, step_payload)
        return self.run_service.public_run(run)

    async def _fail(
        self, run: dict[str, Any], code: str, message: str
    ) -> dict[str, Any]:
        await self._record_step(
            run, 'step.failed', {'code': code, 'message': message[:500]}
        )
        return await self._finish(
            run,
            'failed',
            {'error': {'code': code, 'message': message[:500]}},
            'run.failed',
            {'code': code},
        )

    async def _succeed(
        self, run: dict[str, Any], summary: dict[str, Any]
    ) -> dict[str, Any]:
        await self._record_step(
            run,
            'step.completed',
            {'capabilityId': run['capability_id'], 'result': summary.get('kind')},
        )
        return await self._finish(run, 'succeeded', summary, 'run.completed', {})

    # -- payload resolution ----------------------------------------------

    async def _resolve_payload(
        self, run: dict[str, Any], payload: dict[str, Any] | None
    ) -> dict[str, Any]:
        if isinstance(payload, dict):
            return payload
        # Approval-gated runs freeze their exact payload on the pending
        # action; an approved action is the payload of record.
        try:
            detail = await self.run_service.get_run(
                user_id=run['user_id'], run_id=run['id']
            )
        except Exception:
            return {}
        for action in detail.get('pendingActions') or []:
            if action.get('status') == 'approved' and isinstance(
                action.get('payload'), dict
            ):
                return action['payload']
        return {}

    # -- adapters ---------------------------------------------------------

    async def _run_gmail_search(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        query = str(payload.get('query') or '').strip()
        if not query:
            return await self._fail(
                run,
                'INVALID_RUN_INPUT',
                'This run is missing its search query, so it cannot be executed.',
            )
        try:
            max_results = int(payload.get('maxResults') or 10)
        except (TypeError, ValueError):
            max_results = 10
        try:
            access_token = await self._access_token(run['user_id'])
            connector = self._connector()
            messages = await connector.search_messages(
                access_token, query, max(1, min(max_results, 50))
            )
        except ConnectionRequiredError as exc:
            return await self._fail(run, CONNECTION_REQUIRED, exc.message)
        except GoogleConnectorError as exc:
            return await self._fail(run, exc.code, exc.message)
        summary = {
            'kind': 'gmail.search',
            'count': len(messages),
            'messages': _fence_summary_items(messages),
        }
        return await self._succeed(run, summary)

    async def _run_calendar_list(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            access_token = await self._access_token(run['user_id'])
            connector = self._connector()
            events = await connector.list_events(
                access_token,
                time_min=str(payload.get('timeMin') or '') or None,
                time_max=str(payload.get('timeMax') or '') or None,
            )
        except ConnectionRequiredError as exc:
            return await self._fail(run, CONNECTION_REQUIRED, exc.message)
        except GoogleConnectorError as exc:
            return await self._fail(run, exc.code, exc.message)
        summary = {
            'kind': 'calendar.list',
            'count': len(events),
            'events': _fence_summary_items(events),
        }
        return await self._succeed(run, summary)

    async def _run_today_brief(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        brief = await build_today_brief(
            run['user_id'],
            run_service=self.run_service,
            google_connector=self._connector(),
        )
        calendar = brief.get('calendar')
        inbox = brief.get('inboxHighlights')
        summary = {
            'kind': 'agent.today_brief',
            'generatedAt': brief.get('generatedAt'),
            'pendingApprovals': len(brief.get('pendingApprovals') or []),
            'recentRuns': len(brief.get('recentRuns') or []),
            'googleConnected': bool(
                (brief.get('connections') or {}).get('google', {}).get('connected')
            ),
            'calendar': len(calendar) if isinstance(calendar, list) else calendar,
            'inboxHighlights': len(inbox) if isinstance(inbox, list) else inbox,
        }
        return await self._succeed(run, summary)

    async def _run_browser_read(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            result = await browser_agent.execute(
                'browser.read', run['user_id'], payload
            )
        except BrowserAgentError as exc:
            return await self._fail(run, exc.code, exc.message)
        text = str(result.get('text') or '')
        summary = {
            'kind': 'browser.read',
            'finalUrl': result.get('finalUrl'),
            'title': result.get('title'),
            'fetchedAt': result.get('fetchedAt'),
            'bytes': result.get('bytes'),
            'textLength': result.get('textLength'),
            'text': text[:MAX_BROWSER_TEXT_CHARS],
            'textTruncated': bool(result.get('truncated'))
            or len(text) > MAX_BROWSER_TEXT_CHARS,
        }
        return await self._succeed(run, summary)

    async def _run_gmail_write(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            result = await agent_gmail_write.execute(
                run['capability_id'],
                run['user_id'],
                payload,
                connector=self._connector(),
            )
        except GoogleConnectorError as exc:
            return await self._fail(run, exc.code, exc.message)
        summary = {'kind': run['capability_id'], **result}
        return await self._succeed(run, summary)

    _ADAPTERS = {
        'gmail.search': _run_gmail_search,
        'calendar.list': _run_calendar_list,
        'agent.today_brief': _run_today_brief,
        'browser.read': _run_browser_read,
        'gmail.draft': _run_gmail_write,
        'gmail.send': _run_gmail_write,
    }

    # -- dispatch ---------------------------------------------------------

    async def execute_run_record(
        self, run: dict[str, Any], *, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute one loaded run row. The run must be queued."""
        if run.get('status') != 'queued':
            raise AgentRunConflictError('This run is not queued for execution.')
        run = await self.run_service._set_status(run, 'running')
        await self._record_step(run, 'run.started', {})
        resolved = await self._resolve_payload(run, payload)
        await self._record_step(
            run, 'step.started', {'capabilityId': run['capability_id']}
        )
        adapter = self._ADAPTERS.get(str(run.get('capability_id') or ''))
        if adapter is None:
            return await self._fail(
                run,
                EXECUTOR_NOT_AVAILABLE,
                'No executor is available for this capability yet.',
            )
        try:
            return await adapter(self, run, resolved)
        except Exception:
            return await self._fail(
                run,
                'EXECUTOR_ERROR',
                'The executor could not complete this run.',
            )

    async def execute_run(
        self,
        *,
        user_id: str,
        run_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run = await self.run_service._get_owned_run(user_id=user_id, run_id=run_id)
        return await self.execute_run_record(run, payload=payload)

    async def execute_run_dict(
        self, run: dict[str, Any], *, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Dispatch a single run dict (raw row or public shape)."""
        run_id = run.get('id')
        user_id = run.get('user_id') or run.get('userId')
        if run_id and user_id:
            return await self.execute_run(
                user_id=str(user_id), run_id=str(run_id), payload=payload
            )
        normalized = {
            'id': run_id,
            'user_id': user_id,
            'capability_id': run.get('capability_id') or run.get('capabilityId'),
            'status': run.get('status'),
        }
        return await self.execute_run_record(normalized, payload=payload)

    async def execute_queued_runs(
        self, *, user_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Claim and execute the user's queued runs."""
        queued = await self.run_service.list_runs(
            user_id=user_id, status='queued', limit=limit
        )
        results: list[dict[str, Any]] = []
        for item in queued:
            results.append(
                await self.execute_run(user_id=user_id, run_id=str(item['id']))
            )
        return results
