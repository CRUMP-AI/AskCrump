"""Connected-account endpoints for Google (Gmail and Calendar).

Status is readable whether or not the deployment is configured, so the
client can render a connection card either way. Connecting fails
closed when the OAuth client or the token vault is not configured.
The executor endpoints below are the Slice 1 read surface: they run
``gmail.search`` and ``calendar.list`` against the signed-in user's own
connection and return ``CONNECTION_REQUIRED`` when there is none.
Creating events and sending mail stay behind the approval-gated
executor in the next increment.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth_service import authenticate_request
from ..google_connector import (
    ConnectionRequiredError,
    GoogleConnector,
    GoogleConnectorError,
)
from ..google_vault import GoogleVault, GoogleVaultError
from ..runtime import db, settings

router = APIRouter(tags=['connected-apps'])

NO_STORE = {'Cache-Control': 'private, no-store'}


def get_connector() -> GoogleConnector:
    return GoogleConnector(settings=settings, db=db, vault=GoogleVault())


def _error(message: str, code: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={'success': False, 'error': message, 'code': code},
        headers=NO_STORE,
    )


def _connector_error(exc: GoogleConnectorError) -> JSONResponse:
    return _error(exc.message, exc.code, exc.status_code)


async def _authenticate(request: Request):
    return await authenticate_request(
        request,
        db,
        settings,
        require_account=True,
        require_expected_owner_header=True,
    )


@router.get('/api/connections/google/status')
async def google_status(request: Request):
    auth = await _authenticate(request)
    connector = get_connector()
    if not connector.oauth_configured:
        return JSONResponse(
            content={
                'success': True,
                'configured': False,
                'connected': False,
                'accounts': [],
            },
            headers=NO_STORE,
        )
    status = await connector.status(auth.user['id'])
    return JSONResponse(
        content={'success': True, 'configured': True, **status},
        headers=NO_STORE,
    )


@router.get('/api/connections/google/connect')
async def google_connect(request: Request):
    auth = await _authenticate(request)
    connector = get_connector()
    if not connector.oauth_configured:
        return _error(
            'Google connections are not configured yet.',
            'GOOGLE_NOT_CONFIGURED',
            503,
        )
    try:
        url = connector.authorization_url(auth.user['id'])
    except GoogleVaultError as exc:
        return _error(exc.message, exc.code, exc.status_code)
    except GoogleConnectorError as exc:
        return _connector_error(exc)
    return JSONResponse(
        content={'success': True, 'authorizationUrl': url},
        headers=NO_STORE,
    )


@router.get('/api/connections/google/callback')
async def google_callback(request: Request):
    connector = get_connector()
    code = str(request.query_params.get('code') or '')
    state = str(request.query_params.get('state') or '')
    failure = RedirectResponse(
        url=f"{settings.app_url}/app?google=failed", status_code=302
    )
    if not code or not state:
        return failure
    try:
        user_id = connector.state_user_id(state)
        await connector.exchange_code(code, user_id=user_id, state=state)
    except (GoogleConnectorError, GoogleVaultError):
        return failure
    return RedirectResponse(
        url=f"{settings.app_url}/app?google=connected", status_code=302
    )


@router.post('/api/connections/google/disconnect')
async def google_disconnect(request: Request):
    auth = await _authenticate(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    account_email = str(payload.get('accountEmail') or '').strip().lower() or None
    connector = get_connector()
    status = await connector.disconnect(auth.user['id'], account_email)
    return JSONResponse(
        content={'success': True, **status},
        headers=NO_STORE,
    )


@router.post('/api/agent/google/search')
async def google_search(request: Request):
    auth = await _authenticate(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    query = str(payload.get('query') or '').strip()
    if not query:
        return _error('A search query is required.', 'INVALID_GMAIL_SEARCH', 400)
    try:
        max_results = int(payload.get('maxResults') or 10)
    except (TypeError, ValueError):
        return _error('A search query is required.', 'INVALID_GMAIL_SEARCH', 400)
    connector = get_connector()
    try:
        access_token = await connector.access_token_for(auth.user['id'])
        messages = await connector.search_messages(
            access_token, query, max(1, min(max_results, 50))
        )
    except ConnectionRequiredError as exc:
        return _connector_error(exc)
    except GoogleVaultError as exc:
        return _error(exc.message, exc.code, exc.status_code)
    except GoogleConnectorError as exc:
        return _connector_error(exc)
    return JSONResponse(
        content={'success': True, 'messages': messages},
        headers=NO_STORE,
    )


@router.post('/api/agent/google/calendar')
async def google_calendar(request: Request):
    auth = await _authenticate(request)
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    payload = payload if isinstance(payload, dict) else {}
    connector = get_connector()
    try:
        access_token = await connector.access_token_for(auth.user['id'])
        events = await connector.list_events(
            access_token,
            time_min=str(payload.get('timeMin') or '') or None,
            time_max=str(payload.get('timeMax') or '') or None,
        )
    except ConnectionRequiredError as exc:
        return _connector_error(exc)
    except GoogleVaultError as exc:
        return _error(exc.message, exc.code, exc.status_code)
    except GoogleConnectorError as exc:
        return _connector_error(exc)
    return JSONResponse(
        content={'success': True, 'events': events},
        headers=NO_STORE,
    )
