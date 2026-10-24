from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from starlette.requests import Request

from backend.auth_service import AuthenticationError
from backend.db import DatabaseError
from backend.email_service import EmailDeliveryError
from backend.routes import auth as auth_routes
from backend.schemas import RegisterRequest, ResendVerificationRequest
from backend.security import token_hash
from backend.verification_tokens import (
    create_resend_verification_alias,
    parse_resend_verification_alias,
    resend_verification_alias_matches,
)


USER_ID = '11111111-1111-4111-8111-111111111111'
OTHER_USER_ID = '22222222-2222-4222-8222-222222222222'
LEGACY_TOKEN = 'the-original-verification-token'
ANCHOR = token_hash(LEGACY_TOKEN)
OTHER_ANCHOR = 'b' * 64
NEW_ANCHOR = token_hash('unused-new-token')
WINNER_ANCHOR = token_hash('concurrent-winner-token')
CURRENT_SIGNING_SECRET = 'current-verification-signing-key-' + ('1' * 48)
OLD_SIGNING_SECRET = 'retired-verification-signing-key-' + ('0' * 48)
SIGNING_KEYS = {
    'k1': CURRENT_SIGNING_SECRET,
    'k0': OLD_SIGNING_SECRET,
}
NOW = '2026-10-25T12:00:00+00:00'
OLD_EXPIRY = '2026-10-26T00:00:00+00:00'
TARGET_EXPIRY = '2026-10-27T12:00:00+00:00'
WINNER_EXPIRY = '2026-10-28T12:00:00+00:00'
PAST_EXPIRY = '2026-10-24T00:00:00+00:00'
GENERIC_RESULT = {
    'success': True,
    'message': 'If verification is needed, a new email has been sent.',
}


def _request(path: str = '/api/auth/resend-verification') -> Request:
    return Request({
        'type': 'http',
        'method': 'POST',
        'path': path,
        'scheme': 'https',
        'server': ('www.askcrump.com', 443),
        'client': ('127.0.0.1', 12345),
        'headers': [],
    })


def _pending_user(**overrides: object) -> dict:
    return {
        'id': USER_ID,
        'email': 'pending@example.com',
        'full_name': 'Pending User',
        'is_verified': False,
        'verification_token_hash': ANCHOR,
        'verification_token_expires': OLD_EXPIRY,
        **overrides,
    }


def _condition_matches(actual: object, condition: object) -> bool:
    value = str(condition)
    if value == 'is.null':
        return actual is None
    if value.startswith('eq.'):
        expected = value.removeprefix('eq.')
        if isinstance(actual, bool):
            return actual is (expected == 'true')
        return str(actual) == expected
    if value.startswith('gt.'):
        if actual is None:
            return False
        expected = value.removeprefix('gt.')
        return datetime.fromisoformat(str(actual).replace('Z', '+00:00')) > datetime.fromisoformat(
            expected.replace('Z', '+00:00')
        )
    raise AssertionError(f'Unsupported fake database condition: {condition}')


class _ResendDB:
    def __init__(
        self,
        user: dict | None,
        *,
        update_mode: str = 'normal',
    ) -> None:
        self.user = dict(user) if user else None
        self.update_mode = update_mode
        self.updates: list[tuple[dict, dict]] = []
        self.selects: list[dict] = []
        self._special_update_used = False
        self._lock = asyncio.Lock()

    def _matches(self, filters: dict) -> bool:
        return bool(
            self.user
            and all(
                _condition_matches(self.user.get(key), condition)
                for key, condition in filters.items()
            )
        )

    async def select_one(self, table, *, filters, **_kwargs):
        assert table == 'users'
        self.selects.append(dict(filters))
        async with self._lock:
            return dict(self.user) if self._matches(filters) else None

    async def update(self, table, payload, *, filters):
        assert table == 'users'
        self.updates.append((dict(payload), dict(filters)))
        async with self._lock:
            if self.update_mode == 'conflict_once' and not self._special_update_used:
                self._special_update_used = True
                assert self.user is not None
                # Model another request winning the generation replacement.
                self.user.update({
                    'verification_token_hash': WINNER_ANCHOR,
                    'verification_token_expires': WINNER_EXPIRY,
                    'updated_at': 'concurrent-writer',
                })
                return []
            if not self._matches(filters):
                return []
            assert self.user is not None
            self.user.update(payload)
            result = [dict(self.user)]
            if self.update_mode == 'apply_then_raise' and not self._special_update_used:
                self._special_update_used = True
                raise DatabaseError(
                    'The response was lost after the write committed.',
                    status_code=503,
                    retryable=True,
                )
            return result


