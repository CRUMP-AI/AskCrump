"""Account profile, terms, and deletion endpoints."""

from __future__ import annotations

import logging
from typing import Any
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

TERMINAL_SUBSCRIPTION_STATUSES = {'canceled', 'expired', 'incomplete_expired'}


class BillingCancellationUnconfirmed(RuntimeError):
    """Raised when deleting local identity could orphan an open web subscription."""


def requires_stripe_cancellation_confirmation(user: dict[str, Any]) -> bool:
    customer_id = str(user.get('stripe_customer_id') or '')
    status = str(user.get('subscription_status') or 'inactive').lower()
    provider = str(user.get('subscription_provider') or '').lower() or None
    subscription_id = str(user.get('stripe_subscription_id') or '')
    if provider not in {None, 'stripe'} and not subscription_id.startswith('sub_'):
        return False
    has_subscription_evidence = bool(
        subscription_id.startswith('sub_')
        or provider == 'stripe'
        or (provider is None and status not in TERMINAL_SUBSCRIPTION_STATUSES | {'inactive'})
    )
    return bool(
        customer_id
        and has_subscription_evidence
        and status not in TERMINAL_SUBSCRIPTION_STATUSES
    )


async def delete_stripe_customer(user: dict[str, Any]) -> bool:
    """Delete a Stripe customer, requiring proof when a web subscription is open."""
    customer_id = str(user.get('stripe_customer_id') or '')
    if not customer_id:
        return False
    confirmation_required = requires_stripe_cancellation_confirmation(user)
    if not settings.stripe_secret_key:
        if confirmation_required:
            raise BillingCancellationUnconfirmed()
        logger.warning('Stripe cleanup skipped during account deletion because billing is unavailable')
        return False

    import httpx

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            stripe_response = await client.delete(
                f'https://api.stripe.com/v1/customers/{quote(customer_id, safe="")}',
                auth=(settings.stripe_secret_key, ''),
            )
    except httpx.HTTPError as exc:
        logger.exception('Stripe customer cleanup failed during account deletion')
        if confirmation_required:
            raise BillingCancellationUnconfirmed() from exc
        return False

    deleted = False
    if 200 <= stripe_response.status_code < 300:
        try:
            result = stripe_response.json()
        except (ValueError, AttributeError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        deleted = bool(
            result.get('deleted') is True
            and str(result.get('id') or '') == customer_id
        )
    if deleted:
        return True

    logger.error(
        'Stripe customer cleanup was not confirmed status=%s',
        stripe_response.status_code,
    )
    if confirmation_required:
        raise BillingCancellationUnconfirmed()
    return False


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
    try:
        await delete_stripe_customer(auth.user)
    except BillingCancellationUnconfirmed:
        return JSONResponse(
            status_code=502,
            content={
                'success': False,
                'error': (
                    'Ask Crump could not confirm that your web subscription stopped, so no account '
                    'data was deleted. Open Plan & credits to manage billing, or try again shortly.'
                ),
                'code': 'BILLING_CANCELLATION_UNCONFIRMED',
            },
        )

    if settings.revenuecat_secret_api_key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=20) as client:
                revenuecat_response = await client.delete(
                    f"https://api.revenuecat.com/v1/subscribers/{quote(user_id, safe='')}",
                    headers={'Authorization': f'Bearer {settings.revenuecat_secret_api_key}'},
                )
                if revenuecat_response.status_code >= 400 and revenuecat_response.status_code != 404:
                    logger.error(
                        'RevenueCat customer cleanup was not confirmed status=%s',
                        revenuecat_response.status_code,
                    )
        except Exception:
            logger.exception('RevenueCat customer cleanup failed during account deletion')

    await db.rpc('delete_user_account', {'p_user_id': user_id})
    clear_session_cookie(response)
    return {
        'success': True,
        'message': (
            'Your Ask Crump account and conversation data were deleted. '
            'Apple or Google subscriptions must be canceled separately in the applicable store.'
        ),
    }
