from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import ipaddress
from typing import Any

from fastapi import Request

from .db import SupabaseDB
from .security import client_ip, normalize_email, token_hash


GUEST_NETWORK_MESSAGE_HASH_DOMAIN = 'ask-crump:guest-network-message:v1'


@dataclass(slots=True)
class RateLimitError(RuntimeError):
    message: str = 'Too many attempts. Try again later.'
    retry_after: int = 60

    def __str__(self) -> str:
        return self.message


def _hashed_key(scope: str, value: str) -> str:
    return token_hash(f'{scope}:{value}')


def guest_network_message_key_hash(
    request: Request,
    secret: str | None,
) -> str | None:
    """Return a keyed, non-reversible guest network bucket identity.

    IPv4 addresses remain distinct (/32). IPv6 privacy addresses share their
    canonical /64. The raw address and subnet never leave this helper, and a
    missing/weak key or unparseable address fails closed by returning ``None``.
    """
    key = str(secret or '').encode('utf-8')
    if len(key) < 32:
        return None
    raw_ip = client_ip(
        dict(request.headers),
        request.client.host if request.client else None,
    )
    try:
        address = ipaddress.ip_address(str(raw_ip or '').strip())
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    if isinstance(address, ipaddress.IPv4Address):
        network_identity = f'ipv4:{address}/32'
    else:
        network = ipaddress.ip_network(f'{address}/64', strict=False)
        network_identity = f'ipv6:{network.network_address}/64'
    material = f'{GUEST_NETWORK_MESSAGE_HASH_DOMAIN}:{network_identity}'.encode('ascii')
    return hmac.new(key, material, hashlib.sha256).hexdigest()


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


async def enforce_guest_admission_rate_limit(
    db: SupabaseDB,
    request: Request,
    *,
    identity: str,
    identity_limit: int,
    ip_limit: int,
    window_seconds: int,
) -> None:
    """Consume guest installation and shared-IP capacity together or not at all."""
    ip = client_ip(dict(request.headers), request.client.host if request.client else None) or 'unknown'
    normalized_identity = identity.strip()
    identity_scope = 'auth:guest:identity'
    ip_scope = 'auth:guest:ip'
    result = await db.rpc('consume_guest_admission_rate_limit_v1', {
        'p_identity_key_hash': _hashed_key(identity_scope, normalized_identity),
        'p_ip_key_hash': _hashed_key(ip_scope, ip),
        'p_identity_limit': identity_limit,
        'p_ip_limit': ip_limit,
        'p_window_seconds': window_seconds,
    })
    row: dict[str, Any] = result[0] if isinstance(result, list) and result else (
        result if isinstance(result, dict) else {}
    )
    if row.get('allowed') is not True:
        try:
            retry_after = int(row.get('retry_after') or window_seconds)
        except (TypeError, ValueError):
            retry_after = window_seconds
        raise RateLimitError(retry_after=max(1, retry_after))


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
