"""Account profile, terms, and deletion endpoints."""

from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request, public_user
from ..db import eq
from ..http import clear_session_cookie
from ..product_analytics import record_product_event
from ..runtime import db, settings
from ..schemas import DeleteAccountRequest, ProfileUpdateRequest, TermsAcceptanceRequest
from ..security import iso_now, verify_password

router = APIRouter(prefix="/api/account", tags=["account"])
logger = logging.getLogger("askcrump.account")

@router.patch('/profile')
async def update_profile(payload: ProfileUpdateRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    first_completion = not str(auth.user.get('full_name') or '').strip()
    full_name = payload.fullName.strip()
    if not full_name:
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Enter a valid name.'})
    await db.update('users', {'full_name': full_name, 'updated_at': iso_now()}, filters={'id': eq(auth.user['id'])})
    auth.user['full_name'] = full_name
    if first_completion:
        await record_product_event(
            db,
            user_id=auth.user['id'],
            event_name='OnboardingCompleted',
            event_key='initial-profile',
            request=request,
        )
    return {'success': True, 'user': public_user(auth.user)}


@router.post('/accept-terms')
async def accept_terms(payload: TermsAcceptanceRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    accepted_at = iso_now()
    await db.update('users', {
        'terms_accepted_at': accepted_at,
        'terms_version': payload.version,
        'updated_at': accepted_at,
    }, filters={'id': eq(auth.user['id'])})
    auth.user['terms_accepted_at'] = accepted_at
    auth.user['terms_version'] = payload.version
    return {'success': True, 'user': public_user(auth.user)}


@router.delete('')
async def delete_account(payload: DeleteAccountRequest, request: Request, response: Response):
    auth = await authenticate_request(request, db, settings)
    if payload.confirmation.strip().upper() != 'DELETE':
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Type DELETE to confirm.'})
    if not verify_password(payload.password, auth.user.get('password_hash')):
        return JSONResponse(status_code=401, content={'success': False, 'error': 'Password is incorrect.'})

    user_id = auth.user['id']
    stripe_customer_id = auth.user.get('stripe_customer_id')
    if settings.revenuecat_secret_api_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=20) as client:
                await client.delete(
                    f"https://api.revenuecat.com/v1/subscribers/{quote(user_id, safe='')}",
                    headers={'Authorization': f'Bearer {settings.revenuecat_secret_api_key}'},
                )
        except Exception:
            logger.exception('RevenueCat customer cleanup failed during account deletion')
    if stripe_customer_id and settings.stripe_secret_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=20) as client:
                await client.delete(
                    f'https://api.stripe.com/v1/customers/{stripe_customer_id}',
                    auth=(settings.stripe_secret_key, ''),
                )
        except Exception:
            logger.exception('Stripe customer cleanup failed during account deletion')

    await db.rpc('delete_user_account', {'p_user_id': user_id})
    clear_session_cookie(response)
    return {'success': True, 'message': 'Your Ask Crump account and conversation data were deleted.'}
