from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.requests import Request

from backend.email_service import EmailDeliveryError, EmailService
from backend.db import DatabaseError
from backend.password_reset_email_queue import PasswordResetEmailQueueService
from backend.password_reset_tokens import (
    create_password_reset_alias,
    parse_password_reset_alias,
    password_reset_alias_matches,
)
from backend.routes import auth as auth_routes
from backend.schemas import EmailRequest, ResetPasswordRequest
from backend.security import token_hash


JOB_ID = '11111111-1111-4111-8111-111111111111'
LEASE_TOKEN = '22222222-2222-4222-8222-222222222222'
USER_ID = '33333333-3333-4333-8333-333333333333'
SIGNING_SECRET = 'password-reset-queue-signing-secret-' + ('x' * 48)
ANCHOR = 'a' * 64
EXPIRY = '2026-10-24T17:30:00+00:00'
NONCE = 'stable_reset_nonce_123456'
PASSWORD_RESET_V1_SUBJECT_HTML_SHA256 = (
    '9b402f5218e8a6395b4ed4627eb519bd4cbbf185585b4c9cdaef7d385f1a5c9e'
)
ROOT = Path(__file__).resolve().parents[1]


def queue_outcome_records(caplog):
    records = []
    for item in caplog.records:
        try:
            payload = json.loads(item.message)
        except (TypeError, ValueError):
            continue
        if payload.get('event') == 'email_queue_outcome':
            records.append(payload)
    return records


