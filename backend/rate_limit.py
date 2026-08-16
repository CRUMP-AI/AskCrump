from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Request

from .db import SupabaseDB
from .security import client_ip, normalize_email, token_hash


@dataclass(slots=True)
class RateLimitError(RuntimeError):
    message: str = 'Too many attempts. Try again later.'
    retry_after: int = 60

    def __str__(self) -> str:
        return self.message


def _hashed_key(scope: str, value: str) -> str:
    return token_hash(f'{scope}:{value}')


async def _consume(
    db: SupabaseDB,
    *,
    scope: str,
    value: str,
    limit: int,
    window_seconds: int,
) -> None:
    result = await db.rpc('consume_rate_limit_event', {
        'p_scope': scope,
        'p_key_hash': _hashed_key(scope, value),
        'p_limit': limit,
        'p_window_seconds': window_seconds,
    })
    row: dict[str, Any] = result[0] if isinstance(result, list) and result else (result or {})
    if not row.get('allowed'):
        raise RateLimitError(retry_after=max(1, int(row.get('retry_after') or window_seconds)))


async def enforce_auth_rate_limit(
    db: SupabaseDB,
    request: Request,
    *,
    action: str,
    identity: str,
    identity_limit: int,
    ip_limit: int,
    window_seconds: int,
) -> None:
    """Apply independent account/token and IP limits without storing raw identifiers."""
    ip = client_ip(dict(request.headers), request.client.host if request.client else None) or 'unknown'
    normalized_identity = normalize_email(identity) if '@' in identity else identity.strip()
    await _consume(
        db,
        scope=f'auth:{action}:identity',
        value=normalized_identity,
        limit=identity_limit,
        window_seconds=window_seconds,
    )
    await _consume(
        db,
        scope=f'auth:{action}:ip',
        value=ip,
        limit=ip_limit,
        window_seconds=window_seconds,
    )


async def enforce_user_rate_limit(
    db: SupabaseDB,
    *,
    user_id: str,
    action: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Limit an authenticated action without persisting the raw user identifier."""
    await _consume(
        db,
        scope=f'user:{action}',
        value=user_id,
        limit=limit,
        window_seconds=window_seconds,
    )
