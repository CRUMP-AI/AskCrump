"""Account profile, terms, and deletion endpoints."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ..account_deletion_service import VideoFenceRecoveryState
from ..auth_service import authenticate_request, public_user
from ..db import eq
from ..http import clear_session_cookie
from ..product_analytics import record_product_event
from ..runtime import account_deletions, db, settings
from ..schemas import (
    AIDataSharingConsentRequest,
    DeleteAccountRequest,
    ProfileUpdateRequest,
    TermsAcceptanceRequest,
)
from ..security import iso_now, verify_password

router = APIRouter(prefix="/api/account", tags=["account"])
logger = logging.getLogger("askcrump.account")

TERMINAL_SUBSCRIPTION_STATUSES = {'canceled', 'expired', 'incomplete_expired'}


class BillingCancellationUnconfirmed(RuntimeError):
    """Raised when deleting local identity could orphan an open web subscription."""


def _video_fence_recovery_requires_operator(
    recovery: VideoFenceRecoveryState,
) -> bool:
    """Separate foreign/unknown ownership from safe durable retry states."""
    return recovery in {
        VideoFenceRecoveryState.UNCONFIRMED,
        VideoFenceRecoveryState.NOT_OWNER,
        VideoFenceRecoveryState.JOB_CONFLICT,
    }


def _stripe_response_confirms_deleted(response: Any, customer_id: str) -> bool:
    if response is None or not 200 <= int(getattr(response, 'status_code', 0)) < 300:
        return False
    try:
        result = response.json()
    except (ValueError, AttributeError):
        result = {}
    return bool(
        isinstance(result, dict)
        and result.get('deleted') is True
        and str(result.get('id') or '') == customer_id
    )


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

    customer_url = f'https://api.stripe.com/v1/customers/{quote(customer_id, safe="")}'
    stripe_response = None
    delete_error: httpx.HTTPError | None = None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            stripe_response = await client.delete(
                customer_url,
                auth=(settings.stripe_secret_key, ''),
            )
    except httpx.HTTPError as exc:
        delete_error = exc
        logger.exception('Stripe customer cleanup failed during account deletion')

    if _stripe_response_confirms_deleted(stripe_response, customer_id):
        return True

    # A previous deletion attempt may have succeeded before a later local
    # cleanup failed. Stripe keeps a retrievable tombstone for deleted
    # customers, so confirm that exact identity before allowing a retry.
    if confirmation_required:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                lookup_response = await client.get(
                    customer_url,
                    auth=(settings.stripe_secret_key, ''),
                )
            if _stripe_response_confirms_deleted(lookup_response, customer_id):
                return True
        except httpx.HTTPError:
            logger.exception('Stripe customer deletion lookup failed during account deletion')

    logger.error(
        'Stripe customer cleanup was not confirmed status=%s',
        getattr(stripe_response, 'status_code', 'transport-error'),
    )
    if confirmation_required:
        raise BillingCancellationUnconfirmed() from delete_error
    return False


def deletion_pending_response(*, code: str) -> JSONResponse:
    response = JSONResponse(
        status_code=202,
        content={
            'success': True,
            'pending': True,
            'message': (
                'Your deletion request is secured and this account is no longer available. '
                'Ask Crump is retrying provider and private storage cleanup in the background; no further '
                'action is required. Any confirmed web subscription cancellation remains '
                'effective. Apple or Google subscriptions must still be canceled in the '
                'applicable store.'
            ),
            'code': code,
        },
    )
    clear_session_cookie(response)
    return response


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


@router.post('/ai-data-sharing-consent')
async def accept_ai_data_sharing_consent(
    payload: AIDataSharingConsentRequest,
    request: Request,
):
    auth = await authenticate_request(request, db, settings)
    accepted_at = iso_now()
    values = {
        'ai_data_sharing_consent_at': accepted_at,
        'ai_data_sharing_consent_version': payload.version,
        'ai_data_sharing_consent_revoked_at': None,
        'ai_data_sharing_consent_updated_at': accepted_at,
        'updated_at': accepted_at,
    }
    await db.update('users', values, filters={'id': eq(auth.user['id'])})
    auth.user.update(values)
    return {'success': True, 'user': public_user(auth.user)}


@router.delete('/ai-data-sharing-consent')
async def withdraw_ai_data_sharing_consent(request: Request):
    auth = await authenticate_request(request, db, settings)
    updated_at = iso_now()
    values = {
        'ai_data_sharing_consent_revoked_at': (
            updated_at
            if auth.user.get('ai_data_sharing_consent_at')
            and auth.user.get('ai_data_sharing_consent_version')
            else None
        ),
        'ai_data_sharing_consent_updated_at': updated_at,
        'updated_at': updated_at,
    }
    await db.update('users', values, filters={'id': eq(auth.user['id'])})
    auth.user.update(values)
    return {'success': True, 'user': public_user(auth.user)}


@router.delete('')
async def delete_account(payload: DeleteAccountRequest, request: Request, response: Response):
    auth = await authenticate_request(request, db, settings)
    if payload.confirmation.strip().upper() != 'DELETE':
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Type DELETE to confirm.'})
    if not verify_password(payload.password, auth.user.get('password_hash')):
        return JSONResponse(status_code=401, content={'success': False, 'error': 'Password is incorrect.'})

    user_id = auth.user['id']
    deletion_token = str(uuid4())
    try:
        # A reserved start conflicts *without* creating a fence or touching
        # billing. A successful token-owned fence excludes new dispatches.
        video_starts_settled = await account_deletions.confirm_video_fence(
            user_id=user_id,
            operation_token=deletion_token,
        )
    except Exception:
        logger.error('Video account-deletion fence is unavailable')
        recovery = await account_deletions.recover_video_fence(
            user_id=user_id,
            operation_token=deletion_token,
        )
        recovery_required = _video_fence_recovery_requires_operator(recovery)
        return JSONResponse(
            status_code=503,
            content={
                'success': False,
                'error': (
                    'Account deletion could not be reconciled. Please contact support before '
                    'starting another video.'
                    if recovery_required
                    else 'Account deletion is temporarily unavailable. No account data was deleted.'
                ),
                'code': (
                    'ACCOUNT_DELETION_RECOVERY_REQUIRED'
                    if recovery_required
                    else 'ACCOUNT_DELETION_FENCE_UNAVAILABLE'
                ),
            },
        )
    if not video_starts_settled:
        stale_recovery = await account_deletions.recover_stale_orphan_video_fence(
            user_id=user_id,
        )
        if stale_recovery in {
            VideoFenceRecoveryState.ABANDONED,
            VideoFenceRecoveryState.RELEASED,
            VideoFenceRecoveryState.ALREADY_RELEASED,
        }:
            try:
                video_starts_settled = await account_deletions.confirm_video_fence(
                    user_id=user_id,
                    operation_token=deletion_token,
                )
            except Exception:
                logger.error('Replacement video account-deletion fence is unavailable')
                recovery = await account_deletions.recover_video_fence(
                    user_id=user_id,
                    operation_token=deletion_token,
                )
                recovery_required = _video_fence_recovery_requires_operator(recovery)
                return JSONResponse(
                    status_code=503,
                    content={
                        'success': False,
                        'error': (
                            'Account deletion could not be reconciled. Please contact support '
                            'before starting another video.'
                            if recovery_required
                            else 'Account deletion is temporarily unavailable. No account data '
                            'was deleted.'
                        ),
                        'code': (
                            'ACCOUNT_DELETION_RECOVERY_REQUIRED'
                            if recovery_required
                            else 'ACCOUNT_DELETION_FENCE_UNAVAILABLE'
                        ),
                    },
                )
    if not video_starts_settled:
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'error': 'A video request or account deletion is settling. Please retry shortly.',
                'code': 'VIDEO_START_SETTLING',
            },
        )

    try:
        await delete_stripe_customer(auth.user)
    except BillingCancellationUnconfirmed:
        release_result = await account_deletions.recover_video_fence(
            user_id=user_id,
            operation_token=deletion_token,
        )
        if release_result not in {
            VideoFenceRecoveryState.RELEASED,
            VideoFenceRecoveryState.ALREADY_RELEASED,
        }:
            logger.error('Account-deletion fence release could not be confirmed after billing failure')
            recovery_required = _video_fence_recovery_requires_operator(
                release_result
            )
            return JSONResponse(
                status_code=503,
                content={
                    'success': False,
                    'error': (
                        'Account deletion did not complete. Please contact support before '
                        'starting another video.'
                        if recovery_required
                        else 'Account deletion is temporarily unavailable. Its durable state '
                        'will be retried safely.'
                    ),
                    'code': (
                        'ACCOUNT_DELETION_RECOVERY_REQUIRED'
                        if recovery_required
                        else 'ACCOUNT_DELETION_FENCE_UNAVAILABLE'
                    ),
                },
            )
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

    try:
        deletion_job = await account_deletions.begin(
            user_id=user_id,
            operation_token=deletion_token,
        )
    except Exception:
        logger.exception('Durable account deletion fence could not be confirmed')
        recovery = await account_deletions.recover_video_fence(
            user_id=user_id,
            operation_token=deletion_token,
        )
        # A recent exact-token job, an established users fence, or completed
        # deletion remains owned by the durable worker. Only an ownership or
        # confirmation conflict needs operator intervention here.
        recovery_required = _video_fence_recovery_requires_operator(recovery)
        return JSONResponse(
            status_code=503,
            content={
                'success': False,
                'error': (
                    'Ask Crump could not reconcile which deletion request owns the account. '
                    'Please contact support before starting another video.'
                    if recovery_required
                    else 'Ask Crump could not finish starting deletion. Its durable state '
                    'remains safe to retry, and any confirmed web subscription cancellation '
                    'remains effective. Try again shortly.'
                ),
                'code': (
                    'ACCOUNT_DELETION_RECOVERY_REQUIRED'
                    if recovery_required
                    else 'ACCOUNT_DELETION_FENCE_UNAVAILABLE'
                ),
            },
        )

    try:
        progress = await account_deletions.process(deletion_job)
    except Exception:
        logger.exception('Durable account deletion will continue after request failure')
        return deletion_pending_response(code='ACCOUNT_DELETION_RETRY_SCHEDULED')

    if not progress.account_deleted:
        return deletion_pending_response(
            code=progress.code or 'ACCOUNT_DELETION_RETRY_SCHEDULED',
        )

    clear_session_cookie(response)
    return {
        'success': True,
        'cleanupPending': not progress.cleanup_complete,
        'message': (
            'Your Ask Crump account, conversation data, and currently stored private files '
            'were deleted. A protected cleanup record will continue checking the private '
            'storage prefix long enough to remove an upload that was already in flight. '
            'Apple or Google subscriptions must be canceled separately in the applicable store.'
        ),
    }
