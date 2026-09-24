from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app as app_module
from backend import checkin_service
from backend import config as config_module
from backend.ai_consent import (
    AI_DATA_SHARING_CATEGORIES,
    AI_DATA_SHARING_PROVIDERS,
    AIDataSharingConsentRequired,
    CURRENT_AI_DATA_SHARING_CONSENT_VERSION,
    has_current_ai_data_sharing_consent,
    require_ai_data_sharing_consent,
)
from backend.routes import account as account_routes
from backend.routes import chat as chat_routes
from backend.routes import manuscripts as manuscript_routes
from backend.manuscript_service import ManuscriptService


ROOT = Path(__file__).resolve().parents[1]
CLIENT = TestClient(app_module.app)


class ConsentDB:
    def __init__(self) -> None:
        self.updates: list[tuple[str, dict, dict]] = []

    async def update(self, table, values, *, filters):
        self.updates.append((table, dict(values), dict(filters)))
        return [dict(values)]


def test_current_consent_requires_both_timestamp_and_exact_version():
    current = {
        'ai_data_sharing_consent_at': '2026-09-17T23:55:00+00:00',
        'ai_data_sharing_consent_version': CURRENT_AI_DATA_SHARING_CONSENT_VERSION,
    }
    assert has_current_ai_data_sharing_consent(current) is True
    assert has_current_ai_data_sharing_consent({**current, 'ai_data_sharing_consent_at': None}) is False
    assert has_current_ai_data_sharing_consent({**current, 'ai_data_sharing_consent_version': '2026-08-01'}) is False
    assert has_current_ai_data_sharing_consent({
        **current,
        'ai_data_sharing_consent_revoked_at': '2026-09-18T00:00:00+00:00',
    }) is False
    assert has_current_ai_data_sharing_consent({
        **current,
        'deleted_at': '2026-09-18T00:01:00+00:00',
    }) is False
    assert has_current_ai_data_sharing_consent(None) is False

    require_ai_data_sharing_consent(current)
    try:
        require_ai_data_sharing_consent({})
    except AIDataSharingConsentRequired as exc:
        assert exc.status_code == 428
        assert exc.code == 'AI_DATA_SHARING_CONSENT_REQUIRED'
    else:
        raise AssertionError('missing consent must fail closed')


def test_accept_and_withdraw_are_separate_server_authoritative_account_actions(monkeypatch):
    fake_db = ConsentDB()
    user = {'id': 'consent-owner', 'email': 'owner@example.com'}

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user, session={'id': 'session-1'}, token='token')

    monkeypatch.setattr(account_routes, 'db', fake_db)
    monkeypatch.setattr(account_routes, 'authenticate_request', fake_authenticate)

    accepted = CLIENT.post(
        '/api/account/ai-data-sharing-consent',
        json={'version': CURRENT_AI_DATA_SHARING_CONSENT_VERSION},
    )
    assert accepted.status_code == 200
    accepted_user = accepted.json()['user']
    assert accepted_user['aiDataSharingConsentAt']
    assert accepted_user['aiDataSharingConsentVersion'] == CURRENT_AI_DATA_SHARING_CONSENT_VERSION
    assert accepted_user['aiDataSharingConsentRevokedAt'] is None
    assert fake_db.updates[-1][0] == 'users'

    withdrawn = CLIENT.delete('/api/account/ai-data-sharing-consent')
    assert withdrawn.status_code == 200
    withdrawn_user = withdrawn.json()['user']
    assert withdrawn_user['aiDataSharingConsentAt']
    assert withdrawn_user['aiDataSharingConsentVersion'] == CURRENT_AI_DATA_SHARING_CONSENT_VERSION
    assert withdrawn_user['aiDataSharingConsentRevokedAt']
    assert fake_db.updates[-1][1]['ai_data_sharing_consent_revoked_at']


