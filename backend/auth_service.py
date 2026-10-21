from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import Settings
from .db import SupabaseDB, eq, gt
from .security import client_ip, expiry_iso, iso_now, new_uuid, random_token, token_hash
from .usage_service import tier_name


@dataclass(slots=True)
class AuthenticatedUser:
    user: dict[str, Any]
    session: dict[str, Any]
    token: str


class AuthenticationError(RuntimeError):
    def __init__(self, message: str = 'Authentication required.', status_code: int = 401) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


# Guest mode: a signed-out visitor gets a real anonymous account and a small
# chat allowance. Reaching the limit (or touching any account/paid surface)
# is what asks them to create a free account — which upgrades the same row,
# so their conversation carries over.
GUEST_MESSAGE_LIMIT = 5


def is_guest_user(user: dict[str, Any] | None) -> bool:
    return bool(user and user.get('is_guest'))


def guest_limit_reached(user: dict[str, Any] | None) -> bool:
    if not is_guest_user(user):
        return False
    return int(user.get('guest_message_count') or 0) >= GUEST_MESSAGE_LIMIT


async def reserve_guest_message(db: SupabaseDB, user: dict[str, Any]) -> bool:
    """Atomically consume one message from a guest's allowance.

    Compare-and-swap on users.guest_message_count: the PATCH only lands
    when the stored count still equals the value just read, so two
    concurrent fresh messages can never both take the last slot. Returns
    False when the allowance is exhausted (or a race was lost at the cap).
    Callers must invoke this only for a genuinely fresh message — after
    any idempotency claim has resolved — so retries never double-charge.
    A successful reservation is consumed even if generation later fails:
    the allowance counts messages accepted for generation, the same
    send-based metering the registered plans use. Non-guests have no
    allowance and always pass.
    """
    if not is_guest_user(user):
        return True
    user_id = str(user.get('id') or '')
    if not user_id:
        return False
    for _attempt in range(2):
        row = await db.select_one(
            'users',
            columns='guest_message_count',
            filters={'id': eq(user_id)},
        )
        count = int((row or {}).get('guest_message_count') or 0)
        if count >= GUEST_MESSAGE_LIMIT:
            return False
        updated = await db.update(
            'users',
            {'guest_message_count': count + 1, 'updated_at': iso_now()},
            filters={'id': eq(user_id), 'guest_message_count': eq(count)},
        )
        if updated:
            return True
    return False


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
    """Direct guest capability signals that require an account.

    Only explicit client signals are rejected here; `image_requested` is
    the caller's media-service verdict for the message text. Semantic
    intent is handled separately: creation inference is disabled for
    guests and text-detected artifact/manuscript intent is downgraded to
    plain chat, so an ordinary question is never bounced — it is
    answered as text.
    """
    if _payload_file_ids(payload):
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
        'guestMessagesUsed': int(user.get('guest_message_count') or 0),
        'guestMessageLimit': GUEST_MESSAGE_LIMIT,
        'createdAt': user.get('created_at'),
        'preferences': user.get('preferences') or {},
        'tier': tier,
        'subscriptionTier': tier,
        'subscriptionStatus': 'internal' if internal_access else user.get('subscription_status') or 'inactive',
        'trialEnd': user.get('trial_end'),
        'termsAcceptedAt': user.get('terms_accepted_at'),
        'termsVersion': user.get('terms_version'),
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
    now = iso_now()
    device_id = (request.headers.get('x-installation-id') or '')[:200] or None

    payload = {
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
        'device_id': device_id,
        'device_name': (
            device_name or request.headers.get('x-device-name') or 'Unknown device'
        )[:160],
        'platform': (
            platform or request.headers.get('x-crump-platform') or 'web'
        )[:80],
        'device_info': {
            'client': request.headers.get('x-crump-client', 'web'),
            'platform': platform or request.headers.get('x-crump-platform') or 'web',
        },
        'revoked_at': None,
    }

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


async def authenticate_request(
    request: Request,
    db: SupabaseDB,
    settings: Settings,
    *,
    touch: bool = True,
    require_account: bool = False,
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

    user = await db.select_one('users', columns='*', filters={'id': eq(session['user_id'])})
    if not user or user.get('deleted_at'):
        raise AuthenticationError('This account is no longer available.')
    if require_account and is_guest_user(user):
        raise AuthenticationError(
            'Create your free account to use this feature.',
            status_code=403,
        )

    if touch:
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
                {'last_activity': now, 'expires_at': renewed_expiry},
                filters={'id': eq(session['id'])},
            )
            session['last_activity'] = now
            session['expires_at'] = renewed_expiry

    return AuthenticatedUser(user=user, session=session, token=raw_token)


async def revoke_current_session(request: Request, db: SupabaseDB, settings: Settings) -> None:
    for raw_token in session_tokens_from_request(request, settings):
        await db.update(
            'sessions',
            {'revoked_at': iso_now()},
            filters={'token_hash': eq(token_hash(raw_token)), 'revoked_at': 'is.null'},
        )
