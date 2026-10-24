"""Conversation presence, proactive check-ins, and push registration."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..checkin_service import get_preferences, run_check_ins, save_preferences
from ..runtime import ai, db, push_service, settings
from ..schemas import PresencePreferencesRequest, PushTokenRequest
from ..security import expiry_iso

router = APIRouter(prefix="/api", tags=["presence"])

@router.get('/presence/preferences')
async def presence_preferences(request: Request):
    auth = await authenticate_request(
        request,
        db,
        settings,
        require_expected_owner_header=True,
    )
    return {'success': True, 'preferences': await get_preferences(db, auth.user['id'])}


@router.patch('/presence/preferences')
async def update_presence_preferences(payload: PresencePreferencesRequest, request: Request):
    # Enrolling in proactive check-ins is an account capability: a guest's
    # stored preference would otherwise be honored by the check-in worker
    # even though guest chat itself is capped and text-only.
    auth = await authenticate_request(
        request,
        db,
        settings,
        require_account=True,
        require_expected_owner_header=True,
    )
    preferences = await save_preferences(db, auth.user['id'], payload.model_dump())
    return {'success': True, 'preferences': preferences}


@router.post('/notifications/register')
async def register_push_token(payload: PushTokenRequest, request: Request):
    auth = await authenticate_request(
        request,
        db,
        settings,
        touch=False,
        require_account=True,
        require_expected_owner_header=True,
    )
    platform = payload.platform.lower()
    if platform not in {'ios', 'android'}:
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Push notifications are available only in the iOS and Android apps.'})
    session_installation = str(auth.session.get('device_id') or '').strip()
    if not session_installation or session_installation != payload.installationId:
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'error': 'This device session changed before push registration completed.',
                'code': 'PUSH_REGISTRATION_STALE',
                'staleAuth': True,
                'retryable': True,
            },
        )
    rows = await db.rpc(
        'mutate_push_registration_v1',
        {
            'p_user_id': auth.user['id'],
            'p_session_id': auth.session['id'],
            'p_session_token_hash': auth.session['token_hash'],
            'p_installation_id': session_installation,
            'p_platform': platform,
            'p_token': payload.token,
            'p_enabled': True,
            'p_session_expires_at': expiry_iso(days=settings.session_days),
        },
    )
    result = rows[0] if isinstance(rows, list) and len(rows) == 1 else None
    if not result or result.get('applied') is not True:
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'error': 'This device session changed before push registration completed.',
                'code': 'PUSH_REGISTRATION_STALE',
                'staleAuth': True,
                'retryable': True,
            },
        )
    return {'success': True}


@router.delete('/notifications/register')
async def unregister_push_token(request: Request):
    auth = await authenticate_request(
        request,
        db,
        settings,
        touch=False,
        require_expected_owner_header=True,
    )
    installation_id = str(auth.session.get('device_id') or '').strip()
    requested_installation = str(request.headers.get('x-installation-id') or '').strip()
    if requested_installation and requested_installation != installation_id:
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'error': 'This device session changed before push registration completed.',
                'code': 'PUSH_REGISTRATION_STALE',
                'staleAuth': True,
                'retryable': True,
            },
        )
    if not installation_id:
        return {'success': True}
    rows = await db.rpc(
        'mutate_push_registration_v1',
        {
            'p_user_id': auth.user['id'],
            'p_session_id': auth.session['id'],
            'p_session_token_hash': auth.session['token_hash'],
            'p_installation_id': installation_id,
            'p_platform': '',
            'p_token': '',
            'p_enabled': False,
            'p_session_expires_at': auth.session['expires_at'],
        },
    )
    result = rows[0] if isinstance(rows, list) and len(rows) == 1 else None
    if not result or result.get('applied') is not True:
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'error': 'This device session changed before push registration completed.',
                'code': 'PUSH_REGISTRATION_STALE',
                'staleAuth': True,
                'retryable': True,
            },
        )
    return {'success': True}


@router.get('/cron/check-ins')
async def check_in_cron(request: Request):
    expected = settings.cron_secret
    authorization = request.headers.get('authorization', '')
    if not expected or not hmac.compare_digest(authorization, f'Bearer {expected}'):
        return JSONResponse(status_code=401, content={'success': False, 'error': 'Unauthorized.'})
    summary = await run_check_ins(
        db,
        ai,
        push_service,
        batch_size=settings.check_in_batch_size,
    )
    return {'success': True, **summary}
