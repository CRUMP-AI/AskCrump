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
