from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx

import app as app_module
from backend.routes import account as account_routes
from backend.security import hash_password


client = TestClient(app_module.app)
PUBLIC = Path(__file__).resolve().parents[1] / 'public'


class FakeDB:
    def __init__(self):
        self.rpc_calls = []

    async def rpc(self, name, payload):
        self.rpc_calls.append((name, payload))


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


def install_stripe_response(monkeypatch, response):
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


def test_open_web_subscription_blocks_deletion_when_stripe_rejects_cleanup(monkeypatch):
    fake_db = configure_account(monkeypatch, account_user())
    calls = install_stripe_response(monkeypatch, FakeStripeResponse(500, {'error': 'fixture'}))

    response = delete_request()

    assert response.status_code == 502
    assert fake_db.rpc_calls == []
    assert calls[0][0].endswith('/customers/cus_delete_fixture')


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


def test_account_deletion_copy_distinguishes_web_and_store_billing():
    account_manager = (PUBLIC / 'account-manager.js').read_text(encoding='utf-8')
    deletion_page = (PUBLIC / 'delete-account.html').read_text(encoding='utf-8')
    legal_page = (PUBLIC / 'legal.html').read_text(encoding='utf-8')

    for source in (account_manager, deletion_page, legal_page):
        assert 'web subscription' in source
        assert 'refund' in source
        assert 'Apple App Store' in source
        assert 'Google Play' in source
