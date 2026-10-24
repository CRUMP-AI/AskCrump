from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.db import DatabaseError
from backend.email_service import EmailDeliveryError, EmailService
from backend.routes.manuscripts import _cron_lane_order
from backend.verification_email_queue import VerificationEmailQueueService
from backend.verification_tokens import (
    parse_resend_verification_alias,
    resend_verification_alias_matches,
)


JOB_ID = '11111111-1111-4111-8111-111111111111'
LEASE_TOKEN = '22222222-2222-4222-8222-222222222222'
USER_ID = '33333333-3333-4333-8333-333333333333'
SIGNING_SECRET = 'verification-queue-signing-secret-' + ('x' * 48)
ANCHOR = 'a' * 64
EXPIRY = '2026-10-25T12:00:00+00:00'
VERIFICATION_V1_SUBJECT_HTML_SHA256 = (
    '3be0895aff7bbd072389eb9e2e200854b1405202383d1b6e2db819127caec839'
)
ROOT = Path(__file__).resolve().parents[1]


def _settings(**overrides):
    return SimpleNamespace(
        verification_link_signing_keys=(('k1', SIGNING_SECRET),),
        environment='test',
        app_name='Ask Crump',
        app_url='https://www.askcrump.com',
        support_email='askcrump@gmail.com',
        from_email='Ask Crump <noreply@askcrump.com>',
        **overrides,
    )


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


def _stage_row(*, disposition='deliver', fingerprint: str | None = None):
    from backend.verification_email_queue import _recipient_fingerprint

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
        'verification_token_hash': ANCHOR,
        'verification_token_expires': EXPIRY,
        'alias_key_id': 'k1',
        'alias_nonce': 'stable_queue_nonce_123456',
        'intent': 'presentation',
        'plan': 'professional',
        'template_version': 'verification-v1',
        'app_name': 'Ask Crump',
        'app_url': 'https://www.askcrump.com',
        'support_email': 'askcrump@gmail.com',
        'from_email': 'Ask Crump <noreply@askcrump.com>',
        'attempts': 1,
    }


@pytest.mark.asyncio
async def test_verification_v1_provider_bytes_are_frozen():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={'id': 'email_123'})

    settings = _settings(resend_api_key='re_test')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        sent = await EmailService(settings, client=client).send_verification(
            'pending@example.com',
            None,
            'rv1.k1.stable-alias-token',
            intent='presentation',
            plan='professional',
            idempotency_key=f'ask-crump-verify-job-{JOB_ID}',
            provider_attempts=1,
            template_version='verification-v1',
            app_name='Ask Crump',
            app_url='https://www.askcrump.com',
            support_email='askcrump@gmail.com',
            from_email='Ask Crump <noreply@askcrump.com>',
        )

    assert sent is True
    assert len(calls) == 1
    payload = json.loads(calls[0].content)
    subject_html = f"{payload['subject']}\n{payload['html']}".encode('utf-8')
    assert hashlib.sha256(subject_html).hexdigest() == VERIFICATION_V1_SUBJECT_HTML_SHA256


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('provider_code', 'retryable'),
    [
        ('concurrent_idempotent_requests', True),
        ('invalid_idempotent_request', False),
    ],
)
async def test_resend_idempotency_conflicts_preserve_only_known_retry_semantics(
    provider_code,
    retryable,
):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                'name': provider_code,
                'message': 'provider-internal-detail-must-not-escape',
            },
        )

    settings = _settings(resend_api_key='re_test')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmailDeliveryError) as captured:
            await EmailService(settings, client=client).send_verification(
                'pending@example.com',
                None,
                'rv1.k1.stable-alias-token',
                idempotency_key=f'ask-crump-verify-job-{JOB_ID}',
                provider_attempts=1,
            )

    assert captured.value.status_code == 409
    assert captured.value.provider_code == provider_code
    assert captured.value.retryable is retryable
    assert 'provider-internal-detail' not in str(captured.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('provider_code', ['future_conflict', []])
async def test_unknown_resend_conflict_stays_permanent_and_content_free(provider_code):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={'name': provider_code, 'message': 'sensitive provider detail'},
        )

    settings = _settings(resend_api_key='re_test')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmailDeliveryError) as captured:
            await EmailService(settings, client=client).send_verification(
                'pending@example.com',
                None,
                'rv1.k1.stable-alias-token',
                idempotency_key=f'ask-crump-verify-job-{JOB_ID}',
                provider_attempts=1,
            )

    assert captured.value.provider_code is None
    assert captured.value.retryable is False
    assert 'sensitive provider detail' not in str(captured.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('retry_after', ['1e999', 'nan', '999999999999999999999999'])
async def test_malformed_or_oversized_retry_after_stays_controlled(retry_after):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={'retry-after': retry_after})

    settings = _settings(resend_api_key='re_test')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmailDeliveryError) as captured:
            await EmailService(settings, client=client).send_verification(
                'pending@example.com',
                None,
                'rv1.k1.stable-alias-token',
                idempotency_key=f'ask-crump-verify-job-{JOB_ID}',
                provider_attempts=1,
            )

    assert captured.value.status_code == 503
    assert captured.value.retryable is True
    assert 0 <= captured.value.retry_after_seconds <= 3600