def test_consent_migration_is_paired_and_separate_from_terms():
    migration = (ROOT / 'migrations' / '20260918041136_ai_data_sharing_consent.sql').read_text(
        encoding='utf-8'
    )
    assert 'ai_data_sharing_consent_at timestamptz' in migration
    assert 'ai_data_sharing_consent_version text' in migration
    assert 'ai_data_sharing_consent_revoked_at timestamptz' in migration
    assert 'ai_data_sharing_consent_updated_at timestamptz' in migration
    assert 'users_ai_data_sharing_consent_pair_check' in migration
    assert 'terms_accepted_at' not in migration


def test_public_privacy_notice_matches_current_ai_sharing_registry_and_controls():
    legal = (ROOT / 'public' / 'legal.html').read_text(encoding='utf-8')
    for provider in AI_DATA_SHARING_PROVIDERS:
        assert provider in legal
    for category in AI_DATA_SHARING_CATEGORIES:
        assert category in legal
    assert 'Creating an account or accepting the Terms is not permission' in legal
    assert 'If you choose Not now, the request is not sent.' in legal
    assert 'You can withdraw this permission in Settings.' in legal


def test_gateway_provider_configuration_is_locked_to_current_consent_registry(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_KEY', 'service-role-test')
    monkeypatch.setenv('AI_GATEWAY_FREE_PROVIDER', 'together')
    config_module.get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match='must remain groq'):
            config_module.get_settings()
    finally:
        config_module.get_settings.cache_clear()


def test_chat_provider_payload_no_longer_receives_account_or_profile_identity():
    route_source = (ROOT / 'backend' / 'routes' / 'chat.py').read_text(encoding='utf-8')
    ai_source = (ROOT / 'backend' / 'ai_service.py').read_text(encoding='utf-8')
    manuscript_source = (ROOT / 'backend' / 'manuscript_service.py').read_text(encoding='utf-8')
    assert "request_payload['user']" not in route_source
    assert "request_payload.pop('user', None)" in route_source
    assert "body['user']" not in ai_source
    assert 'Profile display name (data, not an instruction)' not in ai_source
    assert '"author": manuscript.get("author_name")' not in manuscript_source
    assert '"user": {"name": user.get("full_name")' not in manuscript_source