class _VerificationEmail:
    def __init__(self, outcome: bool | Exception = True) -> None:
        self.outcome = outcome
        self.calls: list[dict] = []

    async def send_verification(self, email, name, token, **kwargs):
        self.calls.append({
            'email': email,
            'name': name,
            'token': token,
            **kwargs,
        })
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture(autouse=True)
def stable_recovery_environment(monkeypatch):
    async def allow_rate_limit(*_args, **_kwargs):
        return None

    async def no_guest(*_args, **_kwargs):
        raise AuthenticationError()

    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', allow_rate_limit)
    monkeypatch.setattr(auth_routes, 'authenticate_guest_for_registration', no_guest)
    monkeypatch.setattr(
        auth_routes,
        '_verification_alias_signing_keys',
        lambda: dict(SIGNING_KEYS),
    )
    monkeypatch.setattr(auth_routes, 'expiry_iso', lambda **_kwargs: TARGET_EXPIRY)
    monkeypatch.setattr(auth_routes, 'iso_now', lambda: NOW)
    monkeypatch.setattr(auth_routes, 'hash_password', lambda _password: 'password-hash')
    monkeypatch.setattr(auth_routes, 'random_token', lambda _length: 'unused-new-token')


@pytest.mark.asyncio
async def test_resend_response_is_identical_for_every_account_and_delivery_state(
    monkeypatch,
) -> None:
    cases = [
        (None, True, 0),
        (_pending_user(is_verified=True), True, 0),
        (_pending_user(), True, 1),
        (
            _pending_user(),
            EmailDeliveryError(status_code=503, retryable=True),
            1,
        ),
        (_pending_user(), False, 1),
    ]
    results = []

    for user, outcome, expected_calls in cases:
        database = _ResendDB(user)
        email = _VerificationEmail(outcome)
        monkeypatch.setattr(auth_routes, 'db', database)
        monkeypatch.setattr(auth_routes, 'email_service', email)

        result = await auth_routes.resend_verification(
            ResendVerificationRequest(email='pending@example.com'),
            _request(),
        )

        results.append(result)
        assert len(email.calls) == expected_calls

    # Returning the same ordinary mapping also leaves FastAPI's status at 200.
    assert results == [GENERIC_RESULT] * len(cases)


@pytest.mark.asyncio
async def test_provider_failure_preserves_anchor_and_original_legacy_link(
    monkeypatch,
) -> None:
    database = _ResendDB(_pending_user())
    email = _VerificationEmail(
        EmailDeliveryError(status_code=503, retryable=True),
    )
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'email_service', email)

    result = await auth_routes.resend_verification(
        ResendVerificationRequest(email='pending@example.com'),
        _request(),
    )

    assert result == GENERIC_RESULT
    assert database.user is not None
    assert database.user['verification_token_hash'] == ANCHOR
    assert database.user['verification_token_expires'] == OLD_EXPIRY
    assert database.updates == []
    assert len(email.calls) == 1
    assert email.calls[0]['token'].startswith(f'v2.k1.{USER_ID}.')

    user, resolved_anchor = await auth_routes._verification_user_and_anchor(LEGACY_TOKEN)
    assert user is not None
    assert user['id'] == USER_ID
    assert resolved_anchor == ANCHOR