def _settings(**overrides):
    values = {
        'verification_link_signing_keys': (('k1', SIGNING_SECRET),),
        'environment': 'test',
        'app_name': 'Ask Crump',
        'app_url': 'https://www.askcrump.com',
        'support_email': 'askcrump@gmail.com',
        'from_email': 'Ask Crump <noreply@askcrump.com>',
        'resend_api_key': None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _RPCDatabase:
    def __init__(self, responses):
        self.responses = {key: list(value) for key, value in responses.items()}
        self.calls: list[tuple[str, dict, bool]] = []

    async def rpc(self, name, payload, *, retry_transient=False):
        self.calls.append((name, dict(payload), retry_transient))
        value = self.responses[name].pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class _EmailCapture:
    def __init__(self, outcome=True):
        self.outcome = outcome
        self.calls: list[dict] = []

    async def send_password_reset(self, email, name, token, **kwargs):
        self.calls.append({'email': email, 'name': name, 'token': token, **kwargs})
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _stage_row(*, disposition='deliver', fingerprint: str | None = None):
    from backend.password_reset_email_queue import _recipient_fingerprint

    return {
        'disposition': disposition,
        'job_id': JOB_ID,
        'lease_token': LEASE_TOKEN,
        'user_id': USER_ID if disposition == 'deliver' else None,
        'recipient_email': 'pending@example.com' if disposition == 'deliver' else None,
        'recipient_fingerprint': (
            fingerprint
            if fingerprint is not None
            else _recipient_fingerprint(SIGNING_SECRET, 'pending@example.com')
        ),
        'password_reset_token_hash': ANCHOR,
        'password_reset_expires': EXPIRY,
        'alias_key_id': 'k1',
        'alias_nonce': NONCE,
        'template_version': 'password-reset-v1',
        'app_name': 'Ask Crump',
        'app_url': 'https://www.askcrump.com',
        'support_email': 'askcrump@gmail.com',
        'from_email': 'Ask Crump <noreply@askcrump.com>',
        'attempts': 1,
    }


def _request(path: str) -> Request:
    return Request({
        'type': 'http',
        'method': 'POST',
        'path': path,
        'headers': [],
        'query_string': b'',
        'client': ('127.0.0.1', 50000),
    })


def test_password_reset_alias_is_deterministic_and_domain_bound():
    alias = create_password_reset_alias(
        SIGNING_SECRET,
        key_id='k1',
        user_id=USER_ID,
        password_reset_token_hash=ANCHOR,
        expires_at=EXPIRY,
        nonce=NONCE,
    )
    assert alias == create_password_reset_alias(
        SIGNING_SECRET,
        key_id='k1',
        user_id=USER_ID,
        password_reset_token_hash=ANCHOR,
        expires_at=EXPIRY,
        nonce=NONCE,
    )
    parsed = parse_password_reset_alias(alias)
    assert parsed is not None
    assert parsed.user_id == USER_ID
    assert parsed.nonce == NONCE
    assert password_reset_alias_matches(
        parsed,
        {'k1': SIGNING_SECRET},
        password_reset_token_hash=ANCHOR,
    )
    assert not password_reset_alias_matches(
        parsed,
        {'k1': SIGNING_SECRET},
        password_reset_token_hash='b' * 64,
    )
    assert not password_reset_alias_matches(
        parsed,
        {'retired-key-absent': SIGNING_SECRET},
        password_reset_token_hash=ANCHOR,
    )
    tampered = parse_password_reset_alias(alias[:-1] + ('A' if alias[-1] != 'A' else 'B'))
    assert tampered is not None
    assert not password_reset_alias_matches(
        tampered,
        {'k1': SIGNING_SECRET},
        password_reset_token_hash=ANCHOR,
    )
    assert parse_password_reset_alias('x' * 241) is None


@pytest.mark.asyncio
async def test_enqueue_is_one_content_minimized_replay_safe_rpc(monkeypatch):
    database = _RPCDatabase({
        'enqueue_password_reset_email_job_v1': [[{'accepted': True, 'job_id': JOB_ID}]],
    })
    email = _EmailCapture()
    service = PasswordResetEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.password_reset_email_queue.new_uuid', lambda: JOB_ID)
    monkeypatch.setattr(
        'backend.password_reset_email_queue.random_token',
        lambda _length: 'replacement-token',
    )
    monkeypatch.setattr(
        'backend.password_reset_email_queue.expiry_iso',
        lambda **_kwargs: EXPIRY,
    )
    monkeypatch.setattr(
        'backend.password_reset_email_queue.secrets.token_urlsafe',
        lambda _length: NONCE,
    )

    await service.enqueue(email='Pending@Example.com')

    assert len(database.calls) == 1
    name, payload, retry_transient = database.calls[0]
    assert name == 'enqueue_password_reset_email_job_v1'
    assert retry_transient is True
    assert payload['p_job_id'] == JOB_ID
    assert payload['p_normalized_email'] == 'pending@example.com'
    assert payload['p_alias_nonce'] == NONCE
    assert payload['p_template_version'] == 'password-reset-v1'
    assert len(payload['p_recipient_fingerprint']) == 64
    assert 'replacement-token' not in repr(payload)
    assert 'p_intent' not in payload and 'p_plan' not in payload
    assert email.calls == []


@pytest.mark.asyncio
async def test_worker_reconstructs_exact_alias_and_records_provider_acceptance(
    monkeypatch,
    caplog,
):
    database = _RPCDatabase({
        'claim_password_reset_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_password_reset_email_job_v1': [[_stage_row()]],
        'complete_password_reset_email_job_v1': ['provider_accepted'],
    })
    email = _EmailCapture()
    service = PasswordResetEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.password_reset_email_queue.new_uuid', lambda: LEASE_TOKEN)
    caplog.set_level(logging.INFO, logger='askcrump.password_reset_email_queue')

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'provider_accepted'}
    call = email.calls[0]
    assert call['email'] == 'pending@example.com'
    assert call['idempotency_key'] == f'ask-crump-reset-job-{JOB_ID}'
    assert call['provider_attempts'] == 1
    assert call['template_version'] == 'password-reset-v1'
    parsed = parse_password_reset_alias(call['token'])
    assert parsed is not None and parsed.nonce == NONCE
    assert password_reset_alias_matches(
        parsed,
        {'k1': SIGNING_SECRET},
        password_reset_token_hash=ANCHOR,
    )
    assert database.calls[-1][0] == 'complete_password_reset_email_job_v1'
    assert queue_outcome_records(caplog) == [{
        'component': 'minute_worker',
        'event': 'email_queue_outcome',
        'lane': 'password-reset-email',
        'handled': True,
        'status': 'provider_accepted',
        'attempt': 1,
        'provider_attempts': 1,
    }]
    assert JOB_ID not in caplog.text
    assert 'pending@example.com' not in caplog.text
    assert call['token'] not in caplog.text


