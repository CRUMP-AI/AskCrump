import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

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
        self.video_starts_settled = True
        self.fenced = False
        self.deleted = False
        self.deletion_token = None
        self.begin_commit_then_error = False
        self.recovery_commit_then_error = False
        self.recovery_replacement_token = None
        self.video_fence_read_failures = 0
        self.video_fence_read_calls = 0
        self.video_fence_read_failure_calls = set()
        self.video_fence_requested_at = datetime.now().astimezone().isoformat()
        self.establish_forced_result = None

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
            expected_attempts = filters.get('attempts')
            if (
                expected_attempts is not None
                and int(str(expected_attempts).removeprefix('eq.'))
                != int(self.deletion_job.get('attempts') or 0)
            ):
                return []
            due = str(filters.get('next_attempt_at') or '')
            if (
                due.startswith('lte.')
                and str(self.deletion_job.get('next_attempt_at') or '') > due[4:]
            ):
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
        if table == 'video_account_deletion_fences':
            self.video_fence_read_calls += 1
            if self.video_fence_read_failures:
                self.video_fence_read_failures -= 1
                raise RuntimeError('video fence read unavailable')
            if self.video_fence_read_calls in self.video_fence_read_failure_calls:
                raise RuntimeError('video fence read unavailable')
            if not self.fenced:
                return None
            return {
                'user_id': str(self.user.get('id')) if self.user else 'user-delete-1',
                'operation_token': self.deletion_token,
                'requested_at': self.video_fence_requested_at,
                'deleted_at': 'delete committed' if self.deleted else None,
            }
        assert table == 'users'
        return dict(self.user) if self.user else None

    async def select(self, table, **_kwargs):
        assert table == 'account_deletion_jobs'
        return [dict(self.deletion_job)] if self.deletion_job else []

    async def rpc(self, name, payload, retry_transient=False):
        self.rpc_calls.append((name, payload))
        self.events.append(('rpc', name, payload))
        if name == 'begin_video_account_deletion':
            if not self.video_starts_settled:
                return False
            token = payload['p_operation_token']
            if self.user and (
                self.user.get('deleted_at') or self.user.get('account_deletion_token')
            ):
                return bool(
                    self.user.get('deleted_at')
                    and self.user.get('account_deletion_token') == token
                    and self.fenced
                    and self.deletion_token == token
                )
            if self.fenced and self.deletion_token != token:
                return False
            self.deletion_token = token
            self.fenced = True
            self.video_fence_requested_at = datetime.now().astimezone().isoformat()
            if self.begin_commit_then_error:
                self.begin_commit_then_error = False
                raise RuntimeError('response lost after video fence commit')
            return True
        if name == 'establish_account_deletion_fence':
            if self.establish_forced_result:
                return self.establish_forced_result
            if self.deleted or self.user is None:
                return 'user_deleted'
            token = payload['p_operation_token']
            if (
                not self.deletion_job
                or self.deletion_job.get('operation_token') != token
                or self.deletion_job.get('completed_at')
            ):
                return 'job_unavailable'
            if not self.fenced or self.deletion_token != token:
                return 'video_fence_unavailable'
            if self.user.get('deleted_at') or self.user.get('account_deletion_token'):
                if (
                    self.user.get('deleted_at')
                    and self.user.get('account_deletion_token') == token
                ):
                    return 'fenced'
                return 'user_fence_conflict'
            fenced_at = payload['p_fenced_at']
            self.user.update({
                'deleted_at': fenced_at,
                'account_deletion_token': token,
                'ai_data_sharing_consent_revoked_at': fenced_at,
                'ai_data_sharing_consent_updated_at': fenced_at,
                'updated_at': fenced_at,
            })
            self.events.append(('fence', self.user['id']))
            return 'fenced'
        if name == 'recover_video_account_deletion_fence':
            if self.deleted or self.user is None:
                return 'user_deleted'
            token = payload['p_operation_token']
            if self.recovery_replacement_token:
                self.deletion_token = self.recovery_replacement_token
                self.fenced = True
            if self.user.get('deleted_at') or self.user.get('account_deletion_token'):
                return 'account_deleting'
            if self.deletion_job:
                if self.deletion_job.get('operation_token') != token:
                    return 'job_conflict'
                if not self.deletion_job.get('completed_at'):
                    return 'still_reconciling'
            if self.fenced and token != self.deletion_token:
                return 'not_owner'
            if self.fenced and payload.get('p_require_stale'):
                requested_at = datetime.fromisoformat(self.video_fence_requested_at)
                if requested_at > datetime.now().astimezone() - timedelta(minutes=15):
                    return 'still_reconciling'
            result = 'released' if self.fenced else 'already_released'
            self.fenced = False
            self.deletion_token = None
            if self.recovery_commit_then_error:
                self.recovery_commit_then_error = False
                raise RuntimeError('response lost after atomic recovery')
            return result
        if name == 'release_video_account_deletion_fence':
            if self.deleted or self.user is None:
                return 'user_deleted'
            if self.fenced and payload['p_operation_token'] == self.deletion_token:
                self.fenced = False
                self.deletion_token = None
                return 'released'
            return 'not_owner'
        if name == 'delete_user_account':
            if self.rpc_deletes_before_error:
                self.user = None
                self.deleted = True
            if self.rpc_error:
                raise RuntimeError('private database failure')
            self.user = None
            self.deleted = True
            return None
        raise AssertionError(name)


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


