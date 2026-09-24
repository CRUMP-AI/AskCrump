from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import app as app_module
from backend.routes import account as account_routes
from backend.routes import chat as chat_routes
from backend.intelligence_service import PreparedRequest
from backend.security import hash_password


client = TestClient(app_module.app)


def consented_user(**values):
    return {
        'id': 'user-1',
        'email': 'owner@example.com',
        'full_name': 'Owner',
        'ai_data_sharing_consent_at': '2026-09-17T23:55:00+00:00',
        'ai_data_sharing_consent_version': '2026-09-17',
        'ai_data_sharing_consent_revoked_at': None,
        **values,
    }


class FakeDB:
    def __init__(self):
        self.rpc_calls = []

    async def select_one(self, table, **_kwargs):
        if table == 'user_settings':
            return {'assistant_name': 'Server Crump', 'work_mode': True}
        return None

    async def rpc(self, name, payload, **_kwargs):
        self.rpc_calls.append((name, payload))
        if name == 'begin_video_account_deletion':
            return True
        return None


class FakeAI:
    def __init__(self):
        self.payload = None

    def needs_external_lookup(self, _message):
        return False

    async def chat(self, payload):
        self.payload = payload
        return {'response': 'ok', 'model': 'test-model', 'usage': {}}


class FakeFeatures:
    def entitled(self, *_args):
        return False

    async def require_tier(self, *_args):
        return None

    async def authorize(self, _user, components, *_args, **_kwargs):
        return SimpleNamespace(
            action_key='test-action',
            max_by_code={str(code): 0 for code in components},
        )

    async def consume_message(self, *_args, **_kwargs):
        return {
            'eventId': 'event-1',
            'used': 1,
            'limit': 100,
            'remaining': 99,
            'creditsSpent': 0,
        }

    async def consume(self, *_args, **_kwargs):
        return {'eventId': 'feature-1', 'creditsSpent': 0}

    async def refund(self, *_args, **_kwargs):
        return None

    @staticmethod
    def project_limit(_user):
        return 2


def test_chat_identity_and_settings_are_server_authoritative(monkeypatch):
    fake_db = FakeDB()
    fake_ai = FakeAI()
    events = []

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user=consented_user(),
            session={'id': 'session-1'},
            token='token',
        )

    async def record_event(*_args, **kwargs):
        events.append(dict(kwargs))
        return True

    monkeypatch.setattr(chat_routes, 'db', fake_db)
    monkeypatch.setattr(chat_routes, 'ai', fake_ai)
    monkeypatch.setattr(chat_routes, 'features', FakeFeatures())
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(chat_routes, 'record_product_event', record_event)

    response = client.post('/api/chat', json={
        'message': 'hello',
        'assistantName': 'Client Override',
        'workMode': 'companion',
        'user': {'id': 'attacker', 'email': 'attacker@example.com', 'name': 'Attacker'},
    })

    assert response.status_code == 200
    assert fake_ai.payload['assistantName'] == 'Server Crump'
    assert fake_ai.payload['workMode'] == 'work'
    assert 'user' not in fake_ai.payload
    assert fake_ai.payload['_userTier'] == 'free'
    assert all(event.get('event_name') != 'ActivationReached' for event in events)


def test_chat_packages_contextual_download_follow_up_when_semantic_router_is_unavailable(monkeypatch):
    fake_db = FakeDB()
    fake_ai = FakeAI()
    created = {}
    events = []

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user=consented_user(),
            session={'id': 'session-1'},
            token='token',
        )

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
    fake_features = FakeFeatures()
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
    monkeypatch.setattr(
        chat_routes,
        'feature_for_request',
        lambda **_kwargs: (None, {}),
    )
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


