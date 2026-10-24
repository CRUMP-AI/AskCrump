"""Authentication and device-session endpoints."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth_service import (
    AuthenticationError,
    authenticate_guest_for_registration,
    authenticate_request,
    create_session,
    finalize_login_session,
    guest_mode_enabled,
    is_guest_user,
    public_user,
    verify_guest_and_create_session,
    verify_registered_and_create_session,
)
from ..db import DatabaseError, eq, gt
from ..email_service import EmailDeliveryError
from ..http import native_token_payload, set_session_cookie
from ..product_analytics import (
    environment_for_request,
    record_account_created_event,
    record_product_event,
)
from ..rate_limit import enforce_auth_rate_limit, enforce_guest_admission_rate_limit
from ..runtime import (
    db,
    email_service,
    password_reset_emails,
    settings,
    verification_emails,
)
from ..schemas import (
    CURRENT_TERMS_VERSION,
    EmailRequest,
    LoginRequest,
    RegisterRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    RevokeDeviceRequest,
)
from ..verification_handoff import verified_workspace_url
from ..verification_tokens import (
    create_resend_verification_alias,
    parse_resend_verification_alias,
    resend_verification_alias_matches,
)
from ..verification_email_queue import VerificationEmailQueueUnavailable
from ..password_reset_email_queue import PasswordResetEmailQueueUnavailable
from ..password_reset_tokens import (
    parse_password_reset_alias,
    password_reset_alias_matches,
)
from ..security import (
    client_ip,
    expiry_iso,
    hash_password,
    iso_now,
    new_uuid,
    normalize_email,
    origin_allowed,
    password_hash_needs_upgrade,
    random_token,
    token_hash,
    validate_email,
    validate_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])
logger = logging.getLogger("askcrump.auth")

_GUEST_INSTALLATION_ID = re.compile(r'^[A-Za-z0-9._:-]{16,200}$')


def _guest_rate_identity(request: Request, ip: str) -> str:
    """Use the app's opaque installation ID without browser fingerprinting.

    The shared public IP remains a separate ceiling in ``enforce_auth_rate_limit``.
    Invalid or absent installation IDs fall back to that canonical IP so a
    caller cannot bypass the stricter identity bucket with malformed headers.
    """
    installation_id = str(request.headers.get('x-installation-id') or '').strip()
    if _GUEST_INSTALLATION_ID.fullmatch(installation_id):
        return f'installation:{installation_id}'
    return f'ip:{ip}'


def _registration_terms_values(
    payload: RegisterRequest,
    *,
    accepted_at: str,
) -> dict[str, str]:
    if not payload.termsAccepted or payload.termsVersion != CURRENT_TERMS_VERSION:
        return {}
    return {
        'terms_accepted_at': accepted_at,
        'terms_version': CURRENT_TERMS_VERSION,
    }


def _is_guest_placeholder_email(value: object, user_id: object) -> bool:
    """Identify the server-minted address that has never submitted registration."""
    email = str(value or '').strip().lower()
    expected = f'guest-{str(user_id or "").strip().lower()}@guest.askcrump.local'
    return email == expected


async def _guest_mode_enabled() -> bool:
    """Read the database kill switch and fail closed on any uncertainty."""
    return await guest_mode_enabled(db)


def _auth_client_kind(request: Request) -> str:
    """Return an allowlisted client category without logging user-supplied identity data."""
    return (
        'native'
        if request.headers.get('x-crump-client', '').lower() == 'native'
        else 'web'
    )


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


_GENERIC_RESEND_RESULT = {
    'success': True,
    'message': 'If verification is needed, an email will be sent.',
}

_GENERIC_RESEND_UNAVAILABLE = {
    'success': False,
    'error': 'Verification email requests are temporarily unavailable. Please try again shortly.',
    'code': 'VERIFICATION_EMAIL_QUEUE_UNAVAILABLE',
}

_GENERIC_PASSWORD_RESET_RESULT = {
    'success': True,
    'message': 'If an account exists for that email, check your email for a reset link.',
}

_GENERIC_PASSWORD_RESET_UNAVAILABLE = {
    'success': False,
    'error': 'Password-reset email requests are temporarily unavailable. Please try again shortly.',
    'code': 'PASSWORD_RESET_EMAIL_QUEUE_UNAVAILABLE',
}


def _verification_alias_signing_keys() -> dict[str, str]:
    configured = dict(getattr(settings, 'verification_link_signing_keys', ()) or ())
    if configured:
        return configured
    environment = str(getattr(settings, 'environment', 'development')).lower()
    if environment in {'production', 'preview'}:
        raise RuntimeError('Verification-link signing keys are unavailable.')
    return {
        'local': 'ask-crump-local-verification-alias-tests-key-000000000000',
    }


def _timestamp_after(value: object, boundary_value: str) -> bool:
    try:
        candidate = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        boundary = datetime.fromisoformat(boundary_value.replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return False
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    if boundary.tzinfo is None:
        boundary = boundary.replace(tzinfo=timezone.utc)
    return candidate > boundary


def _timestamp_epoch(value: object) -> int | None:
    try:
        candidate = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if candidate.tzinfo is None:
        candidate = candidate.replace(tzinfo=timezone.utc)
    return int(candidate.timestamp())


def _updated_user(current: dict, updated: object) -> dict | None:
    row = (
        updated[0]
        if isinstance(updated, list) and updated and isinstance(updated[0], dict)
        else updated if isinstance(updated, dict) else None
    )
    return {**current, **row} if row is not None else None


async def _prepare_resend_verification_alias(user: dict) -> str | None:
    """Sign a live anchor or atomically replace one that is already expired."""
    user_id = str(user.get('id') or '')
    if not user_id or user.get('is_verified'):
        return None

    current = dict(user)
    for _attempt in range(4):
        if current.get('is_verified'):
            return None
        anchor = str(current.get('verification_token_hash') or '').strip().lower()
        previous_expiry = current.get('verification_token_expires')
        if (
            re.fullmatch(r'[0-9a-f]{64}', anchor)
            and _timestamp_after(previous_expiry, iso_now())
        ):
            signing_keys = _verification_alias_signing_keys()
            key_id, signing_secret = next(iter(signing_keys.items()))
            return create_resend_verification_alias(
                signing_secret,
                key_id=key_id,
                user_id=user_id,
                verification_token_hash=anchor,
                expires_at=previous_expiry,
            )

        # Never extend an existing generation: doing so would revive every
        # expired bearer derived from it. Once the generation is expired (or
        # incomplete), replace its anchor and expiry together under a CAS. A
        # concurrent winner is adopted on readback, so every sender uses the
        # one current generation and the expired one stays permanently dead.
        replacement_anchor = token_hash(random_token(40))
        replacement_expiry = expiry_iso(hours=24)
        try:
            updated = await db.update(
                'users',
                {
                    'verification_token_hash': replacement_anchor,
                    'verification_token_expires': replacement_expiry,
                    'updated_at': iso_now(),
                },
                filters={
                    'id': eq(user_id),
                    'is_verified': eq(False),
                    'verification_token_hash': eq(anchor or None),
                    'verification_token_expires': eq(previous_expiry),
                },
            )
        except DatabaseError:
            updated = None
        confirmed = _updated_user(current, updated)
        if confirmed is not None:
            current = confirmed
        else:
            current = await db.select_one(
                'users',
                columns='*',
                filters={'id': eq(user_id)},
            ) or {}
    return None


async def _verification_user_and_anchor(token: str) -> tuple[dict | None, str]:
    if token.startswith('v2.'):
        alias = parse_resend_verification_alias(token)
        now = iso_now()
        now_epoch = _timestamp_epoch(now)
        if alias is None or now_epoch is None or alias.expires_at <= now_epoch:
            return None, ''
        user = await db.select_one(
            'users',
            columns='*',
            filters={
                'id': eq(alias.user_id),
                'verification_token_expires': gt(now),
            },
        )
        anchor = str((user or {}).get('verification_token_hash') or '').strip().lower()
        row_expiry = _timestamp_epoch((user or {}).get('verification_token_expires'))
        if (
            not user
            or user.get('deleted_at') is not None
            or row_expiry is None
            or (not user.get('is_verified') and alias.expires_at > row_expiry)
            or not resend_verification_alias_matches(
                alias,
                _verification_alias_signing_keys(),
                verification_token_hash=anchor,
            )
        ):
            return None, ''
        return user, anchor

    anchor = token_hash(token)
    user = await db.select_one(
        'users',
        columns='*',
        filters={
            'verification_token_hash': eq(anchor),
            'verification_token_expires': gt(iso_now()),
        },
    )
    return user, anchor


async def _password_reset_anchor(token: str) -> str:
    if not token.startswith('r1.'):
        return token_hash(token)

    alias = parse_password_reset_alias(token)
    now = iso_now()
    now_epoch = _timestamp_epoch(now)
    if alias is None or now_epoch is None or alias.expires_at <= now_epoch:
        return ''
    user = await db.select_one(
        'users',
        columns='id,deleted_at,password_reset_token_hash,password_reset_expires',
        filters={
            'id': eq(alias.user_id),
            'password_reset_expires': gt(now),
        },
    )
    anchor = str((user or {}).get('password_reset_token_hash') or '').strip().lower()
    row_expiry = _timestamp_epoch((user or {}).get('password_reset_expires'))
    if (
        not user
        or user.get('deleted_at') is not None
        or not re.fullmatch(r'[0-9a-f]{64}', anchor)
        or row_expiry is None
        or alias.expires_at != row_expiry
        or not password_reset_alias_matches(
            alias,
            _verification_alias_signing_keys(),
            password_reset_token_hash=anchor,
        )
    ):
        return ''
    return anchor


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
    registration_environment = environment_for_request(request)
    terms_values = _registration_terms_values(payload, accepted_at=now)
    verification_values = {
        'verification_token_hash': token_hash(verification_token),
        'verification_token_expires': expiry_iso(hours=24),
        'updated_at': now,
        **terms_values,
    }

    if existing and existing.get('is_verified'):
        return JSONResponse(
            status_code=409,
            content={'success': False, 'error': 'An account with that email already exists.'},
        )

    # Resolve only the guest identity registration is allowed to preserve.
    # This narrow path accepts a database control-revoked token so rollback
    # cannot strand the conversation/allowance, but it never reopens ordinary
    # guest access and never accepts a normal logout/revocation.
    session_guest = None
    try:
        session_auth = await authenticate_guest_for_registration(request, db, settings)
        session_guest = session_auth.user
    except AuthenticationError:
        session_guest = None

    own_guest_row = bool(
        session_guest and existing and existing['id'] == session_guest['id']
    )
    if existing and session_guest and not own_guest_row:
        # The submitted email belongs to a different, still-unverified
        # registration. The guest has not proven they own that inbox, so
        # the pending row is left completely untouched — no token rotation,
        # no merge — and the guest session and its conversation stay as
        # they are. The path forward is the pending account's own inbox.
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'error': (
                    'That email already has a registration waiting for verification. '
                    'Check your inbox for the verification email to finish creating '
                    'that account. Your guest conversation is still here — nothing '
                    'was changed.'
                ),
                'message': (
                    'That email already has a registration waiting for verification. '
                    'Check your inbox for the verification email to finish creating '
                    'that account. Your guest conversation is still here — nothing '
                    'was changed.'
                ),
                'code': 'PENDING_ACCOUNT_RECOVERY',
                'guestPreserved': True,
            },
        )

    pending_account = bool(existing) and not own_guest_row
    if existing and not own_guest_row:
        user = existing
        try:
            verification_token = await _prepare_resend_verification_alias(user)
        except (DatabaseError, RuntimeError, ValueError):
            logger.warning('Pending verification recovery preparation unavailable.')
            verification_token = None
        if not verification_token:
            return {
                **_GENERIC_RESEND_RESULT,
                'emailSent': False,
            }
    else:
        guest_user = session_guest
        if guest_user:
            # Conversion: the guest's own row becomes the account, so their
            # conversations and history carry over instead of starting over.
            # is_guest stays set until the email is verified (see
            # verify_email) — registration alone must not unlock a full
            # account behind an unverified address.
            conversion_values = {
                'email': email,
                'password_hash': hash_password(payload.password),
                'full_name': (payload.fullName or '').strip() or None,
                **verification_values,
            }
            if _is_guest_placeholder_email(
                guest_user.get('email'),
                guest_user.get('id'),
            ):
                conversion_values.update({
                    'registration_submitted_at': now,
                    'registration_environment': registration_environment,
                })
            updated = await db.update(
                'users',
                conversion_values,
                filters={'id': eq(guest_user['id'])},
            )
            returned_user = (
                updated[0]
                if isinstance(updated, list) and updated and isinstance(updated[0], dict)
                else updated if isinstance(updated, dict) else {}
            )
            # Merge defensively because small test/fallback adapters may return
            # only the changed columns. A full database representation still
            # wins last, so trigger-preserved marker values remain authoritative.
            user = {**guest_user, **conversion_values, **returned_user}
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
                'registration_environment': registration_environment,
                'registration_submitted_at': now,
                'preferences': {},
                'created_at': now,
                'updated_at': now,
                **terms_values,
            }
            inserted = await db.insert('users', user_payload)
            user = inserted[0] if isinstance(inserted, list) and inserted else user_payload
        if not guest_user:
            # A guest receives this row when the preview session is created.
            # Re-upserting it during registration is redundant, and—after an
            # emergency guest-mode disable—would correctly hit the database
            # guest-write barrier after the identity update had already
            # committed. Preserve the existing row so rollback registration
            # can still deliver its verification email without leaving a
            # half-converted account.
            await db.upsert(
                'user_settings',
                {'user_id': user['id'], 'updated_at': now},
                on_conflict='user_id',
            )
        await record_account_created_event(
            db,
            user_id=user['id'],
            request=request,
            acquisition=payload.source,
            placement=payload.placement,
            campaign=payload.campaign,
            creative=payload.creative,
            intent=payload.intent,
        )
        if user.get('full_name'):
            await record_product_event(
                db,
                user_id=user['id'],
                event_name='OnboardingCompleted',
                event_key='initial-profile',
                request=request,
            )

    try:
        sent = await email_service.send_verification(
            email,
            user.get('full_name'),
            verification_token,
            intent=payload.intent,
            plan=payload.plan,
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


@router.post('/guest')
async def start_guest_session(request: Request, response: Response):
    # A browser that already holds any valid session keeps it; guest sessions
    # are minted only for genuinely signed-out visitors.
    try:
        current = await authenticate_request(request, db, settings, touch=False)
        return {
            'success': True,
            'data': {
                'user': public_user(current.user),
                'guest': is_guest_user(current.user),
            },
        }
    except AuthenticationError:
        pass

    # Minting sets a session cookie, and CORS does not stop a cross-site
    # form POST from planting one in a visitor's browser. Refuse mints
    # that are not same-site before any rate budget or row is spent.
    if not origin_allowed(dict(request.headers), settings.allowed_origins):
        return JSONResponse(
            status_code=403,
            content={
                'success': False,
                'error': 'Guest sessions can only start from Ask Crump.',
                'code': 'ORIGIN_NOT_ALLOWED',
            },
        )

    # The database control is the rollback authority. It defaults off, and its
    # session/user triggers close races with an operator disabling guest mode.
    # Read it before consuming rate-limit budget or writing any guest data.
    if not await _guest_mode_enabled():
        return JSONResponse(
            status_code=503,
            content={
                'success': False,
                'error': (
                    'Guest preview is temporarily unavailable. '
                    'Sign in or create an account.'
                ),
                'code': 'GUEST_MODE_DISABLED',
            },
        )

    ip = client_ip(
        dict(request.headers),
        request.client.host if request.client else None,
    ) or 'unknown'
    await enforce_guest_admission_rate_limit(
        db,
        request,
        identity=_guest_rate_identity(request, ip),
        identity_limit=3,
        # Keep each installation tightly bounded while allowing a household,
        # workplace, carrier NAT, or controlled verifier to share one public
        # address without three visitors blocking everyone for a full day.
        ip_limit=20,
        window_seconds=86400,
    )
    now = iso_now()
    guest_id = new_uuid()
    user_payload = {
        'id': guest_id,
        # Placeholder address: never mailed, never shown as the visitor's
        # identity, and replaced by the real email when the guest registers.
        # It keeps the row valid under the existing email constraints.
        'email': f'guest-{guest_id}@guest.askcrump.local',
        # users.password_hash is NOT NULL. A guest has no password, so store
        # a real hash of an unguessable random token whose plaintext exists
        # nowhere: password login for a guest can never succeed, and the
        # value is replaced when the guest registers with a real password.
        'password_hash': hash_password(random_token(48)),
        'full_name': None,
        'is_verified': False,
        'is_guest': True,
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
        'registration_environment': environment_for_request(request),
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
    raw_token, session = await create_session(db, settings, user, request)
    set_session_cookie(response, raw_token, request)
    logger.info('Auth guest outcome=session_issued client=%s', _auth_client_kind(request))
    return {
        'success': True,
        'message': 'Guest session started.',
        'data': {
            'user': public_user(user),
            'guest': True,
            'expiresAt': session.get('expires_at'),
            **native_token_payload(request, raw_token),
        },
    }


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
        logger.info(
            'Auth login outcome=invalid_credentials client=%s',
            _auth_client_kind(request),
        )
        return JSONResponse(
            status_code=401,
            content={
                'success': False,
                'error': 'Invalid email or password.',
                'code': 'INVALID_CREDENTIALS',
            },
        )
    if not user.get('is_verified'):
        logger.info(
            'Auth login outcome=verification_required client=%s',
            _auth_client_kind(request),
        )
        return JSONResponse(
            status_code=403,
            content={
                'success': False,
                'error': 'Verify your email before signing in.',
                'code': 'EMAIL_VERIFICATION_REQUIRED',
                'needsVerification': True,
                'email': email,
            },
        )

    expected_password_hash = str(user.get('password_hash') or '')
    upgraded_password_hash = None
    if password_hash_needs_upgrade(expected_password_hash):
        upgraded_password_hash = hash_password(payload.password)

    finalized = await finalize_login_session(
        db,
        settings,
        user,
        request,
        expected_password_hash=expected_password_hash,
        upgraded_password_hash=upgraded_password_hash,
        device_name=payload.deviceName,
        platform=payload.platform,
    )
    if finalized is None:
        logger.info(
            'Auth login outcome=invalid_credentials client=%s',
            _auth_client_kind(request),
        )
        return JSONResponse(
            status_code=401,
            content={
                'success': False,
                'error': 'Invalid email or password.',
                'code': 'INVALID_CREDENTIALS',
            },
        )
    raw_token, user, session = finalized
    set_session_cookie(response, raw_token, request)
    logger.info(
        'Auth login outcome=session_issued client=%s',
        _auth_client_kind(request),
    )
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
    except AuthenticationError as exc:
        # A stale browser tab must not translate an explicit owner mismatch
        # into an ordinary signed-out answer.  Preserve the 409 so the client
        # can scrub the previous account's private UI and reload against the
        # authoritative HttpOnly-cookie owner.
        if exc.code == 'AUTH_OWNER_MISMATCH':
            raise
        logger.info(
            'Auth session outcome=unauthenticated client=%s',
            _auth_client_kind(request),
        )
        return {'success': True, 'authenticated': False}
    logger.info(
        'Auth session outcome=authenticated client=%s',
        _auth_client_kind(request),
    )
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
    # Do not re-emit an old credential from a delayed response. Login and
    # verification are the credential-issuing boundaries; this endpoint only
    # renews the server-side session lifetime.
    return {
        'success': True,
        'user': public_user(auth.user),
        'expiresAt': auth.session.get('expires_at'),
    }


@router.post('/logout')
async def logout(request: Request, response: Response):
    try:
        auth = await authenticate_request(
            request,
            db,
            settings,
            touch=False,
            require_expected_owner_header=True,
        )
        await db.update(
            'sessions',
            {'revoked_at': iso_now()},
            filters={
                'id': eq(auth.session['id']),
                'user_id': eq(auth.user['id']),
                'token_hash': eq(auth.session['token_hash']),
                'revoked_at': 'is.null',
            },
        )
    except AuthenticationError as exc:
        if exc.code == 'AUTH_OWNER_MISMATCH':
            raise
        # An already-expired/revoked credential is already signed out. Do not
        # revoke a different cookie candidate or emit a late cookie deletion.
        pass
    return {'success': True, 'message': 'Signed out.'}


@router.post('/logout-all')
async def logout_all(request: Request, response: Response):
    auth = await authenticate_request(
        request,
        db,
        settings,
        require_expected_owner_header=True,
    )
    now = iso_now()
    await db.update(
        'sessions',
        {'revoked_at': now},
        filters={'user_id': eq(auth.user['id']), 'revoked_at': 'is.null'},
    )
    return {'success': True, 'message': 'Signed out on every device.'}


@router.get('/devices')
async def list_devices(request: Request):
    auth = await authenticate_request(
        request,
        db,
        settings,
        require_expected_owner_header=True,
    )
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
    auth = await authenticate_request(
        request,
        db,
        settings,
        require_expected_owner_header=True,
    )
    session = await db.select_one(
        'sessions',
        columns='id,device_id,token_hash',
        filters={'id': eq(payload.sessionId), 'user_id': eq(auth.user['id'])},
    )
    now = iso_now()
    await db.update(
        'sessions',
        {'revoked_at': now},
        filters={
            'id': eq(payload.sessionId),
            'user_id': eq(auth.user['id']),
            'token_hash': eq((session or {}).get('token_hash')),
            'revoked_at': 'is.null',
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
    try:
        await password_reset_emails.enqueue(email=email)
    except (PasswordResetEmailQueueUnavailable, RuntimeError, ValueError):
        logger.warning('Password-reset durable enqueue unavailable.')
        return JSONResponse(
            status_code=503,
            content=_GENERIC_PASSWORD_RESET_UNAVAILABLE,
        )
    return _GENERIC_PASSWORD_RESET_RESULT


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
    reset_anchor = await _password_reset_anchor(payload.token)
    if not reset_anchor:
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'This reset link is invalid or expired.'},
        )
    reset_result = await db.rpc(
        'consume_password_reset_v1',
        {
            'p_token_hash': reset_anchor,
            'p_password_hash': hash_password(payload.newPassword),
        },
    )
    reset_row = (
        reset_result[0]
        if isinstance(reset_result, list) and reset_result
        else reset_result if isinstance(reset_result, dict) else {}
    )
    if reset_row.get('reset_applied') is not True:
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'This reset link is invalid or expired.'},
        )
    return {'success': True, 'message': 'Password updated. Sign in with your new password.'}


@router.post('/resend-verification')
async def resend_verification(payload: ResendVerificationRequest, request: Request):
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
    try:
        await verification_emails.enqueue_resend(
            email=email,
            intent=payload.intent,
            plan=payload.plan,
        )
    except (VerificationEmailQueueUnavailable, RuntimeError, ValueError):
        logger.warning('Verification resend durable enqueue unavailable.')
        return JSONResponse(
            status_code=503,
            content=dict(_GENERIC_RESEND_UNAVAILABLE),
        )
    logger.info('Verification resend outcome=durably_accepted')
    return JSONResponse(
        status_code=202,
        content=dict(_GENERIC_RESEND_RESULT),
    )


@router.get('/verify-email')
async def verify_email(
    token: str,
    request: Request,
    intent: str | None = None,
    plan: str | None = None,
):
    user, verification_token_hash = await _verification_user_and_anchor(token)
    if not user:
        return RedirectResponse(
            f'{settings.app_url}/app?verification=failed',
            status_code=303,
        )

    if user.get('is_verified'):
        logger.info(
            'Auth verification outcome=already_verified client=%s',
            _auth_client_kind(request),
        )
        return RedirectResponse(
            verified_workspace_url(
                settings.app_url,
                intent=intent,
                plan=plan,
                result='already_verified',
            ),
            status_code=303,
        )

    # Possession of the verification link proves control of the inbox. Issue the
    # first session here so a successful signup does not require another password
    # entry. Keep the hash recognizable for 15 minutes so a repeated link can
    # report an accurate, non-authenticating result. Only the transaction that
    # changes is_verified from false to true may mint or set a session.
    raw_token = None
    if not user.get('is_verified') and is_guest_user(user):
        atomic_result = await verify_guest_and_create_session(
            db,
            settings,
            user,
            request,
            verification_token_hash=verification_token_hash,
            device_name='Verified email link',
            platform='web',
        )
        if atomic_result:
            raw_token, user, _ = atomic_result
        else:
            # A concurrent click may have completed the locked conversion while
            # this request waited. Re-read before taking the ordinary verified
            # replay path; never fall back to a non-atomic guest conversion.
            user = await db.select_one(
                'users',
                columns='*',
                filters={
                    'id': eq(user['id']),
                    'verification_token_hash': eq(verification_token_hash),
                    'verification_token_expires': gt(iso_now()),
                },
            )
            if not user:
                return RedirectResponse(
                    f'{settings.app_url}/app?verification=failed',
                    status_code=303,
                )
            if not user.get('is_verified'):
                raise RuntimeError('Guest verification did not complete atomically.')

            logger.info(
                'Auth verification outcome=already_verified client=%s',
                _auth_client_kind(request),
            )
            return RedirectResponse(
                verified_workspace_url(
                    settings.app_url,
                    intent=intent,
                    plan=plan,
                    result='already_verified',
                ),
                status_code=303,
            )

    if not user.get('is_verified'):
        atomic_result = await verify_registered_and_create_session(
            db,
            settings,
            user,
            request,
            verification_token_hash=verification_token_hash,
            device_name='Verified email link',
            platform='web',
        )
        if atomic_result:
            raw_token, user, _ = atomic_result
        else:
            # A concurrent verifier may have completed the locked transition.
            # Re-read only by account plus the still-valid bearer token. A
            # password reset clears that token, so stale verification fails
            # instead of minting a post-reset session.
            user = await db.select_one(
                'users',
                columns='*',
                filters={
                    'id': eq(user['id']),
                    'verification_token_hash': eq(verification_token_hash),
                    'verification_token_expires': gt(iso_now()),
                },
            )
            if not user:
                return RedirectResponse(
                    f'{settings.app_url}/app?verification=failed',
                    status_code=303,
                )
            if not user.get('is_verified'):
                # The database clock may have crossed the bearer expiry, or
                # another writer may have made the account ineligible after
                # the initial application read. Neither condition authenticates
                # the click or warrants a server error.
                return RedirectResponse(
                    f'{settings.app_url}/app?verification=failed',
                    status_code=303,
                )
            logger.info(
                'Auth verification outcome=already_verified client=%s',
                _auth_client_kind(request),
            )
            return RedirectResponse(
                verified_workspace_url(
                    settings.app_url,
                    intent=intent,
                    plan=plan,
                    result='already_verified',
                ),
                status_code=303,
            )

    if raw_token is None:
        raise RuntimeError('Email verification did not return an atomic session.')
    response = RedirectResponse(
        verified_workspace_url(settings.app_url, intent=intent, plan=plan),
        status_code=303,
    )
    set_session_cookie(response, raw_token, request)
    logger.info(
        'Auth verification outcome=session_issued client=%s',
        _auth_client_kind(request),
    )
    return response
