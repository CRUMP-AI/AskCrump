import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx

import app as app_module
from backend.account_deletion_service import AccountDeletionService
from backend.file_service import FileServiceError
from backend.routes import account as account_routes
from backend.security import hash_password


client = TestClient(app_module.app)
PUBLIC = Path(__file__).resolve().parents[1] / 'public'


class FakeDB:
    def __init__(
        self,
        user,
        events=None,
        *,
        rpc_error=False,
        rpc_deletes_before_error=False,
    ):
        self.user = user
        self.rpc_calls = []
        self.events = events if events is not None else []
        self.rpc_error = rpc_error
        self.rpc_deletes_before_error = rpc_deletes_before_error
        self.deletion_job = None

    async def insert(self, table, payload):
        assert table == 'account_deletion_jobs'
        self.deletion_job = {
            'created_at': payload.get('fenced_at'),
            **dict(payload),
        }
        return [dict(self.deletion_job)]

    async def update(self, table, payload, *, filters, retry_transient=False):
        if table == 'account_deletion_jobs':
            if not self.deletion_job:
                return []
            if self.deletion_job.get('completed_at') and filters.get('completed_at') == 'is.null':
                return []
            self.deletion_job.update(payload)
            return [dict(self.deletion_job)]
        assert table == 'users'
        if not self.user:
            return []
        expected_id = str(filters.get('id') or '').removeprefix('eq.')
        expected_deleted = filters.get('deleted_at')
        current_deleted = self.user.get('deleted_at')
        if str(self.user.get('id')) != expected_id:
            return []
        if expected_deleted == 'is.null' and current_deleted is not None:
            return []
        if (
            expected_deleted not in {None, 'is.null'}
            and str(current_deleted) != str(expected_deleted).removeprefix('eq.')
        ):
            return []
        self.user.update(payload)
        if payload.get('deleted_at') is not None:
            self.events.append(('fence', self.user['id']))
        return [dict(self.user)]

    async def select_one(self, table, **_kwargs):
        if table == 'account_deletion_jobs':
            return dict(self.deletion_job) if self.deletion_job else None
        assert table == 'users'
        return dict(self.user) if self.user else None

    async def select(self, table, **_kwargs):
        assert table == 'account_deletion_jobs'
        return [dict(self.deletion_job)] if self.deletion_job else []

    async def rpc(self, name, payload, retry_transient=False):
        self.rpc_calls.append((name, payload))
        self.events.append(('rpc', name, payload))
        if self.rpc_deletes_before_error:
            self.user = None
        if self.rpc_error:
            raise RuntimeError('private database failure')
        self.user = None


class FakeFiles:
    def __init__(self, events, error=None):
        self.events = events
        self.error = error
        self.cleanup_calls = []

    async def hard_delete_all_owned(self, *, user_id):
        self.cleanup_calls.append(user_id)
        self.events.append(('storage_cleanup', user_id))
        if self.error:
            raise self.error
        return 0


class FakeStripeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


