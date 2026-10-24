"""Versioned password-reset aliases bound to the active database token hash."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import re
import uuid


_VERSION = 'r1'
_KEY_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,16}$')
_NONCE_RE = re.compile(r'^[A-Za-z0-9_-]{16,64}$')
_EXPIRY_RE = re.compile(r'^[1-9][0-9]{9,11}$')
_SIGNATURE_RE = re.compile(r'^[A-Za-z0-9_-]{43}$')
_ANCHOR_RE = re.compile(r'^[0-9a-fA-F]{64}$')


@dataclass(frozen=True, slots=True)
class PasswordResetAlias:
    key_id: str
    user_id: str
    nonce: str
    expires_at: int
    signature: str


def _urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _anchor(value: object) -> str:
    normalized = str(value or '').strip().lower()
    if not _ANCHOR_RE.fullmatch(normalized):
        raise ValueError('Password-reset token anchor is invalid.')
    return normalized


def _expiry_epoch(value: object) -> int:
    if isinstance(value, int):
        resolved = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except (TypeError, ValueError) as exc:
            raise ValueError('Password-reset alias expiry is invalid.') from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        resolved = int(parsed.timestamp())
    if resolved <= 0 or not _EXPIRY_RE.fullmatch(str(resolved)):
        raise ValueError('Password-reset alias expiry is invalid.')
    return resolved


def _signature(
    signing_secret: str,
    *,
    key_id: str,
    user_id: str,
    nonce: str,
    expires_at: int,
    password_reset_token_hash: object,
) -> str:
    secret = str(signing_secret or '')
    if len(secret) < 43:
        raise ValueError('Password-reset signing secret is unavailable.')
    message = (
        f'{_VERSION}\n{key_id}\n{user_id}\n{nonce}\n{expires_at}\n'
        f'{_anchor(password_reset_token_hash)}'
    ).encode('ascii')
    key = hashlib.sha256(
        b'ask-crump-password-reset-alias-v1\x00' + secret.encode('utf-8')
    ).digest()
    return _urlsafe(hmac.new(key, message, hashlib.sha256).digest())


def create_password_reset_alias(
    signing_secret: str,
    *,
    key_id: str,
    user_id: object,
    password_reset_token_hash: object,
    expires_at: object,
    nonce: str,
) -> str:
    canonical_user_id = str(uuid.UUID(str(user_id)))
    resolved_key_id = str(key_id or '')
    resolved_nonce = str(nonce or '')
    resolved_expiry = _expiry_epoch(expires_at)
    if not _KEY_ID_RE.fullmatch(resolved_key_id):
        raise ValueError('Password-reset key id is invalid.')
    if not _NONCE_RE.fullmatch(resolved_nonce):
        raise ValueError('Password-reset nonce is invalid.')
    signature = _signature(
        signing_secret,
        key_id=resolved_key_id,
        user_id=canonical_user_id,
        nonce=resolved_nonce,
        expires_at=resolved_expiry,
        password_reset_token_hash=password_reset_token_hash,
    )
    return (
        f'{_VERSION}.{resolved_key_id}.{canonical_user_id}.{resolved_nonce}.'
        f'{resolved_expiry}.{signature}'
    )


def parse_password_reset_alias(token: object) -> PasswordResetAlias | None:
    value = str(token or '')
    if len(value) > 240:
        return None
    try:
        version, key_id, raw_user_id, nonce, raw_expiry, signature = value.split('.')
        user_id = str(uuid.UUID(raw_user_id))
        expires_at = int(raw_expiry)
    except (TypeError, ValueError):
        return None
    if (
        version != _VERSION
        or not _KEY_ID_RE.fullmatch(key_id)
        or raw_user_id != user_id
        or not _NONCE_RE.fullmatch(nonce)
        or not _EXPIRY_RE.fullmatch(raw_expiry)
        or expires_at <= 0
        or not _SIGNATURE_RE.fullmatch(signature)
    ):
        return None
    return PasswordResetAlias(
        key_id=key_id,
        user_id=user_id,
        nonce=nonce,
        expires_at=expires_at,
        signature=signature,
    )


def password_reset_alias_matches(
    alias: PasswordResetAlias,
    signing_keys: dict[str, str],
    *,
    password_reset_token_hash: object,
) -> bool:
    signing_secret = signing_keys.get(alias.key_id)
    if not signing_secret:
        return False
    try:
        expected = _signature(
            signing_secret,
            key_id=alias.key_id,
            user_id=alias.user_id,
            nonce=alias.nonce,
            expires_at=alias.expires_at,
            password_reset_token_hash=password_reset_token_hash,
        )
    except ValueError:
        return False
    return hmac.compare_digest(alias.signature, expected)
