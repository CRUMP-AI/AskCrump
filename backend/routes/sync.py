"""Cross-device synchronization and usage endpoints."""

from __future__ import annotations

import hmac
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request, is_guest_user, touch_authenticated_session
from ..rate_limit import enforce_user_rate_limit
from ..runtime import db, settings
from ..security import iso_now
from ..sync_service import pull_sync, push_sync
from ..usage_service import current_usage

router = APIRouter(prefix="/api", tags=["synchronization"])
SYNC_OWNER_HEADER = 'x-ask-crump-sync-owner'


def _sync_owner_mismatch(request: Request, authenticated_user_id: str) -> JSONResponse | None:
    """Refuse a request captured for a different browser-side account.

    The HttpOnly session cookie can change in another tab after a sync snapshot
    is queued. Binding that snapshot to the client-observed owner prevents the
    old account's queue from being read or written under the new session.
    """
    headers = getattr(request, 'headers', {})
    expected_owner = str(headers.get(SYNC_OWNER_HEADER, '') or '').strip()
    actual_owner = str(authenticated_user_id or '').strip()
    try:
        expected_bytes = UUID(expected_owner).bytes
        actual_bytes = UUID(actual_owner).bytes
    except (AttributeError, TypeError, ValueError):
        expected_bytes = b''
        actual_bytes = b'\x01'
    if hmac.compare_digest(expected_bytes, actual_bytes):
        return None
    return JSONResponse(
        status_code=409,
        content={
            'success': False,
            'code': 'SYNC_OWNER_MISMATCH',
            'staleAuth': True,
            'error': 'The signed-in account changed before synchronization began. Retry under the current account.',
            'queued': True,
            'retryable': True,
        },
    )


@router.get('/sync/pull')
async def sync_pull(request: Request, since: str | None = None):
    auth = await authenticate_request(request, db, settings, touch=False)
    if mismatch := _sync_owner_mismatch(request, auth.user['id']):
        return mismatch
    await touch_authenticated_session(db, settings, auth)
    # Capture the read watermark before querying. A write that lands while the
    # query is in flight must remain newer than this cursor so the next
    # incremental pull cannot skip it.
    server_time = iso_now()
    data = await pull_sync(db, auth.user['id'], since)
    return {'success': True, 'serverTime': server_time, 'data': data}


@router.post('/sync/push')
async def sync_push(request: Request):
    auth = await authenticate_request(request, db, settings, touch=False)
    if mismatch := _sync_owner_mismatch(request, auth.user['id']):
        return mismatch
    await touch_authenticated_session(db, settings, auth)
    guest = is_guest_user(auth.user)
    if guest:
        # Sync stays open to guests (their conversation must survive to
        # signup), but push frequency is bounded on top of the payload
        # limits push_sync enforces for guests.
        await enforce_user_rate_limit(
            db,
            user_id=auth.user['id'],
            action='guest_sync_push',
            limit=30,
            window_seconds=3600,
        )
    payload = await request.json()
    result = await push_sync(db, auth.user['id'], payload if isinstance(payload, dict) else {}, is_guest=guest)
    if result.get('rejectionCode') == 'GUEST_SYNC_BATCH_TOO_LARGE':
        return JSONResponse(
            status_code=413,
            content={
                'success': False,
                'code': 'GUEST_SYNC_BATCH_TOO_LARGE',
                'error': 'This guest sync batch is too large. Your work is still queued and will be sent in smaller batches.',
                'queued': True,
                'retryable': False,
                'serverTime': iso_now(),
                'limits': result.get('limits'),
                'received': result.get('received'),
            },
        )
    rejected = result.get('rejected')
    if rejected:
        settings_rejections = [
            item
            for item in rejected
            if isinstance(item, dict) and item.get('scope') == 'settings'
        ]
        authority_changed = all(
            isinstance(item, dict) and item.get('reason') == 'not_guest'
            for item in rejected
        )
        if authority_changed:
            settings_only = len(settings_rejections) == len(rejected)
            return JSONResponse(
                status_code=409,
                content={
                    'success': False,
                    'code': (
                        'GUEST_SETTINGS_AUTHORITY_CHANGED'
                        if settings_only
                        else 'GUEST_SYNC_AUTHORITY_CHANGED'
                    ),
                    'error': (
                        'Your account changed while these settings were syncing. '
                        'They are still queued; retry after sign-in finishes.'
                        if settings_only
                        else 'Your account changed while this guest sync was finishing. '
                        'Your work is still queued; retry after sign-in finishes.'
                    ),
                    'queued': True,
                    'retryable': True,
                    'serverTime': iso_now(),
                    **result,
                },
            )
        if settings_rejections and len(settings_rejections) == len(rejected):
            settings_reason = str(settings_rejections[0].get('reason') or '')
            if settings_reason == 'guest_mode_disabled':
                code = 'GUEST_MODE_DISABLED'
                error = (
                    'Guest access is temporarily unavailable. '
                    'Your settings are still queued on this device.'
                )
                retryable = False
            else:
                code = 'GUEST_SETTINGS_NOT_SAVED'
                error = (
                    'These guest settings could not be saved. '
                    'They are still queued on this device.'
                )
                retryable = False
            return JSONResponse(
                status_code=409,
                content={
                    'success': False,
                    'code': code,
                    'error': error,
                    'queued': True,
                    'retryable': retryable,
                    'serverTime': iso_now(),
                    **result,
                },
            )
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'code': 'GUEST_SYNC_NOT_SAVED',
                'error': 'This guest sync could not be saved under the current preview access or storage limits.',
                'queued': True,
                'retryable': False,
                'serverTime': iso_now(),
                **result,
            },
        )
    return {'success': True, 'serverTime': iso_now(), **result}


@router.get('/usage/check')
async def usage_check(request: Request):
    auth = await authenticate_request(
        request, db, settings, require_expected_owner_header=True
    )
    status = await current_usage(db, auth.user, settings)
    credits = status.get('credits') or {'balance': 0}
    balance = max(0, int(credits.get('balance') or 0))
    daily_limit = int(status['limit'])
    free_allowance = status.get('freeMessageAllowance')
    free_text = isinstance(free_allowance, dict)
    # Older clients compare usage.messages >= limits.messages before sending.
    # Free accounts are intentionally subscription-gated at five rolling-24h
    # text messages: credits cannot extend this ceiling. Paid plans retain the
    # existing included-plus-credit compatibility behavior.
    effective_limit = (
        daily_limit
        if free_text
        else -1
        if daily_limit < 0
        else daily_limit + balance
    )
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
        'freeMessageAllowance': free_allowance,
        'credits': credits,
        'requiresPurchase': (
            included_remaining <= 0
            if free_text
            else daily_limit >= 0 and included_remaining <= 0 and balance <= 0
        ),
        'upgradeRequired': free_text and included_remaining <= 0,
        'requiredTier': 'professional' if free_text and included_remaining <= 0 else None,
        'nextRequestSource': (
            'included'
            if daily_limit < 0 or included_remaining > 0
            else 'subscription'
            if free_text
            else 'credits'
            if balance > 0
            else 'purchase'
        ),
    }
