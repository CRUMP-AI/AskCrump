"""Cross-device synchronization and usage endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..auth_service import authenticate_request
from ..runtime import db, settings
from ..security import iso_now
from ..sync_service import pull_sync, push_sync
from ..usage_service import current_usage

router = APIRouter(prefix="/api", tags=["synchronization"])

@router.get('/sync/pull')
async def sync_pull(request: Request, since: str | None = None):
    auth = await authenticate_request(request, db, settings)
    data = await pull_sync(db, auth.user['id'], since)
    return {'success': True, 'serverTime': iso_now(), 'data': data}


@router.post('/sync/push')
async def sync_push(request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    result = await push_sync(db, auth.user['id'], payload if isinstance(payload, dict) else {})
    return {'success': True, 'serverTime': iso_now(), **result}


@router.get('/usage/check')
async def usage_check(request: Request):
    auth = await authenticate_request(request, db, settings)
    status = await current_usage(db, auth.user, settings)
    return {
        'success': True,
        'tier': status['tier'],
        'usage': {'messages': status['used']},
        'limits': {'messages': status['limit']},
        'daily': status,
    }