def configure_account(
    monkeypatch,
    user,
    *,
    stripe_key='sk_test_fixture',
    file_cleanup_error=None,
    rpc_error=False,
    rpc_deletes_before_error=False,
    revenuecat_key=None,
    revenuecat_required=False,
):
    events = []
    fake_db = FakeDB(
        user,
        events,
        rpc_error=rpc_error,
        rpc_deletes_before_error=rpc_deletes_before_error,
    )
    fake_files = FakeFiles(events, file_cleanup_error)

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user, session={'id': 'session-1'}, token='token')

    monkeypatch.setattr(account_routes, 'db', fake_db)
    monkeypatch.setattr(
        account_routes,
        'account_deletions',
        AccountDeletionService(
            fake_db,
            fake_files,
            revenuecat_secret_api_key=revenuecat_key,
            revenuecat_required=revenuecat_required,
        ),
    )
    monkeypatch.setattr(account_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(
        account_routes,
        'settings',
        SimpleNamespace(
            stripe_secret_key=stripe_key,
            revenuecat_secret_api_key=revenuecat_key,
        ),
    )
    fake_db.files = fake_files
    return fake_db


def install_stripe_response(monkeypatch, response, *, lookup_response=None):
    calls = []
    lookup = lookup_response or FakeStripeResponse(404, {'error': 'fixture'})

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def delete(self, url, **kwargs):
            calls.append(('DELETE', url, kwargs))
            return response

        async def get(self, url, **kwargs):
            calls.append(('GET', url, kwargs))
            return lookup

    monkeypatch.setattr(httpx, 'AsyncClient', FakeClient)
    return calls


def install_revenuecat_responses(monkeypatch, *responses):
    calls = []
    queued = iter(responses)

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def delete(self, url, **_kwargs):
            calls.append(url)
            outcome = next(queued)
            if isinstance(outcome, Exception):
                raise outcome
            return SimpleNamespace(status_code=outcome)

    monkeypatch.setattr(httpx, 'AsyncClient', FakeClient)
    return calls


def account_user(**overrides):
    user = {
        'id': 'user-delete-1',
        'email': 'delete@example.com',
        'password_hash': hash_password('StrongPassword123'),
        'stripe_customer_id': 'cus_delete_fixture',
        'stripe_subscription_id': 'sub_delete_fixture',
        'subscription_provider': 'stripe',
        'subscription_status': 'active',
    }
    user.update(overrides)
    return user


def delete_request():
    return client.request(
        'DELETE',
        '/api/account',
        json={'password': 'StrongPassword123', 'confirmation': 'DELETE'},
    )


def test_open_web_subscription_requires_provider_confirmation():
    assert account_routes.requires_stripe_cancellation_confirmation(account_user()) is True
    assert account_routes.requires_stripe_cancellation_confirmation(
        account_user(subscription_status='past_due')
    ) is True
    assert account_routes.requires_stripe_cancellation_confirmation(
        account_user(subscription_status='canceled')
    ) is False
    assert account_routes.requires_stripe_cancellation_confirmation(
        account_user(
            stripe_subscription_id=None,
            subscription_provider=None,
            subscription_status='inactive',
        )
    ) is False
    assert account_routes.requires_stripe_cancellation_confirmation(
        account_user(subscription_status='inactive')
    ) is True
    assert account_routes.requires_stripe_cancellation_confirmation(
        account_user(
            subscription_provider='revenuecat',
            stripe_subscription_id=None,
            subscription_status='active',
        )
    ) is False


def test_open_web_subscription_blocks_deletion_when_billing_is_unavailable(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user(), stripe_key=None)

    response = delete_request()

    assert response.status_code == 502
    assert response.json()['code'] == 'BILLING_CANCELLATION_UNCONFIRMED'
    assert fake_db.rpc_calls == []
    assert fake_db.files.cleanup_calls == []


def test_open_web_subscription_blocks_deletion_when_stripe_rejects_cleanup(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    calls = install_stripe_response(monkeypatch, FakeStripeResponse(500, {'error': 'fixture'}))

    response = delete_request()

    assert response.status_code == 502
    assert fake_db.rpc_calls == []
    assert calls[0][1].endswith('/customers/cus_delete_fixture')


def test_open_web_subscription_blocks_unconfirmed_success_payload(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    install_stripe_response(
        monkeypatch,
        FakeStripeResponse(200, {'deleted': True, 'id': 'cus_different'}),
    )

    response = delete_request()

    assert response.status_code == 502
    assert fake_db.rpc_calls == []


def test_confirmed_stripe_deletion_allows_atomic_local_deletion(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    install_stripe_response(
        monkeypatch,
        FakeStripeResponse(200, {'deleted': True, 'id': 'cus_delete_fixture'}),
    )

    response = delete_request()

    assert response.status_code == 200
    assert fake_db.rpc_calls == [
        ('delete_user_account', {'p_user_id': 'user-delete-1'}),
    ]
    assert fake_db.events == [
        ('fence', 'user-delete-1'),
        ('storage_cleanup', 'user-delete-1'),
        ('rpc', 'delete_user_account', {'p_user_id': 'user-delete-1'}),
    ]


def test_deleted_stripe_customer_tombstone_allows_safe_cleanup_retry(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    calls = install_stripe_response(
        monkeypatch,
        FakeStripeResponse(404, {'error': 'already deleted'}),
        lookup_response=FakeStripeResponse(
            200,
            {'deleted': True, 'id': 'cus_delete_fixture'},
        ),
    )

    response = delete_request()

    assert response.status_code == 200
    assert [call[0] for call in calls] == ['DELETE', 'GET']
    assert fake_db.rpc_calls == [
        ('delete_user_account', {'p_user_id': 'user-delete-1'}),
    ]


def test_terminal_subscription_preserves_privacy_deletion_when_cleanup_fails(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(subscription_status='canceled'),
    )
    install_stripe_response(monkeypatch, FakeStripeResponse(500, {'error': 'fixture'}))

    response = delete_request()

    assert response.status_code == 200
    assert fake_db.rpc_calls == [
        ('delete_user_account', {'p_user_id': 'user-delete-1'}),
    ]


def test_private_storage_cleanup_failure_secures_account_and_schedules_retry(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(),
        file_cleanup_error=FileServiceError(
            'Private file storage is temporarily unavailable.',
            503,
            'STORAGE_ERROR',
        ),
    )
    install_stripe_response(
        monkeypatch,
        FakeStripeResponse(200, {'deleted': True, 'id': 'cus_delete_fixture'}),
    )

    response = delete_request()

    assert response.status_code == 202
    assert response.json()['success'] is True
    assert response.json()['pending'] is True
    assert response.json()['code'] == 'STORAGE_ERROR'
    assert 'storage cleanup' in response.json()['message']
    assert 'subscription cancellation remains effective' in response.json()['message']
    assert fake_db.rpc_calls == []
    assert fake_db.events == [
        ('fence', 'user-delete-1'),
        ('storage_cleanup', 'user-delete-1'),
    ]
    assert fake_db.user['deleted_at'] is not None
    assert fake_db.deletion_job['state'] == 'retry_pending'


def test_final_rpc_failure_keeps_fence_and_schedules_durable_retry(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(),
        rpc_error=True,
    )
    install_stripe_response(
        monkeypatch,
        FakeStripeResponse(200, {'deleted': True, 'id': 'cus_delete_fixture'}),
    )

    response = delete_request()

    assert response.status_code == 202
    assert response.json()['success'] is True
    assert response.json()['pending'] is True
    assert response.json()['code'] == 'ACCOUNT_DELETION_RPC_UNCONFIRMED'
    assert fake_db.user is not None
    assert fake_db.user['deleted_at'] is not None
    assert fake_db.events == [
        ('fence', 'user-delete-1'),
        ('storage_cleanup', 'user-delete-1'),
        ('rpc', 'delete_user_account', {'p_user_id': 'user-delete-1'}),
    ]
    assert fake_db.deletion_job['state'] == 'retry_pending'


def test_rpc_transport_error_after_commit_is_confirmed_as_success(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(),
        rpc_error=True,
        rpc_deletes_before_error=True,
    )
    install_stripe_response(
        monkeypatch,
        FakeStripeResponse(200, {'deleted': True, 'id': 'cus_delete_fixture'}),
    )

    response = delete_request()

    assert response.status_code == 200
    assert response.json()['success'] is True
    assert fake_db.user is None
    assert fake_db.events == [
        ('fence', 'user-delete-1'),
        ('storage_cleanup', 'user-delete-1'),
        ('rpc', 'delete_user_account', {'p_user_id': 'user-delete-1'}),
    ]


def test_revenuecat_failure_preserves_fenced_account_until_worker_retry(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(
            stripe_customer_id=None,
            stripe_subscription_id=None,
            subscription_provider='revenuecat',
        ),
        stripe_key=None,
        revenuecat_key='rc_test_fixture',
    )
    calls = install_revenuecat_responses(monkeypatch, 500, 404)

    response = delete_request()

    assert response.status_code == 202
    assert response.json()['code'] == 'REVENUECAT_CLEANUP_UNCONFIRMED'
    assert fake_db.user['deleted_at'] is not None
    assert fake_db.deletion_job['state'] == 'retry_pending'
    assert fake_db.files.cleanup_calls == []
    assert fake_db.rpc_calls == []

    retry_at = datetime.fromisoformat(fake_db.deletion_job['next_attempt_at'])
    restarted_worker = AccountDeletionService(
        fake_db,
        fake_db.files,
        now=lambda: retry_at + timedelta(seconds=1),
        revenuecat_secret_api_key='rc_test_fixture',
    )
    summary = asyncio.run(restarted_worker.process_due(limit=2))

    assert summary == {'processed': 1, 'deleted': 1, 'completed': 0, 'retrying': 1}
    assert fake_db.user is None
    assert fake_db.rpc_calls == [
        ('delete_user_account', {'p_user_id': 'user-delete-1'}),
    ]
    assert len(calls) == 2


def test_native_account_deletion_waits_for_missing_revenuecat_key(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(
            stripe_customer_id=None,
            stripe_subscription_id=None,
            subscription_provider='revenuecat',
        ),
        stripe_key=None,
    )

    response = delete_request()

    assert response.status_code == 202
    assert response.json()['code'] == 'REVENUECAT_CLEANUP_UNCONFIRMED'
    assert fake_db.user['deleted_at'] is not None
    assert fake_db.files.cleanup_calls == []
    assert fake_db.rpc_calls == []


def test_configured_native_billing_without_server_key_blocks_even_free_user(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(
            stripe_customer_id=None,
            stripe_subscription_id=None,
            subscription_provider=None,
        ),
        stripe_key=None,
        revenuecat_required=True,
    )

    response = delete_request()

    assert response.status_code == 202
    assert response.json()['code'] == 'REVENUECAT_CLEANUP_UNCONFIRMED'
    assert fake_db.user['deleted_at'] is not None
    assert fake_db.rpc_calls == []


def test_free_native_identity_remains_cleanup_required_after_flag_is_disabled(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(
            stripe_customer_id=None,
            stripe_subscription_id=None,
            subscription_provider=None,
            native_billing_identity_possible_at='2026-09-20T12:00:00+00:00',
        ),
        stripe_key=None,
        revenuecat_required=False,
    )

    response = delete_request()

    assert response.status_code == 202
    assert response.json()['code'] == 'REVENUECAT_CLEANUP_UNCONFIRMED'
    assert fake_db.deletion_job['native_billing_identity_possible'] is True
    assert fake_db.user['deleted_at'] is not None
    assert fake_db.files.cleanup_calls == []
    assert fake_db.rpc_calls == []

    # A later deployment can disable native billing, but its durable job must
    # still require a real provider-cleanup key before deleting the user.
    restarted_worker = AccountDeletionService(
        fake_db,
        fake_db.files,
        revenuecat_required=False,
    )
    summary = asyncio.run(restarted_worker.process_due(limit=2))
    assert summary['retrying'] == 1
    assert fake_db.user is not None
    assert fake_db.rpc_calls == []


def test_free_native_identity_is_deleted_at_provider_before_local_account(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(
            stripe_customer_id=None,
            stripe_subscription_id=None,
            subscription_provider=None,
            native_billing_identity_possible_at='2026-09-20T12:00:00+00:00',
        ),
        stripe_key=None,
        revenuecat_key='rc_test_fixture',
        revenuecat_required=False,
    )
    calls = install_revenuecat_responses(monkeypatch, 404)

    response = delete_request()

    assert response.status_code == 200
    assert fake_db.deletion_job['native_billing_identity_possible'] is True
    assert len(calls) == 1
    assert calls[0].endswith('/subscribers/user-delete-1')
    assert fake_db.rpc_calls == [
        ('delete_user_account', {'p_user_id': 'user-delete-1'}),
    ]


def test_revenuecat_cleanup_is_retried_after_storage_failure(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(
            stripe_customer_id=None,
            stripe_subscription_id=None,
            subscription_provider='revenuecat',
        ),
        stripe_key=None,
        revenuecat_key='rc_test_fixture',
        file_cleanup_error=FileServiceError('temporary failure', 503, 'STORAGE_ERROR'),
    )
    calls = install_revenuecat_responses(monkeypatch, 200, 404)

    response = delete_request()
    assert response.status_code == 202
    assert response.json()['code'] == 'STORAGE_ERROR'
    assert fake_db.rpc_calls == []

    fake_db.files.error = None
    retry_at = datetime.fromisoformat(fake_db.deletion_job['next_attempt_at'])
    worker = AccountDeletionService(
        fake_db,
        fake_db.files,
        now=lambda: retry_at + timedelta(seconds=1),
        revenuecat_secret_api_key='rc_test_fixture',
    )
    asyncio.run(worker.process_due(limit=2))
    assert fake_db.user is None
    assert len(calls) == 2


def test_account_deletion_copy_distinguishes_web_and_store_billing():
    account_manager = (PUBLIC / 'account-manager.js').read_text(encoding='utf-8')
    deletion_page = (PUBLIC / 'delete-account.html').read_text(encoding='utf-8')
    legal_page = (PUBLIC / 'legal.html').read_text(encoding='utf-8')

    for source in (account_manager, deletion_page, legal_page):
        assert 'web subscription' in source
        assert 'refund' in source
        assert 'Apple App Store' in source
        assert 'Google Play' in source
