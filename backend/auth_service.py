from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hmac
import logging
from typing import Any
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import Settings
from .db import SupabaseDB, eq, gt
from .policy_consent import (
    CURRENT_POLICY_BUNDLE_HASH,
    CURRENT_POLICY_BUNDLE_ID,
    read_current_policy_acceptance,
)
from .security import client_ip, expiry_iso, iso_now, new_uuid, random_token, token_hash
from .usage_service import tier_name


logger = logging.getLogger("askcrump.auth")
EXPECTED_OWNER_HEADER = 'x-ask-crump-expected-owner'
# Rolling-deploy compatibility: already-open cookie-authenticated web tabs from
# before the owner-boundary release cannot add this header until they reload.
# Route-level ``require_expected_owner_header=True`` markers intentionally stay
# in place so a later release can flip this to False after the old client window
# has elapsed. Any supplied claim is always validated regardless of this flag.
ALLOW_LEGACY_MISSING_EXPECTED_OWNER = True


@dataclass(slots=True)
class AuthenticatedUser:
    user: dict[str, Any]
    session: dict[str, Any]
    token: str


class AuthenticationError(RuntimeError):
    def __init__(
        self,
        message: str = 'Authentication required.',
        status_code: int = 401,
        *,
        code: str = 'AUTH_REQUIRED',
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = dict(details or {})


def require_expected_owner(request: Request, authenticated_user_id: str) -> None:
    """Bind a browser request to the account visible when it was dispatched.

    An HttpOnly session cookie can rotate in another tab before this tab sees
    the storage/auth event. The header is only a precondition: authentication
    still comes exclusively from the cookie/bearer credential. Parse both IDs
    as UUID bytes so malformed or non-ASCII claims fail closed without making
    string comparison an exception path.
    """
    raw_expected = str(request.headers.get(EXPECTED_OWNER_HEADER, '') or '').strip()
    raw_actual = str(authenticated_user_id or '').strip()
    authorization = str(request.headers.get('authorization', '') or '').strip()
    if not raw_expected and authorization.lower().startswith('bearer ') and authorization[7:].strip():
        # Installed native builds already bind each request to a per-installation
        # bearer credential rather than a shared browser cookie. Preserve their
        # compatibility; newer builds may send the claim and are still checked.
        return
    try:
        expected = UUID(raw_expected).bytes
        actual = UUID(raw_actual).bytes
    except (AttributeError, TypeError, ValueError):
        expected = b''
        actual = b'\x01'
    if hmac.compare_digest(expected, actual):
        return
    raise AuthenticationError(
        'The signed-in account changed before this request began. Refresh and try again.',
        status_code=409,
        code='AUTH_OWNER_MISMATCH',
        details={'staleAuth': True, 'retryable': True},
    )


# Guest mode and registered Free accounts share one text-only allowance. The
# authoritative ledger lives in usage_events and follows the unchanged users
# row through guest -> registered conversion, so signup can never mint another
# allowance. Professional, Enterprise, and internal accounts keep their
# independently verified plan entitlements.
FREE_TEXT_MESSAGE_LIMIT = 5
FREE_TEXT_WINDOW_SECONDS = 24 * 60 * 60

# Compatibility name for older imports while the guest-only counter is retired.
GUEST_MESSAGE_LIMIT = FREE_TEXT_MESSAGE_LIMIT


def is_guest_user(user: dict[str, Any] | None) -> bool:
    return bool(user and user.get('is_guest'))


def guest_mode_control_value(raw: object) -> bool:
    """Parse the backend-only control RPC without treating ambiguity as enabled."""
    value = raw
    if isinstance(value, list):
        if len(value) != 1:
            return False
        value = value[0]
    if isinstance(value, dict):
        value = value.get('enabled')
    return value is True


async def guest_mode_enabled(db: SupabaseDB) -> bool:
    """Read the database guest switch and fail closed on errors or malformed data."""
    try:
        raw = await db.rpc('get_guest_mode_control_v1', {})
    except Exception:
        logger.exception('Guest mode control read failed closed')
        return False
    return guest_mode_control_value(raw)


def is_free_text_user(user: dict[str, Any] | None) -> bool:
    """Whether the account is governed by the shared Free text allowance."""
    return bool(user) and tier_name(user or {}) == 'free'


def paid_tools_entitled(user: dict[str, Any] | None) -> bool:
    """Server-authoritative paid-tool entitlement.

    Guests remain text-only even if a malformed row ever carries a paid-looking
    label. ``tier_name`` already verifies billing lifecycle or internal access.
    """
    return bool(user) and not is_guest_user(user) and tier_name(user or {}) in {
        'professional',
        'enterprise',
    }


def guest_limit_reached(user: dict[str, Any] | None) -> bool:
    """Deprecated compatibility predicate; the database ledger is authoritative."""
    if not is_guest_user(user):
        return False
    return int(user.get('guest_message_count') or 0) >= GUEST_MESSAGE_LIMIT


def free_text_message_fingerprint(chat_id: str | None, message: str | None) -> str:
    """Content-free identity of one Free send: conversation plus exact text.

    A retry of the same send reproduces the same fingerprint and reuses
    its reservation; the same message id carrying a different prompt or
    a different conversation is a different send and pays its own slot.
    This server-side send digest is not a device/browser fingerprint and never
    uses hardware, canvas, font, plugin, audio, or other cross-session signals.
    """
    return token_hash(f'{chat_id or ""}\n{message or ""}')


guest_message_fingerprint = free_text_message_fingerprint


async def reserve_free_text_message(
    db: SupabaseDB,
    user: dict[str, Any],
    *,
    message_id: str | None = None,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    """Atomically reserve one rolling-24-hour Free text message.

    The service-role-only RPC owns the hard limit, concurrency lock, rolling
    boundary, and idempotency receipt. A replay deliberately has no refundable
    event id, so a failed retry can never delete the original accepted send.
    """
    if not is_free_text_user(user):
        return {
            'allowed': True,
            'eventId': None,
            'used': 0,
            'limit': -1,
            'remaining': -1,
            'nextAvailableAt': None,
            'idempotentReplay': False,
        }
    user_id = str(user.get('id') or '')
    normalized_message_id = str(message_id or '').strip()
    normalized_fingerprint = str(fingerprint or '').strip().lower()
    if not user_id or not normalized_message_id or len(normalized_fingerprint) != 64:
        raise AuthenticationError(
            'A conversation and message ID are required for Free messages.',
            status_code=400,
        )
    raw = await db.rpc(
        'reserve_free_message_v1',
        {
            'p_user_id': user_id,
            'p_message_id': normalized_message_id,
            'p_fingerprint': normalized_fingerprint,
        },
        retry_transient=True,
    )
    row = raw[0] if isinstance(raw, list) and raw else (raw or {})
    outcome = str(row.get('outcome') or '').lower()
    if outcome == 'guest_mode_disabled':
        raise AuthenticationError(
            'Guest preview is temporarily unavailable. Sign in or create an account.',
            status_code=503,
        )
    if outcome not in {'reserved', 'reused', 'exhausted'}:
        raise RuntimeError('Free message reservation returned an invalid outcome.')
    used = max(0, int(row.get('used') or 0))
    remaining = max(0, int(row.get('remaining') or 0))
    return {
        'allowed': outcome in {'reserved', 'reused'},
        'eventId': row.get('event_id') if outcome == 'reserved' else None,
        'used': used,
        'limit': FREE_TEXT_MESSAGE_LIMIT,
        'remaining': remaining,
        'nextAvailableAt': row.get('next_available_at'),
        'idempotentReplay': outcome == 'reused',
        'freeMessageAllowance': {
            'limit': FREE_TEXT_MESSAGE_LIMIT,
            'used': used,
            'remaining': remaining,
            'windowKind': 'rolling_24h',
            'windowSeconds': FREE_TEXT_WINDOW_SECONDS,
            'nextAvailableAt': row.get('next_available_at'),
        },
    }


async def reserve_guest_message(
    db: SupabaseDB,
    user: dict[str, Any],
    *,
    message_id: str | None = None,
    fingerprint: str | None = None,
) -> bool:
    """Compatibility wrapper for callers/tests during the guest cutover."""
    result = await reserve_free_text_message(
        db,
        user,
        message_id=message_id,
        fingerprint=fingerprint,
    )
    return bool(result.get('allowed'))


def guest_account_required_response(feature_label: str) -> JSONResponse:
    message = (
        f'Guest preview covers standard chat. Create your free account to use '
        f'{feature_label} — this conversation will be saved to your account.'
    )
    return JSONResponse(
        status_code=403,
        content={
            'success': False,
            'error': message,
            'message': message,
            'code': 'GUEST_ACCOUNT_REQUIRED',
            'guestAccountRequired': True,
        },
    )


def paid_feature_required_response(
    feature_label: str,
    user: dict[str, Any] | None,
) -> JSONResponse:
    guest = is_guest_user(user)
    if guest:
        message = (
            f'{feature_label} requires a verified Professional plan. Create an '
            'account to preserve this conversation, then review plans. Creating '
            'the account does not reset or add Free messages.'
        )
    else:
        message = f'{feature_label} requires a verified Professional plan.'
    return JSONResponse(
        status_code=403,
        content={
            'success': False,
            'error': message,
            'message': message,
            'code': 'SUBSCRIPTION_REQUIRED',
            'accountRequired': guest,
            'upgradeRequired': True,
            'requiredTier': 'professional',
        },
    )


def free_text_limit_response(
    user: dict[str, Any],
    allowance: dict[str, Any],
) -> JSONResponse:
    guest = is_guest_user(user)
    next_at = allowance.get('nextAvailableAt')
    if guest:
        message = (
            'You have used your 5 Free text messages in the last 24 hours. '
            'Create an account to preserve this conversation, then choose a paid '
            'plan for more messages. Creating an account does not grant another five.'
        )
    else:
        message = (
            'You have used your 5 Free text messages in the last 24 hours. '
            'A verified Professional plan is required for more messages.'
        )
    free_allowance = {
        'limit': FREE_TEXT_MESSAGE_LIMIT,
        'used': max(FREE_TEXT_MESSAGE_LIMIT, int(allowance.get('used') or 0)),
        'remaining': 0,
        'windowKind': 'rolling_24h',
        'windowSeconds': FREE_TEXT_WINDOW_SECONDS,
        'nextAvailableAt': next_at,
    }
    return JSONResponse(
        status_code=403,
        content={
            'success': False,
            'error': message,
            'message': message,
            'code': 'FREE_TEXT_LIMIT_REACHED',
            'accountRequired': guest,
            'upgradeRequired': True,
            'requiredTier': 'professional',
            'freeMessageAllowance': free_allowance,
            # One-release compatibility for the guest-only shell.
            'guestLimitReached': guest,
            'guestMessageLimit': FREE_TEXT_MESSAGE_LIMIT,
        },
    )
# Client-supplied payload markers that carry no authority for a guest. The
# chat route strips them before preparation so nothing downstream can pick
# them up.
GUEST_STRIPPED_PAYLOAD_KEYS = (
    'creationIntent',
    'creativeTool',
    'artifactFormat',
    'longForm',
    'requestedTool',
    'suppressCreativeExecution',
    'imageUseReference',
    'imageReferencePlan',
    'imageReferencePlanConfirmed',
)


def _payload_file_ids(payload: dict[str, Any]) -> list[str]:
    result: list[str] = []
    values = payload.get('fileRefs') or []
    if isinstance(values, list):
        for item in values:
            value = item.get('id') if isinstance(item, dict) else item
            if value:
                result.append(str(value))
    history = payload.get('history') or []
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict):
                continue
            refs = item.get('fileRefs') or []
            if not isinstance(refs, list):
                continue
            for value in refs:
                file_id = value.get('id') if isinstance(value, dict) else value
                if file_id:
                    result.append(str(file_id))
    return result


def guest_blocked_signal(payload: dict[str, Any], *, image_requested: bool = False) -> str | None:
    """Direct advanced-capability signals blocked for the Free text tier.

    Only explicit client signals are rejected here; `image_requested` is
    the caller's media-service verdict for the message text. Semantic
    intent is handled separately: creation inference is disabled for
    guests and text-detected artifact/manuscript intent is downgraded to
    plain chat, so an ordinary question is never bounced — it is
    answered as text.
    """
    if _payload_file_ids(payload):
        return 'file attachments'
    # Older clients can submit inline base64 attachments instead of owned
    # file references. Treat any non-empty inline payload as the same paid
    # capability before usage reservation or provider work; never rely on a
    # downstream model transport to reject it.
    inline_files = payload.get('fileData')
    if isinstance(inline_files, list) and any(bool(item) for item in inline_files):
        return 'file attachments'
    if inline_files and not isinstance(inline_files, list):
        return 'file attachments'
    if str(payload.get('projectId') or '').strip():
        return 'Projects'
    if str(payload.get('artifactFormat') or '').strip():
        return 'document downloads'
    if payload.get('longForm'):
        return 'manuscripts'
    if str(payload.get('creativeTool') or '').strip():
        return 'creative tools'
    if str(payload.get('requestedTool') or '').strip().lower() == 'web':
        return 'web research'
    if (
        image_requested
        or payload.get('imageUseReference') is True
        or payload.get('imageReferencePlan') is not None
        or payload.get('imageReferencePlanConfirmed') is True
    ):
        return 'image creation'
    return None


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    tier = tier_name(user)
    internal_access = bool(user.get('internal_tier'))
    return {
        'id': user.get('id'),
        'email': user.get('email'),
        'fullName': user.get('full_name'),
        'profilePicture': user.get('profile_picture'),
        'isVerified': bool(user.get('is_verified')),
        'isGuest': bool(user.get('is_guest')),
        'passwordSetupRequired': bool(user.get('password_setup_required')),
        'freeMessageLimit': FREE_TEXT_MESSAGE_LIMIT,
        'freeMessageWindowKind': 'rolling_24h',
        'freeMessageWindowSeconds': FREE_TEXT_WINDOW_SECONDS,
        # Compatibility only. Live usage is fetched from /api/usage/check;
        # the retired lifetime counter is never presented as authoritative.
        'guestMessageLimit': FREE_TEXT_MESSAGE_LIMIT,
        'createdAt': user.get('created_at'),
        'preferences': user.get('preferences') or {},
        'tier': tier,
        'subscriptionTier': tier,
        'subscriptionStatus': 'internal' if internal_access else user.get('subscription_status') or 'inactive',
        'trialEnd': user.get('trial_end'),
        'termsAcceptedAt': user.get('terms_accepted_at'),
        'termsVersion': user.get('terms_version'),
        'policyBundleId': CURRENT_POLICY_BUNDLE_ID,
        'policyBundleHash': CURRENT_POLICY_BUNDLE_HASH,
        # Never promote the legacy timestamp/version mirror to authoritative
        # acceptance. Emergency rollback code can write those fields without
        # creating an append-only receipt. Only authenticate_request or a
        # successful receipt writer may set this private response marker.
        'policyAcceptedCurrent': user.get('_policy_accepted_current') is True,
    }


def session_tokens_from_request(request: Request, settings: Settings) -> tuple[str, ...]:
    authorization = request.headers.get('authorization', '')
    if authorization.lower().startswith('bearer '):
        candidate = authorization[7:].strip()
        if candidate:
            return (candidate,)

    # Browsers can retain both a legacy parent-domain cookie and a newer
    # host-only cookie with the same name. Starlette's cookie mapping exposes
    # only one of those values, which can make a successful login look invalid
    # when the stale value is selected. Inspect the bounded raw cookie list and
    # allow authentication to use the first still-valid candidate.
    candidates: list[str] = []
    cookie_name = settings.session_cookie_name
    for raw_name, raw_value in request.scope.get('headers', []):
        if raw_name.lower() != b'cookie':
            continue
        try:
            cookie_header = raw_value.decode('latin-1')
        except (AttributeError, UnicodeDecodeError):
            continue
        for item in cookie_header.split(';'):
            name, separator, value = item.partition('=')
            candidate = value.strip().strip('"')
            if (
                not separator
                or name.strip() != cookie_name
                or not candidate
                or len(candidate) > 512
                or candidate in candidates
            ):
                continue
            candidates.append(candidate)
            if len(candidates) >= 4:
                return tuple(candidates)

    if not candidates:
        fallback = request.cookies.get(cookie_name)
        if fallback:
            candidates.append(fallback)
    return tuple(candidates)


def session_token_from_request(request: Request, settings: Settings) -> str | None:
    candidates = session_tokens_from_request(request, settings)
    return candidates[0] if candidates else None


def _session_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _registration_guest_session_is_eligible(session: dict[str, Any]) -> bool:
    """Allow active sessions or sessions revoked specifically by guest control.

    A logout/revoke remains final. Disable-and-drain records its authoritative
    revocation timestamp in ``device_info`` so registration can still claim the
    exact guest row without reopening any ordinary guest capability.
    """
    revoked_at = session.get('revoked_at')
    if revoked_at is None:
        return True
    device_info = session.get('device_info')
    if not isinstance(device_info, dict):
        return False
    marked_at = device_info.get('guestControlRevokedAt')
    revoked_timestamp = _session_timestamp(revoked_at)
    marked_timestamp = _session_timestamp(marked_at)
    return bool(
        revoked_timestamp is not None
        and marked_timestamp is not None
        and revoked_timestamp == marked_timestamp
    )


async def authenticate_guest_for_registration(
    request: Request,
    db: SupabaseDB,
    settings: Settings,
) -> AuthenticatedUser:
    """Resolve only the guest identity that registration may upgrade in place.

    This deliberately does not read the guest-mode control. Ordinary guest
    authentication stays fail-closed, while account conversion can preserve
    the guest's row, conversation, and usage ledger during a disablement or a
    transiently unreadable control. Only an unexpired active token or a token
    revoked by the database disable-and-drain operation is eligible.
    """
    raw_tokens = session_tokens_from_request(request, settings)
    if not raw_tokens:
        raise AuthenticationError()

    now = iso_now()
    for raw_token in raw_tokens:
        session = await db.select_one(
            'sessions',
            columns='*',
            filters={
                'token_hash': eq(token_hash(raw_token)),
                'expires_at': gt(now),
            },
        )
        if not session or not _registration_guest_session_is_eligible(session):
            continue

        user = await db.select_one(
            'users',
            columns='*',
            filters={'id': eq(session['user_id'])},
        )
        if not user or user.get('deleted_at') or not is_guest_user(user):
            continue
        return AuthenticatedUser(user=user, session=session, token=raw_token)

    raise AuthenticationError('No guest work is available to preserve.')


def _new_session_values(
    settings: Settings,
    user: dict[str, Any],
    request: Request,
    *,
    raw_token: str,
    device_name: str | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    """Build the shared persisted-session shape for ordinary and conversion mints."""
    now = iso_now()
    resolved_platform = (
        platform or request.headers.get('x-crump-platform') or 'web'
    )[:80]
    return {
        'user_id': user['id'],
        'token_hash': token_hash(raw_token),
        'expires_at': expiry_iso(days=settings.session_days),
        'created_at': now,
        'last_activity': now,
        'ip_address': client_ip(
            dict(request.headers),
            request.client.host if request.client else None,
        ),
        'user_agent': request.headers.get('user-agent', 'Unknown')[:1000],
        'device_id': (request.headers.get('x-installation-id') or '')[:200] or None,
        'device_name': (
            device_name or request.headers.get('x-device-name') or 'Unknown device'
        )[:160],
        'platform': resolved_platform,
        'device_info': {
            'client': request.headers.get('x-crump-client', 'web'),
            'platform': resolved_platform,
        },
        'revoked_at': None,
    }


async def verify_guest_and_create_session(
    db: SupabaseDB,
    settings: Settings,
    user: dict[str, Any],
    request: Request,
    *,
    verification_token_hash: str,
    device_name: str | None = None,
    platform: str | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """Atomically convert a guest, drain old sessions, and mint its first account session.

    The database function locks and rechecks the user row. A concurrent verifier
    therefore either owns the one guest-to-account transition or observes that
    another transaction already completed it; no pre-verification session can
    survive the transition commit.
    """
    if not is_guest_user(user) or user.get('is_verified'):
        return None

    raw_token = random_token(48)
    session_id = new_uuid()
    session_values = _new_session_values(
        settings,
        user,
        request,
        raw_token=raw_token,
        device_name=device_name,
        platform=platform,
    )
    rows = await db.rpc(
        'verify_guest_and_create_session_v1',
        {
            'p_user_id': user['id'],
            'p_verification_token_hash': verification_token_hash,
            'p_session_id': session_id,
            'p_session_token_hash': session_values['token_hash'],
            'p_session_expires_at': session_values['expires_at'],
            'p_device_id': session_values['device_id'],
            'p_device_name': session_values['device_name'],
            'p_platform': session_values['platform'],
            'p_device_info': session_values['device_info'],
            'p_ip_address': session_values['ip_address'],
            'p_user_agent': session_values['user_agent'],
        },
    )
    result = rows[0] if isinstance(rows, list) and rows else None
    if not result or result.get('converted') is not True:
        return None

    verified_user = result.get('user_data')
    session = result.get('session_data')
    if not isinstance(verified_user, dict) or not isinstance(session, dict):
        raise RuntimeError('Guest verification did not return its atomic session.')
    return raw_token, verified_user, session


async def verify_registered_and_create_session(
    db: SupabaseDB,
    settings: Settings,
    user: dict[str, Any],
    request: Request,
    *,
    verification_token_hash: str,
    device_name: str | None = None,
    platform: str | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """Atomically verify a registered account and mint its first session.

    The database function shares the users-row serialization point with password
    reset and password login. A reset that commits first invalidates the email
    token before this session can be written; a reset that commits second revokes
    the session created here.
    """
    if is_guest_user(user) or user.get('is_verified'):
        return None

    raw_token = random_token(48)
    session_values = _new_session_values(
        settings,
        user,
        request,
        raw_token=raw_token,
        device_name=device_name,
        platform=platform,
    )
    rows = await db.rpc(
        'verify_registered_and_create_session_v1',
        {
            'p_user_id': user['id'],
            'p_verification_token_hash': verification_token_hash,
            'p_session_id': new_uuid(),
            'p_session_token_hash': session_values['token_hash'],
            'p_session_expires_at': session_values['expires_at'],
            'p_device_id': session_values['device_id'],
            'p_device_name': session_values['device_name'],
            'p_platform': session_values['platform'],
            'p_device_info': session_values['device_info'],
            'p_ip_address': session_values['ip_address'],
            'p_user_agent': session_values['user_agent'],
        },
    )
    result = rows[0] if isinstance(rows, list) and len(rows) == 1 else None
    if not result or result.get('verification_applied') is not True:
        return None

    verified_user = result.get('user_data')
    session = result.get('session_data')
    if not isinstance(verified_user, dict) or not isinstance(session, dict):
        raise RuntimeError(
            'Registered verification did not return its atomic session.'
        )
    return raw_token, verified_user, session


async def complete_initial_password_setup(
    db: SupabaseDB,
    authenticated: AuthenticatedUser,
    *,
    password_hash: str,
) -> tuple[dict[str, Any], int] | None:
    """Set the first verified password through the exact inbox-proof session.

    The database locks the user before validating the session tuple, updates the
    password, and revokes every other session in one transaction. This prevents
    a pre-registration password or pre-verification guest session from surviving
    the inbox owner's transition.
    """
    rows = await db.rpc(
        'complete_initial_password_setup_v1',
        {
            'p_user_id': authenticated.user['id'],
            'p_session_id': authenticated.session['id'],
            'p_session_token_hash': authenticated.session['token_hash'],
            'p_password_hash': password_hash,
        },
    )
    result = rows[0] if isinstance(rows, list) and len(rows) == 1 else None
    if not result or result.get('password_setup_applied') is not True:
        return None
    updated_user = result.get('user_data')
    if not isinstance(updated_user, dict):
        raise RuntimeError('Password setup did not return the updated account.')
    return updated_user, int(result.get('revoked_sessions') or 0)


async def finalize_login_session(
    db: SupabaseDB,
    settings: Settings,
    user: dict[str, Any],
    request: Request,
    *,
    expected_password_hash: str,
    upgraded_password_hash: str | None = None,
    device_name: str | None = None,
    platform: str | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """Issue a login session only while the verified password state is current.

    Password verification necessarily happens in Python, but the database locks
    the user row and compares the exact hash Python verified before it writes a
    session or upgrades that hash. A concurrent password reset therefore either
    revokes this session after login commits or makes this stale login fail closed.
    """
    raw_token = random_token(48)
    session_values = _new_session_values(
        settings,
        user,
        request,
        raw_token=raw_token,
        device_name=device_name,
        platform=platform,
    )
    rows = await db.rpc(
        'finalize_password_login_v1',
        {
            'p_user_id': user['id'],
            'p_expected_password_hash': expected_password_hash,
            'p_upgraded_password_hash': upgraded_password_hash,
            'p_session_id': new_uuid(),
            'p_session_token_hash': session_values['token_hash'],
            'p_session_expires_at': session_values['expires_at'],
            'p_device_id': session_values['device_id'],
            'p_device_name': session_values['device_name'],
            'p_platform': session_values['platform'],
            'p_device_info': session_values['device_info'],
            'p_ip_address': session_values['ip_address'],
            'p_user_agent': session_values['user_agent'],
        },
    )
    result = rows[0] if isinstance(rows, list) and len(rows) == 1 else None
    if not result or result.get('login_applied') is not True:
        return None

    current_user = result.get('user_data')
    session = result.get('session_data')
    if not isinstance(current_user, dict) or not isinstance(session, dict):
        raise RuntimeError('Atomic login did not return its persisted session.')
    return raw_token, current_user, session


async def create_session(
    db: SupabaseDB,
    settings: Settings,
    user: dict[str, Any],
    request: Request,
    *,
    device_name: str | None = None,
    platform: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Create or atomically rotate the authenticated session for an installation.

    ``sessions.device_id`` is unique. A stable installation ID therefore uses one
    PostgREST upsert keyed by ``device_id`` instead of a read-then-write sequence.
    Concurrent successful logins on the same installation converge on one row and
    the last completed login owns the freshly issued token.
    """
    raw_token = random_token(48)
    payload = _new_session_values(
        settings,
        user,
        request,
        raw_token=raw_token,
        device_name=device_name,
        platform=platform,
    )
    now = payload['created_at']
    device_id = payload['device_id']

    if device_id:
        rows = await db.upsert('sessions', payload, on_conflict='device_id')
        session = rows[0] if isinstance(rows, list) and rows else None
        if not session:
            session = await db.select_one(
                'sessions',
                columns='*',
                filters={'device_id': eq(device_id)},
            )
        if not session:
            raise RuntimeError('Session rotation did not return a persisted session.')
    else:
        insert_payload = {'id': new_uuid(), **payload}
        rows = await db.insert('sessions', insert_payload)
        session = rows[0] if isinstance(rows, list) and rows else insert_payload

    # Keep the most recent sessions while avoiding an unbounded table.
    sessions = await db.select(
        'sessions',
        columns='id,created_at',
        filters={'user_id': eq(user['id']), 'revoked_at': 'is.null'},
        order='created_at.desc',
        limit=40,
    )
    for stale in sessions[20:]:
        await db.update('sessions', {'revoked_at': now}, filters={'id': eq(stale['id'])})
    return raw_token, session


async def touch_authenticated_session(
    db: SupabaseDB,
    settings: Settings,
    auth: AuthenticatedUser,
    *,
    now: str | None = None,
) -> None:
    """Renew an already-authenticated session using the ordinary touch rules.

    Routes that must validate an additional request-bound identity before any
    database mutation can authenticate with ``touch=False``, perform that
    validation, and then call this helper. Keeping the implementation here
    preserves the same ten-minute write throttle and expiry renewal used by
    ordinary authenticated requests.
    """
    session = auth.session
    touch_time = now or iso_now()
    last = session.get('last_activity')
    should_touch = True
    if last:
        try:
            parsed = datetime.fromisoformat(str(last).replace('Z', '+00:00'))
            should_touch = datetime.now(timezone.utc) - parsed > timedelta(minutes=10)
        except ValueError:
            pass
    if should_touch:
        renewed_expiry = expiry_iso(days=settings.session_days)
        await db.update(
            'sessions',
            {'last_activity': touch_time, 'expires_at': renewed_expiry},
            filters={'id': eq(session['id'])},
        )
        session['last_activity'] = touch_time
        session['expires_at'] = renewed_expiry


async def authenticate_request(
    request: Request,
    db: SupabaseDB,
    settings: Settings,
    *,
    touch: bool = True,
    require_account: bool = False,
    require_expected_owner_header: bool = False,
    require_current_policy_acceptance: bool = True,
    include_policy_acceptance_state: bool = False,
) -> AuthenticatedUser:
    raw_tokens = session_tokens_from_request(request, settings)
    if not raw_tokens:
        raise AuthenticationError()

    now = iso_now()
    raw_token = raw_tokens[0]
    session = None
    for candidate in raw_tokens:
        session = await db.select_one(
            'sessions',
            columns='*',
            filters={
                'token_hash': eq(token_hash(candidate)),
                'revoked_at': 'is.null',
                'expires_at': gt(now),
            },
        )
        if session:
            raw_token = candidate
            break
    if not session:
        raise AuthenticationError('Your session has expired. Please sign in again.')

    owner_claim_supplied = request.headers.get(EXPECTED_OWNER_HEADER) is not None
    if owner_claim_supplied:
        # Generic private API clients attach this precondition to every call.
        # Validate any supplied claim centrally, even on routes that still
        # permit legacy callers to omit it. The authenticated session already
        # binds the owner ID, so reject cookie skew before reading that owner's
        # account state or performing the normal session-renewal write.
        require_expected_owner(request, session['user_id'])
    elif require_expected_owner_header and not ALLOW_LEGACY_MISSING_EXPECTED_OWNER:
        # Enforcement is deliberately staged. Keep the route markers active so
        # removing the compatibility window is a one-line, reviewable release.
        require_expected_owner(request, session['user_id'])
    user = await db.select_one('users', columns='*', filters={'id': eq(session['user_id'])})
    if not user or user.get('deleted_at'):
        raise AuthenticationError('This account is no longer available.')
    if is_guest_user(user) and not await guest_mode_enabled(db):
        # The session drain is the normal disable path. This read is the
        # defense-in-depth path for a missing/corrupt control row or a token
        # racing rollback: an existing guest token must also fail closed.
        raise AuthenticationError(
            'Guest preview is temporarily unavailable. Sign in or create an account.',
            status_code=503,
        )
    receipt = None
    if require_current_policy_acceptance or include_policy_acceptance_state:
        receipt = await read_current_policy_acceptance(db, user_id=str(user['id']))
        user['_policy_accepted_current'] = receipt is not None
    if require_current_policy_acceptance:
        if receipt is None:
            raise AuthenticationError(
                'Accept the current Terms, Privacy Notice, age attestation, and AI provider disclosure to continue.',
                status_code=403,
                code='POLICY_ACCEPTANCE_REQUIRED',
                details={
                    'policyAcceptanceRequired': True,
                    'requiredPolicyBundle': CURRENT_POLICY_BUNDLE_ID,
                    'requiredPolicyBundleHash': CURRENT_POLICY_BUNDLE_HASH,
                },
            )
    if require_account and is_guest_user(user):
        raise AuthenticationError(
            'Create your free account to use this feature.',
            status_code=403,
        )

    authenticated = AuthenticatedUser(user=user, session=session, token=raw_token)
    if touch:
        await touch_authenticated_session(db, settings, authenticated, now=now)

    return authenticated


async def revoke_current_session(request: Request, db: SupabaseDB, settings: Settings) -> None:
    for raw_token in session_tokens_from_request(request, settings):
        await db.update(
            'sessions',
            {'revoked_at': iso_now()},
            filters={'token_hash': eq(token_hash(raw_token)), 'revoked_at': 'is.null'},
        )
