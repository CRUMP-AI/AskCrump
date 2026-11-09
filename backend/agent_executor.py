"""Agent run executor and the Today brief composer.

The run ledger (``agent_run_service``) owns lifecycle state; this module
owns doing the work. An executor claims a queued run, moves it through
``running`` to a terminal status, and appends every transition to the
ledger through the run service's own step/status methods, so the Tasks
view and the audit trail keep reading from one store.

Adapters are deliberately narrow. ``gmail.search``, ``gmail.read``, and
``calendar.list`` run against the signed-in user's Google connection
and fail honestly with ``CONNECTION_REQUIRED`` when there is none.
``calendar.create`` dispatches to the connector's event creation with
the run's approved payload, and its result summary carries only the
created event's id, summary, and start/end. ``agent.today_brief``
composes the Today brief from real service calls only, and
``agent.morning_brief`` composes that same brief for a scheduled run.
``browser.read``
dispatches to the browser agent's guarded page fetch, and the Gmail
write capabilities (``gmail.draft``, ``gmail.send``) dispatch to the
Gmail write adapter, which re-checks the granted scopes before any
provider call. ``memory.list`` and ``memory.forget`` run against the
existing intelligence service's owner-scoped memory store. Every other registered capability fails with
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
MEMORY_NOT_FOUND = 'MEMORY_NOT_FOUND'
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


def _default_intelligence_service() -> Any | None:
    """Return the process-scoped intelligence service from runtime."""
    try:
        from .runtime import intelligence

        return intelligence
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
        intelligence_service: Any | None = None,
    ) -> None:
        self.run_service = run_service
        self.google_connector = google_connector
        self.intelligence_service = intelligence_service

    # -- connector ------------------------------------------------------

    def _connector(self) -> Any | None:
        if self.google_connector is not None:
            return self.google_connector
        self.google_connector = _default_google_connector()
        return self.google_connector

    def _intelligence_service(self) -> Any | None:
        if self.intelligence_service is not None:
            return self.intelligence_service
        self.intelligence_service = _default_intelligence_service()
        return self.intelligence_service

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

    async def _run_gmail_read(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        message_id = str(
            payload.get('messageId') or payload.get('message_id') or ''
        ).strip()
        if not message_id:
            return await self._fail(
                run,
                'INVALID_RUN_INPUT',
                'This run is missing the message id, so it cannot be executed.',
            )
        try:
            access_token = await self._access_token(run['user_id'])
            connector = self._connector()
            message = await connector.get_message(access_token, message_id)
        except ConnectionRequiredError as exc:
            return await self._fail(run, CONNECTION_REQUIRED, exc.message)
        except GoogleConnectorError as exc:
            return await self._fail(run, exc.code, exc.message)
        message = message if isinstance(message, dict) else {}
        # The summary carries the same fields as a search result and
        # nothing else: a message body never lands in the ledger, and
        # every field is length-fenced like the search summary.
        item = {
            key: message.get(key)
            for key in ('id', 'from', 'subject', 'snippet', 'date')
        }
        summary = {
            'kind': 'gmail.read',
            'message': _fence_summary_items([item])[0],
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

    async def _run_calendar_create(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        event_title = str(payload.get('summary') or '').strip()
        start = str(payload.get('start') or '').strip()
        end = str(payload.get('end') or '').strip()
        if not event_title or not start or not end:
            return await self._fail(
                run,
                'INVALID_RUN_INPUT',
                'This run is missing the event summary, start, or end, '
                'so it cannot be executed.',
            )
        # Approval-gated runs reach here with the payload frozen on the
        # approved action; dispatch exactly those fields and no others.
        event_fields: dict[str, Any] = {
            'summary': event_title,
            'start': start,
            'end': end,
        }
        attendees = payload.get('attendees')
        if isinstance(attendees, list):
            event_fields['attendees'] = [
                str(item) for item in attendees if str(item or '').strip()
            ]
        try:
            access_token = await self._access_token(run['user_id'])
            connector = self._connector()
            created = await connector.create_event(access_token, **event_fields)
        except ConnectionRequiredError as exc:
            return await self._fail(run, CONNECTION_REQUIRED, exc.message)
        except GoogleConnectorError as exc:
            return await self._fail(run, exc.code, exc.message)
        created = created if isinstance(created, dict) else {}
        summary = {
            'kind': 'calendar.create',
            'eventId': str(created.get('id') or ''),
            'summary': _truncate(str(created.get('summary') or event_title)),
            'start': str(created.get('start') or start),
            'end': str(created.get('end') or end),
        }
        return await self._succeed(run, summary)

    async def _run_brief(
        self, run: dict[str, Any], kind: str
    ) -> dict[str, Any]:
        brief = await build_today_brief(
            run['user_id'],
            run_service=self.run_service,
            google_connector=self._connector(),
        )
        calendar = brief.get('calendar')
        inbox = brief.get('inboxHighlights')
        summary = {
            'kind': kind,
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

    async def _run_today_brief(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._run_brief(run, 'agent.today_brief')

    async def _run_morning_brief(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        return await self._run_brief(run, 'agent.morning_brief')

    async def _run_memory_list(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        service = self._intelligence_service()
        if service is None:
            return await self._fail(
                run,
                EXECUTOR_NOT_AVAILABLE,
                'No executor is available for this capability yet.',
            )
        try:
            limit = int(payload.get('limit') or 100)
        except (TypeError, ValueError):
            limit = 100
        memories = await service.list_memories(
            run['user_id'], limit=max(1, min(limit, 200))
        )
        # Redaction discipline: only id, kind, and creation time cross
        # into the run summary. Memory content and every other stored
        # field stay in the intelligence service.
        items = [
            {
                'id': item.get('id'),
                'kind': item.get('kind'),
                'created_at': item.get('created_at'),
            }
            for item in memories
            if isinstance(item, dict)
        ]
        summary = {
            'kind': 'memory.list',
            'count': len(items),
            'memories': _fence_summary_items(items),
        }
        return await self._succeed(run, summary)

    async def _run_memory_forget(
        self, run: dict[str, Any], payload: dict[str, Any]
    ) -> dict[str, Any]:
        memory_id = str(
            payload.get('memoryId') or payload.get('memory_id') or ''
        ).strip()
        if not memory_id:
            return await self._fail(
                run,
                'INVALID_RUN_INPUT',
                'This run is missing the memory id, so it cannot be executed.',
            )
        service = self._intelligence_service()
        if service is None:
            return await self._fail(
                run,
                EXECUTOR_NOT_AVAILABLE,
                'No executor is available for this capability yet.',
            )
        deleted = await service.delete_memory(run['user_id'], memory_id)
        if not deleted:
            return await self._fail(
                run,
                MEMORY_NOT_FOUND,
                'No memory with that id was found for this account.',
            )
        summary = {
            'kind': 'memory.forget',
            'memoryId': memory_id,
            'deleted': True,
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
        'gmail.read': _run_gmail_read,
        'calendar.list': _run_calendar_list,
        'calendar.create': _run_calendar_create,
        'agent.today_brief': _run_today_brief,
        'agent.morning_brief': _run_morning_brief,
        'memory.list': _run_memory_list,
        'memory.forget': _run_memory_forget,
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