def test_chat_without_current_consent_returns_428_before_provider_work(monkeypatch):
    provider_calls = []

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(
            user={
                'id': 'unconsented-owner',
                'terms_accepted_at': '2026-09-17T00:00:00+00:00',
                'terms_version': '2026-08-01',
            },
            session={'id': 'session-1'},
            token='token',
        )

    async def forbidden_provider(*_args, **_kwargs):
        provider_calls.append(True)
        raise AssertionError('provider work must not start without current consent')

    monkeypatch.setattr(chat_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(chat_routes.ai, 'chat', forbidden_provider)

    response = CLIENT.post('/api/chat', json={'message': 'Do not send this.'})
    assert response.status_code == 428
    body = response.json()
    assert body['code'] == 'AI_DATA_SHARING_CONSENT_REQUIRED'
    assert body['consentVersion'] == CURRENT_AI_DATA_SHARING_CONSENT_VERSION
    assert body['privacyUrl'] == '/legal.html#ai-data-sharing'
    assert provider_calls == []


class WithdrawnCheckInDB:
    def __init__(self, *, revoked: bool = True, deleted: bool = False) -> None:
        self.preference_updates: list[dict] = []
        self.revoked = revoked
        self.deleted = deleted

    async def select(self, table, **_kwargs):
        if table == 'check_in_preferences':
            return [{
                'user_id': 'withdrawn-owner',
                'enabled': True,
                'frequency': 'balanced',
                'quiet_start': 0,
                'quiet_end': 0,
                'allow_followups': True,
                'next_eligible_at': '2026-09-17T00:00:00+00:00',
                'ignored_count': 0,
            }]
        if table == 'check_in_events':
            return []
        if table == 'user_chats':
            return [{
                'chat_id': 'chat-1',
                'title': 'A useful conversation',
                'messages': [
                    {'role': 'user', 'content': 'Help me plan this.'},
                    {'role': 'assistant', 'content': 'Here is the first step.'},
                ],
                'updated_at': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                'revision': 2,
                'deleted_at': None,
            }]
        return []

    async def select_one(self, table, **kwargs):
        if table == 'check_in_events':
            return None
        if table == 'users':
            assert 'deleted_at' in str(kwargs.get('columns') or '')
            return {
                'id': 'withdrawn-owner',
                'email': 'owner@example.com',
                'ai_data_sharing_consent_at': '2026-09-17T00:00:00+00:00',
                'ai_data_sharing_consent_version': CURRENT_AI_DATA_SHARING_CONSENT_VERSION,
                'ai_data_sharing_consent_revoked_at': (
                    '2026-09-18T00:00:00+00:00' if self.revoked else None
                ),
                'deleted_at': (
                    '2026-09-18T00:01:00+00:00' if self.deleted else None
                ),
            }
        return None

    async def update(self, table, values, **_kwargs):
        if table == 'check_in_preferences':
            self.preference_updates.append(dict(values))
        return [dict(values)]


@pytest.mark.asyncio
async def test_withdrawn_consent_skips_scheduled_check_in_before_provider_work():
    database = WithdrawnCheckInDB()

    async def forbidden_generate(*_args, **_kwargs):
        raise AssertionError('withdrawn consent must stop scheduled provider work')

    ai = SimpleNamespace(generate_check_in=forbidden_generate)
    result = await checkin_service.run_check_ins(
        database,
        ai,
        SimpleNamespace(),
        batch_size=10,
    )

    assert result['eligible'] == 1
    assert result['skipped'] == 1
    assert result['sent'] == 0
    assert database.preference_updates


@pytest.mark.asyncio
async def test_deleted_account_skips_scheduled_check_in_before_provider_work():
    database = WithdrawnCheckInDB(revoked=False, deleted=True)

    async def forbidden_generate(*_args, **_kwargs):
        raise AssertionError('deleted account must stop scheduled provider work')

    result = await checkin_service.run_check_ins(
        database,
        SimpleNamespace(generate_check_in=forbidden_generate),
        SimpleNamespace(),
        batch_size=10,
    )

    assert result['eligible'] == 1
    assert result['skipped'] == 1
    assert result['sent'] == 0
    assert database.preference_updates


class WithdrawnManuscriptDB:
    def __init__(self) -> None:
        self.run = {
            'id': 'run-1',
            'user_id': 'withdrawn-owner',
            'project_id': 'project-1',
            'manuscript_id': 'manuscript-1',
            'stage': 'blueprint',
            'status': 'running',
            'lease_token': 'lease-1',
            'brief': 'A safe test manuscript.',
            'target_words': 50000,
            'chapter_count': 20,
        }

    async def rpc(self, name, _payload, **_kwargs):
        assert name == 'claim_manuscript_run'
        return [dict(self.run)]

    async def select_one(self, table, **_kwargs):
        assert table == 'users'
        return {
            'id': 'withdrawn-owner',
            'ai_data_sharing_consent_at': '2026-09-17T00:00:00+00:00',
            'ai_data_sharing_consent_version': CURRENT_AI_DATA_SHARING_CONSENT_VERSION,
            'ai_data_sharing_consent_revoked_at': '2026-09-18T00:00:00+00:00',
            'deleted_at': None,
        }

    async def update(self, table, values, **_kwargs):
        assert table == 'manuscript_runs'
        self.run.update(values)
        return [dict(self.run)]


@pytest.mark.asyncio
async def test_withdrawn_consent_pauses_manuscript_worker_before_provider_work(monkeypatch):
    database = WithdrawnManuscriptDB()
    service = ManuscriptService(
        database,
        SimpleNamespace(),
        SimpleNamespace(),
        features=SimpleNamespace(),
        files=SimpleNamespace(),
    )

    async def fake_get(**_kwargs):
        return {'id': 'manuscript-1', 'title': 'Consent boundary'}

    async def fake_list_sections(**_kwargs):
        return []

    async def forbidden_plan(**_kwargs):
        raise AssertionError('withdrawn consent must stop manuscript provider work')

    monkeypatch.setattr(service, 'get', fake_get)
    monkeypatch.setattr(service, 'list_sections', fake_list_sections)
    monkeypatch.setattr(service, 'plan_blueprint', forbidden_plan)

    result = await service.process_next_run()

    assert result == {
        'claimed': True,
        'runId': 'run-1',
        'status': 'paused',
        'errorCode': 'AI_DATA_SHARING_CONSENT_REQUIRED',
    }
    assert database.run['lease_token'] is None
    assert database.run['last_error_code'] == 'AI_DATA_SHARING_CONSENT_REQUIRED'


class DeletedManuscriptDB(WithdrawnManuscriptDB):
    async def select_one(self, table, **_kwargs):
        user = await super().select_one(table, **_kwargs)
        user['ai_data_sharing_consent_revoked_at'] = None
        user['deleted_at'] = '2026-09-18T00:01:00+00:00'
        return user


@pytest.mark.asyncio
async def test_deleted_account_pauses_manuscript_worker_before_provider_work(monkeypatch):
    database = DeletedManuscriptDB()
    service = ManuscriptService(
        database,
        SimpleNamespace(),
        SimpleNamespace(),
        features=SimpleNamespace(),
        files=SimpleNamespace(),
    )

    async def fake_get(**_kwargs):
        return {'id': 'manuscript-1', 'title': 'Consent boundary'}

    async def fake_list_sections(**_kwargs):
        return []

    async def forbidden_plan(**_kwargs):
        raise AssertionError('deleted account must stop manuscript provider work')

    monkeypatch.setattr(service, 'get', fake_get)
    monkeypatch.setattr(service, 'list_sections', fake_list_sections)
    monkeypatch.setattr(service, 'plan_blueprint', forbidden_plan)

    result = await service.process_next_run()

    assert result['status'] == 'paused'
    assert result['errorCode'] == 'AI_DATA_SHARING_CONSENT_REQUIRED'


def _unconsented_auth():
    return SimpleNamespace(
        user={'id': '00000000-0000-4000-8000-000000000101'},
        session={'id': 'session-1'},
        token='token',
    )


def test_export_only_manuscript_start_remains_available_without_ai_consent(monkeypatch):
    captured = {}

    async def fake_authenticate(*_args, **_kwargs):
        return _unconsented_auth()

    async def fake_latest_run(**_kwargs):
        return None

    async def fake_sections(**_kwargs):
        return [{'id': 'section-1', 'content': 'Finished chapter'}]

    async def fake_authorize(_user, components, *_args, **_kwargs):
        captured['components'] = dict(components)
        return SimpleNamespace(max_by_code={}, action_key='export-only')

    async def fake_queue_run(**kwargs):
        captured['queue'] = kwargs
        return {
            'id': 'run-export',
            'project_id': 'project-1',
            'manuscript_id': kwargs['manuscript_id'],
            'status': 'queued',
            'stage': 'drafting',
            'mode': kwargs['mode'],
        }

    monkeypatch.setattr(manuscript_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'latest_run', fake_latest_run)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'list_sections', fake_sections)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'queue_run', fake_queue_run)
    monkeypatch.setattr(manuscript_routes.features, 'authorize', fake_authorize)

    response = CLIENT.post(
        '/api/manuscripts/00000000-0000-4000-8000-000000000102/runs',
        json={'mode': 'autopilot', 'format': 'docx'},
    )

    assert response.status_code == 200
    assert captured['components'] == {'kdp_export': 1}
    assert captured['queue']['planned_steps'] == 0


