from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app as app_module
from backend.routes import account as account_routes
from backend.routes import chat as chat_routes
from backend.file_service import FileServiceError
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

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
            session={'id': 'session-1'},
            token='token',
        )

    monkeypatch.setattr(chat_routes, 'db', fake_db)
    monkeypatch.setattr(chat_routes, 'ai', fake_ai)
    monkeypatch.setattr(chat_routes, 'features', FakeFeatures())
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)

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


@pytest.mark.parametrize('request_overrides', ({'artifactFormat': 'epub'}, {}))
def test_chat_routes_intentional_manuscript_epub_through_real_endpoint(monkeypatch, request_overrides):
    claim_token = '00000000-0000-4000-8000-000000000070'

    class ClaimedFakeDB(FakeDB):
        async def rpc(self, name, payload, **_options):
            self.rpc_calls.append((name, payload))
            if name == 'claim_chat_job_v2':
                return [{'job_state': 'claimed', 'claim_token': claim_token}]
            return None

    fake_db = ClaimedFakeDB()
    captured = {}
    message = 'Write a complete 70,000-word novel and deliver it as an EPUB.'

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
            session={'id': 'session-1'},
            token='token',
        )

    async def fake_prepare(_user_id, payload, **_kwargs):
        return PreparedRequest(
            payload=dict(payload),
            requested_mode='auto',
            effective_mode='balanced',
            verification_level='off',
            route='manuscript',
            creation_intent={
                'kind': 'manuscript',
                'stage': 'execute',
                'confidence': 0.99,
                'brief': message,
                'question': '',
                'format': '',
            },
            user_tier='free',
        )

    async def fake_begin_long_form(_self, **kwargs):
        captured.update(kwargs)
        return {
            'response': 'The manuscript workspace is ready.',
            'model': 'test-manuscript-model',
            'manuscriptWorkspace': {'preferredFormat': kwargs['preferred_format']},
        }

    fake_intelligence = SimpleNamespace(
        prepare=fake_prepare,
        verify_answer=AsyncMock(side_effect=lambda **kwargs: (kwargs['result'], False)),
        learn_explicit=AsyncMock(return_value=0),
        record_trace=AsyncMock(return_value=None),
    )
    fake_files = SimpleNamespace(resolve_many=AsyncMock(return_value=[]), public_file=lambda row: row)
    fake_media = SimpleNamespace(
        needs_prior_files=lambda _message: False,
        extract_nonvisual=AsyncMock(return_value=''),
        has_visual_files=lambda _rows: False,
        legacy_inline_files=AsyncMock(return_value=[]),
        is_image_request=lambda *_args: False,
        is_edit_request=lambda *_args: False,
    )

    monkeypatch.setattr(chat_routes, 'db', fake_db)
    monkeypatch.setattr(chat_routes, 'intelligence', fake_intelligence)
    monkeypatch.setattr(chat_routes, 'features', FakeFeatures())
    monkeypatch.setattr(chat_routes, 'files', fake_files)
    monkeypatch.setattr(chat_routes, 'media', fake_media)
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(chat_routes, 'apply_project_context', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'mark_check_in_responded', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'record_product_event', AsyncMock(return_value=True))
    monkeypatch.setattr(type(chat_routes.manuscripts), 'begin_long_form', fake_begin_long_form)

    response = client.post('/api/chat', json={
        'chatId': '00000000-0000-4000-8000-000000000071',
        'messageId': '00000000-0000-4000-8000-000000000072',
        'message': message,
        **request_overrides,
    })

    assert response.status_code == 200
    assert response.json()['manuscriptWorkspace']['preferredFormat'] == 'epub'
    assert captured['preferred_format'] == 'epub'
    assert captured['brief'] == message
    assert captured['message_id'] == '00000000-0000-4000-8000-000000000072'
    assert captured['claim_token'] == claim_token


