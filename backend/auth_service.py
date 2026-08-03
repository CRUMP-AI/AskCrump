from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Request

from .config import Settings
from .db import SupabaseDB, eq, gt
from .security import client_ip, expiry_iso, iso_now, new_uuid, random_token, token_hash


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


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    tier = user.get('subscription_tier') or user.get('tier') or 'free'
    return {
        'id': user.get('id'),
        'email': user.get('email'),
        'fullName': user.get('full_name'),
        'profilePicture': user.get('profile_picture'),
        'isVerified': bool(user.get('is_verified')),
        'createdAt': user.get('created_at'),
        'preferences': user.get('preferences') or {},
        'tier': tier,
        'subscriptionTier': tier,
        'subscriptionStatus': user.get('subscription_status') or 'inactive',
        'trialEnd': user.get('trial_end'),
        'termsAcceptedAt': user.get('terms_accepted_at'),
        'termsVersion': user.get('terms_version'),
    }


def session_token_from_request(request: Request, settings: Settings) -> str | None:
    authorization = request.headers.get('authorization', '')
    if authorization.lower().startswith('bearer '):
        candidate = authorization[7:].strip()
        if candidate:
            return candidate
    return request.cookies.get(settings.session_cookie_name)


async def create_session(
    db: SupabaseDB,
    settings: Settings,
    user: dict[str, Any],
    request: Request,
    *,
    device_name: str | None = None,
    platform: str | None = None,
) -> tuple[str, dict[str, Any]]:
    raw_token = random_token(48)
    now = iso_now()
    payload = {
        'id': new_uuid(),
        'user_id': user['id'],
        'token_hash': token_hash(raw_token),
        'expires_at': expiry_iso(days=settings.session_days),
        'created_at': now,
        'last_activity': now,
        'ip_address': client_ip(dict(request.headers), request.client.host if request.client else None),
        'user_agent': request.headers.get('user-agent', 'Unknown')[:1000],
        'device_id': (request.headers.get('x-installation-id') or '')[:200] or None,
        'device_name': (device_name or request.headers.get('x-device-name') or 'Unknown device')[:160],
        'platform': (platform or request.headers.get('x-crump-platform') or 'web')[:80],
        'device_info': {
            'client': request.headers.get('x-crump-client', 'web'),
            'platform': platform or request.headers.get('x-crump-platform') or 'web',
        },
    }
    inserted = await db.insert('sessions', payload)
    session = inserted[0] if isinstance(inserted, list) and inserted else payload

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
) -> AuthenticatedUser:
    raw_token = session_token_from_request(request, settings)
    if not raw_token:
        raise AuthenticationError()

    now = iso_now()
    session = await db.select_one(
        'sessions',
        columns='*',
        filters={
            'token_hash': eq(token_hash(raw_token)),
            'revoked_at': 'is.null',
            'expires_at': gt(now),
        },
    )
    if not session:
        raise AuthenticationError('Your session has expired. Please sign in again.')

    user = await db.select_one('users', columns='*', filters={'id': eq(session['user_id'])})
    if not user or user.get('deleted_at'):
        raise AuthenticationError('This account is no longer available.')

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
    raw_token = session_token_from_request(request, settings)
    if raw_token:
        await db.update(
            'sessions',
            {'revoked_at': iso_now()},
            filters={'token_hash': eq(token_hash(raw_token)), 'revoked_at': 'is.null'},
        )
