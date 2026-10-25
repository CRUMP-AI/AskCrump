"""Focused contracts for the guest-only shared-network message budget."""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import app as app_module
from backend.auth_service import (
    AuthenticationError,
    guest_network_limit_response,
    public_daily_usage,
    reserve_free_text_message,
)
from backend.rate_limit import guest_network_message_key_hash
from backend.routes import chat as chat_routes
from backend.routes import presence as presence_routes
from backend.runtime import settings as runtime_settings
from backend.usage_service import refund_usage


SECRET = 'network-budget-test-secret-' + ('x' * 32)
USER_ID = '81111111-1111-4111-8111-111111111111'
CHAT_ID = '82222222-2222-4222-8222-222222222222'
MESSAGE_ID = '83333333-3333-4333-8333-333333333333'
ROOT = Path(__file__).resolve().parents[1]


def request_for(ip: str | None) -> Request:
    headers = [] if ip is None else [(b'x-forwarded-for', ip.encode('ascii'))]
    return Request({
        'type': 'http',
        'method': 'POST',
        'path': '/api/chat',
        'headers': headers,
        'query_string': b'',
        'client': None,
    })


def free_user(*, guest: bool) -> dict:
    return {
        'id': USER_ID,
        'email': 'guest@example.test' if guest else 'person@example.test',
        'is_guest': guest,
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }


def test_network_hmac_uses_ipv4_32_ipv6_64_and_a_dedicated_key():
    ipv4 = guest_network_message_key_hash(request_for('203.0.113.7'), SECRET)
    assert ipv4 == guest_network_message_key_hash(request_for('203.0.113.7'), SECRET)
    assert ipv4 == guest_network_message_key_hash(request_for('::ffff:203.0.113.7'), SECRET)
    assert ipv4 != guest_network_message_key_hash(request_for('203.0.113.8'), SECRET)

    ipv6_a = guest_network_message_key_hash(request_for('2001:db8:abcd:42::1'), SECRET)
    ipv6_b = guest_network_message_key_hash(request_for('2001:db8:abcd:42:ffff::9'), SECRET)
    ipv6_next = guest_network_message_key_hash(request_for('2001:db8:abcd:43::1'), SECRET)
    assert ipv6_a == ipv6_b
    assert ipv6_a != ipv6_next
    assert ipv6_a != guest_network_message_key_hash(
        request_for('2001:db8:abcd:42::1'),
        'different-network-secret-' + ('y' * 32),
    )
    assert len(ipv4 or '') == 64
    assert '203.0.113.7' not in str(ipv4)


@pytest.mark.parametrize('request_obj,key', [(request_for(None), SECRET), (request_for('bad'), SECRET), (request_for('203.0.113.7'), None), (request_for('203.0.113.7'), 'short')])
def test_network_hmac_fails_closed_without_a_valid_address_and_strong_key(request_obj, key):
    assert guest_network_message_key_hash(request_obj, key) is None


class ReservationDb:
    def __init__(self, row: dict):
        self.row = row
        self.calls = []

    async def rpc(self, name, payload, retry_transient=False):
        self.calls.append((name, dict(payload), retry_transient))
        return [dict(self.row)]


