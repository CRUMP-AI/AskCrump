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
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from backend.auth_service import (
    GUEST_MESSAGE_LIMIT,
    AuthenticationError,
    authenticate_request,
    guest_limit_reached,
    is_guest_user,
    public_user,
)
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

    def __init__(self, user):
        self.user = user
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
    assert payload['guestMessagesUsed'] == 3
    assert payload['guestMessageLimit'] == GUEST_MESSAGE_LIMIT == 5

    payload = public_user(full_user())
    assert payload['isGuest'] is False
    assert payload['guestMessagesUsed'] == 0


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


def test_wrong_token_is_unauthorized_even_for_accounts():
    db = FakeDb(full_user())
    with pytest.raises(AuthenticationError) as excinfo:
        asyncio.run(authenticate_request(
            make_request('some-other-token'), db, SETTINGS, touch=False,
        ))
    assert excinfo.value.status_code == 401


# --- Allowance reservation (compare-and-swap) -------------------------------

from backend.auth_service import reserve_guest_message  # noqa: E402


class CasDb:
    """In-memory users row with PostgREST-style conditional PATCH semantics."""

    def __init__(self, count, *, steal_first_race=False):
        self.count = count
        self.steal_first_race = steal_first_race
        self.update_calls = 0

    async def select_one(self, table, columns='*', filters=None):
        assert table == 'users'
        return {'guest_message_count': self.count}

    async def update(self, table, payload, *, filters):
        assert table == 'users'
        self.update_calls += 1
        expected = int(str(filters['guest_message_count']).removeprefix('eq.'))
        if self.steal_first_race and self.update_calls == 1:
            # A concurrent request consumed the slot between read and PATCH.
            self.count = GUEST_MESSAGE_LIMIT
            return []
        if self.count != expected:
            return []
        self.count = payload['guest_message_count']
        return [{'guest_message_count': self.count}]


def test_reserve_consumes_a_slot_below_the_cap():
    db = CasDb(4)
    assert asyncio.run(reserve_guest_message(db, guest_user(4))) is True
    assert db.count == 5


def test_reserve_refuses_at_the_cap_without_writing():
    db = CasDb(5)
    assert asyncio.run(reserve_guest_message(db, guest_user(5))) is False
    assert db.count == 5
    assert db.update_calls == 0


def test_reserve_loses_a_race_at_the_cap_cleanly():
    db = CasDb(4, steal_first_race=True)
    assert asyncio.run(reserve_guest_message(db, guest_user(4))) is False
    assert db.count == 5


def test_reserve_always_passes_for_full_accounts():
    db = CasDb(0)
    assert asyncio.run(reserve_guest_message(db, full_user())) is True
    assert db.update_calls == 0


# --- Guest capability allowlist (direct signals) ----------------------------

from backend.auth_service import guest_blocked_signal  # noqa: E402


@pytest.mark.parametrize('payload,image_requested,expected', [
    ({'message': 'What is the capital of France?'}, False, None),
    ({'message': 'Explain recursion like I am five'}, False, None),
    ({'message': 'hi', 'fileRefs': [{'id': 'f1'}]}, False, 'file attachments'),
    ({'message': 'hi', 'history': [{'role': 'user', 'fileRefs': ['f9']}]}, False, 'file attachments'),
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

class ReceiptDb(CasDb):
    """In-memory stand-in for the reserve_guest_message Postgres function."""

    def __init__(self, count, *, rpc_down=False):
        super().__init__(count)
        self.receipts = set()
        self.rpc_down = rpc_down

    async def rpc(self, name, payload):
        assert name == 'reserve_guest_message'
        if self.rpc_down:
            from backend.db import DatabaseError
            raise DatabaseError('function unavailable')
        message_id = payload['p_message_id']
        if message_id in self.receipts:
            return 'reused'
        if self.count >= GUEST_MESSAGE_LIMIT:
            return 'exhausted'
        self.receipts.add(message_id)
        self.count += 1
        return 'reserved'


def test_receipt_failed_send_retry_reuses_its_reservation():
    # Polka's reclaimed-retry fixture: 3 -> 4 on the accepted send, and a
    # retry of the SAME message after failure must stay at 4.
    db = ReceiptDb(3)
    user = guest_user(3)
    assert asyncio.run(reserve_guest_message(db, user, message_id='m-1')) is True
    assert db.count == 4
    assert asyncio.run(reserve_guest_message(db, user, message_id='m-1')) is True
    assert db.count == 4


def test_receipt_cap_message_retry_is_not_refused():
    db = ReceiptDb(4)
    user = guest_user(4)
    assert asyncio.run(reserve_guest_message(db, user, message_id='m-5')) is True
    assert db.count == 5
    # Retrying the fifth (already accepted) message reuses its receipt...
    assert asyncio.run(reserve_guest_message(db, user, message_id='m-5')) is True
    assert db.count == 5
    # ...while a genuinely new sixth message is refused.
    assert asyncio.run(reserve_guest_message(db, user, message_id='m-6')) is False
    assert db.count == 5


def test_receipt_rpc_unavailable_fails_closed_for_identified_messages():
    db = ReceiptDb(0, rpc_down=True)
    with pytest.raises(Exception):
        asyncio.run(reserve_guest_message(db, guest_user(0), message_id='m-1'))
    assert db.count == 0


# --- Guest creation stores an unusable password sentinel --------------------

import backend.routes.auth as auth_routes  # noqa: E402
from backend.security import verify_password  # noqa: E402
from starlette.responses import Response as StarletteResponse  # noqa: E402


class GuestFlowDb(FakeDb):
    def __init__(self):
        super().__init__(None)
        self.inserted = []

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


# --- Pending-signup collision: guest + someone else's unverified row --------

from backend.schemas import RegisterRequest  # noqa: E402


class MultiUserDb:
    def __init__(self, users, sessions):
        self.users = {u['id']: u for u in users}
        self.sessions = sessions
        self.updates = []
        self.inserted = []

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
