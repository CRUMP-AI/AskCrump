from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import time
from types import SimpleNamespace

import pytest

from backend.db import DatabaseError
from backend.routes import email_webhooks


_SECRET_BYTES = b'ask-crump-resend-webhook-test-secret'
_WEBHOOK_SECRET = f"whsec_{base64.b64encode(_SECRET_BYTES).decode('ascii')}"
_RPC_KEYS = {
    'p_provider_event_hash',
    'p_provider_email_hash',
    'p_payload_fingerprint',
    'p_environment',
    'p_message_kind',
    'p_event_type',
    'p_outcome_class',
    'p_occurred_at',
}
_HASH = re.compile(r'^[0-9a-f]{64}$')


class RawRequest:
    def __init__(self, body: bytes, headers: dict[str, str]) -> None:
        self._body = body
        self.headers = headers
        self.body_reads = 0

    async def body(self) -> bytes:
        self.body_reads += 1
        return self._body

    async def json(self):
        raise AssertionError('The signed webhook must be verified from the raw request body.')


class RecordingDB:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], dict[str, object]]] = []
        self.persisted: dict[str, dict[str, object]] = {}

    async def rpc(self, name, payload, **kwargs):
        record = dict(payload)
        self.calls.append((name, record, dict(kwargs)))
        event_hash = str(record['p_provider_event_hash'])
        existing = self.persisted.get(event_hash)
        if existing is None:
            self.persisted[event_hash] = record
        elif existing['p_payload_fingerprint'] != record['p_payload_fingerprint']:
            raise DatabaseError(
                'Database operation failed',
                status_code=409,
                details={'reason': 'provider event identity conflict'},
            )
        return [{'inserted': existing is None}]


class FailingDB(RecordingDB):
    def __init__(self, private_sentinel: str) -> None:
        super().__init__()
        self.private_sentinel = private_sentinel

    async def rpc(self, name, payload, **kwargs):
        self.calls.append((name, dict(payload), dict(kwargs)))
        raise DatabaseError(
            'Database operation failed',
            status_code=503,
            details={'private': self.private_sentinel},
            retryable=True,
        )


class SlowDB(RecordingDB):
    async def rpc(self, name, payload, **kwargs):
        self.calls.append((name, dict(payload), dict(kwargs)))
        await asyncio.sleep(1)


def _sha256(namespace: str, value: str) -> str:
    return hashlib.sha256(f'{namespace}:{value}'.encode('utf-8')).hexdigest()


def _settings(
    secret: str | None = _WEBHOOK_SECRET,
    *,
    recovery_enabled: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        resend_webhook_secret=secret,
        environment='test',
        verification_email_recovery_enabled=recovery_enabled,
    )


def _event(
    event_type: str = 'email.delivered',
    *,
    message_kind: str | None = 'verification',
    provider_email_id: str = 'email_provider_123',
    top_level_id: str = 'payload_event_id_must_not_be_trusted',
    bounce_type: str | None = None,
    delivery_environment: str | None = 'test',
) -> dict[str, object]:
    tags = {} if message_kind is None else {'message_kind': message_kind}
    if delivery_environment is not None:
        tags['delivery_environment'] = delivery_environment
    data: dict[str, object] = {
        'email_id': provider_email_id,
        'created_at': '2026-10-07T12:00:00Z',
        'from': 'Ask Crump <noreply@askcrump.com>',
        'to': ['recipient@example.com'],
        'subject': 'Private transactional subject',
        'tags': tags,
    }
    if event_type == 'email.bounced':
        data['bounce'] = {
            'type': bounce_type,
            'subType': 'General',
            'message': 'Provider diagnostic content',
            'diagnosticCode': ['smtp; 550 private diagnostic'],
        }
    return {
        'id': top_level_id,
        'type': event_type,
        'created_at': '2026-10-07T12:00:01Z',
        'data': data,
    }


def _body(payload: object, *, pretty: bool = False) -> bytes:
    if pretty:
        return json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    return json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def _signed_headers(
    body: bytes,
    *,
    delivery_id: str = 'delivery_header_123',
    timestamp: int | None = None,
) -> dict[str, str]:
    timestamp = int(time.time()) if timestamp is None else timestamp
    signed = f'{delivery_id}.{timestamp}.'.encode('utf-8') + body
    signature = base64.b64encode(
        hmac.new(_SECRET_BYTES, signed, hashlib.sha256).digest()
    ).decode('ascii')
    return {
        'svix-id': delivery_id,
        'svix-timestamp': str(timestamp),
        'svix-signature': f'v1,{signature}',
    }