def test_existing_outline_start_is_no_provider_no_charge_without_ai_consent(monkeypatch):
    captured = {}

    async def fake_authenticate(*_args, **_kwargs):
        return _unconsented_auth()

    async def fake_latest_run(**_kwargs):
        return None

    async def fake_sections(**_kwargs):
        return [{'id': 'section-1', 'content': ''}]

    async def forbidden_authorize(*_args, **_kwargs):
        raise AssertionError('an existing outline must not quote provider or export work')

    async def fake_queue_run(**kwargs):
        captured['queue'] = kwargs
        return {
            'id': 'run-outline',
            'project_id': 'project-1',
            'manuscript_id': kwargs['manuscript_id'],
            'status': 'queued',
            'stage': 'complete',
            'mode': kwargs['mode'],
        }

    monkeypatch.setattr(manuscript_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'latest_run', fake_latest_run)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'list_sections', fake_sections)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'queue_run', fake_queue_run)
    monkeypatch.setattr(manuscript_routes.features, 'authorize', forbidden_authorize)

    response = CLIENT.post(
        '/api/manuscripts/00000000-0000-4000-8000-000000000102/runs',
        json={'mode': 'outline', 'format': 'docx'},
    )

    assert response.status_code == 200
    assert captured['queue']['mode'] == 'outline'
    assert captured['queue']['planned_steps'] == 0