def rpc_names(fake_db):
    return [name for name, _ in fake_db.rpc_calls]


def expected_deletion_rpc_names(*tail, begin_count=3):
    names = [
        'begin_video_account_deletion',
        'begin_video_account_deletion',
        'establish_account_deletion_fence',
    ]
    names.extend(['begin_video_account_deletion'] * max(0, begin_count - 2))
    names.extend(tail)
    return names


def assert_shared_video_fence_token(fake_db, expected_count):
    calls = [
        payload
        for name, payload in fake_db.rpc_calls
        if name == 'begin_video_account_deletion'
    ]
    assert len(calls) == expected_count
    tokens = {payload['p_operation_token'] for payload in calls}
    assert len(tokens) == 1
    assert UUID(next(iter(tokens)))


def non_video_events(fake_db):
    return [
        event
        for event in fake_db.events
        if not (
            event[0] == 'rpc'
            and event[1] in {
                'begin_video_account_deletion',
                'establish_account_deletion_fence',
                'recover_video_account_deletion_fence',
            }
        )
    ]


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
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'recover_video_account_deletion_fence',
    ]
    assert fake_db.fenced is False
    assert fake_db.rpc_calls[0][1]['p_operation_token'] == fake_db.rpc_calls[1][1]['p_operation_token']
    assert fake_db.files.cleanup_calls == []


def test_billing_rollback_reconciles_a_lost_atomic_release_response(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user(), stripe_key=None)
    fake_db.recovery_commit_then_error = True

    response = delete_request()

    assert response.status_code == 502
    assert response.json()['code'] == 'BILLING_CANCELLATION_UNCONFIRMED'
    assert fake_db.fenced is False
    assert rpc_names(fake_db) == [
        'begin_video_account_deletion',
        'recover_video_account_deletion_fence',
    ]


def test_billing_rollback_never_releases_a_replaced_fence_token(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user(), stripe_key=None)
    replacement_token = '00000000-0000-4000-8000-000000000099'
    fake_db.recovery_replacement_token = replacement_token

    response = delete_request()

    assert response.status_code == 503
    assert response.json()['code'] == 'ACCOUNT_DELETION_RECOVERY_REQUIRED'
    assert fake_db.fenced is True
    assert fake_db.deletion_token == replacement_token


def test_ambiguous_initial_video_fence_is_recovered_when_readback_fails(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user(), stripe_key=None)
    fake_db.begin_commit_then_error = True
    fake_db.video_fence_read_failures = 1

    response = delete_request()

    assert response.status_code == 503
    assert response.json()['code'] == 'ACCOUNT_DELETION_FENCE_UNAVAILABLE'
    assert fake_db.fenced is False
    assert rpc_names(fake_db) == [
        'begin_video_account_deletion',
        'recover_video_account_deletion_fence',
    ]