@pytest.mark.asyncio
async def test_successful_resend_sends_a_valid_alias_without_rotating_anchor(
    monkeypatch,
) -> None:
    database = _ResendDB(_pending_user())
    email = _VerificationEmail(True)
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'email_service', email)

    result = await auth_routes.resend_verification(
        ResendVerificationRequest(email='pending@example.com'),
        _request(),
    )

    assert result == GENERIC_RESULT
    assert database.user is not None
    assert database.user['verification_token_hash'] == ANCHOR
    alias_token = email.calls[0]['token']
    alias = parse_resend_verification_alias(alias_token)
    assert alias is not None
    assert alias.key_id == 'k1'
    assert alias.user_id == USER_ID
    assert alias.expires_at == int(
        datetime.fromisoformat(OLD_EXPIRY).timestamp()
    )
    assert resend_verification_alias_matches(
        alias,
        SIGNING_KEYS,
        verification_token_hash=ANCHOR,
    )
    assert not resend_verification_alias_matches(
        alias,
        SIGNING_KEYS,
        verification_token_hash=OTHER_ANCHOR,
    )
    user, resolved_anchor = await auth_routes._verification_user_and_anchor(alias_token)
    assert user is not None
    assert user['id'] == USER_ID
    assert resolved_anchor == ANCHOR

    old_key_alias = create_resend_verification_alias(
        OLD_SIGNING_SECRET,
        key_id='k0',
        user_id=USER_ID,
        verification_token_hash=ANCHOR,
        expires_at=OLD_EXPIRY,
        nonce='old_key_nonce_123456789',
    )
    old_key_user, old_key_anchor = await auth_routes._verification_user_and_anchor(
        old_key_alias
    )
    assert old_key_user is not None
    assert old_key_anchor == ANCHOR


@pytest.mark.asyncio
async def test_concurrent_resends_send_distinct_aliases_for_one_immutable_anchor(
    monkeypatch,
) -> None:
    database = _ResendDB(_pending_user())
    email = _VerificationEmail(True)
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'email_service', email)

    first, second = await asyncio.gather(
        auth_routes.resend_verification(
            ResendVerificationRequest(email='pending@example.com'),
            _request(),
        ),
        auth_routes.resend_verification(
            ResendVerificationRequest(email='pending@example.com'),
            _request(),
        ),
    )

    assert first == second == GENERIC_RESULT
    assert database.user is not None
    assert database.user['verification_token_hash'] == ANCHOR
    assert len(email.calls) == 2
    tokens = {call['token'] for call in email.calls}
    assert len(tokens) == 2
    for token in tokens:
        alias = parse_resend_verification_alias(token)
        assert alias is not None
        assert resend_verification_alias_matches(
            alias,
            SIGNING_KEYS,
            verification_token_hash=ANCHOR,
        )
        user, resolved_anchor = await auth_routes._verification_user_and_anchor(token)
        assert user is not None
        assert resolved_anchor == ANCHOR


@pytest.mark.asyncio
async def test_ambiguous_expiry_write_is_confirmed_by_readback_before_email(
    monkeypatch,
) -> None:
    database = _ResendDB(
        _pending_user(verification_token_expires=PAST_EXPIRY),
        update_mode='apply_then_raise',
    )
    email = _VerificationEmail(True)
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'email_service', email)

    result = await auth_routes.resend_verification(
        ResendVerificationRequest(email='pending@example.com'),
        _request(),
    )

    assert result == GENERIC_RESULT
    assert len(database.updates) == 1
    assert any(filters == {'id': f'eq.{USER_ID}'} for filters in database.selects)
    assert database.user is not None
    assert database.user['verification_token_hash'] == NEW_ANCHOR
    assert database.user['verification_token_expires'] == TARGET_EXPIRY
    assert len(email.calls) == 1
    alias = parse_resend_verification_alias(email.calls[0]['token'])
    assert alias is not None
    assert resend_verification_alias_matches(
        alias,
        SIGNING_KEYS,
        verification_token_hash=NEW_ANCHOR,
    )