@pytest.mark.asyncio
async def test_enqueue_is_one_replay_safe_rpc_with_content_minimized_inputs(monkeypatch):
    database = _RPCDatabase({
        'enqueue_verification_email_job_v1': [[{'accepted': True, 'job_id': JOB_ID}]],
    })
    email = _EmailCapture()
    service = VerificationEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.verification_email_queue.new_uuid', lambda: JOB_ID)
    monkeypatch.setattr(
        'backend.verification_email_queue.random_token',
        lambda _length: 'replacement-token',
    )
    monkeypatch.setattr(
        'backend.verification_email_queue.expiry_iso',
        lambda **_kwargs: EXPIRY,
    )
    monkeypatch.setattr(
        'backend.verification_email_queue.secrets.token_urlsafe',
        lambda _length: 'stable_queue_nonce_123456',
    )

    await service.enqueue_resend(
        email='Pending@Example.com',
        intent='presentation',
        plan='professional',
    )

    assert len(database.calls) == 1
    name, payload, retry_transient = database.calls[0]
    assert name == 'enqueue_verification_email_job_v1'
    assert retry_transient is True
    assert payload['p_job_id'] == JOB_ID
    assert payload['p_normalized_email'] == 'pending@example.com'
    assert payload['p_alias_nonce'] == 'stable_queue_nonce_123456'
    assert payload['p_template_version'] == 'verification-v1'
    assert len(payload['p_recipient_fingerprint']) == 64
    assert 'replacement-token' not in repr(payload)
    assert email.calls == []


@pytest.mark.asyncio
async def test_worker_reconstructs_exact_alias_and_records_provider_acceptance(monkeypatch):
    database = _RPCDatabase({
        'claim_verification_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_verification_email_job_v1': [[_stage_row()]],
        'complete_verification_email_job_v1': ['provider_accepted'],
    })
    email = _EmailCapture()
    service = VerificationEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.verification_email_queue.new_uuid', lambda: LEASE_TOKEN)

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'provider_accepted'}
    assert len(email.calls) == 1
    call = email.calls[0]
    assert call['email'] == 'pending@example.com'
    assert call['name'] is None
    assert call['idempotency_key'] == f'ask-crump-verify-job-{JOB_ID}'
    assert call['provider_attempts'] == 1
    assert call['template_version'] == 'verification-v1'
    alias = parse_resend_verification_alias(call['token'])
    assert alias is not None
    assert alias.nonce == 'stable_queue_nonce_123456'
    assert alias.user_id == USER_ID
    assert resend_verification_alias_matches(
        alias,
        {'k1': SIGNING_SECRET},
        verification_token_hash=ANCHOR,
    )
    assert database.calls[-1][0] == 'complete_verification_email_job_v1'
    assert database.calls[-1][1]['p_outcome'] == 'provider_accepted'


@pytest.mark.asyncio
async def test_worker_suppresses_stale_account_without_provider_call(monkeypatch):
    database = _RPCDatabase({
        'claim_verification_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_verification_email_job_v1': [[_stage_row(disposition='suppress')]],
        'complete_verification_email_job_v1': ['suppressed'],
    })
    email = _EmailCapture()
    service = VerificationEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.verification_email_queue.new_uuid', lambda: LEASE_TOKEN)

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'suppressed'}
    assert email.calls == []
    assert database.calls[-1][1]['p_outcome'] == 'suppressed'


@pytest.mark.asyncio
async def test_worker_requeues_retryable_provider_failure_once(monkeypatch):
    database = _RPCDatabase({
        'claim_verification_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_verification_email_job_v1': [[_stage_row()]],
        'release_verification_email_job_v1': ['retry_scheduled'],
    })
    email = _EmailCapture(
        EmailDeliveryError(
            status_code=503,
            retryable=True,
            retry_after_seconds=17,
        )
    )
    service = VerificationEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.verification_email_queue.new_uuid', lambda: LEASE_TOKEN)

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'retry_scheduled'}
    assert len(email.calls) == 1
    name, payload, _retry = database.calls[-1]
    assert name == 'release_verification_email_job_v1'
    assert payload['p_failure_code'] == 'PROVIDER_UNAVAILABLE'
    assert payload['p_retryable'] is True
    assert payload['p_retry_after_seconds'] == 17


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
        'claim_verification_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 6,
        }]],
        'stage_verification_email_job_v1': [[_stage_row()]],
        'release_verification_email_job_v1': [release_result],
    })
    email = _EmailCapture()
    settings = _settings()
    settings.environment = 'production'
    settings.verification_link_signing_keys = configured_keys
    service = VerificationEmailQueueService(settings, database, email)
    monkeypatch.setattr('backend.verification_email_queue.new_uuid', lambda: LEASE_TOKEN)

    result = await service.process_next()

    assert result == {'handled': True, 'status': expected_status}
    assert email.calls == []
    name, payload, _retry = database.calls[-1]
    assert name == 'release_verification_email_job_v1'
    assert payload['p_failure_code'] == 'SIGNING_KEY_UNAVAILABLE'
    assert payload['p_retryable'] is True