@pytest.mark.asyncio
async def test_worker_omits_provider_attempt_when_email_is_not_configured(
    monkeypatch,
    caplog,
):
    database = _RPCDatabase({
        'claim_password_reset_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_password_reset_email_job_v1': [[_stage_row()]],
        'release_password_reset_email_job_v1': ['failed_permanent'],
    })
    email = _EmailCapture(outcome=False)
    service = PasswordResetEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.password_reset_email_queue.new_uuid', lambda: LEASE_TOKEN)
    caplog.set_level(logging.INFO, logger='askcrump.password_reset_email_queue')

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'failed_permanent'}
    assert database.calls[-1][1]['p_failure_code'] == 'EMAIL_NOT_CONFIGURED'
    record = queue_outcome_records(caplog)[-1]
    assert record['attempt'] == 1
    assert 'provider_attempts' not in record


@pytest.mark.asyncio
async def test_worker_requeues_retryable_failure_with_same_provider_key(monkeypatch, caplog):
    database = _RPCDatabase({
        'claim_password_reset_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_password_reset_email_job_v1': [[_stage_row()]],
        'release_password_reset_email_job_v1': ['retry_scheduled'],
    })
    email = _EmailCapture(EmailDeliveryError(status_code=503, retryable=True))
    service = PasswordResetEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.password_reset_email_queue.new_uuid', lambda: LEASE_TOKEN)
    caplog.set_level(logging.INFO, logger='askcrump.password_reset_email_queue')

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'retry_scheduled'}
    assert email.calls[0]['idempotency_key'] == f'ask-crump-reset-job-{JOB_ID}'
    assert database.calls[-1][0] == 'release_password_reset_email_job_v1'
    assert database.calls[-1][1]['p_failure_code'] == 'PROVIDER_UNAVAILABLE'
    assert database.calls[-1][1]['p_retryable'] is True
    assert queue_outcome_records(caplog)[-1] == {
        'component': 'minute_worker',
        'event': 'email_queue_outcome',
        'lane': 'password-reset-email',
        'handled': True,
        'status': 'retry_scheduled',
        'attempt': 1,
        'provider_attempts': 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('release_result', 'expected_status'),
    [
        ('retry_scheduled', 'retry_scheduled'),
        ('failed_permanent', 'failed_permanent'),
        ('lease_lost', 'lease_lost'),
        ('', 'retry_scheduled'),
    ],
)
@pytest.mark.parametrize(
    'configured_keys',
    [(), (('current', SIGNING_SECRET),)],
    ids=['keyring-unavailable', 'queued-key-retired'],
)
async def test_missing_signing_key_reports_the_release_outcome(
    monkeypatch,
    release_result,
    expected_status,
    configured_keys,
):
    database = _RPCDatabase({
        'claim_password_reset_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 6,
        }]],
        'stage_password_reset_email_job_v1': [[_stage_row()]],
        'release_password_reset_email_job_v1': [release_result],
    })
    email = _EmailCapture()
    settings = _settings()
    settings.environment = 'production'
    settings.verification_link_signing_keys = configured_keys
    service = PasswordResetEmailQueueService(settings, database, email)
    monkeypatch.setattr('backend.password_reset_email_queue.new_uuid', lambda: LEASE_TOKEN)

    result = await service.process_next()

    assert result == {'handled': True, 'status': expected_status}
    assert email.calls == []
    name, payload, _retry = database.calls[-1]
    assert name == 'release_password_reset_email_job_v1'
    assert payload['p_failure_code'] == 'SIGNING_KEY_UNAVAILABLE'
    assert payload['p_retryable'] is True


@pytest.mark.asyncio
async def test_missing_signing_key_release_uncertainty_reports_lease_recovery(monkeypatch):
    database = _RPCDatabase({
        'claim_password_reset_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_password_reset_email_job_v1': [[_stage_row()]],
        'release_password_reset_email_job_v1': [DatabaseError('release unavailable')],
    })
    email = _EmailCapture()
    settings = _settings()
    settings.environment = 'production'
    settings.verification_link_signing_keys = ()
    service = PasswordResetEmailQueueService(settings, database, email)
    monkeypatch.setattr('backend.password_reset_email_queue.new_uuid', lambda: LEASE_TOKEN)

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'lease_recovery_pending'}
    assert email.calls == []
    name, payload, _retry = database.calls[-1]
    assert name == 'release_password_reset_email_job_v1'
    assert payload['p_failure_code'] == 'SIGNING_KEY_UNAVAILABLE'
    assert payload['p_retryable'] is True