@pytest.mark.asyncio
async def test_expiry_compare_and_swap_conflict_uses_winning_readback(
    monkeypatch,
) -> None:
    database = _ResendDB(
        _pending_user(verification_token_expires=PAST_EXPIRY),
        update_mode='conflict_once',
    )
    email = _VerificationEmail(True)
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'email_service', email)

    result = await auth_routes.resend_verification(
        ResendVerificationRequest(email='pending@example.com'),
        _request(),
    )

    assert result == GENERIC_RESULT
    assert len(database.updates) == 1
    assert database.updates[0][1] == {
        'id': f'eq.{USER_ID}',
        'is_verified': 'eq.false',
        'verification_token_hash': f'eq.{ANCHOR}',
        'verification_token_expires': f'eq.{PAST_EXPIRY}',
    }
    assert any(filters == {'id': f'eq.{USER_ID}'} for filters in database.selects)
    assert database.user is not None
    assert database.user['verification_token_hash'] == WINNER_ANCHOR
    assert database.user['verification_token_expires'] == WINNER_EXPIRY
    assert len(email.calls) == 1
    alias = parse_resend_verification_alias(email.calls[0]['token'])
    assert alias is not None
    assert alias.expires_at == int(datetime.fromisoformat(WINNER_EXPIRY).timestamp())
    assert resend_verification_alias_matches(
        alias,
        SIGNING_KEYS,
        verification_token_hash=WINNER_ANCHOR,
    )
    winner_user, winner_anchor = await auth_routes._verification_user_and_anchor(
        email.calls[0]['token']
    )
    assert winner_user is not None
    assert winner_anchor == WINNER_ANCHOR


@pytest.mark.asyncio
async def test_resend_replaces_expired_generation_without_reviving_old_bearers(
    monkeypatch,
) -> None:
    database = _ResendDB(_pending_user(verification_token_expires=PAST_EXPIRY))
    email = _VerificationEmail(True)
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'email_service', email)
    old_alias = create_resend_verification_alias(
        CURRENT_SIGNING_SECRET,
        key_id='k1',
        user_id=USER_ID,
        verification_token_hash=ANCHOR,
        expires_at=PAST_EXPIRY,
        nonce='expired_nonce_123456789',
    )

    old_raw_user, _ = await auth_routes._verification_user_and_anchor(LEGACY_TOKEN)
    old_alias_user, _ = await auth_routes._verification_user_and_anchor(old_alias)
    assert old_raw_user is None
    assert old_alias_user is None

    result = await auth_routes.resend_verification(
        ResendVerificationRequest(email='pending@example.com'),
        _request(),
    )

    assert result == GENERIC_RESULT
    assert database.user is not None
    assert database.user['verification_token_hash'] == NEW_ANCHOR
    assert database.user['verification_token_expires'] == TARGET_EXPIRY
    assert len(email.calls) == 1

    old_raw_user, _ = await auth_routes._verification_user_and_anchor(LEGACY_TOKEN)
    old_alias_user, _ = await auth_routes._verification_user_and_anchor(old_alias)
    assert old_raw_user is None
    assert old_alias_user is None

    new_alias = email.calls[0]['token']
    new_user, new_anchor = await auth_routes._verification_user_and_anchor(new_alias)
    assert new_user is not None
    assert new_user['id'] == USER_ID
    assert new_anchor == NEW_ANCHOR


