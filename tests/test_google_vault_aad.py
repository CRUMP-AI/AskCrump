"""Vault format v2: context-bound encryption for Google tokens.

The vault seals tokens with AES-256-GCM under a key derived from the
base64 32-byte master key via HKDF-SHA256 (info
``b"askcrump/google-token-v2"``), stores them as
``"v2." + base64(nonce || ciphertext || tag)``, and binds every value
to its connection through associated data built from the trusted
server-side ids (user, provider, connection). These tests pin the
round-trip, the context binding in each dimension, tamper and legacy
rejection, the fail-closed key handling, and key rotation.
"""
import base64
import hashlib

import pytest

from backend.google_vault import GoogleVault, GoogleVaultError

USER_ID = '11111111-1111-1111-1111-111111111111'
OTHER_USER_ID = '22222222-2222-2222-2222-222222222222'
CONNECTION_ID = 'conn-1'
OTHER_CONNECTION_ID = 'conn-2'
PROVIDER = 'google'

CONTEXT = {
    'user_id': USER_ID,
    'provider': PROVIDER,
    'connection_id': CONNECTION_ID,
}

MASTER_KEY_BYTES = bytes(range(32))
OTHER_KEY_BYTES = bytes(range(32, 64))


def _key(raw: bytes) -> str:
    return base64.b64encode(raw).decode('ascii')


def _vault(raw: bytes = MASTER_KEY_BYTES) -> GoogleVault:
    return GoogleVault(encryption_key=_key(raw))


def _legacy_v1_value(plaintext: str) -> str:
    """Reproduce a pre-v2 stored value (SHA-256 key, no AAD, no prefix)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = hashlib.sha256(b'any-old-key-material').digest()
    nonce = b'\x00' * 12
    sealed = AESGCM(key).encrypt(nonce, plaintext.encode('utf-8'), None)
    return base64.urlsafe_b64encode(nonce + sealed).decode('ascii')


def test_round_trip_with_matching_context_returns_plaintext():
    vault = _vault()
    sealed = vault.encrypt('access-token-value', **CONTEXT)
    assert sealed.startswith('v2.')
    assert 'access-token-value' not in sealed
    assert vault.decrypt(sealed, **CONTEXT) == 'access-token-value'


def test_each_encryption_uses_a_fresh_nonce():
    vault = _vault()
    first = vault.encrypt('same-token', **CONTEXT)
    second = vault.encrypt('same-token', **CONTEXT)
    assert first != second
    assert vault.decrypt(first, **CONTEXT) == 'same-token'
    assert vault.decrypt(second, **CONTEXT) == 'same-token'


def test_wrong_user_id_fails():
    vault = _vault()
    sealed = vault.encrypt('token', **CONTEXT)
    with pytest.raises(GoogleVaultError):
        vault.decrypt(sealed, **{**CONTEXT, 'user_id': OTHER_USER_ID})


def test_wrong_provider_fails():
    vault = _vault()
    sealed = vault.encrypt('token', **CONTEXT)
    with pytest.raises(GoogleVaultError):
        vault.decrypt(sealed, **{**CONTEXT, 'provider': 'other-provider'})


def test_wrong_connection_id_fails():
    vault = _vault()
    sealed = vault.encrypt('token', **CONTEXT)
    with pytest.raises(GoogleVaultError):
        vault.decrypt(
            sealed, **{**CONTEXT, 'connection_id': OTHER_CONNECTION_ID}
        )


def test_tampered_ciphertext_fails():
    vault = _vault()
    sealed = vault.encrypt('token', **CONTEXT)
    raw = bytearray(base64.b64decode(sealed[len('v2.'):]))
    raw[-1] ^= 0x01
    tampered = 'v2.' + base64.b64encode(bytes(raw)).decode('ascii')
    with pytest.raises(GoogleVaultError):
        vault.decrypt(tampered, **CONTEXT)


def test_truncated_and_malformed_values_fail():
    vault = _vault()
    sealed = vault.encrypt('token', **CONTEXT)
    bad_values = [
        sealed[: len(sealed) // 2],
        'v2.',
        'v2.not-base64!!!',
        'v2.' + base64.b64encode(b'short').decode('ascii'),
        'not-a-vault-value',
    ]
    for bad in bad_values:
        with pytest.raises(GoogleVaultError):
            vault.decrypt(bad, **CONTEXT)


def test_legacy_format_value_fails():
    vault = _vault()
    legacy = _legacy_v1_value('token')
    assert not legacy.startswith('v2.')
    with pytest.raises(GoogleVaultError):
        vault.decrypt(legacy, **CONTEXT)


def test_missing_key_makes_the_vault_unavailable(monkeypatch):
    monkeypatch.delenv('GOOGLE_TOKEN_ENCRYPTION_KEY', raising=False)
    vault = GoogleVault()
    assert vault.configured is False
    with pytest.raises(GoogleVaultError) as caught:
        vault.encrypt('token', **CONTEXT)
    assert caught.value.code == 'GOOGLE_VAULT_NOT_CONFIGURED'
    with pytest.raises(GoogleVaultError) as caught:
        vault.decrypt('v2.whatever', **CONTEXT)
    assert caught.value.code == 'GOOGLE_VAULT_NOT_CONFIGURED'


@pytest.mark.parametrize(
    'bad_key',
    [
        'not-base64!!!',
        base64.b64encode(b'\x01' * 16).decode('ascii'),
        base64.b64encode(b'\x01' * 64).decode('ascii'),
        'plain-text-passphrase',
    ],
)
def test_malformed_key_fails_closed(bad_key):
    vault = GoogleVault(encryption_key=bad_key)
    assert vault.configured is False
    with pytest.raises(GoogleVaultError) as caught:
        vault.encrypt('token', **CONTEXT)
    assert caught.value.code == 'GOOGLE_VAULT_NOT_CONFIGURED'


def test_key_from_environment_is_used(monkeypatch):
    monkeypatch.setenv('GOOGLE_TOKEN_ENCRYPTION_KEY', _key(MASTER_KEY_BYTES))
    vault = GoogleVault()
    assert vault.configured is True
    sealed = vault.encrypt('token', **CONTEXT)
    assert vault.decrypt(sealed, **CONTEXT) == 'token'


def test_ciphertext_does_not_decrypt_under_a_rotated_key():
    sealed = _vault(MASTER_KEY_BYTES).encrypt('token', **CONTEXT)
    with pytest.raises(GoogleVaultError):
        _vault(OTHER_KEY_BYTES).decrypt(sealed, **CONTEXT)