@pytest.mark.asyncio
async def test_provider_acceptance_completion_uncertainty_replays_exact_envelope(monkeypatch):
    second_lease = '44444444-4444-4444-8444-444444444444'
    first_stage = _stage_row()
    second_stage = {**_stage_row(), 'lease_token': second_lease, 'attempts': 2}
    database = _RPCDatabase({
        'claim_password_reset_email_job_v1': [
            [{'job_id': JOB_ID, 'lease_token': LEASE_TOKEN, 'attempts': 1}],
            [{'job_id': JOB_ID, 'lease_token': second_lease, 'attempts': 2}],
        ],
        'stage_password_reset_email_job_v1': [[first_stage], [second_stage]],
        'complete_password_reset_email_job_v1': [
            DatabaseError('completion outcome uncertain'),
            'provider_accepted',
        ],
    })
    email = _EmailCapture()
    service = PasswordResetEmailQueueService(_settings(), database, email)
    lease_tokens = iter((LEASE_TOKEN, second_lease))
    monkeypatch.setattr(
        'backend.password_reset_email_queue.new_uuid',
        lambda: next(lease_tokens),
    )

    first = await service.process_next()
    second = await service.process_next()

    assert first == {'handled': True, 'status': 'lease_recovery_pending'}
    assert second == {'handled': True, 'status': 'provider_accepted'}
    assert len(email.calls) == 2
    assert email.calls[0] == email.calls[1]
    assert email.calls[0]['idempotency_key'] == f'ask-crump-reset-job-{JOB_ID}'


@pytest.mark.asyncio
async def test_worker_rejects_recipient_fingerprint_mismatch(monkeypatch):
    database = _RPCDatabase({
        'claim_password_reset_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_password_reset_email_job_v1': [[_stage_row(fingerprint='f' * 64)]],
        'release_password_reset_email_job_v1': ['failed_permanent'],
    })
    email = _EmailCapture()
    service = PasswordResetEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.password_reset_email_queue.new_uuid', lambda: LEASE_TOKEN)

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'failed_permanent'}
    assert email.calls == []
    assert database.calls[-1][1]['p_failure_code'] == 'JOB_INTEGRITY_INVALID'


