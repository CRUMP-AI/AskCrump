from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.email_service import EmailDeliveryError, EmailSendReceipt
from backend.routes import auth as auth_routes
from backend.verification_email_recovery import (
    VerificationEmailRecoveryWorker,
    provider_email_hash,
)


ORIGINAL_PROVIDER_ID = 'provider-message-original-private'
RETRY_PROVIDER_ID = 'provider-message-retry-private'
ORIGINAL_HASH = provider_email_hash(ORIGINAL_PROVIDER_ID)
RETRY_HASH = provider_email_hash(RETRY_PROVIDER_ID)
CLAIM_TOKEN = '30000000-0000-0000-0000-000000000001'


def recovery_settings(*, enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        verification_email_recovery_enabled=enabled,
        resend_api_key='re_test',
        resend_webhook_secret='whsec_test',
    )


class WorkerDB:
    def __init__(self, *, prepared: bool = True) -> None:
        self.prepared = prepared
        self.calls: list[tuple[str, dict, dict]] = []
        self.events: list[str] = []
        self.claim = {
            'provider_email_hash': ORIGINAL_HASH,
            'user_id': 'user-1',
            'claim_token': CLAIM_TOKEN,
            'previous_token_hash': 'a' * 64,
            'previous_token_expires_at': '2099-01-01T00:00:00+00:00',
        }

    async def rpc(self, name, payload, **kwargs):
        self.calls.append((name, dict(payload), dict(kwargs)))
        self.events.append(name)
        if name == 'claim_verification_email_recovery':
            return [dict(self.claim)]
        if name == 'prepare_verification_email_recovery':
            return self.prepared
        if name == 'complete_verification_email_recovery':
            return True
        if name == 'fail_verification_email_recovery':
            return True
        raise AssertionError(name)

    async def select_one(self, table, *, columns='*', filters=None):
        assert table == 'users'
        assert columns == 'id,email,full_name,is_verified'
        assert filters == {'id': 'eq.user-1'}
        return {
            'id': 'user-1',
            'email': 'private-recipient@example.com',
            'full_name': 'Private Recipient',
            'is_verified': False,
        }


class SuccessfulRecoveryEmail:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple] = []

    async def send_verification_receipt(self, email, name, token, **kwargs):
        self.events.append('provider_send')
        self.calls.append((email, name, token, dict(kwargs)))
        return EmailSendReceipt(True, RETRY_PROVIDER_ID)


class FailedRecoveryEmail:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def send_verification_receipt(self, email, name, token, **kwargs):
        self.events.append('provider_send')
        raise EmailDeliveryError(status_code=503, retryable=True)


@pytest.mark.asyncio
async def test_static_off_switch_prevents_claim_or_provider_work():
    db = WorkerDB()
    email = SuccessfulRecoveryEmail(db.events)
    worker = VerificationEmailRecoveryWorker(
        recovery_settings(enabled=False),
        db,
        email,
    )

    result = await worker.process_next()

    assert result == {'handled': False, 'status': 'disabled'}
    assert db.calls == []
    assert email.calls == []


@pytest.mark.asyncio
async def test_claim_precedes_fresh_token_and_one_provider_send(monkeypatch):
    db = WorkerDB()
    email = SuccessfulRecoveryEmail(db.events)
    worker = VerificationEmailRecoveryWorker(recovery_settings(), db, email)

    def mint_token(length):
        assert length == 40
        db.events.append('mint_token')
        return 'fresh-recovery-token'

    monkeypatch.setattr(
        'backend.verification_email_recovery.uuid4',
        lambda: CLAIM_TOKEN,
    )
    monkeypatch.setattr(
        'backend.verification_email_recovery.random_token',
        mint_token,
    )
    monkeypatch.setattr(
        'backend.verification_email_recovery.token_hash',
        lambda token: 'b' * 64,
    )
    monkeypatch.setattr(
        'backend.verification_email_recovery.expiry_iso',
        lambda **kwargs: '2099-01-02T00:00:00+00:00',
    )

    result = await worker.process_next()

    assert result == {'handled': True, 'status': 'retry_sent'}
    assert db.events == [
        'claim_verification_email_recovery',
        'mint_token',
        'prepare_verification_email_recovery',
        'provider_send',
        'complete_verification_email_recovery',
    ]
    assert len(email.calls) == 1
    assert email.calls[0][2] == 'fresh-recovery-token'
    complete = next(
        payload
        for name, payload, _options in db.calls
        if name == 'complete_verification_email_recovery'
    )
    assert complete['p_retry_provider_email_hash'] == RETRY_HASH
    serialized_db_calls = repr(db.calls)
    assert ORIGINAL_PROVIDER_ID not in serialized_db_calls
    assert RETRY_PROVIDER_ID not in serialized_db_calls
    assert 'private-recipient@example.com' not in serialized_db_calls
    assert 'fresh-recovery-token' not in serialized_db_calls
    assert all(options == {'retry_transient': True, 'timeout': 3.0} for _, _, options in db.calls)


