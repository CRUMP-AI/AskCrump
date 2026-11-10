"""Token vault for connected-account credentials.

Tokens are never stored in plaintext. Encryption stays behind the two
isolated methods in this module so the storage format can move to a
managed KMS without touching the connector or the routes.

Construction (format version 2):

- The master key is ``GOOGLE_TOKEN_ENCRYPTION_KEY``, a base64-encoded
  32-byte key. A missing or malformed key makes the vault unavailable:
  it fails closed with ``GOOGLE_VAULT_NOT_CONFIGURED`` instead of
  writing anything or falling back to a weaker derivation.
- The data-encryption key is derived from the master key with
  HKDF-SHA256 (salt=None, length=32) and the domain-separation info
  string ``b"askcrump/google-token-v2"``, so these keys are bound to
  this one purpose and never reused elsewhere.
- Ciphertexts are sealed with AES-256-GCM under a fresh 12-byte random
  nonce per encryption. The stored string is
  ``"v2." + base64(nonce || ciphertext || tag)`` using standard
  base64. Anything without the ``v2.`` prefix is rejected: format v1
  values are treated as malformed (clean break — no production
  connections or ciphertexts exist yet).
- Every seal/open is bound to the connection it belongs to through
  GCM associated data: the UTF-8 encoding of
  ``user_id + "\\n" + provider + "\\n" + connection_id``, built only
  from trusted server-side identifiers (the authenticated user, the
  literal provider from server code, and the connection row's id) —
  never from caller-supplied payload fields. A ciphertext sealed for
  one connection cannot be opened as another.
"""
from __future__ import annotations

import base64
import binascii
import os
from collections.abc import Callable

_FORMAT_PREFIX = 'v2.'
_KDF_INFO = b'askcrump/google-token-v2'
_NONCE_BYTES = 12


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


def _parse_master_key(raw: str | None) -> bytes | None:
    """Return the 32-byte master key, or None when missing/malformed."""
    text = str(raw or '').strip()
    if not text:
        return None
    try:
        decoded = base64.b64decode(text.encode('ascii'), validate=True)
    except (binascii.Error, ValueError, UnicodeEncodeError):
        return None
    if len(decoded) != 32:
        return None
    return decoded


def _derive_data_key(master_key: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_KDF_INFO,
    ).derive(master_key)


def _associated_data(user_id: str, provider: str, connection_id: str) -> bytes:
    return f'{user_id}\n{provider}\n{connection_id}'.encode('utf-8')


def _load_aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except Exception as exc:
        raise GoogleVaultError(
            'Google token encryption is unavailable on this deployment.',
            code='GOOGLE_VAULT_ENCRYPTION_UNAVAILABLE',
        ) from exc
    return AESGCM


def _encrypt_with_key(
    key: bytes, plaintext: str, *, user_id: str, provider: str, connection_id: str
) -> str:
    aesgcm = _load_aesgcm()
    nonce = os.urandom(_NONCE_BYTES)
    sealed = aesgcm(key).encrypt(
        nonce,
        plaintext.encode('utf-8'),
        _associated_data(user_id, provider, connection_id),
    )
    return _FORMAT_PREFIX + base64.b64encode(nonce + sealed).decode('ascii')


def _decrypt_with_key(
    key: bytes, ciphertext: str, *, user_id: str, provider: str, connection_id: str
) -> str:
    stored = str(ciphertext or '')
    if not stored.startswith(_FORMAT_PREFIX):
        raise GoogleVaultError(
            'The stored Google token is not in a supported format.',
            code='GOOGLE_VAULT_DECRYPT_FAILED',
        )
    try:
        raw = base64.b64decode(
            stored[len(_FORMAT_PREFIX):].encode('ascii'), validate=True
        )
    except (binascii.Error, ValueError, UnicodeEncodeError) as exc:
        raise GoogleVaultError(
            'The stored Google token could not be read.',
            code='GOOGLE_VAULT_DECRYPT_FAILED',
        ) from exc
    if len(raw) <= _NONCE_BYTES:
        raise GoogleVaultError(
            'The stored Google token could not be read.',
            code='GOOGLE_VAULT_DECRYPT_FAILED',
        )
    aesgcm = _load_aesgcm()
    try:
        opened = aesgcm(key).decrypt(
            raw[:_NONCE_BYTES],
            raw[_NONCE_BYTES:],
            _associated_data(user_id, provider, connection_id),
        )
    except Exception as exc:
        raise GoogleVaultError(
            'The stored Google token could not be read.',
            code='GOOGLE_VAULT_DECRYPT_FAILED',
        ) from exc
    return opened.decode('utf-8')


class GoogleVault:
    """Encrypt and decrypt OAuth tokens for storage in agent_connections."""

    def __init__(
        self,
        encryption_key: str | None = None,
        *,
        encrypt_fn: Callable[..., str] | None = None,
        decrypt_fn: Callable[..., str] | None = None,
    ) -> None:
        self._key = (
            encryption_key
            if encryption_key is not None
            else os.getenv('GOOGLE_TOKEN_ENCRYPTION_KEY')
        )
        self._encrypt_fn = encrypt_fn
        self._decrypt_fn = decrypt_fn
        self._data_key: bytes | None = None

    @property
    def configured(self) -> bool:
        if self._encrypt_fn is not None and self._decrypt_fn is not None:
            return True
        return _parse_master_key(self._key) is not None

    def _require_data_key(self) -> bytes:
        if self._data_key is None:
            master_key = _parse_master_key(self._key)
            if master_key is None:
                raise GoogleVaultError()
            self._data_key = _derive_data_key(master_key)
        return self._data_key

    def encrypt(
        self,
        plaintext: str,
        *,
        user_id: str,
        provider: str,
        connection_id: str,
    ) -> str:
        if not plaintext:
            return ''
        context = {
            'user_id': str(user_id),
            'provider': str(provider),
            'connection_id': str(connection_id),
        }
        if self._encrypt_fn is not None:
            return self._encrypt_fn(plaintext, **context)
        return _encrypt_with_key(self._require_data_key(), plaintext, **context)

    def decrypt(
        self,
        ciphertext: str,
        *,
        user_id: str,
        provider: str,
        connection_id: str,
    ) -> str:
        if not ciphertext:
            return ''
        context = {
            'user_id': str(user_id),
            'provider': str(provider),
            'connection_id': str(connection_id),
        }
        if self._decrypt_fn is not None:
            return self._decrypt_fn(ciphertext, **context)
        return _decrypt_with_key(self._require_data_key(), ciphertext, **context)
