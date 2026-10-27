from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import asyncio

from fastapi.testclient import TestClient

import app as app_module
from backend.routes import chat as chat_routes
from backend.routes import presence as presence_routes
from backend.checkin_service import allowed_categories, in_quiet_hours, run_check_ins, sanitize_preferences
from backend.policy_consent import CURRENT_POLICY_BUNDLE_HASH, CURRENT_POLICY_BUNDLE_ID


client = TestClient(app_module.app)


class ReceiptDB:
    def __init__(self):
        self.upserts = []

    async def upsert(self, table, payload, *, on_conflict):
        self.upserts.append((table, payload, on_conflict))
        return [payload]


def test_preferences_are_opt_in_and_sanitized():
    preferences = sanitize_preferences({
        'enabled': False,
        'frequency': 'constant',
        'quiet_start': 99,
        'quiet_end': -4,
        'timezone': 'Not/AZone',
        'allow_encouragement': True,
    })
    assert preferences['enabled'] is False
    assert preferences['frequency'] == 'balanced'
    assert preferences['quiet_start'] == 23
    assert preferences['quiet_end'] == 0
    assert preferences['timezone'] == 'America/New_York'
    assert preferences['allow_encouragement'] is True


def test_quiet_hours_cross_midnight():
    preferences = sanitize_preferences({
        'quiet_start': 21,
        'quiet_end': 8,
        'timezone': 'UTC',
    })
    assert in_quiet_hours(preferences, datetime(2026, 8, 1, 23, tzinfo=timezone.utc)) is True
    assert in_quiet_hours(preferences, datetime(2026, 8, 1, 12, tzinfo=timezone.utc)) is False


def test_chat_ack_records_seen_receipt_and_activity(monkeypatch):
    fake_db = ReceiptDB()

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'user-1'}, session={'id': 'session-1'}, token='token')

    monkeypatch.setattr(chat_routes, 'db', fake_db)
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)

    response = client.post('/api/chat/ack', json={
        'chatId': '2db25736-ad99-4c66-9022-985455f9e4f4',
        'messageId': '18ace47c-720e-484a-903e-59ffdf26a141',
        'message': 'Please search the web for the latest update',
        'fileTypes': [],
    })
    assert response.status_code == 200
    body = response.json()
    assert body['activity'] == 'searching'
    table, payload, conflict = fake_db.upserts[0]
    assert table == 'message_receipts'
    assert payload['seen_at']
    assert payload['delivered_at']
    assert conflict == 'user_id,message_id'


def test_check_in_cron_requires_secret(monkeypatch):
    monkeypatch.setattr(presence_routes, 'settings', replace(presence_routes.settings, cron_secret='unit-test-secret'))
    assert client.get('/api/cron/check-ins').status_code == 401
    assert client.get('/api/cron/check-ins', headers={'Authorization': 'Bearer wrong'}).status_code == 401


def test_check_in_categories_can_be_fully_disabled():
    preferences = sanitize_preferences({
        'allow_followups': False,
        'allow_reminders': False,
        'allow_goals': False,
        'allow_encouragement': False,
    })
    assert allowed_categories(preferences) == []


def test_check_in_request_avoids_unsupported_sampling_parameters():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'backend' / 'ai_service.py').read_text()
    section = source.split('async def generate_check_in', 1)[1]
    assert "'temperature'" not in section
    assert "'max_tokens': 1024" in section


