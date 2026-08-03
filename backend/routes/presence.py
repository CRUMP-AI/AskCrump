"""Conversation presence, proactive check-ins, and push registration."""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..checkin_service import get_preferences, run_check_ins, save_preferences
from ..db import eq
from ..runtime import ai, db, push_service, settings
from ..schemas import PresencePreferencesRequest, PushTokenRequest
from ..security import iso_now

router = APIRouter(prefix="/api", tags=["presence"])

@router.get('/presence/preferences')
async def presence_preferences(request: Request):
    auth = await authenticate_request(request, db, settings)
    return {'success': True, 'preferences': await get_preferences(db, auth.user['id'])}


@router.patch('/presence/preferences')
async def update_presence_preferences(payload: PresencePreferencesRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    preferences = await save_preferences(db, auth.user['id'], payload.model_dump())
    return {'success': True, 'preferences': preferences}


@router.post('/notifications/register')
async def register_push_token(payload: PushTokenRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    platform = payload.platform.lower()
    if platform not in {'ios', 'android'}:
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Push notifications are available only in the iOS and Android apps.'})
    now = iso_now()
    await db.delete('push_tokens', filters={'platform': eq(platform), 'token': eq(payload.token)})
    await db.upsert('push_tokens', {
        'user_id': auth.user['id'],
        'installation_id': payload.installationId,
        'platform': platform,
        'token': payload.token,
        'enabled': True,
        'updated_at': now,
        'last_used_at': now,
    }, on_conflict='user_id,installation_id')
    return {'success': True}


@router.delete('/notifications/register')
async def unregister_push_token(request: Request):
    auth = await authenticate_request(request, db, settings)
    installation_id = request.headers.get('x-installation-id', '')[:200]
    if installation_id:
        await db.update(
            'push_tokens',
            {'enabled': False, 'updated_at': iso_now()},
            filters={'user_id': eq(auth.user['id']), 'installation_id': eq(installation_id)},
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
