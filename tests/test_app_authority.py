from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import app as app_module
from backend.routes import account as account_routes
from backend.routes import chat as chat_routes
from backend.intelligence_service import PreparedRequest
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

    def needs_external_lookup(self, _message):
        return False

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
    assert fake_ai.payload['_userTier'] == 'free'


def test_chat_packages_contextual_download_follow_up_when_semantic_router_is_unavailable(monkeypatch):
    fake_db = FakeDB()
    fake_ai = FakeAI()
    created = {}
    events = []

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
            session={'id': 'session-1'},
            token='token',
        )

    async def fake_consume(*_args, **_kwargs):
        return {'eventId': 'event-1', 'used': 1, 'limit': 100, 'remaining': 99}

    async def fake_prepare(_user_id, payload, **_kwargs):
        return PreparedRequest(
            payload=dict(payload),
            requested_mode='auto',
            effective_mode='balanced',
            verification_level='off',
            route='chat',
            creation_intent=None,
            user_tier='free',
        )

    async def fake_create(_self, **kwargs):
        created.update(kwargs)
        return {'id': 'artifact-1', 'format': kwargs['format_name'], 'name': 'launch-deck.pptx'}

    async def fake_record_event(_db, **kwargs):
        events.append((kwargs['event_name'], kwargs.get('artifact_type')))

    fake_intelligence = SimpleNamespace(
        prepare=fake_prepare,
        verify_answer=AsyncMock(side_effect=lambda **kwargs: (kwargs['result'], False)),
        learn_explicit=AsyncMock(return_value=0),
        record_trace=AsyncMock(return_value=None),
    )
    fake_features = SimpleNamespace(
        entitled=lambda *_args: False,
        refund=AsyncMock(return_value=None),
    )
    fake_files = SimpleNamespace(
        resolve_many=AsyncMock(return_value=[]),
        public_file=lambda row: row,
    )
    fake_media = SimpleNamespace(
        needs_prior_files=lambda _message: False,
        is_image_request=lambda *_args: False,
        is_edit_request=lambda *_args: False,
    )

    monkeypatch.setattr(chat_routes, 'db', fake_db)
    monkeypatch.setattr(chat_routes, 'ai', fake_ai)
    monkeypatch.setattr(chat_routes, 'intelligence', fake_intelligence)
    monkeypatch.setattr(chat_routes, 'features', fake_features)
    monkeypatch.setattr(chat_routes, 'files', fake_files)
    monkeypatch.setattr(chat_routes, 'media', fake_media)
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(chat_routes, 'consume_usage', fake_consume)
    monkeypatch.setattr(chat_routes, 'consume_feature_for_request', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'apply_project_context', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'mark_check_in_responded', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'record_product_event', fake_record_event)
    monkeypatch.setattr(type(chat_routes.artifacts), 'create', fake_create)

    response = client.post('/api/chat', json={
        'message': 'Can you export it?',
        'history': [
            {'role': 'user', 'content': 'Build a presentation for the product launch.'},
            {'role': 'assistant', 'content': 'Here is the completed slide narrative.'},
        ],
    })

    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert body['artifact']['format'] == 'pptx'
    assert created['format_name'] == 'pptx'
    assert fake_ai.payload['artifactFormat'] == 'pptx'
    assert any(item.get('source') == 'artifact_request' for item in fake_ai.payload['relevantContext'])
    assert ('ArtifactRequested', 'presentation') in events
    assert ('ArtifactPackaged', 'presentation') in events


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
