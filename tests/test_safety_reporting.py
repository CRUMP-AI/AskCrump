from types import SimpleNamespace

from fastapi.testclient import TestClient

import app as app_module
from backend.routes import safety as safety_routes


client = TestClient(app_module.app)


class SafetyDB:
    def __init__(self):
        self.inserted = None

    async def select_one(self, table, **_kwargs):
        assert table == 'user_chats'
        return {
            'messages': [
                {'id': 'prompt-1', 'role': 'user', 'content': 'Previous user context'},
                {'id': 'answer-1', 'role': 'assistant', 'content': 'Server-owned answer'},
            ]
        }

    async def insert(self, table, payload):
        assert table == 'ai_content_reports'
        self.inserted = dict(payload)
        return [dict(payload)]


def test_report_uses_authenticated_server_context(monkeypatch):
    fake_db = SafetyDB()

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'user-1'}, session={'id': 'session-1'}, token='token')

    async def allow_report(*_args, **_kwargs):
        return None

    monkeypatch.setattr(safety_routes, 'db', fake_db)
    monkeypatch.setattr(safety_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(safety_routes, 'enforce_user_rate_limit', allow_report)

    response = client.post('/api/safety/reports', json={
        'chatId': '2db25736-ad99-4c66-9022-985455f9e4f4',
        'messageId': 'answer-1',
        'category': 'violence_or_danger',
        'comment': 'Please review this.',
        'response': 'Client-forged answer',
    })

    assert response.status_code == 201
    assert response.json()['success'] is True
    assert fake_db.inserted['user_id'] == 'user-1'
    assert fake_db.inserted['reported_output'] == 'Server-owned answer'
    assert fake_db.inserted['prompt_context'] == 'Previous user context'
    assert fake_db.inserted['status'] == 'new'


def test_report_rejects_unknown_category():
    response = client.post('/api/safety/reports', json={
        'chatId': '2db25736-ad99-4c66-9022-985455f9e4f4',
        'messageId': 'answer-1',
        'category': 'not-a-real-category',
        'response': 'Answer',
    })
    assert response.status_code == 422
