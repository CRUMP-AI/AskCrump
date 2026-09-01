import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.routes import billing as billing_routes


ROOT = Path(__file__).resolve().parents[1]


class BillingDB:
    def __init__(self, user=None):
        self.user = user
        self.updates = []
        self.events = []

    async def select_one(self, table, *, columns='*', filters=None):
        assert table == 'users'
        return self.user

    async def update(self, table, payload, *, filters):
        self.updates.append((table, dict(payload), dict(filters)))
        return [dict(payload)]

    async def rpc(self, function, payload):
        assert function == 'record_product_event'
        self.events.append(dict(payload))
        return [True]


def request_stub():
    return SimpleNamespace(
        url=SimpleNamespace(hostname='askcrump.com'),
        headers={},
    )


def settings_stub():
    return SimpleNamespace(
        app_url='https://www.askcrump.com',
        stripe_professional_price_id='price_professional',
        stripe_enterprise_price_id='price_enterprise',
    )


def checkout_session(**overrides):
    session = {
        'id': 'cs_live_reconcile',
        'mode': 'subscription',
        'status': 'complete',
        'customer': 'cus_owner',
        'subscription': 'sub_paid',
        'client_reference_id': 'user-1',
        'metadata': {
            'purchase_type': 'subscription',
            'user_id': 'user-1',
            'tier': 'enterprise',
        },
    }
    session.update(overrides)
    return session


def stripe_subscription(
    *,
    status='active',
    price_id='price_professional',
    subscription_id='sub_paid',
    customer_id='cus_owner',
):
    return {
        'id': subscription_id,
        'customer': customer_id,
        'status': status,
        'current_period_end': 1_800_000_000,
        'items': {'data': [{'price': {'id': price_id}}]},
    }


def test_subscription_checkout_payload_has_reconcilable_return_and_dynamic_methods(monkeypatch):
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    payload = billing_routes.checkout_payload(
        'cus_owner',
        'user-1',
        'professional',
        'price_professional',
    )

    assert payload['success_url'].endswith(
        '/app?billing=success&session_id={CHECKOUT_SESSION_ID}'
    )
    assert 'payment_method_types' not in payload
    assert re.fullmatch(r'askcrump_subscription_[a-z]{8}', payload['integration_identifier'])
    assert billing_routes.STRIPE_API_VERSION == '2026-07-29.dahlia'


@pytest.mark.asyncio
async def test_stripe_post_sends_provider_idempotency_header(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {'id': 'cs_live_retry_safe'}

    class Client:
        def __init__(self, *, timeout):
            assert timeout == 25

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, auth, headers, data):
            captured.update(url=url, auth=auth, headers=dict(headers), data=dict(data))
            return Response()

    httpx = __import__('httpx')
    monkeypatch.setattr(httpx, 'AsyncClient', Client)
    monkeypatch.setattr(
        billing_routes,
        'settings',
        SimpleNamespace(stripe_secret_key='fixture-secret'),
    )

    result = await billing_routes.stripe_post(
        'checkout/sessions',
        {'mode': 'subscription'},
        idempotency_key='askcrump_subscription_retry_identity',
    )

    assert result['id'] == 'cs_live_retry_safe'
    assert captured['headers']['Stripe-Version'] == billing_routes.STRIPE_API_VERSION
    assert captured['headers']['Idempotency-Key'] == 'askcrump_subscription_retry_identity'
    assert captured['auth'] == ('fixture-secret', '')