@pytest.mark.asyncio
async def test_alias_rejects_signature_nonce_user_anchor_and_expiry_tampering(
    monkeypatch,
) -> None:
    database = _ResendDB(_pending_user(verification_token_expires=TARGET_EXPIRY))
    monkeypatch.setattr(auth_routes, 'db', database)
    alias_token = create_resend_verification_alias(
        CURRENT_SIGNING_SECRET,
        key_id='k1',
        user_id=USER_ID,
        verification_token_hash=ANCHOR,
        expires_at=TARGET_EXPIRY,
        nonce='fixed_nonce_1234567890',
    )
    version, key_id, user_id, nonce, expires_at, signature = alias_token.split('.')

    valid_user, valid_anchor = await auth_routes._verification_user_and_anchor(alias_token)
    assert valid_user is not None
    assert valid_anchor == ANCHOR

    replacement = 'A' if signature[-1] != 'A' else 'B'
    invalid_tokens = [
        f'{version}.{key_id}.{user_id}.{nonce}.{expires_at}.{signature[:-1]}{replacement}',
        f'{version}.{key_id}.{user_id}.changed_nonce_123456.{expires_at}.{signature}',
        f'{version}.{key_id}.{OTHER_USER_ID}.{nonce}.{expires_at}.{signature}',
        f'{version}.{key_id}.{user_id}.{nonce}.{int(expires_at) + 60}.{signature}',
        f'{version}.unknown.{user_id}.{nonce}.{expires_at}.{signature}',
    ]
    for invalid in invalid_tokens:
        user, anchor = await auth_routes._verification_user_and_anchor(invalid)
        assert user is None
        assert anchor == ''

    # Even a correctly signed alias cannot claim a lifetime past the immutable
    # database generation expiry.
    overlong_alias = create_resend_verification_alias(
        CURRENT_SIGNING_SECRET,
        key_id='k1',
        user_id=USER_ID,
        verification_token_hash=ANCHOR,
        expires_at='2026-10-28T12:00:00+00:00',
        nonce='overlong_nonce_12345678',
    )
    user, anchor = await auth_routes._verification_user_and_anchor(overlong_alias)
    assert user is None
    assert anchor == ''

    assert database.user is not None
    database.user['verification_token_hash'] = OTHER_ANCHOR
    user, anchor = await auth_routes._verification_user_and_anchor(alias_token)
    assert user is None
    assert anchor == ''

    database.user['verification_token_hash'] = ANCHOR
    database.user['verification_token_expires'] = PAST_EXPIRY
    user, anchor = await auth_routes._verification_user_and_anchor(alias_token)
    assert user is None
    assert anchor == ''


@pytest.mark.asyncio
async def test_legacy_raw_verification_token_lookup_remains_compatible(
    monkeypatch,
) -> None:
    database = _ResendDB(_pending_user(verification_token_expires=TARGET_EXPIRY))
    monkeypatch.setattr(auth_routes, 'db', database)

    user, anchor = await auth_routes._verification_user_and_anchor(LEGACY_TOKEN)

    assert user is not None
    assert user['id'] == USER_ID
    assert anchor == ANCHOR
    assert database.selects[-1] == {
        'verification_token_hash': f'eq.{ANCHOR}',
        'verification_token_expires': f'gt.{NOW}',
    }


@pytest.mark.asyncio
async def test_signed_alias_rejects_a_soft_deleted_account(monkeypatch) -> None:
    database = _ResendDB(
        _pending_user(
            verification_token_expires=TARGET_EXPIRY,
            deleted_at='2026-10-25T11:00:00+00:00',
        )
    )
    monkeypatch.setattr(auth_routes, 'db', database)
    alias_token = create_resend_verification_alias(
        CURRENT_SIGNING_SECRET,
        key_id='k1',
        user_id=USER_ID,
        verification_token_hash=ANCHOR,
        expires_at=TARGET_EXPIRY,
        nonce='deleted_user_nonce_123456',
    )

    user, anchor = await auth_routes._verification_user_and_anchor(alias_token)

    assert user is None
    assert anchor == ''


@pytest.mark.asyncio
async def test_pending_reregistration_sends_alias_without_rotating_anchor(
    monkeypatch,
) -> None:
    database = _ResendDB(_pending_user())
    email = _VerificationEmail(True)
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(auth_routes, 'email_service', email)

    result = await auth_routes.register(
        RegisterRequest(
            email='pending@example.com',
            password='StrongPass1',
            fullName='Replacement Name',
            termsAccepted=True,
            termsVersion='2026-08-01',
        ),
        _request('/api/auth/register'),
    )

    assert result == {
        'success': True,
        'message': 'Verification email resent. Check your inbox.',
        'emailSent': True,
    }
    assert database.user is not None
    assert database.user['verification_token_hash'] == ANCHOR
    assert all('verification_token_hash' not in payload for payload, _filters in database.updates)
    assert all('password_hash' not in payload for payload, _filters in database.updates)
    assert len(email.calls) == 1
    alias_token = email.calls[0]['token']
    assert alias_token.startswith(f'v2.k1.{USER_ID}.')
    user, resolved_anchor = await auth_routes._verification_user_and_anchor(alias_token)
    assert user is not None
    assert resolved_anchor == ANCHOR
