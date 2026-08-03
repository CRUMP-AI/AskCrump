from types import SimpleNamespace

from fastapi.testclient import TestClient

import app as app_module
from backend.routes import account as account_routes
from backend.routes import chat as chat_routes
from backend.security import hash_password


client = TestClient(app_module.app)


class FakeDB:
    def __init__(self):
        self.rpc_calls = []

    async def select_one(self, table, **_kwargs):
        if table == 'user_settings':
            return {'assistant_name': 'Server Crump', 'work_mode': True}
        return None

    async def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))
        return None


class FakeAI:
    def __init__(self):
        self.payload = None

    async def chat(self, payload):
        self.payload = payload
        return {'response': 'ok', 'model': 'test-model', 'usage': {}}


def test_chat_identity_and_settings_are_server_authoritative(monkeypatch):
    fake_db = FakeDB()
    fake_ai = FakeAI()

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
            session={'id': 'session-1'},
            token='token',
        )

    async def fake_consume(*_args, **_kwargs):
        return {'eventId': 'event-1', 'used': 1, 'limit': 100, 'remaining': 99}

    monkeypatch.setattr(chat_routes, 'db', fake_db)
    monkeypatch.setattr(chat_routes, 'ai', fake_ai)
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(chat_routes, 'consume_usage', fake_consume)

    response = client.post('/api/chat', json={
        'message': 'hello',
        'assistantName': 'Client Override',
        'workMode': 'companion',
        'user': {'id': 'attacker', 'email': 'attacker@example.com', 'name': 'Attacker'},
    })

    assert response.status_code == 200
    assert fake_ai.payload['assistantName'] == 'Server Crump'
    assert fake_ai.payload['workMode'] == 'work'
    assert fake_ai.payload['user'] == {
        'id': 'user-1',
        'email': 'owner@example.com',
        'name': 'Owner',
    }


def test_account_deletion_uses_atomic_database_rpc(monkeypatch):
    fake_db = FakeDB()
    password_hash = hash_password('StrongPassword123')

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-2', 'email': 'delete@example.com', 'password_hash': password_hash},
            session={'id': 'session-2'},
            token='token',
        )

    monkeypatch.setattr(account_routes, 'db', fake_db)
    monkeypatch.setattr(account_routes, 'authenticate_request', fake_authenticate)

    response = client.request('DELETE', '/api/account', json={
        'password': 'StrongPassword123',
        'confirmation': 'DELETE',
    })

    assert response.status_code == 200
    assert fake_db.rpc_calls == [('delete_user_account', {'p_user_id': 'user-2'})]