def test_invalid_file_releases_exact_reply_claim_for_immediate_same_message_retry(monkeypatch):
    chat_id = '00000000-0000-0000-0000-000000000021'
    message_id = '00000000-0000-0000-0000-000000000022'
    tokens = [
        '00000000-0000-4000-8000-000000000781',
        '00000000-0000-4000-8000-000000000782',
    ]

    class FileFailureDB(FakeDB):
        def __init__(self):
            super().__init__()
            self.claims = 0
            self.active_token = None
            self.releases = []

        async def rpc(self, name, payload, **_options):
            self.rpc_calls.append((name, payload))
            if name == 'claim_chat_job_v2':
                self.active_token = tokens[self.claims]
                self.claims += 1
                return [{'job_state': 'claimed', 'claim_token': self.active_token}]
            if name == 'release_chat_job_claim':
                self.releases.append(dict(payload))
                assert payload['p_claim_token'] == self.active_token
                self.active_token = None
                return True
            raise AssertionError(f'unexpected RPC {name}')

        async def select_one(self, table, **_kwargs):
            if table == 'user_chats':
                return None
            return await super().select_one(table, **_kwargs)

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
            session={'id': 'session-1'},
            token='token',
        )

    database = FileFailureDB()
    fake_files = SimpleNamespace(resolve_many=AsyncMock(side_effect=FileServiceError(
        'That file is unavailable.', 404, 'FILE_NOT_FOUND',
    )))
    monkeypatch.setattr(chat_routes, 'db', database)
    monkeypatch.setattr(chat_routes, 'files', fake_files)
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)

    payload = {
        'chatId': chat_id,
        'messageId': message_id,
        'message': 'Use the attached file.',
        'fileIds': ['00000000-0000-0000-0000-000000000023'],
    }
    first = client.post('/api/chat', json=payload)
    second = client.post('/api/chat', json=payload)

    assert first.status_code == 404
    assert second.status_code == 404
    assert database.claims == 2
    assert [call['p_claim_token'] for call in database.releases] == tokens
    assert all(call['p_error_code'] == 'FILE_NOT_FOUND' for call in database.releases)


def test_unexpected_pre_persistence_failure_releases_claim_for_immediate_retry(monkeypatch):
    chat_id = '00000000-0000-0000-0000-000000000031'
    message_id = '00000000-0000-0000-0000-000000000032'
    tokens = [
        '00000000-0000-4000-8000-000000000791',
        '00000000-0000-4000-8000-000000000792',
    ]

    class InfrastructureFailureDB(FakeDB):
        def __init__(self):
            super().__init__()
            self.claims = 0
            self.active_token = None
            self.releases = []

        async def rpc(self, name, payload, **_options):
            if name == 'claim_chat_job_v2':
                self.active_token = tokens[self.claims]
                self.claims += 1
                return [{'job_state': 'claimed', 'claim_token': self.active_token}]
            if name == 'release_chat_job_claim':
                self.releases.append(dict(payload))
                assert payload['p_claim_token'] == self.active_token
                self.active_token = None
                return True
            raise AssertionError(f'unexpected RPC {name}')

        async def select_one(self, table, **_kwargs):
            if table == 'user_chats':
                return None
            if table == 'user_settings':
                raise RuntimeError('private settings outage detail')
            return None

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
            session={'id': 'session-1'},
            token='token',
        )

    database = InfrastructureFailureDB()
    monkeypatch.setattr(chat_routes, 'db', database)
    monkeypatch.setattr(chat_routes, 'files', SimpleNamespace(
        resolve_many=AsyncMock(return_value=[]),
    ))
    monkeypatch.setattr(chat_routes, 'media', SimpleNamespace(needs_prior_files=lambda _message: False))
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)

    unsafe_client = TestClient(app_module.app, raise_server_exceptions=False)
    payload = {'chatId': chat_id, 'messageId': message_id, 'message': 'Help me.'}
    first = unsafe_client.post('/api/chat', json=payload)
    second = unsafe_client.post('/api/chat', json=payload)

    assert first.status_code == 500
    assert second.status_code == 500
    assert database.claims == 2
    assert [call['p_claim_token'] for call in database.releases] == tokens
    assert all(call['p_error_code'] == 'REPLY_PRE_PERSISTENCE_FAILED' for call in database.releases)