@pytest.mark.asyncio
async def test_checkout_retry_reuses_stable_provider_idempotency(monkeypatch):
    user = {
        'id': 'user-1',
        'email': 'owner@example.com',
        'stripe_customer_id': 'cus_owner',
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user)

    calls = []

    async def stripe_post(path, data, *, idempotency_key=None):
        calls.append((path, dict(data), idempotency_key))
        return {
            'id': 'cs_live_retry_safe',
            'url': 'https://checkout.stripe.com/c/pay/cs_live_retry_safe',
        }

    monkeypatch.setattr(billing_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(billing_routes, 'stripe_post', stripe_post)
    request = SimpleNamespace(headers={}, url=SimpleNamespace(hostname='askcrump.com'))
    payload = billing_routes.CheckoutRequest(
        tier='professional',
        attemptId='web:11111111-2222-4333-8444-555555555555',
    )

    first = await billing_routes.create_checkout(payload, request)
    second = await billing_routes.create_checkout(payload, request)

    assert first['sessionId'] == second['sessionId'] == 'cs_live_retry_safe'
    assert calls[0][2] == calls[1][2]
    assert calls[0][1] == calls[1][1]
    assert calls[0][1]['integration_identifier'] == calls[1][1]['integration_identifier']


@pytest.mark.asyncio
async def test_past_due_subscription_routes_to_management_instead_of_duplicate_checkout(monkeypatch):
    user = {
        'id': 'user-1',
        'email': 'owner@example.com',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_needs_attention',
        'subscription_tier': 'free',
        'subscription_status': 'past_due',
        'subscription_provider': 'stripe',
    }
    monkeypatch.setattr(billing_routes, 'db', BillingDB(user=user))
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user)

    async def unexpected_stripe_post(*_args, **_kwargs):
        raise AssertionError('past-due accounts must not create a second subscription')

    monkeypatch.setattr(billing_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(billing_routes, 'stripe_post', unexpected_stripe_post)
    request = SimpleNamespace(headers={}, url=SimpleNamespace(hostname='askcrump.com'))

    response = await billing_routes.create_checkout(
        billing_routes.CheckoutRequest(tier='enterprise'),
        request,
    )

    assert response.status_code == 409
    assert b'SUBSCRIPTION_ALREADY_ACTIVE' in response.body
    assert b'stripe' in response.body


@pytest.mark.asyncio
async def test_checkout_reconciliation_uses_actual_subscription_price_not_metadata(monkeypatch):
    fake_db = BillingDB()
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def stripe_get(_path):
        return stripe_subscription(price_id='price_professional')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)
    user = {
        'id': 'user-1',
        'email': 'owner@example.com',
        'stripe_customer_id': 'cus_owner',
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }

    result = await billing_routes.reconcile_stripe_checkout_session(
        user=user,
        session=checkout_session(),
        request=request_stub(),
    )

    assert result['entitled'] is True
    assert result['tier'] == 'professional'
    assert fake_db.updates[0][1]['subscription_tier'] == 'professional'
    assert fake_db.updates[0][1]['subscription_status'] == 'active'
    assert fake_db.events[0]['p_event_name'] == 'SubscriptionCheckoutCompleted'
    assert fake_db.events[0]['p_event_key'] == 'cs_live_reconcile'
    assert fake_db.events[0]['p_plan'] == 'professional'


@pytest.mark.asyncio
async def test_checkout_reconciliation_never_entitles_incomplete_subscription(monkeypatch):
    fake_db = BillingDB()
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def stripe_get(_path):
        return stripe_subscription(status='incomplete', price_id='price_enterprise')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }

    result = await billing_routes.reconcile_stripe_checkout_session(
        user=user,
        session=checkout_session(),
        request=request_stub(),
    )

    assert result['entitled'] is False
    assert result['tier'] == 'enterprise'
    assert result['user']['tier'] == 'free'
    assert fake_db.updates[0][1]['subscription_tier'] == 'enterprise'
    assert fake_db.updates[0][1]['subscription_status'] == 'incomplete'
    assert fake_db.events == []


@pytest.mark.asyncio
async def test_checkout_reconciliation_rejects_cross_account_session_before_lookup(monkeypatch):
    fake_db = BillingDB()
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    looked_up = False

    async def stripe_get(_path):
        nonlocal looked_up
        looked_up = True
        return stripe_subscription()

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)
    user = {'id': 'user-1', 'stripe_customer_id': 'cus_owner'}
    session = checkout_session(
        client_reference_id='user-2',
        metadata={'purchase_type': 'subscription', 'user_id': 'user-2'},
    )

    with pytest.raises(PermissionError):
        await billing_routes.reconcile_stripe_checkout_session(
            user=user,
            session=session,
            request=request_stub(),
        )

    assert looked_up is False
    assert fake_db.updates == []