def test_durable_begin_failure_invokes_recovery_but_keeps_recent_job_fenced(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(subscription_status='canceled'),
    )
    fake_db.establish_forced_result = 'job_unavailable'

    response = delete_request()

    assert response.status_code == 503
    assert response.json()['code'] == 'ACCOUNT_DELETION_FENCE_UNAVAILABLE'
    assert 'contact support' not in response.json()['error'].lower()
    assert fake_db.fenced is True
    assert fake_db.deletion_job.get('completed_at') is None
    assert rpc_names(fake_db)[-1] == 'recover_video_account_deletion_fence'


def test_ambiguous_reacquisition_after_stale_orphan_is_compensated(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(subscription_status='canceled'),
    )
    old_token = '00000000-0000-4000-8000-000000000090'
    fake_db.fenced = True
    fake_db.deletion_token = old_token
    fake_db.video_fence_requested_at = (
        datetime.now().astimezone() - timedelta(minutes=16)
    ).isoformat()
    # The first begin sees the old token, stale recovery releases it, and the
    # replacement begin commits before losing both its response and readback.
    fake_db.begin_commit_then_error = True
    fake_db.video_fence_read_failure_calls = {3}

    response = delete_request()

    assert response.status_code == 503
    assert response.json()['code'] == 'ACCOUNT_DELETION_FENCE_UNAVAILABLE'
    assert fake_db.fenced is False
    assert fake_db.deletion_job is None
    calls = [
        (name, payload['p_operation_token'])
        for name, payload in fake_db.rpc_calls
        if name in {
            'begin_video_account_deletion',
            'recover_video_account_deletion_fence',
        }
    ]
    assert [name for name, _token in calls] == [
        'begin_video_account_deletion',
        'recover_video_account_deletion_fence',
        'begin_video_account_deletion',
        'recover_video_account_deletion_fence',
    ]
    assert calls[0][1] != old_token
    assert calls[1][1] == old_token
    assert calls[2][1] == calls[0][1]
    assert calls[3][1] == calls[0][1]


def test_open_web_subscription_blocks_deletion_when_stripe_rejects_cleanup(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    calls = install_stripe_response(monkeypatch, FakeStripeResponse(500, {'error': 'fixture'}))

    response = delete_request()

    assert response.status_code == 502
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'recover_video_account_deletion_fence',
    ]
    assert fake_db.fenced is False
    assert calls[0][1].endswith('/customers/cus_delete_fixture')


def test_open_web_subscription_blocks_unconfirmed_success_payload(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    install_stripe_response(
        monkeypatch,
        FakeStripeResponse(200, {'deleted': True, 'id': 'cus_different'}),
    )

    response = delete_request()

    assert response.status_code == 502
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'recover_video_account_deletion_fence',
    ]
    assert fake_db.fenced is False