def _configure(
    monkeypatch,
    fake_db,
    *,
    secret: str | None = _WEBHOOK_SECRET,
    recovery_enabled: bool = False,
) -> None:
    monkeypatch.setattr(
        email_webhooks,
        'settings',
        _settings(secret, recovery_enabled=recovery_enabled),
    )
    monkeypatch.setattr(email_webhooks, 'db', fake_db)


@pytest.mark.asyncio
async def test_enabled_recovery_uses_the_atomic_signed_event_rpc(monkeypatch):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db, recovery_enabled=True)
    raw_body = _body(
        _event('email.delivery_delayed', provider_email_id='transient-provider-id')
    )

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(raw_body, _signed_headers(raw_body))
    )

    assert response.status_code == 204
    assert fake_db.calls[0][0] == 'record_resend_delivery_event_and_recovery'
    record = fake_db.calls[0][1]
    assert record['p_outcome_class'] == 'transient'
    assert record['p_provider_email_hash'] == _sha256(
        'resend-email', 'transient-provider-id'
    )


@pytest.mark.asyncio
async def test_signed_send_environment_not_receiver_environment_is_authoritative(monkeypatch):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    monkeypatch.setattr(
        email_webhooks,
        'settings',
        SimpleNamespace(
            resend_webhook_secret=_WEBHOOK_SECRET,
            environment='production',
            verification_email_recovery_enabled=False,
        ),
    )
    raw_body = _body(_event(delivery_environment='preview'))

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(raw_body, _signed_headers(raw_body))
    )

    assert response.status_code == 204
    assert fake_db.calls[0][1]['p_environment'] == 'preview'


@pytest.mark.asyncio
async def test_resend_webhook_verifies_the_exact_raw_body_before_parsing(monkeypatch):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    payload = _event()
    original = _body(payload, pretty=True)
    headers = _signed_headers(original)

    request = RawRequest(original, headers)
    response = await email_webhooks.resend_delivery_webhook(request)

    assert response.status_code == 204
    assert response.body == b''
    assert request.body_reads == 1
    assert len(fake_db.calls) == 1
    assert fake_db.calls[0][1]['p_payload_fingerprint'] == hashlib.sha256(original).hexdigest()

    # The payload is semantically identical, but changing its bytes must invalidate
    # the original signature rather than being accepted after JSON reserialization.
    reserialized = _body(payload)
    rejected = await email_webhooks.resend_delivery_webhook(
        RawRequest(reserialized, headers)
    )
    assert rejected.status_code == 400
    assert len(fake_db.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('event_type', 'bounce_type', 'expected_outcome'),
    (
        ('email.sent', None, 'accepted'),
        ('email.delivered', None, 'delivered'),
        ('email.delivery_delayed', None, 'transient'),
        ('email.bounced', 'Permanent', 'permanent'),
        ('email.bounced', 'Transient', 'transient'),
        ('email.bounced', 'Undetermined', 'failed'),
        ('email.failed', None, 'failed'),
        ('email.suppressed', None, 'suppressed'),
        ('email.complained', None, 'complaint'),
    ),
)
async def test_resend_delivery_classification_is_allowlisted(
    monkeypatch,
    event_type,
    bounce_type,
    expected_outcome,
):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    raw_body = _body(_event(event_type, bounce_type=bounce_type))

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(raw_body, _signed_headers(raw_body))
    )

    assert response.status_code == 204
    assert len(fake_db.calls) == 1
    name, record, options = fake_db.calls[0]
    assert name == 'record_resend_delivery_event'
    assert options == {'timeout': 3.0}
    assert set(record) == _RPC_KEYS
    assert record['p_event_type'] == event_type
    assert record['p_outcome_class'] == expected_outcome
    assert record['p_message_kind'] == 'verification'
    assert record['p_environment'] == 'test'
    assert record['p_occurred_at'] == '2026-10-07T12:00:01+00:00'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'payload',
    (
        _event('email.opened'),
        _event(message_kind=None),
        _event(message_kind='marketing'),
    ),
)
async def test_signed_non_delivery_or_unowned_email_events_are_acknowledged_without_storage(
    monkeypatch,
    payload,
):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    raw_body = _body(payload)

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(raw_body, _signed_headers(raw_body))
    )

    assert response.status_code == 204
    assert response.body == b''
    assert fake_db.calls == []


