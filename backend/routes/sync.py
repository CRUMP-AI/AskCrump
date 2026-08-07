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
    credits = status.get('credits') or {'balance': 0}
    balance = max(0, int(credits.get('balance') or 0))
    daily_limit = int(status['limit'])
    # Older clients compare usage.messages >= limits.messages before sending.
    # Extend the effective ceiling by the durable credit balance so 5.0 and
    # earlier shells continue seamlessly until both included usage and credits
    # are exhausted.
    effective_limit = -1 if daily_limit < 0 else daily_limit + balance
    included_remaining = int(status['remaining'])
    return {
        'success': True,
        'tier': status['tier'],
        'usage': {'messages': status['used']},
        'limits': {'messages': effective_limit},
        'daily': {
            'tier': status['tier'],
            'used': status['used'],
            'limit': daily_limit,
            'remaining': included_remaining,
        },
        'credits': credits,
        'requiresPurchase': daily_limit >= 0 and included_remaining <= 0 and balance <= 0,
        'nextRequestSource': (
            'included'
            if daily_limit < 0 or included_remaining > 0
            else 'credits'
            if balance > 0
            else 'purchase'
        ),
    }
