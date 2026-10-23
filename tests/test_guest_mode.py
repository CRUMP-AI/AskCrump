"""Guest-mode enforcement coverage.

Covers the pieces that keep the free preview bounded and honest:
- public_user exposes the guest state the frontend renders.
- The 5-message limit predicate is exact (5th message is the last free one).
- authenticate_request(require_account=True) rejects guest sessions with a
  403 everywhere it guards, while full accounts pass and ordinary chat
  authentication still accepts the guest.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request
from unittest.mock import AsyncMock

import app as app_module
from backend.auth_service import (
    FREE_TEXT_MESSAGE_LIMIT,
    AuthenticationError,
    authenticate_guest_for_registration,
    authenticate_request,
    free_text_message_fingerprint,
    guest_mode_control_value,
    guest_limit_reached,
    is_free_text_user,
    is_guest_user,
    paid_tools_entitled,
    public_user,
)
from backend.routes import chat as chat_routes
from backend.security import token_hash

RAW_TOKEN = '<MASKED_SECRET_001>'
USER_ID = '11111111-1111-5111-8111-111111111111'
SETTINGS = SimpleNamespace(session_cookie_name='crump_session')


def make_request(token: str | None = RAW_TOKEN) -> Request:
    headers = []
    if token:
        headers.append((b'authorization', f'Bearer {token}'.encode()))
    return Request({
        'type': 'http',
        'method': 'GET',
        'path': '/api/test',
        'headers': headers,
        'query_string': b'',
    })


class FakeDb:
    """Returns the canned session only when the presented token hash matches."""

    def __init__(self, user, *, guest_mode_control=True):
        self.user = user
        self.guest_mode_control = guest_mode_control
        self.rpc_calls = []
        self.session = {
            'id': 'session-1',
            'user_id': user['id'] if user else USER_ID,
            'token_hash': token_hash(RAW_TOKEN),
        }

    async def select_one(self, table, columns='*', filters=None):
        if table == 'sessions':
            expected = f'eq.{self.session["token_hash"]}'
            if (filters or {}).get('token_hash') != expected:
                return None
            return self.session
        if table == 'users':
            return self.user
        return None

    async def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))
        if name == 'get_guest_mode_control_v1':
            if isinstance(self.guest_mode_control, Exception):
                raise self.guest_mode_control
            return self.guest_mode_control
        return [{'allowed': True}]


def guest_user(count=0):
    return {
        'id': USER_ID,
        'email': 'guest-x@guest.askcrump.local',
        'is_guest': True,
        'guest_message_count': count,
        'is_verified': False,
        'subscription_tier': 'free',
    }


def full_user():
    return {
        'id': USER_ID,
        'email': 'person@example.com',
        'is_guest': False,
        'guest_message_count': 0,
        'is_verified': True,
        'subscription_tier': 'free',
    }


def test_public_user_exposes_guest_state():
    payload = public_user(guest_user(count=3))
    assert payload['isGuest'] is True
    assert payload['freeMessageLimit'] == FREE_TEXT_MESSAGE_LIMIT == 5
    assert payload['freeMessageWindowKind'] == 'rolling_24h'
    assert payload['freeMessageWindowSeconds'] == 86400
    assert 'guestMessagesUsed' not in payload

    payload = public_user(full_user())
    assert payload['isGuest'] is False
    assert payload['freeMessageLimit'] == 5
    assert is_free_text_user(full_user()) is True


@pytest.mark.parametrize(
    'paid_fields',
    [
        {'internal_tier': 'enterprise'},
        {'subscription_tier': 'professional', 'subscription_status': 'active'},
        {'subscription_tier': 'enterprise', 'subscription_status': 'trialing'},
    ],
)
def test_guest_state_dominates_malformed_paid_or_internal_labels(paid_fields):
    from backend.usage_service import has_internal_access, tier_name

    user = {**guest_user(), **paid_fields}
    assert tier_name(user) == 'free'
    assert has_internal_access(user) is False
    assert is_free_text_user(user) is True
    assert paid_tools_entitled(user) is False


@pytest.mark.parametrize(
    'user,expected',
    [
        (guest_user(0), False),
        (guest_user(4), False),
        (guest_user(5), True),
        (guest_user(9), True),
        (full_user(), False),
        ({**full_user(), 'guest_message_count': 99}, False),
        (None, False),
        ({}, False),
    ],
)
def test_guest_limit_predicate(user, expected):
    assert guest_limit_reached(user) is expected
    assert is_guest_user(user) is bool(user and user.get('is_guest'))


def test_require_account_rejects_guest_with_403():
    db = FakeDb(guest_user())
    with pytest.raises(AuthenticationError) as excinfo:
        asyncio.run(authenticate_request(
            make_request(), db, SETTINGS, touch=False, require_account=True,
        ))
    assert excinfo.value.status_code == 403
    assert 'Create your free account' in excinfo.value.message


def test_require_account_allows_full_user():
    db = FakeDb(full_user())
    auth = asyncio.run(authenticate_request(
        make_request(), db, SETTINGS, touch=False, require_account=True,
    ))
    assert auth.user['email'] == 'person@example.com'


def test_guest_session_still_authenticates_for_chat():
    db = FakeDb(guest_user(count=2))
    auth = asyncio.run(authenticate_request(
        make_request(), db, SETTINGS, touch=False,
    ))
    assert auth.user['is_guest'] is True


@pytest.mark.parametrize(
    'control_value',
    [False, None, [], {}, [True, False], {'enabled': False}],
)
def test_existing_guest_session_fails_closed_when_control_is_not_enabled(control_value):
    db = FakeDb(guest_user(), guest_mode_control=control_value)

    with pytest.raises(AuthenticationError) as excinfo:
        asyncio.run(authenticate_request(make_request(), db, SETTINGS, touch=False))

    assert excinfo.value.status_code == 503
    assert db.rpc_calls == [('get_guest_mode_control_v1', {})]


def test_existing_guest_session_fails_closed_when_control_read_errors():
    db = FakeDb(guest_user(), guest_mode_control=RuntimeError('control unavailable'))

    with pytest.raises(AuthenticationError) as excinfo:
        asyncio.run(authenticate_request(make_request(), db, SETTINGS, touch=False))

    assert excinfo.value.status_code == 503
    assert db.rpc_calls == [('get_guest_mode_control_v1', {})]


def test_existing_registered_session_does_not_depend_on_guest_control():
    db = FakeDb(full_user(), guest_mode_control=False)

    auth = asyncio.run(authenticate_request(make_request(), db, SETTINGS, touch=False))

    assert auth.user['email'] == 'person@example.com'
    assert db.rpc_calls == []


@pytest.mark.parametrize(
    'control_value,expected',
    [
        (True, True),
        ([True], True),
        ({'enabled': True}, True),
        ([{'enabled': True}], True),
        (False, False),
        (None, False),
        ([], False),
        ({}, False),
        ([True, False], False),
    ],
)
def test_guest_control_parser_accepts_only_explicit_true_shapes(control_value, expected):
    assert guest_mode_control_value(control_value) is expected


def test_wrong_token_is_unauthorized_even_for_accounts():
    db = FakeDb(full_user())
    with pytest.raises(AuthenticationError) as excinfo:
        asyncio.run(authenticate_request(
            make_request('some-other-token'), db, SETTINGS, touch=False,
        ))
    assert excinfo.value.status_code == 401


# --- Shared rolling allowance reservation -----------------------------------

from backend.auth_service import reserve_free_text_message  # noqa: E402


class ReservationDb:
    """In-memory contract stand-in for reserve_free_message_v1."""

    def __init__(self, count=0, *, rpc_down=False):
        self.count = count
        self.receipts = set()
        self.rpc_down = rpc_down
        self.calls = []

    async def rpc(self, name, payload, retry_transient=False):
        assert name == 'reserve_free_message_v1'
        assert retry_transient is True
        self.calls.append(dict(payload))
        if self.rpc_down:
            from backend.db import DatabaseError
            raise DatabaseError('function unavailable')
        key = (payload['p_message_id'], payload['p_fingerprint'])
        if key in self.receipts:
            return [{
                'outcome': 'reused',
                'event_id': None,
                'used': self.count,
                'remaining': max(0, 5 - self.count),
                'next_available_at': '2026-10-23T12:00:00+00:00' if self.count >= 5 else None,
            }]
        if self.count >= 5:
            return [{
                'outcome': 'exhausted',
                'event_id': None,
                'used': self.count,
                'remaining': 0,
                'next_available_at': '2026-10-23T12:00:00+00:00',
            }]
        self.receipts.add(key)
        self.count += 1
        return [{
            'outcome': 'reserved',
            'event_id': f'event-{self.count}',
            'used': self.count,
            'remaining': 5 - self.count,
            'next_available_at': '2026-10-23T12:00:00+00:00' if self.count >= 5 else None,
        }]


def reserve(db, user, message_id='11111111-1111-5111-8111-111111111119', fingerprint='a' * 64):
    return asyncio.run(reserve_free_text_message(
        db,
        user,
        message_id=message_id,
        fingerprint=fingerprint,
    ))


def test_reserve_consumes_a_slot_for_guest_and_registered_free():
    db = ReservationDb(3)
    guest_result = reserve(db, guest_user())
    assert guest_result['allowed'] is True
    assert guest_result['used'] == 4
    assert guest_result['eventId'] == 'event-4'

    registered_result = reserve(
        db,
        full_user(),
        message_id='11111111-1111-5111-8111-111111111120',
        fingerprint='b' * 64,
    )
    assert registered_result['allowed'] is True
    assert registered_result['used'] == 5
    assert db.count == 5


def test_reserve_refuses_sixth_for_registered_free_after_guest_conversion():
    db = ReservationDb(5)
    result = reserve(db, full_user())
    assert result['allowed'] is False
    assert result['remaining'] == 0
    assert result['nextAvailableAt'] == '2026-10-23T12:00:00+00:00'


def test_paid_account_bypasses_free_reservation_rpc():
    paid = {
        **full_user(),
        'subscription_tier': 'professional',
        'subscription_status': 'active',
    }
    db = ReservationDb(5)
    result = reserve(db, paid)
    assert result['allowed'] is True
    assert result['limit'] == -1
    assert db.calls == []


def test_database_guest_write_barrier_maps_to_fail_closed_auth_response():
    class DisabledReservationDb:
        async def rpc(self, name, payload, retry_transient=False):
            assert name == 'reserve_free_message_v1'
            assert retry_transient is True
            return [{
                'outcome': 'guest_mode_disabled',
                'event_id': None,
                'used': 0,
                'remaining': 0,
                'next_available_at': None,
            }]

    with pytest.raises(AuthenticationError) as excinfo:
        reserve(DisabledReservationDb(), guest_user())

    assert excinfo.value.status_code == 503
    assert 'Guest preview is temporarily unavailable' in excinfo.value.message


def test_free_reservation_requires_durable_message_identity():
    with pytest.raises(AuthenticationError) as excinfo:
        asyncio.run(reserve_free_text_message(
            ReservationDb(),
            full_user(),
            message_id=None,
            fingerprint='a' * 64,
        ))
    assert excinfo.value.status_code == 400


# --- Guest capability allowlist (direct signals) ----------------------------

from backend.auth_service import guest_blocked_signal  # noqa: E402


@pytest.mark.parametrize('payload,image_requested,expected', [
    ({'message': 'What is the capital of France?'}, False, None),
    ({'message': 'Explain recursion like I am five'}, False, None),
    ({'message': 'hi', 'fileRefs': [{'id': 'f1'}]}, False, 'file attachments'),
    ({'message': 'hi', 'history': [{'role': 'user', 'fileRefs': ['f9']}]}, False, 'file attachments'),
    ({'message': 'hi', 'fileData': [{'name': 'legacy.png', 'data': 'abc'}]}, False, 'file attachments'),
    ({'message': 'hi', 'projectId': 'p1'}, False, 'Projects'),
    ({'message': 'hi', 'artifactFormat': 'docx'}, False, 'document downloads'),
    ({'message': 'hi', 'longForm': True}, False, 'manuscripts'),
    ({'message': 'hi', 'creativeTool': 'image'}, False, 'creative tools'),
    ({'message': 'hi', 'requestedTool': 'web'}, False, 'web research'),
    ({'message': 'draw a cat'}, True, 'image creation'),
    ({'message': 'hi', 'imageReferencePlan': [{'x': 1}]}, False, 'image creation'),
    ({'message': 'hi', 'imageUseReference': True}, False, 'image creation'),
])
def test_guest_blocked_signal_matrix(payload, image_requested, expected):
    assert guest_blocked_signal(payload, image_requested=image_requested) == expected


def test_raw_inline_file_payload_is_rejected_before_free_reservation_or_provider_work(monkeypatch):
    class GateDb:
        def __init__(self):
            self.calls = []

        async def rpc(self, name, payload, **_kwargs):
            self.calls.append(name)
            if name == 'claim_chat_job_v2':
                return [{
                    'job_state': 'claimed',
                    'claim_token': '11111111-1111-4111-8111-111111111113',
                }]
            if name == 'release_chat_job_claim':
                return True
            raise AssertionError(f'Paid attachment gate must run before {name}.')

        async def select_one(self, table, **_kwargs):
            assert table == 'user_chats'
            return None

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user=full_user(),
            session={'id': 'session-1'},
            token='token',
        )

    database = GateDb()
    monkeypatch.setattr(chat_routes, 'db', database)
    monkeypatch.setattr(chat_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(chat_routes, 'features', SimpleNamespace(entitled=lambda *_args: False))
    monkeypatch.setattr(
        chat_routes,
        'media',
        SimpleNamespace(is_image_request=lambda *_args: False),
    )
    monkeypatch.setattr(
        chat_routes,
        'files',
        SimpleNamespace(resolve_many=AsyncMock(side_effect=AssertionError('Files must not resolve.'))),
    )
    monkeypatch.setattr(
        chat_routes,
        'ai',
        SimpleNamespace(chat=AsyncMock(side_effect=AssertionError('Provider must not run.'))),
    )

    response = TestClient(app_module.app).post('/api/chat', json={
        'chatId': '11111111-1111-4111-8111-111111111114',
        'messageId': '11111111-1111-4111-8111-111111111115',
        'message': 'Use this old client attachment.',
        'fileData': [{'name': 'legacy.png', 'type': 'image/png', 'data': 'YWJj'}],
    })

    assert response.status_code == 403
    assert response.json()['code'] == 'SUBSCRIPTION_REQUIRED'
    assert response.json()['requiredTier'] == 'professional'
    assert database.calls == ['claim_chat_job_v2', 'release_chat_job_claim']


# --- Preparation lockdown in guest mode -------------------------------------

from backend.intelligence_service import IntelligenceService  # noqa: E402


class ExplodingAi:
    def __getattr__(self, name):
        raise AssertionError(f'AI service must not be touched here (.{name})')


class StubDb:
    async def select_one(self, table, columns='*', filters=None, **kwargs):
        return None

    async def select(self, table, columns='*', filters=None, **kwargs):
        return []

    async def rpc(self, name, params=None, **kwargs):
        return []


def test_prepare_guest_preview_disables_creation_and_lookups():
    service = IntelligenceService(db=StubDb(), ai=ExplodingAi(), settings=SETTINGS)
    prepared = asyncio.run(service.prepare(
        'guest-1',
        {
            'message': 'Write me a childrens book about a turtle and search the web for turtle facts',
            'requestedTool': 'web',
            'creationIntent': {'kind': 'manuscript', 'stage': 'execute'},
            'creativeTool': 'image',
        },
        allow_think_longer=False,
        user_tier='free',
        guest_preview=True,
    ))
    assert prepared.creation_intent is None
    assert prepared.payload['_externalLookupPolicy'] == {'search': False, 'weather': False}
    assert 'needsSearch' not in prepared.payload
    assert 'needsWeather' not in prepared.payload
    assert 'creationIntent' not in prepared.payload


def test_prepare_registered_user_keeps_tool_policy():
    service = IntelligenceService(db=StubDb(), ai=ExplodingAi(), settings=SETTINGS)
    prepared = asyncio.run(service.prepare(
        'user-1',
        {'message': 'What is the weather in Savannah today?'},
        allow_think_longer=False,
        user_tier='free',
    ))
    assert prepared.payload['_externalLookupPolicy']['weather'] is True


# --- Durable allowance receipts (user + message ID) --------------------------

def test_receipt_failed_send_retry_reuses_without_refundable_event():
    db = ReservationDb(3)
    user = guest_user(3)
    message_id = '11111111-1111-5111-8111-111111111121'
    first = reserve(db, user, message_id=message_id, fingerprint='c' * 64)
    assert first['eventId'] == 'event-4'
    replay = reserve(db, user, message_id=message_id, fingerprint='c' * 64)
    assert replay['allowed'] is True
    assert replay['eventId'] is None
    assert replay['idempotentReplay'] is True
    assert db.count == 4


def test_receipt_cap_message_retry_is_not_refused():
    db = ReservationDb(4)
    user = guest_user(4)
    message_id = '11111111-1111-5111-8111-111111111122'
    assert reserve(db, user, message_id=message_id, fingerprint='d' * 64)['allowed'] is True
    assert reserve(db, user, message_id=message_id, fingerprint='d' * 64)['allowed'] is True
    denied = reserve(
        db,
        user,
        message_id='11111111-1111-5111-8111-111111111123',
        fingerprint='e' * 64,
    )
    assert denied['allowed'] is False
    assert db.count == 5


def test_receipt_rpc_unavailable_fails_closed_for_identified_messages():
    db = ReservationDb(0, rpc_down=True)
    with pytest.raises(Exception):
        reserve(db, guest_user(0))
    assert db.count == 0


def test_receipt_recycled_message_id_with_new_content_pays_again():
    db = ReservationDb(3)
    user = guest_user(3)
    message_id = '11111111-1111-5111-8111-111111111124'
    assert reserve(db, user, message_id=message_id, fingerprint='f' * 64)['allowed'] is True
    assert reserve(db, user, message_id=message_id, fingerprint='1' * 64)['allowed'] is True
    assert reserve(db, user, message_id=message_id, fingerprint='f' * 64)['allowed'] is True
    assert reserve(db, user, message_id=message_id, fingerprint='2' * 64)['allowed'] is False
    assert db.count == 5


def test_guest_message_fingerprint_binds_chat_and_text():
    from backend.auth_service import guest_message_fingerprint
    assert guest_message_fingerprint('c1', 'hello') == guest_message_fingerprint('c1', 'hello')
    assert guest_message_fingerprint('c1', 'hello') != guest_message_fingerprint('c2', 'hello')
    assert guest_message_fingerprint('c1', 'hello') != guest_message_fingerprint('c1', 'hello!')


# --- Guest creation stores an unusable password sentinel --------------------

import backend.routes.auth as auth_routes  # noqa: E402
from backend.security import verify_password  # noqa: E402
from starlette.responses import Response as StarletteResponse  # noqa: E402


class GuestFlowDb(FakeDb):
    def __init__(self, *, guest_mode_control=True, user=None):
        super().__init__(user)
        self.inserted = []
        self.guest_mode_control = guest_mode_control
        self.rpc_calls = []

    async def insert(self, table, payload):
        self.inserted.append((table, payload))
        return [payload]

    async def upsert(self, table, payload, on_conflict=None):
        self.inserted.append((table, payload))
        return [payload]

    async def select(self, table, columns='*', filters=None, order=None, limit=None):
        return []

    async def update(self, table, payload, filters=None, **kwargs):
        return [payload]

    async def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))
        if name == 'get_guest_mode_control_v1':
            if isinstance(self.guest_mode_control, Exception):
                raise self.guest_mode_control
            return self.guest_mode_control
        return [{'allowed': True}]


def flow_request(token=None):
    headers = []
    if token:
        headers.append((b'authorization', f'Bearer {token}'.encode()))
    return Request({
        'type': 'http',
        'method': 'POST',
        'path': '/api/auth/test',
        'headers': headers,
        'query_string': b'',
        'client': ('203.0.113.7', 12345),
    })


def test_guest_creation_stores_unusable_password_sentinel(monkeypatch):
    db = GuestFlowDb()
    monkeypatch.setattr(auth_routes, 'db', db)
    result = asyncio.run(auth_routes.start_guest_session(flow_request(), StarletteResponse()))
    assert result['success'] is True
    created = [row for table, row in db.inserted if table == 'users']
    assert len(created) == 1
    sentinel = created[0]['password_hash']
    assert isinstance(sentinel, str) and sentinel  # NOT NULL satisfied
    assert verify_password('password', sentinel) is False
    assert verify_password('Password123', sentinel) is False
    assert verify_password('', sentinel) is False
    assert created[0]['is_guest'] is True
    assert 'registration_submitted_at' not in created[0]


@pytest.mark.parametrize(
    'control_value',
    [False, None, [], {}, [True, False], {'enabled': False}],
)
def test_guest_control_fail_closed_before_rate_budget_or_writes(monkeypatch, control_value):
    db = GuestFlowDb(guest_mode_control=control_value)
    monkeypatch.setattr(auth_routes, 'db', db)

    response = asyncio.run(auth_routes.start_guest_session(flow_request(), StarletteResponse()))

    assert response.status_code == 503
    body = json.loads(response.body)
    assert body['code'] == 'GUEST_MODE_DISABLED'
    assert db.inserted == []
    assert db.rpc_calls == [('get_guest_mode_control_v1', {})]


def test_guest_control_error_fails_closed_before_rate_budget_or_writes(monkeypatch):
    db = GuestFlowDb(guest_mode_control=RuntimeError('control unavailable'))
    monkeypatch.setattr(auth_routes, 'db', db)

    response = asyncio.run(auth_routes.start_guest_session(flow_request(), StarletteResponse()))

    assert response.status_code == 503
    assert json.loads(response.body)['code'] == 'GUEST_MODE_DISABLED'
    assert db.inserted == []
    assert db.rpc_calls == [('get_guest_mode_control_v1', {})]


def test_disabled_guest_entry_does_not_interrupt_registered_session(monkeypatch):
    db = GuestFlowDb(guest_mode_control=False, user=full_user())
    monkeypatch.setattr(auth_routes, 'db', db)

    result = asyncio.run(auth_routes.start_guest_session(
        flow_request(RAW_TOKEN),
        StarletteResponse(),
    ))

    assert result['success'] is True
    assert result['data']['guest'] is False
    assert db.rpc_calls == []
    assert db.inserted == []


@pytest.mark.parametrize(
    'control_value',
    [True, [True], {'enabled': True}, [{'enabled': True}]],
)
def test_guest_control_accepts_only_explicit_true_shapes(monkeypatch, control_value):
    db = GuestFlowDb(guest_mode_control=control_value)
    monkeypatch.setattr(auth_routes, 'db', db)

    result = asyncio.run(auth_routes.start_guest_session(flow_request(), StarletteResponse()))

    assert result['success'] is True
    assert [name for name, _payload in db.rpc_calls] == [
        'get_guest_mode_control_v1',
        'consume_rate_limit_event',
        'consume_rate_limit_event',
    ]
    assert len([row for table, row in db.inserted if table == 'users']) == 1


# --- Pending-signup collision: guest + someone else's unverified row --------

from backend.schemas import RegisterRequest, ResetPasswordRequest  # noqa: E402


class MultiUserDb:
    def __init__(self, users, sessions):
        self.users = {u['id']: u for u in users}
        self.sessions = sessions
        self.updates = []
        self.inserted = []
        self.rpc_calls = []

    async def select_one(self, table, columns='*', filters=None):
        filters = filters or {}
        if table == 'users':
            if 'email' in filters:
                email = str(filters['email']).removeprefix('eq.')
                return next((u for u in self.users.values() if u['email'] == email), None)
            if 'id' in filters:
                return self.users.get(str(filters['id']).removeprefix('eq.'))
            return None
        if table == 'sessions':
            return self.sessions.get(str(filters['token_hash']).removeprefix('eq.'))
        return None

    async def insert(self, table, payload):
        self.inserted.append((table, payload))
        return [payload]

    async def update(self, table, payload, filters=None, **kwargs):
        self.updates.append((table, payload, filters or {}))
        return [payload]

    async def upsert(self, table, payload, on_conflict=None):
        self.inserted.append((table, payload))
        return [payload]

    async def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))
        return [{'allowed': True}]


def test_register_guest_with_pending_email_never_mutates_pending_row(monkeypatch):
    guest = {**guest_user(2), 'email': 'guest-a@guest.askcrump.local', 'is_verified': False}
    pending = {
        'id': 'pending-b',
        'email': 'person@example.com',
        'password_hash': 'pending-b-hash',
        'is_verified': False,
        'verification_token_hash': 'original-token-hash',
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }
    guest_session = {'id': 's-guest', 'user_id': guest['id'], 'token_hash': token_hash(RAW_TOKEN)}
    db = MultiUserDb([guest, pending], {token_hash(RAW_TOKEN): guest_session})
    monkeypatch.setattr(auth_routes, 'db', db)
    payload = RegisterRequest(
        email='person@example.com',
        password='Password123',
        fullName='Pat',
        termsAccepted=True,
        termsVersion='2026-08-01',
    )
    response = asyncio.run(auth_routes.register(payload, flow_request(RAW_TOKEN)))
    assert response.status_code == 409
    import json as _json
    body = _json.loads(response.body)
    assert body['code'] == 'PENDING_ACCOUNT_RECOVERY'
    assert body['guestPreserved'] is True
    # The pending row was not touched: no update targeted it, token intact.
    assert all(
        str(f.get('id', '')).removeprefix('eq.') != 'pending-b'
        for _table, _payload, f in db.updates
    )
    assert db.users['pending-b']['verification_token_hash'] == 'original-token-hash'


def test_register_converts_the_same_guest_row_without_resetting_usage(monkeypatch):
    guest = {
        **guest_user(0),
        'email': f'guest-{USER_ID}@guest.askcrump.local',
        'is_verified': False,
    }
    guest_session = {
        'id': 's-guest',
        'user_id': guest['id'],
        'token_hash': token_hash(RAW_TOKEN),
    }
    db = MultiUserDb([guest], {token_hash(RAW_TOKEN): guest_session})
    monkeypatch.setattr(auth_routes, 'db', db)

    async def sent(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes.email_service, 'send_verification', sent)
    payload = RegisterRequest(
        email='person@example.com',
        password='Password123',
        fullName='Pat',
        termsAccepted=True,
        termsVersion='2026-08-01',
    )
    response = asyncio.run(auth_routes.register(payload, flow_request(RAW_TOKEN)))
    assert response['success'] is True
    user_updates = [item for item in db.updates if item[0] == 'users']
    assert len(user_updates) == 1
    _table, values, filters = user_updates[0]
    assert filters['id'] == f'eq.{guest["id"]}'
    assert values['email'] == 'person@example.com'
    assert 'is_guest' not in values  # remains guest until inbox verification
    assert 'created_at' not in values
    assert values['registration_submitted_at']
    assert values['registration_environment'] == 'development'
    assert 'guest_message_count' not in values
    assert all(table != 'usage_events' for table, _payload in db.inserted)


def test_register_preserves_control_revoked_guest_row_and_allowance(monkeypatch):
    guest = {
        **guest_user(4),
        'email': f'guest-{USER_ID}@guest.askcrump.local',
        'is_verified': False,
    }
    revoked_at = '2026-10-22T20:00:00+00:00'
    guest_session = {
        'id': 's-control-revoked',
        'user_id': guest['id'],
        'token_hash': token_hash(RAW_TOKEN),
        'revoked_at': revoked_at,
        'device_info': {'guestControlRevokedAt': revoked_at},
    }
    db = MultiUserDb([guest], {token_hash(RAW_TOKEN): guest_session})
    monkeypatch.setattr(auth_routes, 'db', db)

    async def sent(*_args, **_kwargs):
        return True

    monkeypatch.setattr(auth_routes.email_service, 'send_verification', sent)
    response = asyncio.run(auth_routes.register(
        RegisterRequest(
            email='person@example.com',
            password='Password123',
            fullName='Pat',
            termsAccepted=True,
            termsVersion='2026-08-01',
        ),
        flow_request(RAW_TOKEN),
    ))

    assert response['success'] is True
    user_updates = [item for item in db.updates if item[0] == 'users']
    assert len(user_updates) == 1
    assert user_updates[0][2]['id'] == f'eq.{guest["id"]}'
    assert user_updates[0][1]['email'] == 'person@example.com'
    assert all(table not in {'users', 'usage_events'} for table, _row in db.inserted)
    assert all(name != 'get_guest_mode_control_v1' for name, _payload in db.rpc_calls)


@pytest.mark.parametrize(
    'session',
    [
        {
            'id': 's-logout-revoked',
            'user_id': USER_ID,
            'token_hash': token_hash(RAW_TOKEN),
            'revoked_at': '2026-10-22T20:00:00+00:00',
            'device_info': {},
        },
        {
            'id': 's-mismatched-revocation',
            'user_id': USER_ID,
            'token_hash': token_hash(RAW_TOKEN),
            'revoked_at': '2026-10-22T20:00:01+00:00',
            'device_info': {
                'guestControlRevokedAt': '2026-10-22T20:00:00+00:00',
            },
        },
    ],
)
def test_registration_does_not_resurrect_other_revoked_guest_tokens(session):
    db = MultiUserDb([guest_user(4)], {token_hash(RAW_TOKEN): session})

    with pytest.raises(AuthenticationError):
        asyncio.run(authenticate_guest_for_registration(
            flow_request(RAW_TOKEN), db, SETTINGS,
        ))


class GuestPasswordResetDb:
    def __init__(self):
        self.user = {
            **guest_user(4),
            'email': 'person@example.com',
            'password_reset_token_hash': token_hash('reset-token-with-enough-entropy'),
            'password_reset_expires': '2099-01-01T00:00:00+00:00',
        }
        self.updates = []

    async def select_one(self, table, columns='*', filters=None):
        assert table == 'users'
        return dict(self.user)

    async def update(self, table, payload, filters=None, **kwargs):
        self.updates.append((table, payload, filters or {}))
        if table == 'users':
            self.user.update(payload)
        return [payload]


def test_password_reset_verification_clears_converted_guest_state(monkeypatch):
    db = GuestPasswordResetDb()
    monkeypatch.setattr(auth_routes, 'db', db)
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', AsyncMock(return_value=None))

    result = asyncio.run(auth_routes.reset_password(
        ResetPasswordRequest(token='reset-token-with-enough-entropy', newPassword='NewPassword123'),
        flow_request(),
    ))

    assert result['success'] is True
    user_update = next(payload for table, payload, _filters in db.updates if table == 'users')
    assert user_update['is_verified'] is True
    assert user_update['is_guest'] is False
    assert 'registration_submitted_at' not in user_update
    assert 'registration_environment' not in user_update
    assert db.user['is_guest'] is False
    assert any(table == 'sessions' for table, _payload, _filters in db.updates)


# --- Check-in worker fails closed for guests ---------------------------------

from backend.checkin_service import run_check_ins  # noqa: E402


class CheckinDb:
    def __init__(self, pref_row, user_row, chat_row):
        self.pref_row = pref_row
        self.user_row = user_row
        self.chat_row = chat_row
        self.updates = []

    async def select(self, table, columns='*', filters=None, order=None, limit=None):
        if table == 'check_in_preferences':
            return [self.pref_row]
        if table == 'user_chats':
            return [self.chat_row]
        return []

    async def select_one(self, table, columns='*', filters=None):
        if table == 'users':
            return self.user_row
        return None

    async def update(self, table, payload, filters=None, **kwargs):
        self.updates.append((table, payload, filters or {}))
        return [payload]


class NoGenerateAi:
    async def generate_check_in(self, **kwargs):
        raise AssertionError('guest check-in must never reach generation')


def test_check_in_worker_skips_and_disables_guest_enrollment():
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    pref_row = {
        'user_id': 'guest-1',
        'enabled': True,
        'frequency': 'balanced',
        'quiet_start': 0,
        'quiet_end': 0,
        'timezone': 'UTC',
        'allow_followups': True,
        'ignored_count': 0,
    }
    user_row = {'id': 'guest-1', 'email': 'guest-1@guest.askcrump.local', 'is_guest': True}
    chat_row = {
        'chat_id': 'c1',
        'title': 'Chat',
        'messages': [{'role': 'user', 'content': 'hi'}, {'role': 'assistant', 'content': 'hello'}],
        'updated_at': recent,
        'revision': 1,
        'deleted_at': None,
    }
    db = CheckinDb(pref_row, user_row, chat_row)
    summary = asyncio.run(run_check_ins(db, NoGenerateAi(), object(), batch_size=10))
    assert summary['sent'] == 0
    assert summary['skipped'] == 1
    assert any(
        table == 'check_in_preferences' and payload.get('enabled') is False
        for table, payload, _filters in db.updates
    )


# --- Client IP canonicalization + mint origin gate ---------------------------

from backend.security import client_ip, origin_allowed  # noqa: E402


def test_client_ip_prefers_vercel_forwarded_for_and_canonicalizes():
    headers = {
        'x-vercel-forwarded-for': ' 203.0.113.7 , 10.0.0.1',
        'x-forwarded-for': '198.51.100.9',
    }
    assert client_ip(headers) == '203.0.113.7'


def test_client_ip_falls_back_and_normalizes():
    assert client_ip({'x-forwarded-for': '203.0.113.7, 10.0.0.1'}) == '203.0.113.7'
    assert client_ip({'x-forwarded-for': 'not-an-ip', 'x-real-ip': '192.0.2.4'}) == '192.0.2.4'
    assert client_ip({'x-forwarded-for': '2001:0DB8:0000:0000:0000:ff00:0042:8329'}) == '2001:db8::ff00:42:8329'
    assert client_ip({}, '192.0.2.1') == '192.0.2.1'


def test_origin_allowed_matrix():
    allowed = ('https://askcrump.com', 'http://localhost:3000')
    same = {'host': 'askcrump.com', 'origin': 'https://askcrump.com'}
    assert origin_allowed(same, allowed) is True
    assert origin_allowed({'host': 'app.askcrump.com', 'origin': 'https://app.askcrump.com'}, allowed) is True
    assert origin_allowed({'host': 'askcrump.com', 'origin': 'https://evil.example'}, allowed) is False
    assert origin_allowed({'host': 'askcrump.com', 'sec-fetch-site': 'cross-site'}, allowed) is False
    assert origin_allowed({'host': 'askcrump.com', 'sec-fetch-site': 'same-origin', 'origin': 'https://askcrump.com'}, allowed) is True
    assert origin_allowed({'host': 'askcrump.com'}, allowed) is True  # non-browser client
    assert origin_allowed({'host': 'x', 'origin': 'https://askcrump.com'}, allowed) is True  # configured origin


def header_request(headers: dict):
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({
        'type': 'http',
        'method': 'POST',
        'path': '/api/auth/guest',
        'headers': raw,
        'query_string': b'',
        'client': ('203.0.113.7', 12345),
    })


def test_guest_mint_refuses_cross_site_origin(monkeypatch):
    db = GuestFlowDb()
    monkeypatch.setattr(auth_routes, 'db', db)
    response = asyncio.run(auth_routes.start_guest_session(
        header_request({'host': 'askcrump.com', 'origin': 'https://evil.example'}),
        StarletteResponse(),
    ))
    assert response.status_code == 403
    import json as _json
    assert _json.loads(response.body)['code'] == 'ORIGIN_NOT_ALLOWED'
    assert db.inserted == []  # nothing minted, no rate budget spent


def test_guest_identity_uses_same_site_session_and_bounded_ip_control_without_device_fingerprinting():
    controller = (Path(__file__).parents[1] / 'public' / 'auth-controller.js').read_text(encoding='utf-8')
    guest_bootstrap = controller.split('async function enterAsGuest()', 1)[1].split(
        'window.CrumpAccess =', 1
    )[0] if 'window.CrumpAccess =' in controller.split('async function enterAsGuest()', 1)[1] else controller.split(
        'async function enterAsGuest()', 1
    )[1].split('function focusAuthView', 1)[0]
    route = (Path(__file__).parents[1] / 'backend' / 'routes' / 'auth.py').read_text(encoding='utf-8')
    http = (Path(__file__).parents[1] / 'backend' / 'http.py').read_text(encoding='utf-8')
    fingerprint_doc = free_text_message_fingerprint.__doc__ or ''

    assert "authRequest(\n        '/api/auth/guest'" in guest_bootstrap
    assert 'window.deviceAuth.checkSession()' in guest_bootstrap
    for invasive_signal in (
        'canvas', 'webgl', 'audiocontext', 'navigator.plugins',
        'hardwareconcurrency', 'devicememory', 'document.fonts',
    ):
        assert invasive_signal not in guest_bootstrap.lower()
    assert 'origin_allowed' in route
    assert 'identity=ip' in route
    assert 'window_seconds=86400' in route
    assert 'httponly=True' in http
    assert 'samesite="lax"' in http
    assert 'not a device/browser fingerprint' in fingerprint_doc


# --- Guest sync bounds --------------------------------------------------------

from backend.sync_service import push_sync  # noqa: E402


class SyncDb:
    """Simulates the registered and all-in-one guest sync RPCs."""

    def __init__(
        self,
        stored_ids=(),
        stored_bytes=0,
        stored_sizes=None,
        settings_outcome='accepted',
    ):
        self.stored = list(stored_ids)
        self.stored_bytes = stored_bytes
        self.stored_sizes = dict(stored_sizes or {})
        self.settings_outcome = settings_outcome
        self.guest_apply_calls = []
        self.guest_settings_calls = []
        self.registered_apply_calls = []
        self.registered_settings_calls = []

    async def select(self, table, columns='*', filters=None, order=None, limit=None):
        raise AssertionError('push_sync must not perform a Python-side guest quota read')

    async def rpc(self, name, payload, retry_transient=False):
        if name == 'apply_guest_user_settings_v1':
            self.guest_settings_calls.append((payload, retry_transient))
            return [{
                'accepted': self.settings_outcome == 'accepted',
                'outcome': self.settings_outcome,
            }]

        if name == 'apply_guest_chat_sync_v2':
            self.guest_apply_calls.append(payload)
            chat_id = payload['p_chat_id']
            exists = chat_id in self.stored
            if payload['p_deleted_at'] and not exists:
                return [{'accepted': False, 'outcome': 'unknown_tombstone'}]

            prior_size = self.stored_sizes.get(chat_id, 0)
            candidate_size = len(
                json.dumps(payload['p_messages'], ensure_ascii=False).encode('utf-8')
            )
            next_count = len(self.stored) + (0 if exists else 1)
            next_total = self.stored_bytes - prior_size + candidate_size
            within_caps = (
                next_count <= 50
                and candidate_size <= 200_000
                and next_total <= 2_000_000
            )
            safe_reduction = (
                exists
                and candidate_size <= prior_size
                and next_total <= self.stored_bytes
                and (
                    payload['p_deleted_at'] is not None
                    or candidate_size < prior_size
                )
            )
            if not within_caps and not safe_reduction:
                return [{'accepted': False, 'outcome': 'quota_exceeded'}]
            if not exists:
                self.stored.append(chat_id)
            self.stored_bytes = next_total
            self.stored_sizes[chat_id] = candidate_size
            return [{'accepted': True, 'outcome': 'accepted'}]

        assert name == 'apply_chat_sync'
        self.registered_apply_calls.append(payload)
        return [{'accepted': True}]

    async def upsert(self, table, payload, on_conflict=None, retry_transient=False):
        self.registered_settings_calls.append(
            (table, payload, on_conflict, retry_transient)
        )
        return [payload]


def make_chat(index, content_chars=10):
    return {
        'id': f'chat-{index}',
        'title': 'Chat',
        'messages': [{'role': 'user', 'content': 'x' * content_chars, 'timestamp': '2026-10-20T12:00:00Z'}],
        'updated_at': '2026-10-20T12:00:00Z',
        'created_at': '2026-10-20T12:00:00Z',
        'revision': 1,
    }


def test_guest_sync_push_rejects_overflow_before_any_chat_or_tombstone_is_applied():
    db = SyncDb()
    payload = {
        'chats': [make_chat(i) for i in range(25)],
        'deletedChats': [{'id': f'deleted-{i}'} for i in range(21)],
        'settings': {'assistant_name': 'Must not partially save'},
    }
    result = asyncio.run(push_sync(db, 'guest-1', payload, is_guest=True))
    assert result['accepted'] == []
    assert result['ignored'] == []
    assert result['rejected'] == []
    assert result['rejectionCode'] == 'GUEST_SYNC_BATCH_TOO_LARGE'
    assert result['limits'] == {'chats': 20, 'deletedChats': 20}
    assert result['received'] == {'chats': 25, 'deletedChats': 21}
    assert db.guest_apply_calls == []
    assert db.guest_settings_calls == []
    assert db.registered_apply_calls == []


def test_guest_settings_only_push_keeps_request_authority_in_locked_rpc():
    db = SyncDb()

    result = asyncio.run(push_sync(db, 'guest-1', {
        'settings': {
            'assistant_name': 'Echo',
            'work_mode': True,
            'unknown': 'discard me',
        },
    }, is_guest=True))

    assert result == {'accepted': [], 'ignored': []}
    assert len(db.guest_settings_calls) == 1
    payload, retry_transient = db.guest_settings_calls[0]
    assert payload['p_user_id'] == 'guest-1'
    assert payload['p_settings'] == {
        'assistant_name': 'Echo',
        'work_mode': True,
    }
    assert payload['p_updated_at']
    assert retry_transient is True
    assert db.registered_settings_calls == []


def test_stale_guest_settings_only_push_cannot_fall_through_as_registered_write():
    db = SyncDb(settings_outcome='not_guest')

    result = asyncio.run(push_sync(db, 'guest-1', {
        'settings': {'assistant_name': 'Must not persist after verification'},
    }, is_guest=True))

    assert result['accepted'] == []
    assert result['ignored'] == []
    assert result['rejected'] == [{
        'scope': 'settings',
        'reason': 'not_guest',
    }]
    assert len(db.guest_settings_calls) == 1
    assert db.registered_settings_calls == []


def test_registered_sync_push_keeps_general_limits():
    db = SyncDb()
    payload = {'chats': [make_chat(i) for i in range(25)]}
    result = asyncio.run(push_sync(db, 'user-1', payload))
    assert len(result['accepted']) == 25
    assert len(db.registered_apply_calls) == 25
    assert db.guest_apply_calls == []


def test_guest_sync_push_rejects_oversized_chat():
    db = SyncDb()
    big = make_chat(1, content_chars=90_000)
    big['messages'] = [
        {'role': 'user', 'content': 'x' * 90_000, 'timestamp': '2026-10-20T12:00:00Z'},
        {'role': 'assistant', 'content': 'y' * 90_000, 'timestamp': '2026-10-20T12:01:00Z'},
        {'role': 'user', 'content': 'z' * 90_000, 'timestamp': '2026-10-20T12:02:00Z'},
    ]
    result = asyncio.run(push_sync(db, 'guest-1', {'chats': [big]}, is_guest=True))
    assert result['accepted'] == []
    assert result['ignored'] == []
    assert len(result['rejected']) == 1
    assert result['rejected'][0]['reason'] == 'quota_exceeded'
    assert len(db.guest_apply_calls) == 1
    assert db.registered_apply_calls == []


def test_guest_sync_push_bounds_stored_conversations_but_allows_updates():
    from backend.security import normalize_chat_id
    db = SyncDb(stored_ids=[normalize_chat_id(f'chat-{i}') for i in range(50)])
    update = make_chat(0)          # already stored: always allowed
    new_chat = make_chat(999)      # would exceed the stored ceiling
    result = asyncio.run(push_sync(db, 'guest-1', {'chats': [update, new_chat]}, is_guest=True))
    assert len(result['accepted']) == 1
    assert result['ignored'] == []
    assert len(result['rejected']) == 1
    assert result['rejected'][0]['reason'] == 'quota_exceeded'


def test_guest_sync_push_bounds_stored_bytes():
    from backend.security import normalize_chat_id
    db = SyncDb(stored_ids=[normalize_chat_id('chat-0')], stored_bytes=1_999_999)
    new_chat = make_chat(7, content_chars=100)
    result = asyncio.run(push_sync(db, 'guest-1', {'chats': [new_chat]}, is_guest=True))
    assert result['accepted'] == []
    assert result['ignored'] == []
    assert len(result['rejected']) == 1
    assert result['rejected'][0]['reason'] == 'quota_exceeded'


def test_guest_sync_tombstone_only_for_stored_conversations():
    from backend.security import normalize_chat_id
    db = SyncDb(stored_ids=[normalize_chat_id('chat-0')])
    payload = {
        'chats': [],
        'deletedChats': [
            {'id': 'chat-0', 'deleted_at': '2026-10-20T13:00:00Z', 'revision': 2},
            {'id': 'chat-unknown', 'deleted_at': '2026-10-20T13:00:00Z', 'revision': 2},
        ],
    }
    result = asyncio.run(push_sync(db, 'guest-1', payload, is_guest=True))
    assert len(result['accepted']) == 1
    assert len(result['ignored']) == 1
    assert len(db.stored) == 1
    assert len(db.guest_apply_calls) == 2


def test_guest_sync_known_tombstone_can_shrink_legacy_oversized_state():
    from backend.security import normalize_chat_id
    chat_id = normalize_chat_id('chat-0')
    db = SyncDb(
        stored_ids=[chat_id],
        stored_bytes=2_100_000,
        stored_sizes={chat_id: 2_100_000},
    )
    payload = {
        'deletedChats': [{
            'id': 'chat-0',
            'deleted_at': '2026-10-20T13:00:00Z',
            'revision': 2,
        }],
    }

    result = asyncio.run(push_sync(db, 'guest-1', payload, is_guest=True))

    assert result['accepted'] == [chat_id]
    assert result['ignored'] == []
    assert db.stored_bytes < 2_100_000