@pytest.mark.asyncio
async def test_provider_delivery_and_email_identities_are_independent_hashed_fields(monkeypatch):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    delivery_id = 'header_delivery_identity'
    provider_email_id = 'provider_email_identity'
    conflicting_payload_id = 'payload_identity_must_be_ignored'
    raw_body = _body(
        _event(
            provider_email_id=provider_email_id,
            top_level_id=conflicting_payload_id,
        )
    )

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(
            raw_body,
            _signed_headers(raw_body, delivery_id=delivery_id),
        )
    )

    assert response.status_code == 204
    _, record, _ = fake_db.calls[0]
    assert record['p_provider_event_hash'] == _sha256('resend-event', delivery_id)
    assert record['p_provider_email_hash'] == _sha256('resend-email', provider_email_id)
    assert record['p_provider_event_hash'] != _sha256(
        'resend-event', conflicting_payload_id
    )
    assert _HASH.fullmatch(str(record['p_provider_event_hash']))
    assert _HASH.fullmatch(str(record['p_provider_email_hash']))
    assert _HASH.fullmatch(str(record['p_payload_fingerprint']))
    serialized = repr(record)
    assert delivery_id not in serialized
    assert provider_email_id not in serialized
    assert conflicting_payload_id not in serialized


@pytest.mark.asyncio
async def test_exact_provider_replay_is_acknowledged_and_logically_idempotent(monkeypatch):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    raw_body = _body(_event())
    headers = _signed_headers(raw_body, delivery_id='replayed_delivery_id')

    first = await email_webhooks.resend_delivery_webhook(RawRequest(raw_body, headers))
    second = await email_webhooks.resend_delivery_webhook(RawRequest(raw_body, headers))

    assert first.status_code == 204
    assert second.status_code == 204
    assert len(fake_db.calls) == 2
    assert len(fake_db.persisted) == 1
    assert fake_db.calls[0][1] == fake_db.calls[1][1]


@pytest.mark.asyncio
async def test_same_delivery_id_with_conflicting_payload_fails_closed(monkeypatch):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    delivery_id = 'conflicting_delivery_id'
    first_body = _body(_event(provider_email_id='email_first'))
    second_body = _body(_event(provider_email_id='email_conflict'))

    first = await email_webhooks.resend_delivery_webhook(
        RawRequest(first_body, _signed_headers(first_body, delivery_id=delivery_id))
    )
    second = await email_webhooks.resend_delivery_webhook(
        RawRequest(second_body, _signed_headers(second_body, delivery_id=delivery_id))
    )

    assert first.status_code == 204
    assert second.status_code == 503
    assert len(fake_db.persisted) == 1
    persisted = next(iter(fake_db.persisted.values()))
    assert persisted['p_provider_email_hash'] == _sha256('resend-email', 'email_first')


@pytest.mark.asyncio
async def test_one_email_can_have_multiple_distinct_delivery_events(monkeypatch):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    provider_email_id = 'shared_email_identity'

    for sequence, event_type in enumerate(('email.sent', 'email.delivered'), start=1):
        raw_body = _body(_event(event_type, provider_email_id=provider_email_id))
        response = await email_webhooks.resend_delivery_webhook(
            RawRequest(
                raw_body,
                _signed_headers(raw_body, delivery_id=f'delivery_{sequence}'),
            )
        )
        assert response.status_code == 204

    assert len(fake_db.persisted) == 2
    records = list(fake_db.persisted.values())
    assert records[0]['p_provider_event_hash'] != records[1]['p_provider_event_hash']
    assert records[0]['p_provider_email_hash'] == records[1]['p_provider_email_hash']


@pytest.mark.asyncio
async def test_only_allowlisted_metadata_crosses_the_database_boundary(monkeypatch, caplog):
    private = 'PRIVATE-CUSTOMER-CONTENT-SENTINEL-7402'
    delivery_id = f'delivery-{private}'
    provider_email_id = f'email-{private}'
    payload = _event(
        'email.bounced',
        provider_email_id=provider_email_id,
        top_level_id=f'payload-{private}',
        bounce_type='Permanent',
    )
    data = payload['data']
    assert isinstance(data, dict)
    data['from'] = private
    data['to'] = [private]
    data['subject'] = private
    data['headers'] = {'x-private': private}
    data['tags'] = {
        'message_kind': 'password_reset',
        'delivery_environment': 'test',
        'private': private,
    }
    bounce = data['bounce']
    assert isinstance(bounce, dict)
    bounce['message'] = private
    bounce['diagnosticCode'] = [private]
    raw_body = _body(payload)
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)

    with caplog.at_level('INFO'):
        response = await email_webhooks.resend_delivery_webhook(
            RawRequest(raw_body, _signed_headers(raw_body, delivery_id=delivery_id))
        )

    assert response.status_code == 204
    assert response.body == b''
    name, record, options = fake_db.calls[0]
    assert name == 'record_resend_delivery_event'
    assert options == {'timeout': 3.0}
    assert set(record) == _RPC_KEYS
    assert record['p_message_kind'] == 'password_reset'
    assert private not in repr(fake_db.calls)
    assert private not in caplog.text
    assert delivery_id not in repr(fake_db.calls)
    assert provider_email_id not in repr(fake_db.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('missing_header', ('svix-id', 'svix-timestamp', 'svix-signature'))
async def test_missing_signature_headers_are_rejected_without_database_work(
    monkeypatch,
    missing_header,
):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    raw_body = _body(_event())
    headers = _signed_headers(raw_body)
    del headers[missing_header]

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(raw_body, headers)
    )

    assert response.status_code == 400
    assert json.loads(response.body) == {
        'success': False,
        'error': 'Invalid webhook signature.',
    }
    assert fake_db.calls == []