@pytest.mark.asyncio
async def test_prepare_race_loss_never_calls_provider(monkeypatch):
    db = WorkerDB(prepared=False)
    email = SuccessfulRecoveryEmail(db.events)
    worker = VerificationEmailRecoveryWorker(recovery_settings(), db, email)
    monkeypatch.setattr(
        'backend.verification_email_recovery.uuid4',
        lambda: CLAIM_TOKEN,
    )

    result = await worker.process_next()

    assert result == {'handled': True, 'status': 'superseded'}
    assert email.calls == []
    assert [name for name, _payload, _options in db.calls] == [
        'claim_verification_email_recovery',
        'prepare_verification_email_recovery',
    ]


@pytest.mark.asyncio
async def test_provider_failure_invokes_fenced_token_rollback_once(monkeypatch):
    db = WorkerDB()
    email = FailedRecoveryEmail(db.events)
    worker = VerificationEmailRecoveryWorker(recovery_settings(), db, email)
    monkeypatch.setattr(
        'backend.verification_email_recovery.uuid4',
        lambda: CLAIM_TOKEN,
    )
    monkeypatch.setattr(
        'backend.verification_email_recovery.token_hash',
        lambda token: 'c' * 64,
    )
    monkeypatch.setattr(
        'backend.verification_email_recovery.expiry_iso',
        lambda **kwargs: '2099-01-02T00:00:00+00:00',
    )

    result = await worker.process_next()

    assert result == {'handled': True, 'status': 'send_failed'}
    assert db.events == [
        'claim_verification_email_recovery',
        'prepare_verification_email_recovery',
        'provider_send',
        'fail_verification_email_recovery',
    ]
    rollback = db.calls[-1][1]
    assert rollback == {
        'p_provider_email_hash': ORIGINAL_HASH,
        'p_claim_token': CLAIM_TOKEN,
        'p_expected_token_hash': 'c' * 64,
        'p_previous_token_hash': 'a' * 64,
        'p_previous_token_expires_at': '2099-01-01T00:00:00+00:00',
    }
    assert all(name != 'complete_verification_email_recovery' for name, *_ in db.calls)


class InitialSendDB:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = []

    async def rpc(self, name, payload, **kwargs):
        self.calls.append((name, dict(payload), dict(kwargs)))
        if self.fail:
            raise RuntimeError('private database detail')
        return True


class InitialSendEmail:
    async def send_verification_receipt(self, *args, **kwargs):
        return EmailSendReceipt(True, ORIGINAL_PROVIDER_ID)


@pytest.mark.asyncio
async def test_initial_send_registers_only_hashed_provider_identity(monkeypatch):
    db = InitialSendDB()
    monkeypatch.setattr(auth_routes, 'db', db)
    monkeypatch.setattr(auth_routes, 'email_service', InitialSendEmail())
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(
            verification_email_recovery_enabled=True,
            environment='test',
        ),
    )

    sent = await auth_routes._send_verification_email(
        user_id='user-1',
        email='private-recipient@example.com',
        name='Private Recipient',
        token='private-token',
        token_expires_at='2099-01-01T00:00:00+00:00',
    )

    assert sent is True
    assert db.calls == [
        (
            'register_verification_email_recovery_attempt',
            {
                'p_provider_email_hash': ORIGINAL_HASH,
                'p_user_id': 'user-1',
                'p_environment': 'test',
                'p_token_expires_at': '2099-01-01T00:00:00+00:00',
            },
            {'retry_transient': True, 'timeout': 3.0},
        )
    ]
    assert ORIGINAL_PROVIDER_ID not in repr(db.calls)
    assert 'private-recipient@example.com' not in repr(db.calls)
    assert 'private-token' not in repr(db.calls)


@pytest.mark.asyncio
async def test_initial_send_fails_closed_when_attempt_ledger_is_unavailable(monkeypatch):
    db = InitialSendDB(fail=True)
    monkeypatch.setattr(auth_routes, 'db', db)
    monkeypatch.setattr(auth_routes, 'email_service', InitialSendEmail())
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(
            verification_email_recovery_enabled=True,
            environment='test',
        ),
    )

    with pytest.raises(EmailDeliveryError) as captured:
        await auth_routes._send_verification_email(
            user_id='user-1',
            email='private-recipient@example.com',
            name='Private Recipient',
            token='private-token',
            token_expires_at='2099-01-01T00:00:00+00:00',
        )

    assert captured.value.retryable is True


def test_provider_hash_is_stable_lowercase_sha256_and_not_raw_identity():
    assert len(ORIGINAL_HASH) == 64
    assert ORIGINAL_HASH == ORIGINAL_HASH.lower()
    assert ORIGINAL_PROVIDER_ID not in ORIGINAL_HASH
    assert provider_email_hash(ORIGINAL_PROVIDER_ID) == ORIGINAL_HASH
