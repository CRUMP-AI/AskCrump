import asyncio
import base64
from dataclasses import replace
from email import message_from_bytes
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backend.agent_gmail_write import execute as adapter_execute
from backend.config import get_settings
from backend.db import eq
from backend.google_connector import (
    GMAIL_WRITE_SCOPES,
    READ_SCOPES,
    WRITE_SCOPES,
    ConnectionRequiredError,
    GoogleConnector,
    GoogleConnectorError,
)

USER_ID = '11111111-1111-1111-1111-111111111111'
ACCOUNT = 'owner@example.com'
RECIPIENT = 'person@example.com'
SUBJECT = 'Quarterly update'
BODY = 'Hello,\n\nThe quarterly numbers are attached below.\n'


def _settings(**overrides):
    base = get_settings()
    values = {
        'google_oauth_client_id': 'client-123',
        'google_oauth_client_secret': 'secret-xyz',
        'google_oauth_redirect_uri': (
            'https://askcrump.com/api/connections/google/callback'
        ),
    }
    values.update(overrides)
    return replace(base, **values)


class FakeVault:
    @property
    def configured(self):
        return True

    def encrypt(self, plaintext, *, user_id, provider, connection_id):
        return f'enc:{plaintext[::-1]}' if plaintext else ''

    def decrypt(self, ciphertext, *, user_id, provider, connection_id):
        return ciphertext[4:][::-1] if ciphertext.startswith('enc:') else ''


class FakeDB:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    @staticmethod
    def _matches(row, filters):
        for key, raw in (filters or {}).items():
            expected = raw[3:] if str(raw).startswith('eq.') else raw
            if str(row.get(key)) != str(expected):
                return False
        return True

    async def select(self, table, *, columns='*', filters=None, order=None, limit=None):
        return [row for row in self.rows if self._matches(row, filters)]

    async def select_one(self, table, *, columns='*', filters=None):
        rows = await self.select(table, columns=columns, filters=filters)
        return rows[0] if rows else None

    async def insert(self, table, payload):
        row = dict(payload)
        row.setdefault('id', 'conn-1')
        self.rows.append(row)
        return [row]

    async def upsert(self, table, payload, *, on_conflict):
        existing = await self.select_one(
            table,
            filters={
                'user_id': eq(payload['user_id']),
                'provider': eq(payload['provider']),
                'account_email': eq(payload['account_email']),
            },
        )
        if existing:
            existing.update(payload)
            return [existing]
        return await self.insert(table, payload)

    async def update(self, table, payload, *, filters, retry_transient=False):
        updated = []
        for row in self.rows:
            if self._matches(row, filters):
                row.update(payload)
                updated.append(row)
        return updated


def _connected_db(scopes):
    return FakeDB(
        rows=[
            {
                'id': 'conn-1',
                'user_id': USER_ID,
                'provider': 'google',
                'account_email': ACCOUNT,
                'scopes': list(scopes),
                'access_token_ciphertext': FakeVault().encrypt(
                    'access-token-1',
                    user_id=USER_ID,
                    provider='google',
                    connection_id='conn-1',
                ),
                'refresh_token_ciphertext': '',
                'token_expires_at': '2099-01-01T00:00:00+00:00',
                'status': 'connected',
            }
        ]
    )


def _write_handler(captured, *, fail_scope=False):
    def handler(request):
        captured.append(request)
        path = request.url.path
        if fail_scope and (
            path.endswith('/drafts') or path.endswith('/messages/send')
        ):
            return httpx.Response(
                403,
                json={
                    'error': {
                        'code': 403,
                        'message': 'Insufficient Permission',
                        'errors': [
                            {
                                'domain': 'global',
                                'reason': 'insufficientPermissions',
                                'message': 'Insufficient Permission',
                            }
                        ],
                        'status': 'PERMISSION_DENIED',
                    }
                },
            )
        if path.endswith('/drafts') and request.method == 'POST':
            return httpx.Response(
                200,
                json={
                    'id': 'draft-1',
                    'message': {'id': 'm-draft-1', 'threadId': 'thread-1'},
                },
            )
        if path.endswith('/messages/send') and request.method == 'POST':
            return httpx.Response(
                200,
                json={'id': 'm-sent-1', 'threadId': 'thread-2', 'labelIds': ['SENT']},
            )
        return httpx.Response(404, json={})

    return handler