@pytest.mark.asyncio
async def test_missing_signing_key_release_uncertainty_reports_lease_recovery(monkeypatch):
    database = _RPCDatabase({
        'claim_verification_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_verification_email_job_v1': [[_stage_row()]],
        'release_verification_email_job_v1': [DatabaseError('release unavailable')],
    })
    email = _EmailCapture()
    settings = _settings()
    settings.environment = 'production'
    settings.verification_link_signing_keys = ()
    service = VerificationEmailQueueService(settings, database, email)
    monkeypatch.setattr('backend.verification_email_queue.new_uuid', lambda: LEASE_TOKEN)

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'lease_recovery_pending'}
    assert email.calls == []
    name, payload, _retry = database.calls[-1]
    assert name == 'release_verification_email_job_v1'
    assert payload['p_failure_code'] == 'SIGNING_KEY_UNAVAILABLE'
    assert payload['p_retryable'] is True


@pytest.mark.asyncio
async def test_worker_requeues_concurrent_idempotent_provider_conflict(monkeypatch):
    database = _RPCDatabase({
        'claim_verification_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_verification_email_job_v1': [[_stage_row()]],
        'release_verification_email_job_v1': ['retry_scheduled'],
    })
    email = _EmailCapture(
        EmailDeliveryError(
            status_code=409,
            provider_code='concurrent_idempotent_requests',
            retryable=True,
        )
    )
    service = VerificationEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.verification_email_queue.new_uuid', lambda: LEASE_TOKEN)

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'retry_scheduled'}
    name, payload, _retry = database.calls[-1]
    assert name == 'release_verification_email_job_v1'
    assert payload['p_failure_code'] == 'PROVIDER_UNAVAILABLE'
    assert payload['p_retryable'] is True


@pytest.mark.asyncio
async def test_worker_rejects_recipient_fingerprint_mismatch(monkeypatch):
    database = _RPCDatabase({
        'claim_verification_email_job_v1': [[{
            'job_id': JOB_ID,
            'lease_token': LEASE_TOKEN,
            'attempts': 1,
        }]],
        'stage_verification_email_job_v1': [[_stage_row(fingerprint='f' * 64)]],
        'release_verification_email_job_v1': ['failed_permanent'],
    })
    email = _EmailCapture()
    service = VerificationEmailQueueService(_settings(), database, email)
    monkeypatch.setattr('backend.verification_email_queue.new_uuid', lambda: LEASE_TOKEN)

    result = await service.process_next()

    assert result == {'handled': True, 'status': 'failed_permanent'}
    assert email.calls == []
    assert database.calls[-1][1]['p_failure_code'] == 'JOB_INTEGRITY_INVALID'
    assert database.calls[-1][1]['p_retryable'] is False


def test_cron_rotation_gives_every_lane_first_position_once_per_five_minutes():
    base = datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc)
    orders = [_cron_lane_order(base + timedelta(minutes=offset)) for offset in range(5)]

    assert {order[0] for order in orders} == {
        'account-storage-deletion',
        'verification-email',
        'password-reset-email',
        'code',
        'manuscripts',
    }
    assert all(len(order) == len(set(order)) == 5 for order in orders)


def test_queue_migration_is_bound_to_the_postgresql_17_release_gate():
    workflow = (
        ROOT / '.github' / 'workflows' / 'postgres-migration-gate.yml'
    ).read_text(encoding='utf-8')
    job = workflow.split('durable-verification-email-queue:', 1)[1].split(
        '\n  durable-password-reset-email-queue:', 1
    )[0]

    assert 'image: postgres:17' in job
    assert 'verification_email_queue_baseline.sql' in job
    assert job.count('20261024144202_durable_verification_email_jobs.sql') == 3
    assert 'test_verification_email_queue_migration.sql' in job
    assert 'test_verification_email_queue_concurrency.sh' in job
    assert 'test_verification_email_queue_drift.sh' in job
    assert 'test_verification_email_queue_first_apply_guards.sh' in job
    assert '--command=begin' in job
    assert '--command=rollback' in job