def test_deleted_stripe_customer_is_verified_before_local_retry(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    calls = install_stripe_response(
        monkeypatch,
        FakeStripeResponse(404, {'error': {'code': 'resource_missing'}}),
        lookup_response=FakeStripeResponse(
            200, {'id': 'cus_delete_fixture', 'deleted': True},
        ),
    )

    response = delete_request()

    assert response.status_code == 200
    assert len(calls) == 2
    assert calls[0][1] == calls[1][1]
    assert rpc_names(fake_db) == expected_deletion_rpc_names('delete_user_account')
    assert_shared_video_fence_token(fake_db, 3)


def test_confirmed_stripe_deletion_allows_atomic_local_deletion(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    install_stripe_response(
        monkeypatch,
        FakeStripeResponse(200, {'deleted': True, 'id': 'cus_delete_fixture'}),
    )

    response = delete_request()

    assert response.status_code == 200
    assert rpc_names(fake_db) == expected_deletion_rpc_names('delete_user_account')
    operation_tokens = [
        payload['p_operation_token']
        for name, payload in fake_db.rpc_calls
        if name == 'begin_video_account_deletion'
    ]
    assert len(set(operation_tokens)) == 1
    assert UUID(operation_tokens[0])
    assert ('fence', 'user-delete-1') in fake_db.events
    assert ('storage_cleanup', 'user-delete-1') in fake_db.events
    assert fake_db.events[-1] == (
        'rpc', 'delete_user_account', {'p_user_id': 'user-delete-1'},
    )


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
    assert rpc_names(fake_db) == expected_deletion_rpc_names('delete_user_account')


def test_terminal_subscription_preserves_privacy_deletion_when_cleanup_fails(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(subscription_status='canceled'),
    )
    install_stripe_response(monkeypatch, FakeStripeResponse(500, {'error': 'fixture'}))

    response = delete_request()

    assert response.status_code == 200
    assert rpc_names(fake_db) == expected_deletion_rpc_names('delete_user_account')
    assert_shared_video_fence_token(fake_db, 3)


def test_unsettled_video_reservation_defers_local_account_deletion(monkeypatch):
    fake_db = configure_account(
        monkeypatch, account_user(),
    )
    fake_db.video_starts_settled = False
    stripe_calls = install_stripe_response(
        monkeypatch, FakeStripeResponse(200, {'deleted': True, 'id': 'cus_delete_fixture'}),
    )

    response = delete_request()

    assert response.status_code == 409
    assert response.json()['code'] == 'VIDEO_START_SETTLING'
    assert [name for name, _ in fake_db.rpc_calls] == ['begin_video_account_deletion']
    assert fake_db.fenced is False
    assert stripe_calls == []


def test_failed_local_delete_keeps_durable_and_video_fences_for_retry(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(subscription_status='canceled'),
        rpc_error=True,
    )

    response = delete_request()

    assert response.status_code == 202
    assert response.json()['code'] == 'ACCOUNT_DELETION_RPC_UNCONFIRMED'
    assert fake_db.fenced is True
    assert fake_db.deleted is False
    assert rpc_names(fake_db) == expected_deletion_rpc_names('delete_user_account')
    assert_shared_video_fence_token(fake_db, 3)


def test_lost_local_delete_response_does_not_restore_deleted_account(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(subscription_status='canceled'),
        rpc_error=True,
        rpc_deletes_before_error=True,
    )

    response = delete_request()

    assert response.status_code == 200
    assert fake_db.deleted is True
    assert rpc_names(fake_db) == expected_deletion_rpc_names('delete_user_account')
    assert_shared_video_fence_token(fake_db, 3)


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
    assert rpc_names(fake_db) == expected_deletion_rpc_names()
    assert_shared_video_fence_token(fake_db, 3)
    assert non_video_events(fake_db) == [
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
    assert rpc_names(fake_db) == expected_deletion_rpc_names('delete_user_account')
    assert_shared_video_fence_token(fake_db, 3)
    assert non_video_events(fake_db) == [
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
    assert rpc_names(fake_db) == expected_deletion_rpc_names('delete_user_account')
    assert_shared_video_fence_token(fake_db, 3)
    assert non_video_events(fake_db) == [
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
    assert rpc_names(fake_db) == expected_deletion_rpc_names()
    assert_shared_video_fence_token(fake_db, 3)

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
    assert rpc_names(fake_db) == expected_deletion_rpc_names(
        'delete_user_account', begin_count=4,
    )
    assert_shared_video_fence_token(fake_db, 4)
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
    assert rpc_names(fake_db) == expected_deletion_rpc_names()
    assert_shared_video_fence_token(fake_db, 3)


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
    assert rpc_names(fake_db) == expected_deletion_rpc_names()
    assert_shared_video_fence_token(fake_db, 3)


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
    assert rpc_names(fake_db) == expected_deletion_rpc_names()
    assert_shared_video_fence_token(fake_db, 3)

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
    assert rpc_names(fake_db) == expected_deletion_rpc_names()
    assert_shared_video_fence_token(fake_db, 3)


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
    assert rpc_names(fake_db) == expected_deletion_rpc_names('delete_user_account')
    assert_shared_video_fence_token(fake_db, 3)


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
    assert rpc_names(fake_db) == expected_deletion_rpc_names()
    assert_shared_video_fence_token(fake_db, 3)

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