@pytest.mark.asyncio
async def test_stale_signature_is_rejected_without_database_work(monkeypatch):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    raw_body = _body(_event())

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(raw_body, _signed_headers(raw_body, timestamp=1))
    )

    assert response.status_code == 400
    assert fake_db.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('raw_body', 'signature'),
    (
        (_body(_event()), 'v1,a'),
        (b'\xff', None),
    ),
)
async def test_malformed_signature_inputs_fail_as_a_controlled_400(
    monkeypatch,
    raw_body,
    signature,
):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    headers = _signed_headers(raw_body)
    if signature is not None:
        headers['svix-signature'] = signature

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(raw_body, headers)
    )

    assert response.status_code == 400
    assert json.loads(response.body) == {
        'success': False,
        'error': 'Invalid webhook signature.',
    }
    assert fake_db.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'payload',
    (
        [],
        {
            'type': 'email.delivered',
            'created_at': 'not-a-timestamp',
            'data': {
                'email_id': 'email_provider_123',
                'tags': {
                    'message_kind': 'verification',
                    'delivery_environment': 'test',
                },
            },
        },
        _event('email.bounced', bounce_type='Unknown'),
    ),
)
async def test_signed_malformed_supported_payloads_are_rejected(monkeypatch, payload):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    raw_body = _body(payload)

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(raw_body, _signed_headers(raw_body))
    )

    assert response.status_code == 400
    assert json.loads(response.body) == {
        'success': False,
        'error': 'Invalid webhook payload.',
    }
    assert fake_db.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('delivery_environment', (None, 'staging', 'production '))
async def test_signed_owned_event_without_allowlisted_send_environment_fails_closed(
    monkeypatch,
    delivery_environment,
):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db)
    raw_body = _body(_event(delivery_environment=delivery_environment))

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(raw_body, _signed_headers(raw_body))
    )

    assert response.status_code == 400
    assert fake_db.calls == []


@pytest.mark.asyncio
async def test_unconfigured_webhook_is_unavailable_without_reading_or_persisting(monkeypatch):
    fake_db = RecordingDB()
    _configure(monkeypatch, fake_db, secret=None)
    request = RawRequest(b'not-read', {})

    response = await email_webhooks.resend_delivery_webhook(request)

    assert response.status_code == 503
    assert json.loads(response.body) == {
        'success': False,
        'error': 'Email delivery webhook is not configured.',
    }
    assert request.body_reads == 0
    assert fake_db.calls == []


@pytest.mark.asyncio
async def test_database_failure_returns_retryable_503_without_private_data(
    monkeypatch,
    caplog,
):
    private = 'PRIVATE-DATABASE-DETAIL-SENTINEL-9918'
    delivery_id = 'private-delivery-id'
    provider_email_id = 'private-provider-email-id'
    fake_db = FailingDB(private)
    _configure(monkeypatch, fake_db)
    raw_body = _body(_event(provider_email_id=provider_email_id))

    with caplog.at_level('ERROR'):
        response = await email_webhooks.resend_delivery_webhook(
            RawRequest(
                raw_body,
                _signed_headers(raw_body, delivery_id=delivery_id),
            )
        )

    assert response.status_code == 503
    assert json.loads(response.body) == {
        'success': False,
        'error': 'Webhook persistence unavailable.',
    }
    assert len(fake_db.calls) == 1
    assert private not in response.body.decode('utf-8')
    assert private not in caplog.text
    assert delivery_id not in caplog.text
    assert provider_email_id not in caplog.text


@pytest.mark.asyncio
async def test_database_write_has_a_strict_total_acknowledgement_deadline(monkeypatch):
    fake_db = SlowDB()
    _configure(monkeypatch, fake_db)
    monkeypatch.setattr(email_webhooks, '_PERSISTENCE_DEADLINE_SECONDS', 0.01)
    raw_body = _body(_event())

    response = await email_webhooks.resend_delivery_webhook(
        RawRequest(raw_body, _signed_headers(raw_body))
    )

    assert response.status_code == 503
    assert json.loads(response.body) == {
        'success': False,
        'error': 'Webhook persistence unavailable.',
    }
    assert len(fake_db.calls) == 1
    assert fake_db.calls[0][2] == {'timeout': 3.0}