def test_guest_network_exhaustion_is_a_distinct_v2_result():
    boundary = (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()
    database = ReservationDb({
        'outcome': 'network_exhausted',
        'event_id': None,
        'used': 2,
        'remaining': 3,
        'next_available_at': None,
        'network_used': 25,
        'network_remaining': 0,
        'network_next_available_at': boundary,
    })
    result = asyncio.run(reserve_free_text_message(
        database,
        free_user(guest=True),
        message_id=MESSAGE_ID,
        fingerprint='a' * 64,
        network_key_hash='b' * 64,
    ))
    assert result['allowed'] is False
    assert result['networkLimited'] is True
    assert result['eventId'] is None
    assert result['networkNextAvailableAt'] == boundary
    name, payload, retry_transient = database.calls[0]
    assert name == 'reserve_free_message_v2'
    assert payload['p_network_key_hash'] == 'b' * 64
    assert retry_transient is True


def test_registered_free_bypasses_network_input_but_still_uses_v2_account_budget():
    database = ReservationDb({
        'outcome': 'reserved',
        'event_id': '84444444-4444-4444-8444-444444444444',
        'used': 1,
        'remaining': 4,
        'next_available_at': None,
        'network_used': None,
        'network_remaining': None,
        'network_next_available_at': None,
    })
    result = asyncio.run(reserve_free_text_message(
        database,
        free_user(guest=False),
        message_id=MESSAGE_ID,
        fingerprint='c' * 64,
    ))
    assert result['allowed'] is True
    assert result['networkLimit'] is None
    assert database.calls[0][1]['p_network_key_hash'] is None


@pytest.mark.parametrize('rpc_result', [[{'refunded': True}], {'refunded': True}])
def test_usage_refund_requires_the_service_only_atomic_rpc(rpc_result):
    class RefundDb:
        def __init__(self):
            self.calls = []

        async def rpc(self, name, payload, **_kwargs):
            self.calls.append((name, dict(payload)))
            return rpc_result

        async def delete(self, *_args, **_kwargs):
            raise AssertionError('Usage refunds must not directly delete the parent row.')

    database = RefundDb()
    event_id = '84444444-4444-4444-8444-444444444444'
    asyncio.run(refund_usage(database, USER_ID, event_id))
    assert database.calls == [(
        'refund_usage_event_v2',
        {'p_user_id': USER_ID, 'p_event_id': event_id},
    )]


def test_usage_refund_fails_closed_without_explicit_confirmation():
    database = ReservationDb({'refunded': False})
    with pytest.raises(RuntimeError, match='not confirmed'):
        asyncio.run(refund_usage(
            database,
            USER_ID,
            '84444444-4444-4444-8444-444444444444',
        ))


@pytest.mark.parametrize('outcome', ['reserved', 'reused'])
def test_successful_guest_usage_never_exposes_shared_network_occupancy(outcome):
    database = ReservationDb({
        'outcome': outcome,
        'event_id': '84444444-4444-4444-8444-444444444444',
        'used': 1,
        'remaining': 4,
        'next_available_at': None,
        'network_used': 17,
        'network_remaining': 8,
        'network_next_available_at': '2026-10-25T02:00:00+00:00',
    })
    internal = asyncio.run(reserve_free_text_message(
        database,
        free_user(guest=True),
        message_id=MESSAGE_ID,
        fingerprint='c' * 64,
        network_key_hash='d' * 64,
    ))

    public = public_daily_usage(internal)

    assert public['allowed'] is True
    assert public['freeMessageAllowance']['remaining'] == 4
    assert not any(key.startswith('network') for key in public)


def test_cached_chat_response_scrubs_private_network_usage_defensively():
    cached = chat_routes._public_chat_response({
        'response': 'Hello',
        'dailyUsage': {
            'used': 1,
            'remaining': 4,
            'networkLimited': False,
            'networkUsed': 17,
            'networkLimit': 25,
            'networkRemaining': 8,
            'networkNextAvailableAt': '2026-10-25T02:00:00+00:00',
        },
    })

    assert cached == {
        'response': 'Hello',
        'dailyUsage': {'used': 1, 'remaining': 4},
    }


def test_chat_persists_and_returns_only_public_daily_usage():
    source = (ROOT / 'backend' / 'routes' / 'chat.py').read_text(encoding='utf-8')
    persistence = source.index("'response_data': result")
    assert source.index('daily_usage = public_daily_usage(usage)') < persistence
    assert source.index("result['dailyUsage'] = daily_usage") < persistence
    assert "return {'success': True, **result, 'dailyUsage': usage}" not in source
    assert "**claim['response_data']" not in source


def test_guest_missing_network_hash_fails_closed_before_rpc():
    database = ReservationDb({})
    with pytest.raises(AuthenticationError) as excinfo:
        asyncio.run(reserve_free_text_message(
            database,
            free_user(guest=True),
            message_id=MESSAGE_ID,
            fingerprint='d' * 64,
        ))
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == 'GUEST_NETWORK_BUDGET_UNAVAILABLE'
    assert database.calls == []


def test_network_limit_response_is_neutral_coarse_and_manual():
    boundary = (datetime.now(timezone.utc) + timedelta(seconds=90)).isoformat()
    response = guest_network_limit_response({'networkNextAvailableAt': boundary})
    body = json.loads(response.body)
    assert response.status_code == 429
    assert int(response.headers['Retry-After']) == 300
    assert body['code'] == 'GUEST_NETWORK_LIMIT_REACHED'
    assert body['accountRequired'] is True
    assert body['shouldRetry'] is False
    assert body['retryAfter'] == 300
    assert 'networkNextAvailableAt' not in body
    assert 'Sign in to an existing account or create and verify one' in body['message']
    assert 'you have used' not in body['message'].lower()


def test_network_denial_releases_claim_before_files_or_provider_work(monkeypatch):
    boundary = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()

    class GateDb:
        def __init__(self):
            self.calls = []

        async def rpc(self, name, payload, **_kwargs):
            self.calls.append((name, dict(payload)))
            if name == 'claim_chat_job_v2':
                return [{
                    'job_state': 'claimed',
                    'claim_token': '85555555-5555-4555-8555-555555555555',
                }]
            if name == 'reserve_free_message_v2':
                return [{
                    'outcome': 'network_exhausted',
                    'event_id': None,
                    'used': 1,
                    'remaining': 4,
                    'next_available_at': None,
                    'network_used': 25,
                    'network_remaining': 0,
                    'network_next_available_at': boundary,
                }]
            if name == 'release_chat_job_claim':
                assert payload['p_error_code'] == 'GUEST_NETWORK_LIMIT_REACHED'
                return True
            raise AssertionError(f'Unexpected RPC after network denial: {name}')

        async def select_one(self, table, **_kwargs):
            assert table == 'user_chats'
            return None

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=free_user(guest=True), session={'id': 's1'}, token='t1')

    database = GateDb()
    file_resolver = AsyncMock(side_effect=AssertionError('Files must not resolve.'))
    provider = AsyncMock(side_effect=AssertionError('Provider must not run.'))
    monkeypatch.setattr(chat_routes, 'db', database)
    monkeypatch.setattr(chat_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(chat_routes, 'settings', SimpleNamespace(guest_network_hash_key=SECRET))
    monkeypatch.setattr(chat_routes, 'features', SimpleNamespace(entitled=lambda *_args: False))
    monkeypatch.setattr(chat_routes, 'media', SimpleNamespace(is_image_request=lambda *_args: False))
    monkeypatch.setattr(chat_routes, 'files', SimpleNamespace(resolve_many=file_resolver))
    monkeypatch.setattr(chat_routes, 'ai', SimpleNamespace(chat=provider))

    response = TestClient(app_module.app).post(
        '/api/chat',
        headers={'x-forwarded-for': '203.0.113.7'},
        json={
            'chatId': CHAT_ID,
            'messageId': MESSAGE_ID,
            'message': 'Hello from guest chat.',
        },
    )
    assert response.status_code == 429
    assert response.json()['code'] == 'GUEST_NETWORK_LIMIT_REACHED'
    assert [name for name, _payload in database.calls] == [
        'claim_chat_job_v2',
        'reserve_free_message_v2',
        'release_chat_job_claim',
    ]
    file_resolver.assert_not_awaited()
    provider.assert_not_awaited()


def test_network_denial_fails_closed_when_claim_release_is_unconfirmed(monkeypatch):
    boundary = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()

    class GateDb:
        def __init__(self):
            self.calls = []

        async def rpc(self, name, payload, **_kwargs):
            self.calls.append((name, dict(payload)))
            if name == 'claim_chat_job_v2':
                return [{
                    'job_state': 'claimed',
                    'claim_token': '85555555-5555-4555-8555-555555555555',
                }]
            if name == 'reserve_free_message_v2':
                return [{
                    'outcome': 'network_exhausted',
                    'event_id': None,
                    'used': 1,
                    'remaining': 4,
                    'next_available_at': None,
                    'network_used': 25,
                    'network_remaining': 0,
                    'network_next_available_at': boundary,
                }]
            if name == 'release_chat_job_claim':
                assert payload['p_error_code'] == 'GUEST_NETWORK_LIMIT_REACHED'
                return False
            raise AssertionError(f'Unexpected RPC after network denial: {name}')

        async def select_one(self, table, **_kwargs):
            assert table == 'user_chats'
            return None

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=free_user(guest=True), session={'id': 's1'}, token='t1')

    database = GateDb()
    file_resolver = AsyncMock(side_effect=AssertionError('Files must not resolve.'))
    provider = AsyncMock(side_effect=AssertionError('Provider must not run.'))
    monkeypatch.setattr(chat_routes, 'db', database)
    monkeypatch.setattr(chat_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(chat_routes, 'settings', SimpleNamespace(guest_network_hash_key=SECRET))
    monkeypatch.setattr(chat_routes, 'features', SimpleNamespace(entitled=lambda *_args: False))
    monkeypatch.setattr(chat_routes, 'media', SimpleNamespace(is_image_request=lambda *_args: False))
    monkeypatch.setattr(chat_routes, 'files', SimpleNamespace(resolve_many=file_resolver))
    monkeypatch.setattr(chat_routes, 'ai', SimpleNamespace(chat=provider))

    response = TestClient(app_module.app).post(
        '/api/chat',
        headers={'x-forwarded-for': '203.0.113.7'},
        json={
            'chatId': CHAT_ID,
            'messageId': MESSAGE_ID,
            'message': 'Hello from guest chat.',
        },
    )
    assert response.status_code == 503
    assert response.json() == {
        'success': False,
        'error': 'Crump could not safely release this reply after guest access was limited.',
        'message': 'Wait before retrying this same message, or send it again as a new message.',
        'code': 'REPLY_CLAIM_RELEASE_UNCONFIRMED',
        'shouldRetry': False,
    }
    assert [name for name, _payload in database.calls] == [
        'claim_chat_job_v2',
        'reserve_free_message_v2',
        'release_chat_job_claim',
    ]
    file_resolver.assert_not_awaited()
    provider.assert_not_awaited()


def test_config_requires_hosted_key_but_allows_unconfigured_development():
    replace(
        runtime_settings,
        environment='development',
        guest_network_hash_key=None,
    ).validate_required()
    with pytest.raises(RuntimeError, match='GUEST_NETWORK_HASH_KEY'):
        replace(
            runtime_settings,
            environment='preview',
            guest_network_hash_key=None,
        ).validate_required()
    with pytest.raises(RuntimeError, match='GUEST_NETWORK_HASH_KEY'):
        replace(runtime_settings, guest_network_hash_key='too-short').validate_required()
    with pytest.raises(RuntimeError, match='documented placeholder'):
        replace(
            runtime_settings,
            guest_network_hash_key='REPLACE_WITH_AT_LEAST_32_RANDOM_BYTES',
        ).validate_required()


def test_hourly_cron_runs_private_retention_sweep_before_check_ins(monkeypatch):
    class CronDb:
        def __init__(self):
            self.calls = []

        async def rpc(self, name, payload, retry_transient=False):
            self.calls.append((name, payload, retry_transient))
            return [{'deleted_count': 3, 'has_more': False}]

    database = CronDb()

    async def check_ins(*_args, **_kwargs):
        assert database.calls
        return {'processed': 0}

    monkeypatch.setattr(presence_routes, 'db', database)
    monkeypatch.setattr(presence_routes, 'run_check_ins', check_ins)
    monkeypatch.setattr(
        presence_routes,
        'settings',
        replace(runtime_settings, cron_secret='retention-test-secret'),
    )
    response = TestClient(app_module.app).get(
        '/api/cron/check-ins',
        headers={'Authorization': 'Bearer retention-test-secret'},
    )
    assert response.status_code == 200
    assert database.calls == [
        ('purge_guest_network_message_events_v1', {}, True),
    ]


def test_frontend_opens_neutral_account_recovery_for_network_denial():
    controller = (ROOT / 'public' / 'auth-controller.js').read_text(encoding='utf-8')
    branch = controller.split("code === 'GUEST_NETWORK_LIMIT_REACHED'", 1)[1].split(
        "code === 'FREE_TEXT_LIMIT_REACHED'", 1
    )[0]
    assert "showAuth('register')" in branch
    assert 'Sign in to an existing account or create and verify one' in branch
    assert 'another five' not in branch
