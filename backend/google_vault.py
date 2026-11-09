"""Token vault for connected-account credentials.

Tokens are never stored in plaintext. Encryption stays behind the two
isolated functions in this module so the storage format can move to a
managed KMS without touching the connector or the routes.

The vault fails closed: without ``GOOGLE_TOKEN_ENCRYPTION_KEY`` it
raises ``GOOGLE_VAULT_NOT_CONFIGURED`` instead of writing anything.
Encryption uses AES-GCM from the ``cryptography`` package when that
package is importable; it is currently present only as a transitive
dependency (via ``PyJWT[crypto]``), so a deployment must either promote
it to a direct dependency or replace these functions with a KMS call
before a real account is connected. Tests inject a fake vault instead
of relying on any of this.
"""
from __future__ import annotations

import base64
import hashlib
import os
from collections.abc import Callable


class GoogleVaultError(RuntimeError):
    def __init__(
        self,
        message: str = 'Google token storage is not configured.',
        code: str = 'GOOGLE_VAULT_NOT_CONFIGURED',
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = 503


def _decode_key(raw: str) -> bytes:
    text = str(raw or '').strip()
    try:
        decoded = base64.urlsafe_b64decode(text.encode('ascii'))
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return hashlib.sha256(text.encode('utf-8')).digest()


def _encrypt_with_key(key: bytes, plaintext: str) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as exc:
        raise GoogleVaultError(
            'Google token encryption is unavailable on this deployment.',
            code='GOOGLE_VAULT_ENCRYPTION_UNAVAILABLE',
        ) from exc
    nonce = os.urandom(12)
    sealed = AESGCM(key).encrypt(nonce, plaintext.encode('utf-8'), None)
    return base64.urlsafe_b64encode(nonce + sealed).decode('ascii')


def _decrypt_with_key(key: bytes, ciphertext: str) -> str:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as exc:
        raise GoogleVaultError(
            'Google token encryption is unavailable on this deployment.',
            code='GOOGLE_VAULT_ENCRYPTION_UNAVAILABLE',
        ) from exc
    raw = base64.urlsafe_b64decode(str(ciphertext or '').encode('ascii'))
    return AESGCM(key).decrypt(raw[:12], raw[12:], None).decode('utf-8')


class GoogleVault:
    """Encrypt and decrypt OAuth tokens for storage in agent_connections."""

    def __init__(
        self,
        encryption_key: str | None = None,
        *,
        encrypt_fn: Callable[[str], str] | None = None,
        decrypt_fn: Callable[[str], str] | None = None,
    ) -> None:
        self._key = (
            encryption_key
            if encryption_key is not None
            else os.getenv('GOOGLE_TOKEN_ENCRYPTION_KEY')
        )
        self._encrypt_fn = encrypt_fn
        self._decrypt_fn = decrypt_fn

    @property
    def configured(self) -> bool:
        if self._encrypt_fn is not None and self._decrypt_fn is not None:
            return True
        return bool(str(self._key or '').strip())

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return ''
        if self._encrypt_fn is not None:
            return self._encrypt_fn(plaintext)
        if not self.configured:
            raise GoogleVaultError()
        return _encrypt_with_key(_decode_key(str(self._key)), plaintext)

    def decrypt(self, ciphertext: str) -> str:
        if not ciphertext:
            return ''
        if self._decrypt_fn is not None:
            return self._decrypt_fn(ciphertext)
        if not self.configured:
            raise GoogleVaultError()
        return _decrypt_with_key(_decode_key(str(self._key)), ciphertext)