def test_unexpected_post_consumption_failure_refunds_before_releasing_claim(monkeypatch):
    chat_id = '00000000-0000-0000-0000-000000000041'
    message_id = '00000000-0000-0000-0000-000000000042'
    token = '00000000-0000-4000-8000-000000000793'

    class PostConsumptionFailureDB(FakeDB):
        def __init__(self):
            super().__init__()
            self.releases = []

        async def rpc(self, name, payload, **_options):
            if name == 'claim_chat_job_v2':
                return [{'job_state': 'claimed', 'claim_token': token}]
            if name == 'release_chat_job_claim':
                self.releases.append(dict(payload))
                return True
            raise AssertionError(f'unexpected RPC {name}')

        async def select_one(self, table, **_kwargs):
            if table == 'user_chats':
                return None
            if table == 'user_settings':
                return {}
            return None

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
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

    database = PostConsumptionFailureDB()
    fake_features = FakeFeatures()
    fake_features.refund = AsyncMock(return_value=None)
    usage_refund = AsyncMock(return_value=None)
    fake_intelligence = SimpleNamespace(
        prepare=fake_prepare,
        verify_answer=AsyncMock(side_effect=RuntimeError('private verifier outage detail')),
        learn_explicit=AsyncMock(return_value=0),
        record_trace=AsyncMock(return_value=None),
    )
    fake_media = SimpleNamespace(
        needs_prior_files=lambda _message: False,
        extract_nonvisual=AsyncMock(return_value=''),
        has_visual_files=lambda _rows: False,
        legacy_inline_files=AsyncMock(return_value=[]),
        is_image_request=lambda *_args: False,
        is_edit_request=lambda *_args: False,
    )

    monkeypatch.setattr(chat_routes, 'db', database)
    monkeypatch.setattr(chat_routes, 'ai', FakeAI())
    monkeypatch.setattr(chat_routes, 'features', fake_features)
    monkeypatch.setattr(chat_routes, 'intelligence', fake_intelligence)
    monkeypatch.setattr(chat_routes, 'files', SimpleNamespace(
        resolve_many=AsyncMock(return_value=[]),
        public_file=lambda row: row,
    ))
    monkeypatch.setattr(chat_routes, 'media', fake_media)
    monkeypatch.setattr(chat_routes, 'projects', SimpleNamespace(reference_files=AsyncMock(return_value=[])))
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(chat_routes, 'apply_project_context', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'mark_check_in_responded', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'refund_usage', usage_refund)

    unsafe_client = TestClient(app_module.app, raise_server_exceptions=False)
    response = unsafe_client.post('/api/chat', json={
        'chatId': chat_id,
        'messageId': message_id,
        'message': 'Help me with this.',
    })

    assert response.status_code == 500
    usage_refund.assert_awaited_once_with(database, 'user-1', 'event-1')
    fake_features.refund.assert_awaited_once_with('user-1', None)
    assert database.releases == [{
        'p_user_id': 'user-1',
        'p_message_id': message_id,
        'p_claim_token': token,
        'p_error_code': 'REPLY_PRE_PERSISTENCE_FAILED',
    }]