@pytest.mark.asyncio
async def test_finalize_checkout_returns_provider_failure_for_stripe_outage(monkeypatch):
    fake_db = BillingDB()
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'user-1', 'stripe_customer_id': 'cus_owner'})

    async def stripe_get(_path):
        raise billing_routes.StripeAPIError('temporarily unavailable')

    class Request:
        headers = {}

        async def json(self):
            return {'sessionId': 'cs_live_reconcile'}

    monkeypatch.setattr(billing_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    response = await billing_routes.finalize_checkout(Request())

    assert response.status_code == 502
    assert b'BILLING_PROVIDER_UNAVAILABLE' in response.body


@pytest.mark.asyncio
async def test_webhook_and_browser_share_checkout_session_conversion_key(monkeypatch):
    user = {
        'id': 'user-1',
        'email': 'owner@example.com',
        'stripe_customer_id': 'cus_owner',
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    monkeypatch.setattr(billing_routes, 'verify_stripe_signature', lambda _body, _header: True)

    async def stripe_get(_path):
        return stripe_subscription(price_id='price_professional')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)
    event = {
        'id': 'evt_delivery_attempt',
        'type': 'checkout.session.completed',
        'data': {'object': checkout_session()},
    }

    class Request:
        headers = {'stripe-signature': 'verified'}
        url = SimpleNamespace(hostname='askcrump.com')

        async def body(self):
            return json.dumps(event).encode('utf-8')

    result = await billing_routes.stripe_webhook(Request())

    assert result == {'received': True}
    assert fake_db.events[0]['p_event_key'] == 'cs_live_reconcile'
    assert fake_db.events[0]['p_event_key'] != 'evt_delivery_attempt'


@pytest.mark.asyncio
async def test_subscription_update_fetches_latest_provider_state_before_mutation(monkeypatch):
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_paid',
        'subscription_tier': 'professional',
        'subscription_status': 'active',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def stripe_get(path):
        assert path == 'subscriptions/sub_paid'
        return stripe_subscription(status='past_due', price_id='price_professional')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)
    applied = await billing_routes.reconcile_stripe_subscription_event(
        event_object=stripe_subscription(status='active', price_id='price_enterprise'),
        event_id='evt_delayed_active',
        event_type='customer.subscription.updated',
        request=request_stub(),
    )

    assert applied is True
    assert fake_db.updates[0][1]['subscription_status'] == 'past_due'
    assert fake_db.updates[0][1]['subscription_tier'] == 'professional'
    assert fake_db.events[0]['p_event_key'] == 'evt_delayed_active'


@pytest.mark.asyncio
async def test_superseded_subscription_event_cannot_roll_back_current_subscription(monkeypatch):
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_current',
        'subscription_tier': 'enterprise',
        'subscription_status': 'active',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    provider_looked_up = False

    async def stripe_get(_path):
        nonlocal provider_looked_up
        provider_looked_up = True
        return stripe_subscription()

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)
    applied = await billing_routes.reconcile_stripe_subscription_event(
        event_object=stripe_subscription(
            status='canceled',
            subscription_id='sub_previous',
        ),
        event_id='evt_old_delete',
        event_type='customer.subscription.deleted',
        request=request_stub(),
    )

    assert applied is False
    assert provider_looked_up is False
    assert fake_db.updates == []
    assert fake_db.events == []


@pytest.mark.asyncio
async def test_billing_status_exposes_recovery_for_non_entitled_stripe_subscription(monkeypatch):
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_needs_attention',
        'subscription_tier': 'professional',
        'subscription_status': 'past_due',
        'subscription_provider': 'stripe',
    }
    monkeypatch.setattr(billing_routes, 'db', BillingDB(user=user))
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user)

    monkeypatch.setattr(billing_routes, 'authenticate_request', authenticate)
    result = await billing_routes.billing_status(SimpleNamespace(headers={}))

    assert result['tier'] == 'free'
    assert result['plan'] == 'professional'
    assert result['status'] == 'past_due'
    assert result['provider'] == 'stripe'
    assert result['manageable'] is True


def test_subscription_return_frontend_finalizes_and_retries_once():
    source = (ROOT / 'public' / 'crump-billing-5.1.js').read_text(encoding='utf-8')

    assert "billing === 'success' && sessionId" in source
    assert "'/api/stripe/finalize-checkout'" in source
    assert 'for (let attempt = 0; attempt < 2; attempt += 1)' in source
    assert "'SUBSCRIPTION_PENDING'" in source
    assert "url.searchParams.delete('session_id')" in source


def test_all_web_subscription_launchers_send_retry_identity_and_recover_billing():
    manager = (ROOT / 'public' / 'billing-manager.js').read_text(encoding='utf-8')
    billing = (ROOT / 'public' / 'crump-billing-5.1.js').read_text(encoding='utf-8')
    subscriptions = (ROOT / 'public' / 'crump-subscriptions-5.3.2.js').read_text(
        encoding='utf-8'
    )
    legacy = (ROOT / 'public' / 'subscription-ui.js').read_text(encoding='utf-8')

    assert 'subscriptionCheckoutAttempt' in manager
    assert 'completeSubscriptionCheckoutAttempt' in manager
    for source in (billing, subscriptions, legacy):
        assert 'subscriptionCheckoutAttempt?.(tier)' in source
        assert 'JSON.stringify({tier,attemptId})' in re.sub(r'\s+', '', source)
        assert 'completeSubscriptionCheckoutAttempt?.(tier, attemptId)' in source
    assert 'function billingAttentionCard(billingStatus)' in subscriptions
    assert "title.textContent = 'Your subscription needs attention'" in subscriptions
    assert ": 'Fix billing';" in subscriptions
    assert 'recoveryRequired' in subscriptions
    assert 'Boolean(billingStatus?.manageable)' in subscriptions
    assert 'Boolean(billingStatus?.manageable)' in billing