@pytest.mark.asyncio
async def test_legacy_outline_drafting_run_completes_without_provider_work(monkeypatch):
    database = WithdrawnManuscriptDB()
    database.run.update({'stage': 'drafting', 'mode': 'outline'})
    service = ManuscriptService(
        database,
        SimpleNamespace(),
        SimpleNamespace(),
        features=SimpleNamespace(),
        files=SimpleNamespace(),
    )

    async def fake_sections(**_kwargs):
        return [{'id': 'section-1', 'content': ''}]

    async def forbidden_draft(**_kwargs):
        raise AssertionError('outline mode must never draft existing sections')

    monkeypatch.setattr(service, 'list_sections', fake_sections)
    monkeypatch.setattr(service, 'draft_section_with_generation', forbidden_draft)

    result = await service.process_next_run()

    assert result['status'] == 'completed'
    assert result['stage'] == 'complete'
    assert database.run['status'] == 'completed'
    assert database.run['stage'] == 'complete'


def test_export_stage_resume_remains_available_without_ai_consent(monkeypatch):
    calls = []

    async def fake_authenticate(*_args, **_kwargs):
        return _unconsented_auth()

    async def fake_get_run(**_kwargs):
        return {
            'id': '00000000-0000-4000-8000-000000000103',
            'user_id': '00000000-0000-4000-8000-000000000101',
            'project_id': 'project-1',
            'manuscript_id': '00000000-0000-4000-8000-000000000102',
            'status': 'paused',
            'stage': 'export',
        }

    async def fake_resume_run(**_kwargs):
        calls.append(True)
        return {**(await fake_get_run()), 'status': 'queued'}

    monkeypatch.setattr(manuscript_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'get_run', fake_get_run)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'resume_run', fake_resume_run)

    response = CLIENT.post(
        '/api/manuscript-runs/00000000-0000-4000-8000-000000000103/resume',
        json={},
    )

    assert response.status_code == 200
    assert calls == [True]


def test_drafting_resume_requires_ai_consent_before_requeue(monkeypatch):
    resume_calls = []

    async def fake_authenticate(*_args, **_kwargs):
        return _unconsented_auth()

    async def fake_get_run(**_kwargs):
        return {
            'id': '00000000-0000-4000-8000-000000000103',
            'user_id': '00000000-0000-4000-8000-000000000101',
            'manuscript_id': '00000000-0000-4000-8000-000000000102',
            'status': 'paused',
            'stage': 'drafting',
        }

    async def fake_sections(**_kwargs):
        return [{'id': 'section-1', 'content': ''}]

    async def forbidden_resume(**_kwargs):
        resume_calls.append(True)
        raise AssertionError('provider-bound resume must remain blocked')

    monkeypatch.setattr(manuscript_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'get_run', fake_get_run)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'list_sections', fake_sections)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'resume_run', forbidden_resume)

    response = CLIENT.post(
        '/api/manuscript-runs/00000000-0000-4000-8000-000000000103/resume',
        json={},
    )

    assert response.status_code == 428
    assert response.json()['code'] == 'AI_DATA_SHARING_CONSENT_REQUIRED'
    assert resume_calls == []


