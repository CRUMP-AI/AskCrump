from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app as app_module
from backend.routes import chat as chat_routes
from backend.routes import presence as presence_routes
from backend.checkin_service import allowed_categories, in_quiet_hours, sanitize_preferences


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
