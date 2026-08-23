"""Authentication and device-session endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth_service import (
    AuthenticationError,
    authenticate_request,
    create_session,
    public_user,
    revoke_current_session,
)
from ..db import eq, gt
from ..email_service import EmailDeliveryError
from ..http import clear_session_cookie, native_token_payload, set_session_cookie
from ..product_analytics import record_product_event
from ..rate_limit import enforce_auth_rate_limit
from ..runtime import db, email_service, settings
from ..schemas import EmailRequest, LoginRequest, RegisterRequest, ResetPasswordRequest, RevokeDeviceRequest
from ..security import (
    expiry_iso,
    hash_password,
    iso_now,
    new_uuid,
    normalize_email,
    random_token,
    token_hash,
    validate_email,
    validate_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
logger = logging.getLogger("askcrump.auth")


def verification_delivery_failure(
    exc: EmailDeliveryError,
    *,
    account_created: bool,
) -> JSONResponse:
    logger.warning(
        'Verification email delivery unavailable status=%s retryable=%s',
        exc.status_code,
        exc.retryable,
    )
    error = (
        'Your account was created, but the verification email could not be sent. '
        'Use Resend verification in a moment; you do not need to create another account.'
        if account_created
        else (
            'The verification email could not be sent right now. '
            'Please try Resend verification again shortly.'
        )
    )
    return JSONResponse(
        status_code=503,
        content={
            'success': False,
            'accountCreated': account_created,
            'needsVerification': True,
            'code': 'EMAIL_DELIVERY_UNAVAILABLE',
            'error': error,
        },
    )


@router.post('/register')
async def register(payload: RegisterRequest, request: Request):
    email = normalize_email(str(payload.email))
    await enforce_auth_rate_limit(
        db,
        request,
        action='register',
        identity=email,
        identity_limit=5,
        ip_limit=20,
        window_seconds=3600,
    )
    if not validate_email(email):
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Enter a valid email address.'},
        )
    password_ok, password_error = validate_password(payload.password)
    if not password_ok:
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': password_error},
        )

    existing = await db.select_one('users', columns='*', filters={'email': eq(email)})
    verification_token = random_token(40)
    now = iso_now()
    verification_values = {
        'verification_token_hash': token_hash(verification_token),
        'verification_token_expires': expiry_iso(hours=24),
        'updated_at': now,
    }

    if existing and existing.get('is_verified'):
        return JSONResponse(
            status_code=409,
            content={'success': False, 'error': 'An account with that email already exists.'},
        )

    pending_account = bool(existing)
    if existing:
        await db.update('users', verification_values, filters={'id': eq(existing['id'])})
        user = {**existing, **verification_values}
    else:
        user_payload = {
            'id': new_uuid(),
            'email': email,
            'password_hash': hash_password(payload.password),
            'full_name': (payload.fullName or '').strip() or None,
            'is_verified': False,
            'verification_token_hash': verification_values['verification_token_hash'],
            'verification_token_expires': verification_values['verification_token_expires'],
            'subscription_tier': 'free',
            'subscription_status': 'inactive',
            'preferences': {},
            'created_at': now,
            'updated_at': now,
        }
        inserted = await db.insert('users', user_payload)
        user = inserted[0] if isinstance(inserted, list) and inserted else user_payload
        await db.upsert(
            'user_settings',
            {'user_id': user['id'], 'updated_at': now},
            on_conflict='user_id',
        )
        await record_product_event(
            db,
            user_id=user['id'],
            event_name='AccountCreated',
            event_key='account-created',
            request=request,
            source=payload.source,
        )
        if user.get('full_name'):
            await record_product_event(
                db,
                user_id=user['id'],
                event_name='OnboardingCompleted',
                event_key='initial-profile',
                request=request,
                source=payload.source,
            )

    try:
        sent = await email_service.send_verification(
            email,
            user.get('full_name'),
            verification_token,
        )
    except EmailDeliveryError as exc:
        return verification_delivery_failure(exc, account_created=True)

    if sent:
        message = (
            'Verification email resent. Check your inbox.'
            if pending_account
            else 'Account created. Check your email to verify it.'
        )
    else:
        message = 'Email delivery is not configured; an administrator must enable RESEND_API_KEY.'
    return {'success': True, 'message': message, 'emailSent': sent}


@router.post('/login')
async def login(payload: LoginRequest, request: Request, response: Response):
    email = normalize_email(str(payload.email))
    await enforce_auth_rate_limit(
        db,
        request,
        action='login',
        identity=email,
        identity_limit=15,
        ip_limit=60,
        window_seconds=900,
    )
    user = await db.select_one('users', columns='*', filters={'email': eq(email)})
    if not user or not verify_password(payload.password, user.get('password_hash')):
        return JSONResponse(
            status_code=401,
            content={'success': False, 'error': 'Invalid email or password.'},
        )
    if not user.get('is_verified'):
        return JSONResponse(
            status_code=403,
            content={
                'success': False,
                'error': 'Verify your email before signing in.',
                'needsVerification': True,
                'email': email,
            },
        )

    raw_token, session = await create_session(
        db,
        settings,
        user,
        request,
        device_name=payload.deviceName,
        platform=payload.platform,
    )
    await db.update(
        'users',
        {'last_login': iso_now(), 'updated_at': iso_now()},
        filters={'id': eq(user['id'])},
    )
    set_session_cookie(response, raw_token, request)
    user_settings = await db.select_one(
        'user_settings',
        filters={'user_id': eq(user['id'])},
    )
    return {
        'success': True,
        'message': 'Login successful',
        'data': {
            'user': public_user(user),
            'settings': user_settings,
            'expiresAt': session.get('expires_at'),
            **native_token_payload(request, raw_token),
        },
    }


@router.api_route('/check-session', methods=['GET', 'POST'])
async def check_session(request: Request, response: Response):
    try:
        auth = await authenticate_request(request, db, settings)
    except AuthenticationError:
        return {'success': True, 'authenticated': False}
    set_session_cookie(response, auth.token, request)
    user_settings = await db.select_one(
        'user_settings',
        filters={'user_id': eq(auth.user['id'])},
    )
    return {
        'success': True,
        'authenticated': True,
        'data': {
            'user': public_user(auth.user),
            'settings': user_settings,
            'expiresAt': auth.session.get('expires_at'),
        },
    }


@router.post('/refresh')
async def refresh_session(request: Request, response: Response):
    auth = await authenticate_request(request, db, settings)
    set_session_cookie(response, auth.token, request)
    return {
        'success': True,
        'user': public_user(auth.user),
        'expiresAt': auth.session.get('expires_at'),
    }


@router.post('/logout')
async def logout(request: Request, response: Response):
    try:
        auth = await authenticate_request(request, db, settings, touch=False)
        device_id = str(
            auth.session.get('device_id') or request.headers.get('x-installation-id') or ''
        )[:200]
        await db.update(
            'sessions',
            {'revoked_at': iso_now()},
            filters={'id': eq(auth.session['id']), 'user_id': eq(auth.user['id'])},
        )
        if device_id:
            await db.update(
                'push_tokens',
                {'enabled': False, 'updated_at': iso_now()},
                filters={
                    'user_id': eq(auth.user['id']),
                    'installation_id': eq(device_id),
                },
            )
    except AuthenticationError:
        await revoke_current_session(request, db, settings)
    clear_session_cookie(response)
    return {'success': True, 'message': 'Signed out.'}


@router.post('/logout-all')
async def logout_all(request: Request, response: Response):
    auth = await authenticate_request(request, db, settings)
    now = iso_now()
    await db.update(
        'sessions',
        {'revoked_at': now},
        filters={'user_id': eq(auth.user['id']), 'revoked_at': 'is.null'},
    )
    await db.update(
        'push_tokens',
        {'enabled': False, 'updated_at': now},
        filters={'user_id': eq(auth.user['id']), 'enabled': eq(True)},
    )
    clear_session_cookie(response)
    return {'success': True, 'message': 'Signed out on every device.'}


@router.get('/devices')
async def list_devices(request: Request):
    auth = await authenticate_request(request, db, settings)
    sessions = await db.select(
        'sessions',
        columns='id,device_name,platform,created_at,last_activity,expires_at,ip_address,user_agent',
        filters={
            'user_id': eq(auth.user['id']),
            'revoked_at': 'is.null',
            'expires_at': gt(iso_now()),
        },
        order='last_activity.desc',
        limit=50,
    )
    current_id = auth.session.get('id')
    for session in sessions:
        session['current'] = session.get('id') == current_id
        session.pop('ip_address', None)
        session.pop('user_agent', None)
    return {'success': True, 'devices': sessions}


@router.post('/revoke-device')
async def revoke_device(payload: RevokeDeviceRequest, request: Request):
    auth = await authenticate_request(request, db, settings)
    session = await db.select_one(
        'sessions',
        columns='id,device_id',
        filters={'id': eq(payload.sessionId), 'user_id': eq(auth.user['id'])},
    )
    now = iso_now()
    await db.update(
        'sessions',
        {'revoked_at': now},
        filters={'id': eq(payload.sessionId), 'user_id': eq(auth.user['id'])},
    )
    device_id = str((session or {}).get('device_id') or '')
    if device_id:
        await db.update(
            'push_tokens',
            {'enabled': False, 'updated_at': now},
            filters={
                'user_id': eq(auth.user['id']),
                'installation_id': eq(device_id),
            },
        )
    return {'success': True}


@router.post('/forgot-password')
async def forgot_password(payload: EmailRequest, request: Request):
    email = normalize_email(str(payload.email))
    await enforce_auth_rate_limit(
        db,
        request,
        action='forgot',
        identity=email,
        identity_limit=5,
        ip_limit=20,
        window_seconds=3600,
    )
    user = await db.select_one(
        'users',
        columns='id,email,full_name',
        filters={'email': eq(email)},
    )
    # Always return the same result to prevent account enumeration.
    if user:
        raw_token = random_token(40)
        await db.update(
            'users',
            {
                'password_reset_token_hash': token_hash(raw_token),
                'password_reset_expires': expiry_iso(hours=1),
                'updated_at': iso_now(),
            },
            filters={'id': eq(user['id'])},
        )
        try:
            await email_service.send_password_reset(email, user.get('full_name'), raw_token)
        except EmailDeliveryError as exc:
            logger.warning(
                'Password reset email delivery unavailable status=%s retryable=%s',
                exc.status_code,
                exc.retryable,
            )
        except Exception:
            logger.exception('Unexpected password reset email failure')
    return {
        'success': True,
        'message': 'If an account exists for that email, a reset link has been sent.',
    }


@router.post('/reset-password')
async def reset_password(payload: ResetPasswordRequest, request: Request):
    await enforce_auth_rate_limit(
        db,
        request,
        action='reset',
        identity=token_hash(payload.token),
        identity_limit=10,
        ip_limit=30,
        window_seconds=3600,
    )
    password_ok, password_error = validate_password(payload.newPassword)
    if not password_ok:
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': password_error},
        )
    user = await db.select_one(
        'users',
        columns='*',
        filters={
            'password_reset_token_hash': eq(token_hash(payload.token)),
            'password_reset_expires': gt(iso_now()),
        },
    )
    if not user:
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'This reset link is invalid or expired.'},
        )
    await db.update(
        'users',
        {
            'password_hash': hash_password(payload.newPassword),
            # Possession of a valid password-reset token proves control of the
            # account inbox. Complete email verification as part of recovery
            # so an unverified account does not require a second email loop.
            'is_verified': True,
            'verification_token_hash': None,
            'verification_token_expires': None,
            'password_reset_token_hash': None,
            'password_reset_expires': None,
            'updated_at': iso_now(),
        },
        filters={'id': eq(user['id'])},
    )
    await db.update(
        'sessions',
        {'revoked_at': iso_now()},
        filters={'user_id': eq(user['id']), 'revoked_at': 'is.null'},
    )
    return {'success': True, 'message': 'Password updated. Sign in with your new password.'}


@router.post('/resend-verification')
async def resend_verification(payload: EmailRequest, request: Request):
    email = normalize_email(str(payload.email))
    await enforce_auth_rate_limit(
        db,
        request,
        action='resend',
        identity=email,
        identity_limit=5,
        ip_limit=20,
        window_seconds=3600,
    )
    user = await db.select_one('users', columns='*', filters={'email': eq(email)})
    if not user or user.get('is_verified'):
        return {
            'success': True,
            'message': 'If verification is needed, a new email has been sent.',
        }
    raw_token = random_token(40)
    await db.update(
        'users',
        {
            'verification_token_hash': token_hash(raw_token),
            'verification_token_expires': expiry_iso(hours=24),
            'updated_at': iso_now(),
        },
        filters={'id': eq(user['id'])},
    )
    try:
        sent = await email_service.send_verification(email, user.get('full_name'), raw_token)
    except EmailDeliveryError as exc:
        return verification_delivery_failure(exc, account_created=False)
    return {
        'success': True,
        'message': 'Verification email sent.' if sent else 'Email delivery is not configured.',
    }


@router.get('/verify-email')
async def verify_email(token: str):
    user = await db.select_one(
        'users',
        columns='*',
        filters={
            'verification_token_hash': eq(token_hash(token)),
            'verification_token_expires': gt(iso_now()),
        },
    )
    if not user:
        return RedirectResponse(
            f'{settings.app_url}/app?verification=failed',
            status_code=303,
        )
    if user.get('is_verified'):
        return RedirectResponse(
            f'{settings.app_url}/app?verification=already_verified',
            status_code=303,
        )
    await db.update(
        'users',
        {
            'is_verified': True,
            'verification_token_hash': None,
            'verification_token_expires': None,
            'updated_at': iso_now(),
        },
        filters={'id': eq(user['id'])},
    )
    return RedirectResponse(
        f'{settings.app_url}/app?verification=success',
        status_code=303,
    )