def test_outline_blueprint_resume_still_requires_ai_consent(monkeypatch):
    resume_calls = []

    async def fake_authenticate(*_args, **_kwargs):
        return _unconsented_auth()

    async def fake_get_run(**_kwargs):
        return {
            'id': '00000000-0000-4000-8000-000000000103',
            'user_id': '00000000-0000-4000-8000-000000000101',
            'manuscript_id': '00000000-0000-4000-8000-000000000102',
            'status': 'paused',
            'stage': 'blueprint',
            'mode': 'outline',
        }

    async def fake_sections(**_kwargs):
        return []

    async def forbidden_resume(**_kwargs):
        resume_calls.append(True)
        raise AssertionError('outline blueprint resume must remain blocked')

    monkeypatch.setattr(manuscript_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'get_run', fake_get_run)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'list_sections', fake_sections)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'resume_run', forbidden_resume)

    response = CLIENT.post(
        '/api/manuscript-runs/00000000-0000-4000-8000-000000000103/resume',
        json={},
    )

    assert response.status_code == 428
    assert response.json()['code'] == 'AI_DATA_SHARING_CONSENT_REQUIRED'
    assert resume_calls == []


def test_legacy_outline_credit_error_resume_skips_draft_reauthorization(monkeypatch):
    calls = []

    async def fake_authenticate(*_args, **_kwargs):
        return _unconsented_auth()

    async def fake_get_run(**_kwargs):
        return {
            'id': '00000000-0000-4000-8000-000000000103',
            'user_id': '00000000-0000-4000-8000-000000000101',
            'project_id': 'project-1',
            'manuscript_id': '00000000-0000-4000-8000-000000000102',
            'status': 'awaiting_credits',
            'stage': 'drafting',
            'mode': 'outline',
            'last_error_code': 'CREDIT_BUDGET_EXHAUSTED',
        }

    async def fake_sections(**_kwargs):
        return [{'id': 'section-1', 'content': ''}]

    async def forbidden_authorize(*_args, **_kwargs):
        raise AssertionError('legacy outline completion must not quote draft credits')

    async def fake_resume(**_kwargs):
        calls.append('resume')
        return {**(await fake_get_run()), 'status': 'queued', 'last_error_code': None}

    monkeypatch.setattr(manuscript_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'get_run', fake_get_run)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'list_sections', fake_sections)
    monkeypatch.setattr(manuscript_routes.manuscripts, 'resume_run', fake_resume)
    monkeypatch.setattr(manuscript_routes.features, 'authorize', forbidden_authorize)

    response = CLIENT.post(
        '/api/manuscript-runs/00000000-0000-4000-8000-000000000103/resume',
        json={},
    )

    assert response.status_code == 200
    assert calls == ['resume']


@pytest.mark.asyncio
async def test_service_clears_obsolete_credit_error_for_legacy_outline_completion():
    class OutlineResumeDB:
        def __init__(self):
            self.run = {
                'id': '00000000-0000-4000-8000-000000000103',
                'user_id': '00000000-0000-4000-8000-000000000101',
                'status': 'awaiting_credits',
                'stage': 'drafting',
                'mode': 'outline',
                'last_error_code': 'CREDIT_BUDGET_EXHAUSTED',
            }

        async def select_one(self, table, **_kwargs):
            assert table == 'manuscript_runs'
            return dict(self.run)

        async def update(self, table, values, **_kwargs):
            assert table == 'manuscript_runs'
            self.run.update(values)
            return [dict(self.run)]

    database = OutlineResumeDB()
    service = ManuscriptService(database, SimpleNamespace(), SimpleNamespace())

    resumed = await service.resume_run(
        user_id='00000000-0000-4000-8000-000000000101',
        run_id='00000000-0000-4000-8000-000000000103',
    )

    assert resumed['status'] == 'queued'
    assert resumed['last_error_code'] is None