def _paid_artifact_persistence_cleanup_failure(
    monkeypatch,
    *,
    confirm_fallback,
    lookup_unavailable=False,
):
    chat_id = '00000000-0000-0000-0000-000000000051'
    message_id = '00000000-0000-0000-0000-000000000052'
    artifact_id = '00000000-0000-0000-0000-000000000053'
    claim_token = '00000000-0000-4000-8000-000000000794'

    class FailureDB(FakeDB):
        def __init__(self):
            super().__init__()
            self.persist_attempts = 0
            self.update_calls = []
            self.conversation_lookups = 0

        async def rpc(self, name, payload, **_options):
            self.rpc_calls.append((name, payload))
            if name == 'claim_chat_job_v2':
                return [{'job_state': 'claimed', 'claim_token': claim_token}]
            if name == 'persist_chat_reply':
                self.persist_attempts += 1
                raise RuntimeError('definitive conversation write failure')
            raise AssertionError(f'unexpected RPC {name}')

        async def select_one(self, table, **_kwargs):
            if table == 'user_chats':
                self.conversation_lookups += 1
                if lookup_unavailable and self.conversation_lookups > 1:
                    raise RuntimeError('ambiguous conversation read failure')
                return None
            if table == 'user_settings':
                return {}
            return None

        async def update(self, table, payload, **kwargs):
            self.update_calls.append((table, dict(payload), dict(kwargs.get('filters') or {})))
            assert table == 'chat_jobs' and payload.get('status') == 'completed'
            return [dict(payload)] if confirm_fallback else []

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
            session={'id': 'session-1'}, token='token',
        )

    async def prepare(_user_id, payload, **_kwargs):
        return PreparedRequest(
            payload=dict(payload), requested_mode='auto', effective_mode='balanced',
            verification_level='off', route='chat', creation_intent=None, user_tier='free',
        )

    async def create(_self, **kwargs):
        return {
            'id': artifact_id, 'format': kwargs['format_name'], 'name': 'paid-output.docx',
            'kind': 'generated_document', 'status': 'ready',
        }

    database = FailureDB()
    feature_service = FakeFeatures()
    feature_service.consume_message = AsyncMock(return_value={
        'eventId': 'credit:paid-output-ledger', 'used': 1, 'limit': 100,
        'remaining': 99, 'creditsSpent': 5,
    })
    feature_service.refund = AsyncMock(return_value=None)
    usage_refund = AsyncMock(return_value=None)
    soft_delete = AsyncMock(side_effect=RuntimeError('storage cleanup unavailable'))
    intelligence = SimpleNamespace(
        prepare=prepare,
        verify_answer=AsyncMock(side_effect=lambda **kwargs: (kwargs['result'], False)),
        learn_explicit=AsyncMock(return_value=0),
        record_trace=AsyncMock(return_value=None),
    )
    files = SimpleNamespace(
        resolve_many=AsyncMock(return_value=[]), public_file=lambda row: row,
        soft_delete=soft_delete,
    )
    media = SimpleNamespace(
        needs_prior_files=lambda _message: False,
        extract_nonvisual=AsyncMock(return_value=''),
        has_visual_files=lambda _rows: False,
        legacy_inline_files=AsyncMock(return_value=[]),
        is_image_request=lambda *_args: False,
        is_edit_request=lambda *_args: False,
    )
    monkeypatch.setattr(chat_routes, 'db', database)
    monkeypatch.setattr(chat_routes, 'ai', FakeAI())
    monkeypatch.setattr(chat_routes, 'features', feature_service)
    monkeypatch.setattr(chat_routes, 'intelligence', intelligence)
    monkeypatch.setattr(chat_routes, 'files', files)
    monkeypatch.setattr(chat_routes, 'media', media)
    monkeypatch.setattr(chat_routes, 'projects', SimpleNamespace(reference_files=AsyncMock(return_value=[])))
    monkeypatch.setattr(chat_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(chat_routes, 'apply_project_context', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'mark_check_in_responded', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'record_product_event', AsyncMock(return_value=True))
    monkeypatch.setattr(chat_routes, 'refund_usage', usage_refund)
    monkeypatch.setattr(type(chat_routes.artifacts), 'create', create)

    response = client.post('/api/chat', json={
        'chatId': chat_id, 'messageId': message_id,
        'message': 'Create a downloadable document from this answer.',
        'artifactFormat': 'docx',
    })
    return SimpleNamespace(
        response=response, database=database, features=feature_service,
        usage_refund=usage_refund, soft_delete=soft_delete, message_id=message_id,
        artifact_id=artifact_id, claim_token=claim_token,
    )


def test_paid_artifact_is_preserved_without_refund_when_reply_and_cleanup_fail(monkeypatch):
    outcome = _paid_artifact_persistence_cleanup_failure(monkeypatch, confirm_fallback=True)

    assert outcome.response.status_code == 200
    body = outcome.response.json()
    assert body['success'] is True
    assert body['reconciled'] is True
    assert body['artifact']['id'] == outcome.artifact_id
    assert body['assistantMessage']['artifact']['id'] == outcome.artifact_id
    assert 'paid output was preserved' in body['persistenceWarning']
    assert outcome.database.persist_attempts == 1
    assert len(outcome.database.update_calls) == 1
    table, payload, filters = outcome.database.update_calls[0]
    assert table == 'chat_jobs'
    assert payload['status'] == 'completed'
    assert payload['error_code'] == 'CHAT_PERSISTENCE_OUTPUT_PRESERVED'
    assert payload['claim_token'] is None
    assert payload['response_data']['artifact']['id'] == outcome.artifact_id
    assert payload['response_data']['persistenceWarning'] == body['persistenceWarning']
    assert filters == {
        'user_id': 'eq.user-1',
        'message_id': f'eq.{outcome.message_id}',
        'claim_token': f'eq.{outcome.claim_token}',
        'status': 'eq.processing',
    }
    outcome.soft_delete.assert_awaited_once_with(user_id='user-1', file_id=outcome.artifact_id)
    outcome.usage_refund.assert_not_awaited()
    outcome.features.refund.assert_not_awaited()


def test_unconfirmed_paid_artifact_fallback_is_nonretryable_and_not_refunded(monkeypatch):
    outcome = _paid_artifact_persistence_cleanup_failure(monkeypatch, confirm_fallback=False)

    assert outcome.response.status_code == 503
    body = outcome.response.json()
    assert body['success'] is False
    assert body['code'] == 'CHAT_PERSISTENCE_OUTPUT_PRESERVED_UNCONFIRMED'
    assert body['shouldRetry'] is False
    assert 'Do not regenerate' in body['message']
    assert outcome.database.persist_attempts == 1
    assert len(outcome.database.update_calls) == 1
    table, payload, filters = outcome.database.update_calls[0]
    assert table == 'chat_jobs'
    assert payload['status'] == 'completed'
    assert payload['error_code'] == 'CHAT_PERSISTENCE_OUTPUT_PRESERVED'
    assert payload['claim_token'] is None
    assert filters['claim_token'] == f'eq.{outcome.claim_token}'
    assert filters['status'] == 'eq.processing'
    outcome.soft_delete.assert_awaited_once_with(user_id='user-1', file_id=outcome.artifact_id)
    outcome.usage_refund.assert_not_awaited()
    outcome.features.refund.assert_not_awaited()


def test_ambiguous_reply_persistence_warns_not_to_regenerate_and_keeps_claim_fenced(monkeypatch):
    outcome = _paid_artifact_persistence_cleanup_failure(
        monkeypatch,
        confirm_fallback=True,
        lookup_unavailable=True,
    )

    assert outcome.response.status_code == 503
    body = outcome.response.json()
    assert body['code'] == 'CHAT_PERSISTENCE_UNCONFIRMED'
    assert body['shouldRetry'] is True
    assert body['retryAfter'] == 480
    assert 'Do not regenerate' in body['message']
    assert outcome.database.persist_attempts == 1
    assert outcome.database.conversation_lookups == 2
    assert outcome.database.update_calls == []
    assert all(name != 'release_chat_job_claim' for name, _payload in outcome.database.rpc_calls)
    outcome.soft_delete.assert_not_awaited()
    outcome.usage_refund.assert_not_awaited()
    outcome.features.refund.assert_not_awaited()


def test_preserved_manuscript_handoff_retries_from_cache_without_duplicate_workspace(monkeypatch):
    chat_id = '00000000-0000-0000-0000-000000000061'
    message_id = '00000000-0000-0000-0000-000000000062'
    claim_token = '00000000-0000-4000-8000-000000000795'
    message = 'Write a complete novel from this brief.'

    class ManuscriptFailureDB(FakeDB):
        def __init__(self):
            super().__init__()
            self.cached_response = None
            self.update_calls = []
            self.persist_attempts = 0

        async def rpc(self, name, payload, **_options):
            self.rpc_calls.append((name, payload))
            if name == 'claim_chat_job_v2':
                if self.cached_response:
                    return [{'job_state': 'completed', 'response_data': self.cached_response}]
                return [{'job_state': 'claimed', 'claim_token': claim_token}]
            if name == 'persist_chat_reply':
                self.persist_attempts += 1
                raise RuntimeError('definitive conversation write failure')
            raise AssertionError(f'unexpected RPC {name}')

        async def select_one(self, table, **_kwargs):
            if table == 'user_chats':
                return None
            if table == 'user_settings':
                return {}
            return None

        async def update(self, table, payload, **kwargs):
            assert table == 'chat_jobs'
            self.update_calls.append((dict(payload), dict(kwargs.get('filters') or {})))
            self.cached_response = dict(payload['response_data'])
            return [dict(payload)]

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
            session={'id': 'session-1'}, token='token',
        )

    async def prepare(_user_id, payload, **_kwargs):
        return PreparedRequest(
            payload=dict(payload), requested_mode='auto', effective_mode='balanced',
            verification_level='off', route='manuscript',
            creation_intent={
                'kind': 'manuscript', 'stage': 'execute', 'confidence': 0.99,
                'brief': message, 'question': '', 'format': 'docx',
            },
            user_tier='free',
        )

    begin_long_form = AsyncMock(return_value={
        'response': 'The manuscript workspace is ready.',
        'model': 'test-manuscript-model',
        'projectId': '00000000-0000-0000-0000-000000000063',
        'manuscriptWorkspace': {
            'projectId': '00000000-0000-0000-0000-000000000063',
            'preferredFormat': 'docx',
            'runStatus': 'queued',
        },
    })
    database = ManuscriptFailureDB()
    feature_service = FakeFeatures()
    feature_service.consume_message = AsyncMock(return_value={
        'eventId': 'credit:manuscript-message', 'used': 1, 'limit': 100,
        'remaining': 99, 'creditsSpent': 5,
    })
    feature_service.consume = AsyncMock(return_value={
        'eventId': 'credit:manuscript-blueprint', 'creditsSpent': 20,
    })
    feature_service.refund = AsyncMock(return_value=None)
    usage_refund = AsyncMock(return_value=None)
    intelligence = SimpleNamespace(
        prepare=prepare,
        verify_answer=AsyncMock(side_effect=lambda **kwargs: (kwargs['result'], False)),
        learn_explicit=AsyncMock(return_value=0),
        record_trace=AsyncMock(return_value=None),
    )
    files = SimpleNamespace(
        resolve_many=AsyncMock(return_value=[]), public_file=lambda row: row,
        soft_delete=AsyncMock(),
    )
    media = SimpleNamespace(
        needs_prior_files=lambda _message: False,
        extract_nonvisual=AsyncMock(return_value=''),
        has_visual_files=lambda _rows: False,
        legacy_inline_files=AsyncMock(return_value=[]),
        is_image_request=lambda *_args: False,
        is_edit_request=lambda *_args: False,
    )
    monkeypatch.setattr(chat_routes, 'db', database)
    monkeypatch.setattr(chat_routes, 'ai', FakeAI())
    monkeypatch.setattr(chat_routes, 'features', feature_service)
    monkeypatch.setattr(chat_routes, 'intelligence', intelligence)
    monkeypatch.setattr(chat_routes, 'files', files)
    monkeypatch.setattr(chat_routes, 'media', media)
    monkeypatch.setattr(chat_routes, 'projects', SimpleNamespace(reference_files=AsyncMock(return_value=[])))
    monkeypatch.setattr(chat_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(chat_routes, 'apply_project_context', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'mark_check_in_responded', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'record_product_event', AsyncMock(return_value=True))
    monkeypatch.setattr(chat_routes, 'refund_usage', usage_refund)
    monkeypatch.setattr(type(chat_routes.manuscripts), 'begin_long_form', begin_long_form)

    payload = {'chatId': chat_id, 'messageId': message_id, 'message': message}
    first = client.post('/api/chat', json=payload)
    second = client.post('/api/chat', json=payload)

    assert first.status_code == 200 == second.status_code
    first_body = first.json()
    second_body = second.json()
    assert first_body['manuscriptWorkspace']['runStatus'] == 'queued'
    assert first_body['persistenceWarning']
    assert second_body['manuscriptWorkspace'] == first_body['manuscriptWorkspace']
    assert second_body['cached'] is True
    assert database.persist_attempts == 1
    assert begin_long_form.await_count == 1
    assert len(database.update_calls) == 1
    update, filters = database.update_calls[0]
    assert update['status'] == 'completed'
    assert update['error_code'] == 'CHAT_PERSISTENCE_OUTPUT_PRESERVED'
    assert update['claim_token'] is None
    assert filters['claim_token'] == f'eq.{claim_token}'
    assert filters['status'] == 'eq.processing'
    files.soft_delete.assert_not_awaited()
    usage_refund.assert_not_awaited()
    feature_service.refund.assert_not_awaited()


def test_unconfirmed_atomic_manuscript_handoff_keeps_charge_and_claim_fenced(monkeypatch):
    chat_id = '00000000-0000-0000-0000-000000000081'
    message_id = '00000000-0000-0000-0000-000000000082'
    claim_token = '00000000-0000-4000-8000-000000000083'
    message = 'Write a complete novel from this brief.'

    class AmbiguousHandoffDB(FakeDB):
        async def rpc(self, name, payload, **_options):
            self.rpc_calls.append((name, payload))
            if name == 'claim_chat_job_v2':
                return [{'job_state': 'claimed', 'claim_token': claim_token}]
            raise AssertionError(f'unexpected RPC {name}')

        async def select_one(self, table, **_kwargs):
            if table == 'user_settings':
                return {}
            return None

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
            session={'id': 'session-1'}, token='token',
        )

    async def prepare(_user_id, payload, **_kwargs):
        return PreparedRequest(
            payload=dict(payload), requested_mode='auto', effective_mode='balanced',
            verification_level='off', route='manuscript',
            creation_intent={
                'kind': 'manuscript', 'stage': 'execute', 'confidence': 0.99,
                'brief': message, 'question': '', 'format': 'docx',
            },
            user_tier='free',
        )

    database = AmbiguousHandoffDB()
    feature_service = FakeFeatures()
    feature_service.consume_message = AsyncMock(return_value={
        'eventId': 'credit:ambiguous-message', 'used': 1, 'limit': 100,
        'remaining': 99, 'creditsSpent': 5,
    })
    feature_service.consume = AsyncMock(return_value={
        'eventId': 'credit:ambiguous-blueprint', 'creditsSpent': 20,
    })
    feature_service.refund = AsyncMock(return_value=None)
    usage_refund = AsyncMock(return_value=None)
    intelligence = SimpleNamespace(
        prepare=prepare,
        verify_answer=AsyncMock(side_effect=lambda **kwargs: (kwargs['result'], False)),
        learn_explicit=AsyncMock(return_value=0),
        record_trace=AsyncMock(return_value=None),
    )
    files = SimpleNamespace(
        resolve_many=AsyncMock(return_value=[]), public_file=lambda row: row,
        soft_delete=AsyncMock(),
    )
    media = SimpleNamespace(
        needs_prior_files=lambda _message: False,
        extract_nonvisual=AsyncMock(return_value=''),
        has_visual_files=lambda _rows: False,
        legacy_inline_files=AsyncMock(return_value=[]),
        is_image_request=lambda *_args: False,
        is_edit_request=lambda *_args: False,
    )
    begin_long_form = AsyncMock(side_effect=chat_routes.ManuscriptHandoffUnconfirmed())
    monkeypatch.setattr(chat_routes, 'db', database)
    monkeypatch.setattr(chat_routes, 'ai', FakeAI())
    monkeypatch.setattr(chat_routes, 'features', feature_service)
    monkeypatch.setattr(chat_routes, 'intelligence', intelligence)
    monkeypatch.setattr(chat_routes, 'files', files)
    monkeypatch.setattr(chat_routes, 'media', media)
    monkeypatch.setattr(chat_routes, 'projects', SimpleNamespace(reference_files=AsyncMock(return_value=[])))
    monkeypatch.setattr(chat_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(chat_routes, 'apply_project_context', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'mark_check_in_responded', AsyncMock(return_value=None))
    monkeypatch.setattr(chat_routes, 'record_product_event', AsyncMock(return_value=True))
    monkeypatch.setattr(chat_routes, 'refund_usage', usage_refund)
    monkeypatch.setattr(type(chat_routes.manuscripts), 'begin_long_form', begin_long_form)

    response = client.post('/api/chat', json={
        'chatId': chat_id, 'messageId': message_id, 'message': message,
    })

    assert response.status_code == 503
    body = response.json()
    assert body['code'] == 'MANUSCRIPT_WORKSPACE_UNCONFIRMED'
    assert body['shouldRetry'] is False
    assert body['retryAfter'] == 480
    assert 'Do not start it again' in body['message']
    assert begin_long_form.await_count == 1
    assert all(name != 'release_chat_job_claim' for name, _payload in database.rpc_calls)
    usage_refund.assert_not_awaited()
    feature_service.refund.assert_not_awaited()


def test_durable_document_reply_survives_chat_job_cache_finalization_failure(monkeypatch):
    class FinalizationCacheFailureDB(FakeDB):
        def __init__(self):
            super().__init__()
            self.persisted_reply = None
            self.update_calls = []

        async def rpc(self, name, payload, **options):
            self.rpc_calls.append((name, payload))
            if name == 'claim_chat_job_v2':
                return [{
                    'job_state': 'claimed',
                    'claim_token': '00000000-0000-4000-8000-000000000777',
                }]
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

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
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

    async def ignore_event(*_args, **_kwargs):
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
    monkeypatch.setattr(chat_routes, 'record_product_event', ignore_event)
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
    refunds.assert_not_awaited()


def test_chat_retry_recovers_committed_reply_before_regenerating(monkeypatch):
    chat_id = '00000000-0000-0000-0000-000000000002'
    message_id = '00000000-0000-0000-0000-000000000003'
    artifact_id = '00000000-0000-0000-0000-000000000099'

    class AmbiguousCommitDB(FakeDB):
        def __init__(self):
            super().__init__()
            self.update_calls = []

        async def rpc(self, name, payload, **_options):
            self.rpc_calls.append((name, payload))
            if name == 'claim_chat_job_v2':
                return [{
                    'job_state': 'claimed',
                    'claim_token': '00000000-0000-4000-8000-000000000778',
                }]
            raise AssertionError(f'Unexpected RPC after durable reconciliation: {name}')

        async def select_one(self, table, **_kwargs):
            if table == 'user_chats':
                return {
                    'chat_id': chat_id,
                    'revision': 9,
                    'updated_at': '2026-09-24T12:00:00Z',
                    'messages': [{
                        'id': '00000000-0000-0000-0000-000000000004',
                        'role': 'assistant',
                        'content': 'The committed answer.',
                        'inReplyTo': message_id,
                        'artifact': {
                            'id': artifact_id,
                            'name': 'committed.docx',
                            'format': 'docx',
                        },
                    }],
                }
            return await super().select_one(table, **_kwargs)

        async def update(self, table, payload, **_kwargs):
            self.update_calls.append((table, payload))
            return [dict(payload)]

    database = AmbiguousCommitDB()
    fake_ai = FakeAI()
    create_artifact = AsyncMock()
    consume_message = AsyncMock()
    features = FakeFeatures()
    features.consume_message = consume_message

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={'id': 'user-1', 'email': 'owner@example.com', 'full_name': 'Owner'},
            session={'id': 'session-1'},
            token='token',
        )

    monkeypatch.setattr(chat_routes, 'db', database)
    monkeypatch.setattr(chat_routes, 'ai', fake_ai)
    monkeypatch.setattr(chat_routes, 'features', features)
    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(type(chat_routes.artifacts), 'create', create_artifact)

    response = client.post('/api/chat', json={
        'chatId': chat_id,
        'messageId': message_id,
        'message': 'Create a downloadable document from this answer.',
        'artifactFormat': 'docx',
    })

    assert response.status_code == 200
    body = response.json()
    assert body['response'] == 'The committed answer.'
    assert body['artifact']['id'] == artifact_id
    assert body['conversationRevision'] == 9
    assert body['cached'] is True
    assert body['reconciled'] is True
    assert fake_ai.payload is None
    create_artifact.assert_not_awaited()
    consume_message.assert_not_awaited()
    assert any(
        table == 'chat_jobs'
        and payload.get('status') == 'completed'
        and payload.get('response_data', {}).get('artifact', {}).get('id') == artifact_id
        for table, payload in database.update_calls
    )


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

    assert response.status_code == 202
    assert response.json()['deletionStatus'] == 'scheduled'
    assert 'Max-Age=0' in response.headers.get('set-cookie', '')
    assert fake_db.rpc_calls == [
        (
            'delete_user_account',
            {
                'p_user_id': 'user-2',
                'p_storage_bucket': 'crump-files',
            },
        ),
    ]