@pytest.mark.asyncio
async def test_password_reset_renderer_accepts_persisted_replay_inputs():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={'id': 'email_123'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sent = await EmailService(
            _settings(resend_api_key='re_test'),
            client=client,
        ).send_password_reset(
            'pending@example.com',
            None,
            'r1.k1.stable-alias',
            idempotency_key=f'ask-crump-reset-job-{JOB_ID}',
            provider_attempts=1,
            template_version='password-reset-v1',
            app_name='Ask Crump',
            app_url='https://www.askcrump.com',
            support_email='askcrump@gmail.com',
            from_email='Ask Crump <noreply@askcrump.com>',
        )

    assert sent is True and len(requests) == 1
    payload = json.loads(requests[0].content)
    assert payload['subject'] == 'Reset your Ask Crump password'
    assert 'r1.k1.stable-alias' in payload['html']
    subject_html = f"{payload['subject']}\n{payload['html']}".encode('utf-8')
    assert hashlib.sha256(subject_html).hexdigest() == (
        PASSWORD_RESET_V1_SUBJECT_HTML_SHA256
    )
    assert requests[0].headers['idempotency-key'] == f'ask-crump-reset-job-{JOB_ID}'


def test_password_reset_queue_migration_is_bound_to_postgresql_17_release_gate():
    workflow = (
        ROOT / '.github' / 'workflows' / 'postgres-migration-gate.yml'
    ).read_text(encoding='utf-8')
    assert workflow.index('durable-verification-email-queue:') < workflow.index(
        'durable-password-reset-email-queue:'
    ) < workflow.index('atomic-push-registration:')
    job = workflow.split('durable-password-reset-email-queue:', 1)[1].split(
        '\n  atomic-push-registration:', 1
    )[0]

    assert 'image: postgres:17' in job
    assert 'password_reset_email_queue_baseline.sql' in job
    assert job.count('20261024163849_durable_password_reset_email_jobs.sql') == 3
    assert 'test_password_reset_email_queue_first_apply_guards.sh' in job
    assert 'test_password_reset_email_queue_migration.sql' in job
    assert 'test_password_reset_email_queue_concurrency.sh' in job
    assert 'test_password_reset_email_queue_drift.sh' in job
    assert 'password_reset_email_queue_source_drift_fixture.sql' in (
        ROOT / 'tests' / 'postgres' / 'test_password_reset_email_queue_drift.sh'
    ).read_text(encoding='utf-8')
    assert '--command=begin' in job
    assert '--command=rollback' in job


def test_password_reset_queue_migration_stores_no_raw_delivery_secret():
    migration = (
        ROOT / 'migrations' / '20261024163849_durable_password_reset_email_jobs.sql'
    ).read_text(encoding='utf-8')
    table = migration.split(
        'create table if not exists public.password_reset_email_jobs (', 1
    )[1].split('\n);', 1)[0]
    columns = (
        'id', 'delivery_mode', 'user_id', 'recipient_fingerprint',
        'password_reset_token_hash', 'password_reset_expires', 'alias_key_id',
        'alias_nonce', 'status', 'attempts', 'next_attempt_at', 'lease_token',
        'lease_expires_at', 'template_version', 'app_name', 'app_url',
        'support_email', 'from_email', 'staged_at', 'last_failure_code',
        'terminal_at', 'created_at', 'updated_at', 'claim_token_history',
    )
    assert all(f'\n  {column} ' in f'\n{table}' for column in columns)
    assert sum(
        line.startswith('  ') and line.strip().split(' ', 1)[0] in columns
        for line in table.splitlines()
    ) == 24
    for forbidden in ('recipient_email', 'raw_token', 'signed_alias', 'body', 'secret'):
        assert forbidden not in table
    assert 'enable row level security' in migration
    assert 'force row level security' in migration
    assert migration.count('security definer') == 5


def test_forgot_route_is_uniform_and_never_calls_provider(monkeypatch):
    queue = SimpleNamespace(enqueue=AsyncMock(return_value=None))
    monkeypatch.setattr(auth_routes, 'password_reset_emails', queue)
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', AsyncMock(return_value=None))

    result = asyncio.run(auth_routes.forgot_password(
        EmailRequest(email='Pending@Example.com'),
        _request('/api/auth/forgot-password'),
    ))

    assert result == {
        'success': True,
        'message': 'If an account exists for that email, check your email for a reset link.',
    }
    queue.enqueue.assert_awaited_once_with(email='pending@example.com')


def test_signed_alias_reset_consumes_the_database_anchor(monkeypatch):
    expiry = datetime.now(timezone.utc) + timedelta(minutes=45)
    alias = create_password_reset_alias(
        SIGNING_SECRET,
        key_id='k1',
        user_id=USER_ID,
        password_reset_token_hash=ANCHOR,
        expires_at=expiry.isoformat(),
        nonce=NONCE,
    )

    class _ResetDb:
        def __init__(self):
            self.rpc_calls = []

        async def select_one(self, *_args, **_kwargs):
            return {
                'id': USER_ID,
                'deleted_at': None,
                'password_reset_token_hash': ANCHOR,
                'password_reset_expires': expiry.isoformat(),
            }

        async def rpc(self, name, payload, **_kwargs):
            self.rpc_calls.append((name, dict(payload)))
            return [{'reset_applied': True}]

    database = _ResetDb()
    monkeypatch.setattr(auth_routes, 'db', database)
    monkeypatch.setattr(
        auth_routes,
        'settings',
        SimpleNamespace(
            environment='test',
            verification_link_signing_keys=(('k1', SIGNING_SECRET),),
        ),
    )
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', AsyncMock(return_value=None))

    result = asyncio.run(auth_routes.reset_password(
        ResetPasswordRequest(token=alias, newPassword='NewPassword123'),
        _request('/api/auth/reset-password'),
    ))

    assert result['success'] is True
    assert database.rpc_calls[0][0] == 'consume_password_reset_v1'
    assert database.rpc_calls[0][1]['p_token_hash'] == ANCHOR
    assert database.rpc_calls[0][1]['p_token_hash'] != token_hash(alias)