def _connector(db=None, captured=None, *, fail_scope=False):
    transport = httpx.MockTransport(
        _write_handler(captured if captured is not None else [], fail_scope=fail_scope)
    )
    return GoogleConnector(
        settings=_settings(),
        db=db if db is not None else _connected_db(READ_SCOPES + GMAIL_WRITE_SCOPES),
        vault=FakeVault(),
        http_client=httpx.AsyncClient(transport=transport),
    )


def _decode_raw(raw):
    decoded = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4))
    return message_from_bytes(decoded)


# -- Scope posture -------------------------------------------------------


def test_write_scopes_are_staged_and_the_read_default_is_unchanged():
    assert any('gmail.compose' in scope for scope in GMAIL_WRITE_SCOPES)
    assert any('gmail.send' in scope for scope in GMAIL_WRITE_SCOPES)
    assert set(GMAIL_WRITE_SCOPES) <= set(WRITE_SCOPES)
    assert any('gmail.compose' in scope for scope in WRITE_SCOPES)
    assert any('gmail.send' in scope for scope in WRITE_SCOPES)
    assert not any('gmail.send' in scope for scope in READ_SCOPES)
    assert not any('gmail.compose' in scope for scope in READ_SCOPES)

    connector = _connector()
    default_query = parse_qs(urlparse(connector.authorization_url(USER_ID)).query)
    assert set(default_query['scope'][0].split()) == set(READ_SCOPES)

    staged_query = parse_qs(
        urlparse(connector.authorization_url(USER_ID, scopes=WRITE_SCOPES)).query
    )
    staged = set(staged_query['scope'][0].split())
    assert any('gmail.send' in scope for scope in staged)
    assert any('gmail.compose' in scope for scope in staged)


# -- Connector request shape ----------------------------------------------


def test_create_draft_posts_a_base64url_raw_message():
    captured = []
    connector = _connector(captured=captured)
    result = asyncio.run(
        connector.create_draft(USER_ID, to=RECIPIENT, subject=SUBJECT, body=BODY)
    )
    assert result == {'id': 'draft-1', 'messageId': 'm-draft-1', 'threadId': 'thread-1'}
    assert len(captured) == 1
    request = captured[0]
    assert request.method == 'POST'
    assert request.url.path.endswith('/users/me/drafts')
    assert request.headers['authorization'] == 'Bearer access-token-1'
    payload = json.loads(request.content.decode('utf-8'))
    message = _decode_raw(payload['message']['raw'])
    assert message['To'] == RECIPIENT
    assert message['Subject'] == SUBJECT
    assert BODY.strip() in message.get_payload(decode=True).decode('utf-8')


def test_send_message_posts_a_base64url_raw_message():
    captured = []
    connector = _connector(captured=captured)
    result = asyncio.run(
        connector.send_message(USER_ID, to=RECIPIENT, subject=SUBJECT, body=BODY)
    )
    assert result['id'] == 'm-sent-1'
    assert result['threadId'] == 'thread-2'
    assert result['labelIds'] == ['SENT']
    assert len(captured) == 1
    request = captured[0]
    assert request.method == 'POST'
    assert request.url.path.endswith('/users/me/messages/send')
    assert request.headers['authorization'] == 'Bearer access-token-1'
    payload = json.loads(request.content.decode('utf-8'))
    message = _decode_raw(payload['raw'])
    assert message['To'] == RECIPIENT
    assert message['Subject'] == SUBJECT
    assert BODY.strip() in message.get_payload(decode=True).decode('utf-8')


def test_create_draft_without_a_connection_raises_connection_required():
    connector = _connector(db=FakeDB())
    with pytest.raises(ConnectionRequiredError) as caught:
        asyncio.run(
            connector.create_draft(USER_ID, to=RECIPIENT, subject=SUBJECT, body=BODY)
        )
    assert caught.value.code == 'CONNECTION_REQUIRED'
    assert caught.value.status_code == 409


def test_gmail_403_insufficient_permissions_maps_to_insufficient_scope():
    captured = []
    connector = _connector(
        db=_connected_db(()), captured=captured, fail_scope=True
    )
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            connector.send_message(USER_ID, to=RECIPIENT, subject=SUBJECT, body=BODY)
        )
    assert caught.value.code == 'INSUFFICIENT_SCOPE'
    assert caught.value.status_code == 403
    assert len(captured) == 1


def test_message_headers_reject_crlf_injection():
    connector = _connector()
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            connector.send_message(
                USER_ID,
                to=RECIPIENT,
                subject='Hi\r\nBcc: other@example.com',
                body=BODY,
            )
        )
    assert caught.value.code == 'INVALID_MESSAGE'