def test_durable_document_reply_survives_chat_job_cache_finalization_failure(monkeypatch):
    class FinalizationCacheFailureDB(FakeDB):
        def __init__(self):
            super().__init__()
            self.persisted_reply = None
            self.update_calls = []

        async def rpc(self, name, payload, **options):
            self.rpc_calls.append((name, payload))
            if name == 'claim_chat_job':
                return [{'job_state': 'claimed'}]
            if name == 'persist_chat_reply':
                self.persisted_reply = payload
                return [{'resulting_revision': 8, 'resulting_updated_at': '2026-08-31T12:00:00Z'}]
            return None

        async def update(self, table, payload, **_kwargs):
            self.update_calls.append((table, payload))
            if table == 'chat_jobs' and payload.get('status') == 'completed':
                raise RuntimeError('private cache finalization detail')
            return []

    fake_db = FinalizationCacheFailureDB()
    fake_ai = FakeAI()
    refunds = AsyncMock(return_value=None)
    events = []

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user=consented_user(),
            session={'id': 'session-1'},
            token='token',
        )

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
        return {
            'id': '00000000-0000-0000-0000-000000000099',
            'format': kwargs['format_name'],
            'name': 'durable-document.docx',
            'kind': 'generated_document',
            'status': 'ready',
        }

    async def record_event(*_args, **kwargs):
        if kwargs.get('event_name') == 'ActivationReached':
            assert fake_db.persisted_reply is not None
        events.append(dict(kwargs))
        return True

    fake_intelligence = SimpleNamespace(
        prepare=fake_prepare,
        verify_answer=AsyncMock(side_effect=lambda **kwargs: (kwargs['result'], False)),
        learn_explicit=AsyncMock(return_value=0),
        record_trace=AsyncMock(return_value=None),
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
    fake_features = FakeFeatures()

    monkeypatch.setattr(chat_routes, 'db', fake_db)
    monkeypatch.setattr(chat_routes, 'ai', fake_ai)
    monkeypatch.setattr(chat_routes, 'intelligence', fake_intelligence)
    monkeypatch.setattr(chat_routes, 'features', fake_features)
    monkeypatch.setattr(chat_routes, 'files', fake_files)
    monkeypatch.setattr(chat_routes, 'media', fake_media)
    monkeypatch.setattr(chat_routes, 'projects', SimpleNamespace(reference_files=AsyncMock(return_value=[])))
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(chat_routes, 'apply_project_context', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'mark_check_in_responded', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'record_product_event', record_event)
    monkeypatch.setattr(chat_routes, 'refund_usage', refunds)
    monkeypatch.setattr(type(chat_routes.artifacts), 'create', fake_create)

    response = client.post('/api/chat', json={
        'chatId': '00000000-0000-0000-0000-000000000002',
        'messageId': '00000000-0000-0000-0000-000000000003',
        'message': 'Create a downloadable document from this answer.',
        'artifactFormat': 'docx',
    })

    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert body['artifact']['name'] == 'durable-document.docx'
    assert body['assistantMessage']['artifact']['id'] == body['artifact']['id']
    assert body['conversationRevision'] == 8
    assert fake_db.persisted_reply['p_assistant_message']['artifact']['id'] == body['artifact']['id']
    assert any(table == 'chat_jobs' and payload.get('status') == 'completed' for table, payload in fake_db.update_calls)
    assert any(
        event.get('event_name') == 'ActivationReached'
        and event.get('event_key') == 'first-successful-response'
        for event in events
    )
    refunds.assert_not_awaited()


def test_account_deletion_uses_atomic_database_rpc(monkeypatch):
    fake_db = FakeDB()
    cleanup = AsyncMock(return_value=0)
    job = {
        'user_id': 'user-2',
        'operation_token': '00000000-0000-4000-8000-000000000002',
    }
    begin = AsyncMock(return_value=job)

    async def confirm_video_fence(*, user_id, operation_token):
        return await fake_db.rpc(
            'begin_video_account_deletion',
            {'p_user_id': user_id, 'p_operation_token': operation_token},
        )

    async def process(operation):
        assert operation == job
        await cleanup(user_id='user-2')
        await fake_db.rpc('delete_user_account', {'p_user_id': 'user-2'})
        return SimpleNamespace(account_deleted=True, cleanup_complete=False)

    deletion_service = SimpleNamespace(
        confirm_video_fence=AsyncMock(side_effect=confirm_video_fence),
        begin=begin,
        process=AsyncMock(side_effect=process),
    )
    password_hash = hash_password('StrongPassword123')

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-2', 'email': 'delete@example.com', 'password_hash': password_hash},
            session={'id': 'session-2'},
            token='token',
        )

    monkeypatch.setattr(account_routes, 'db', fake_db)
    monkeypatch.setattr(account_routes, 'account_deletions', deletion_service)
    monkeypatch.setattr(account_routes, 'authenticate_request', fake_authenticate)

    response = client.request('DELETE', '/api/account', json={
        'password': 'StrongPassword123',
        'confirmation': 'DELETE',
    })

    assert response.status_code == 200
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'delete_user_account',
    ]
    assert fake_db.rpc_calls[0][1]['p_user_id'] == 'user-2'
    token = fake_db.rpc_calls[0][1]['p_operation_token']
    assert token
    begin.assert_awaited_once_with(user_id='user-2', operation_token=token)
    cleanup.assert_awaited_once_with(user_id='user-2')