class PolicyCheckInDB:
    def __init__(self, receipt: str):
        self.receipt = receipt
        self.calls = []
        self.updates = []
        self.inserts = []

    async def select(self, table, columns='*', filters=None, order=None, limit=None):
        self.calls.append(('select', table))
        if table == 'check_in_preferences':
            return [{
                'user_id': 'registered-1',
                'enabled': True,
                'frequency': 'balanced',
                'quiet_start': 0,
                'quiet_end': 0,
                'timezone': 'UTC',
                'allow_followups': True,
                'allow_reminders': False,
                'allow_goals': False,
                'allow_encouragement': False,
                'notifications_enabled': False,
                'ignored_count': 0,
            }]
        if table == 'check_in_events':
            return []
        if table == 'user_chats':
            return [{
                'chat_id': 'chat-1',
                'title': 'Private chat',
                'messages': [
                    {'role': 'user', 'content': 'private prompt'},
                    {'role': 'assistant', 'content': 'private answer'},
                ],
                'updated_at': '2026-10-25T12:00:00+00:00',
                'revision': 1,
                'deleted_at': None,
            }]
        raise AssertionError(f'unexpected select {table}')

    async def select_one(self, table, columns='*', filters=None):
        self.calls.append(('select_one', table))
        if table == 'users':
            return {
                'id': 'registered-1',
                'email': 'registered@example.test',
                'full_name': 'Registered',
                'is_guest': False,
                'subscription_tier': 'free',
                'subscription_status': 'inactive',
            }
        if table == 'user_settings':
            return {'assistant_name': 'Crump'}
        if table == 'check_in_events':
            return None
        raise AssertionError(f'unexpected select_one {table}')

    async def rpc(self, name, payload, **_kwargs):
        self.calls.append(('rpc', name))
        if name == 'read_current_policy_acceptance_v1':
            if self.receipt == 'missing':
                return []
            if self.receipt == 'stale':
                return [{
                    'bundle_id': 'ask-crump-legal-stale',
                    'bundle_hash': '0' * 64,
                }]
            return [{
                'bundle_id': CURRENT_POLICY_BUNDLE_ID,
                'bundle_hash': CURRENT_POLICY_BUNDLE_HASH,
            }]
        if name == 'append_check_in_message':
            return [{'appended': True}]
        raise AssertionError(f'unexpected rpc {name}')

    async def update(self, table, payload, filters=None, **_kwargs):
        self.updates.append((table, dict(payload), dict(filters or {})))
        return [payload]

    async def insert(self, table, payload):
        self.inserts.append((table, dict(payload)))
        return [payload]


class PolicyCheckInAI:
    def __init__(self):
        self.calls = []

    async def generate_check_in(self, **kwargs):
        self.calls.append(kwargs)
        return 'A private generated follow-up.'


class NoCheckInPush:
    async def send_user(self, *_args, **_kwargs):
        raise AssertionError('push must remain disabled in this fixture')


def test_check_in_worker_requires_exact_current_policy_before_chat_or_provider_work():
    for receipt in ('missing', 'stale'):
        database = PolicyCheckInDB(receipt)
        ai = PolicyCheckInAI()

        summary = asyncio.run(
            run_check_ins(database, ai, NoCheckInPush(), batch_size=10)
        )

        assert summary['policyRequired'] == 1
        assert summary['sent'] == 0
        assert ai.calls == []
        assert database.inserts == []
        assert ('select', 'user_chats') not in database.calls
        assert ('select_one', 'users') not in database.calls
        assert ('rpc', 'append_check_in_message') not in database.calls
        assert len(database.updates) == 1
        table, changes, _filters = database.updates[0]
        assert table == 'check_in_preferences'
        assert set(changes) == {'next_eligible_at', 'updated_at'}


def test_check_in_worker_current_policy_allows_generation_path():
    database = PolicyCheckInDB('current')
    ai = PolicyCheckInAI()

    summary = asyncio.run(
        run_check_ins(database, ai, NoCheckInPush(), batch_size=10)
    )

    assert summary['policyRequired'] == 0
    assert summary['sent'] == 1
    assert len(ai.calls) == 1
    assert ai.calls[0]['conversation'][0]['content'] == 'private prompt'
    assert ('select', 'user_chats') in database.calls
    assert ('rpc', 'append_check_in_message') in database.calls
    assert database.inserts[0][0] == 'check_in_events'