# -- Adapter ---------------------------------------------------------------


def test_adapter_draft_returns_a_redacted_summary():
    captured = []
    connector = _connector(captured=captured)
    result = asyncio.run(
        adapter_execute(
            'gmail.draft',
            USER_ID,
            {'to': RECIPIENT, 'subject': SUBJECT, 'body': BODY},
            connector=connector,
        )
    )
    assert result['status'] == 'draft_created'
    assert result['draftId'] == 'draft-1'
    assert result['messageId'] == 'm-draft-1'
    assert result['recipientDomain'] == 'example.com'
    assert result['subjectLength'] == len(SUBJECT)
    serialized = json.dumps(result)
    assert RECIPIENT not in serialized
    assert BODY.strip() not in serialized
    assert len(captured) == 1


def test_adapter_send_returns_a_redacted_summary():
    connector = _connector()
    result = asyncio.run(
        adapter_execute(
            'gmail.send',
            USER_ID,
            {'to': RECIPIENT, 'subject': SUBJECT, 'body': BODY},
            connector=connector,
        )
    )
    assert result['status'] == 'sent'
    assert result['messageId'] == 'm-sent-1'
    assert result['recipientDomain'] == 'example.com'
    assert result['subjectLength'] == len(SUBJECT)
    serialized = json.dumps(result)
    assert RECIPIENT not in serialized
    assert BODY.strip() not in serialized


def test_adapter_draft_subject_is_optional_per_the_registry():
    connector = _connector()
    result = asyncio.run(
        adapter_execute(
            'gmail.draft', USER_ID, {'to': RECIPIENT, 'body': BODY}, connector=connector
        )
    )
    assert result['status'] == 'draft_created'
    assert result['subjectLength'] == 0


def test_adapter_validation_follows_the_registry_required_fields():
    captured = []
    connector = _connector(captured=captured)
    cases = [
        ('gmail.draft', {'to': RECIPIENT}),
        ('gmail.draft', {'body': BODY}),
        ('gmail.send', {'to': RECIPIENT, 'body': BODY}),
        ('gmail.send', {'to': RECIPIENT, 'subject': SUBJECT}),
        ('gmail.draft', 'not-an-object'),
    ]
    for capability_id, payload in cases:
        with pytest.raises(GoogleConnectorError) as caught:
            asyncio.run(
                adapter_execute(capability_id, USER_ID, payload, connector=connector)
            )
        assert caught.value.code == 'INVALID_PAYLOAD'
    assert captured == []


def test_adapter_rejects_unknown_and_unsupported_capabilities():
    connector = _connector()
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            adapter_execute(
                'gmail.delete_everything',
                USER_ID,
                {'to': RECIPIENT, 'body': BODY},
                connector=connector,
            )
        )
    assert caught.value.code == 'CAPABILITY_NOT_FOUND'
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            adapter_execute(
                'gmail.search', USER_ID, {'query': 'invoice'}, connector=connector
            )
        )
    assert caught.value.code == 'UNSUPPORTED_CAPABILITY'


def test_adapter_without_a_connection_raises_connection_required():
    connector = _connector(db=FakeDB())
    with pytest.raises(ConnectionRequiredError) as caught:
        asyncio.run(
            adapter_execute(
                'gmail.send',
                USER_ID,
                {'to': RECIPIENT, 'subject': SUBJECT, 'body': BODY},
                connector=connector,
            )
        )
    assert caught.value.code == 'CONNECTION_REQUIRED'


def test_adapter_readonly_grant_fails_insufficient_scope_before_any_call():
    captured = []
    connector = _connector(db=_connected_db(READ_SCOPES), captured=captured)
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            adapter_execute(
                'gmail.send',
                USER_ID,
                {'to': RECIPIENT, 'subject': SUBJECT, 'body': BODY},
                connector=connector,
            )
        )
    assert caught.value.code == 'INSUFFICIENT_SCOPE'
    assert 'gmail.send' in caught.value.message
    assert captured == []


def test_adapter_scopeless_record_attempts_and_maps_the_gmail_403():
    captured = []
    connector = _connector(db=_connected_db(()), captured=captured, fail_scope=True)
    with pytest.raises(GoogleConnectorError) as caught:
        asyncio.run(
            adapter_execute(
                'gmail.draft',
                USER_ID,
                {'to': RECIPIENT, 'subject': SUBJECT, 'body': BODY},
                connector=connector,
            )
        )
    assert caught.value.code == 'INSUFFICIENT_SCOPE'
    assert len(captured) == 1
