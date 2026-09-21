from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
import httpx

import app as app_module
from backend.db import DatabaseError
from backend.routes import account as account_routes
from backend.security import hash_password


client = TestClient(app_module.app)
PUBLIC = Path(__file__).resolve().parents[1] / 'public'


class FakeDB:
    def __init__(self):
        self.rpc_calls = []
        self.video_starts_settled = True
        self.fenced = False
        self.deleted = False
        self.deletion_token = None
        self.delete_error = False
        self.delete_committed = False

    async def rpc(self, name, payload, **_kwargs):
        self.rpc_calls.append((name, payload))
        if name == 'begin_video_account_deletion':
            if not self.video_starts_settled:
                return False
            self.deletion_token = payload['p_operation_token']
            self.fenced = True
            return True
        if name == 'release_video_account_deletion_fence':
            if self.deleted:
                return 'user_deleted'
            if self.fenced and payload['p_operation_token'] == self.deletion_token:
                self.fenced = False
                self.deletion_token = None
                return 'released'
            return 'not_owner'
        if name == 'delete_user_account':
            if self.delete_error:
                self.deleted = self.delete_committed
                raise DatabaseError('fixture deletion failure', 503)
            self.deleted = True
            return None


class FakeStripeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload

    def json(self):
        return self.payload


def configure_account(monkeypatch, user, *, stripe_key='sk_test_fixture'):
    fake_db = FakeDB()

    async def fake_authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user, session={'id': 'session-1'}, token='token')

    monkeypatch.setattr(account_routes, 'db', fake_db)
    monkeypatch.setattr(account_routes, 'authenticate_request', fake_authenticate)
    monkeypatch.setattr(
        account_routes,
        'settings',
        SimpleNamespace(
            stripe_secret_key=stripe_key,
            revenuecat_secret_api_key=None,
        ),
    )
    return fake_db


def install_stripe_response(monkeypatch, response, *, lookup_response=None):
    calls = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def delete(self, url, **kwargs):
            calls.append((url, kwargs))
            return response

        async def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return lookup_response or FakeStripeResponse(404, {})

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
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'release_video_account_deletion_fence',
    ]
    assert fake_db.fenced is False
    assert fake_db.rpc_calls[0][1]['p_operation_token'] == fake_db.rpc_calls[1][1]['p_operation_token']


def test_open_web_subscription_blocks_deletion_when_stripe_rejects_cleanup(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    calls = install_stripe_response(monkeypatch, FakeStripeResponse(500, {'error': 'fixture'}))

    response = delete_request()

    assert response.status_code == 502
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'release_video_account_deletion_fence',
    ]
    assert fake_db.fenced is False
    assert calls[0][0].endswith('/customers/cus_delete_fixture')


def test_open_web_subscription_blocks_unconfirmed_success_payload(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    install_stripe_response(
        monkeypatch,
        FakeStripeResponse(200, {'deleted': True, 'id': 'cus_different'}),
    )

    response = delete_request()

    assert response.status_code == 502
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'release_video_account_deletion_fence',
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
    assert calls[0][0] == calls[1][0]
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'delete_user_account',
    ]


def test_confirmed_stripe_deletion_allows_atomic_local_deletion(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    install_stripe_response(
        monkeypatch,
        FakeStripeResponse(200, {'deleted': True, 'id': 'cus_delete_fixture'}),
    )

    response = delete_request()

    assert response.status_code == 200
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'delete_user_account',
    ]
    assert fake_db.rpc_calls[0][1]['p_user_id'] == 'user-delete-1'
    assert UUID(fake_db.rpc_calls[0][1]['p_operation_token'])


def test_terminal_subscription_preserves_privacy_deletion_when_cleanup_fails(monkeypatch):
    fake_db = configure_account(
        monkeypatch,
        account_user(subscription_status='canceled'),
    )
    install_stripe_response(monkeypatch, FakeStripeResponse(500, {'error': 'fixture'}))

    response = delete_request()

    assert response.status_code == 200
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'delete_user_account',
    ]


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


def test_failed_local_delete_releases_active_account_fence(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user(subscription_status='canceled'))
    fake_db.delete_error = True

    response = delete_request()

    assert response.status_code == 503
    assert response.json()['code'] == 'ACCOUNT_DELETION_RETRY'
    assert fake_db.fenced is False
    assert fake_db.deleted is False
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'delete_user_account',
        'release_video_account_deletion_fence',
    ]
    assert fake_db.rpc_calls[0][1]['p_operation_token'] == fake_db.rpc_calls[-1][1]['p_operation_token']


def test_lost_local_delete_response_does_not_restore_deleted_account(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user(subscription_status='canceled'))
    fake_db.delete_error = True
    fake_db.delete_committed = True

    response = delete_request()

    assert response.status_code == 200
    assert fake_db.deleted is True
    assert [name for name, _ in fake_db.rpc_calls] == [
        'begin_video_account_deletion', 'delete_user_account',
        'release_video_account_deletion_fence',
    ]


def test_account_deletion_copy_distinguishes_web_and_store_billing():
    account_manager = (PUBLIC / 'account-manager.js').read_text(encoding='utf-8')
    deletion_page = (PUBLIC / 'delete-account.html').read_text(encoding='utf-8')
    legal_page = (PUBLIC / 'legal.html').read_text(encoding='utf-8')

    for source in (account_manager, deletion_page, legal_page):
        assert 'web subscription' in source
        assert 'refund' in source
        assert 'Apple App Store' in source
        assert 'Google Play' in source
