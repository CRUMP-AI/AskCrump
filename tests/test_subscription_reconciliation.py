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


@pytest.mark.asyncio
@pytest.mark.parametrize('body', [b'{broken', b'[]', b'"event"', b'\xff'])
async def test_subscription_webhook_rejects_signed_non_event_payloads(monkeypatch, body):
    monkeypatch.setattr(billing_routes, 'verify_stripe_signature', lambda *_args: True)

    class Request:
        headers = {'stripe-signature': 'verified'}

        async def body(self):
            return body

    response = await billing_routes.stripe_webhook(Request())

    assert response.status_code == 400
    assert b'Invalid webhook payload.' in response.body


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'event',
    [
        {'type': 'checkout.session.completed', 'data': []},
        {'type': 'checkout.session.completed', 'data': {'object': []}},
        {'type': 'checkout.session.async_payment_succeeded', 'data': []},
        {'type': 'checkout.session.async_payment_failed', 'data': {'object': []}},
        {
            'type': 'checkout.session.completed',
            'data': {'object': {'metadata': []}},
        },
        {'type': 'customer.subscription.updated', 'data': {'object': []}},
    ],
)
async def test_subscription_webhook_rejects_malformed_supported_event_envelopes(
    monkeypatch,
    event,
):
    monkeypatch.setattr(billing_routes, 'verify_stripe_signature', lambda *_args: True)

    class Request:
        headers = {'stripe-signature': 'verified'}

        async def body(self):
            return json.dumps(event).encode('utf-8')

    response = await billing_routes.stripe_webhook(Request())

    assert response.status_code == 400
    assert b'Invalid webhook payload.' in response.body


def checkout_session(**overrides):
    session = {
        'id': 'cs_live_reconcile',
        'mode': 'subscription',
        'status': 'complete',
        'payment_status': 'paid',
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
@pytest.mark.parametrize('payment_status', ['paid', 'no_payment_required'])
async def test_checkout_reconciliation_uses_actual_subscription_price_not_metadata(
    monkeypatch,
    payment_status,
):
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
        session=checkout_session(payment_status=payment_status),
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
async def test_checkout_reconciliation_rejects_unpaid_session_before_provider_or_database(
    monkeypatch,
):
    fake_db = BillingDB()
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    provider_paths = []

    async def stripe_get(path):
        provider_paths.append(path)
        return stripe_subscription()

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }

    with pytest.raises(RuntimeError, match='payment has not completed'):
        await billing_routes.reconcile_stripe_checkout_session(
            user=user,
            session=checkout_session(payment_status='unpaid'),
            request=request_stub(),
        )

    assert provider_paths == []
    assert fake_db.updates == []
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
@pytest.mark.parametrize(
    'event_type',
    ['checkout.session.completed', 'checkout.session.async_payment_succeeded'],
)
async def test_webhook_and_browser_share_checkout_session_conversion_key(monkeypatch, event_type):
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
        'type': event_type,
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
@pytest.mark.parametrize(
    ('event_type', 'payment_status'),
    [
        ('checkout.session.completed', 'unpaid'),
        ('checkout.session.async_payment_failed', 'unpaid'),
    ],
)
async def test_delayed_subscription_checkout_does_not_mutate_before_payment(
    monkeypatch,
    event_type,
    payment_status,
):
    class NoDatabaseAccess:
        async def select_one(self, *_args, **_kwargs):
            raise AssertionError('unpaid or failed Checkout must not read customer state')

    async def unexpected_stripe_get(path):
        raise AssertionError(f'unpaid or failed Checkout must not look up {path}')

    monkeypatch.setattr(billing_routes, 'db', NoDatabaseAccess())
    monkeypatch.setattr(billing_routes, 'verify_stripe_signature', lambda *_args: True)
    monkeypatch.setattr(billing_routes, 'stripe_get', unexpected_stripe_get)
    event = {
        'id': 'evt_delayed_subscription',
        'type': event_type,
        'data': {'object': checkout_session(payment_status=payment_status)},
    }

    class Request:
        headers = {'stripe-signature': 'verified'}
        url = SimpleNamespace(hostname='askcrump.com')

        async def body(self):
            return json.dumps(event).encode('utf-8')

    response = await billing_routes.stripe_webhook(Request())

    assert response == {'received': True}


@pytest.mark.asyncio
async def test_finalize_checkout_reports_unpaid_session_as_pending(monkeypatch):
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user)

    async def stripe_get(path):
        assert path == 'checkout/sessions/cs_live_reconcile'
        return checkout_session(payment_status='unpaid')

    class Request:
        headers = {}

        async def json(self):
            return {'sessionId': 'cs_live_reconcile'}

    monkeypatch.setattr(billing_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    response = await billing_routes.finalize_checkout(Request())

    assert response.status_code == 409
    assert b'SUBSCRIPTION_PENDING' in response.body
    assert b'payment has not completed yet' in response.body
    assert b'payment is complete' not in response.body
    assert fake_db.updates == []
    assert fake_db.events == []


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
async def test_superseded_checkout_session_cannot_roll_back_current_subscription(monkeypatch):
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_current',
        'subscription_tier': 'enterprise',
        'subscription_status': 'active',
        'subscription_provider': 'stripe',
        'subscription_current_period_end': '2027-01-15T08:00:00+00:00',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    provider_paths = []

    async def stripe_get(path):
        provider_paths.append(path)
        if path == 'subscriptions/sub_current':
            return stripe_subscription(
                status='active',
                price_id='price_enterprise',
                subscription_id='sub_current',
            )
        raise AssertionError(f'superseded checkout must not look up {path}')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    reconciled = await billing_routes.reconcile_stripe_checkout_session(
        user=user,
        session=checkout_session(subscription='sub_previous'),
        request=request_stub(),
    )

    assert reconciled['entitled'] is True
    assert reconciled['tier'] == 'enterprise'
    assert reconciled['status'] == 'active'
    assert fake_db.updates == []
    assert fake_db.events == []
    assert provider_paths == []

    applied = await billing_routes.reconcile_stripe_subscription_event(
        event_object=stripe_subscription(
            status='active',
            price_id='price_enterprise',
            subscription_id='sub_current',
        ),
        event_id='evt_current_update',
        event_type='customer.subscription.updated',
        request=request_stub(),
    )

    assert applied is True
    assert provider_paths == ['subscriptions/sub_current']
    assert fake_db.updates[0][1]['stripe_subscription_id'] == 'sub_current'
    assert fake_db.events[0]['p_event_key'] == 'evt_current_update'


@pytest.mark.asyncio
async def test_webhook_ignores_superseded_completed_checkout_session(monkeypatch):
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_current',
        'subscription_tier': 'professional',
        'subscription_status': 'active',
        'subscription_provider': 'stripe',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    monkeypatch.setattr(billing_routes, 'verify_stripe_signature', lambda *_args: True)

    async def unexpected_stripe_get(path):
        raise AssertionError(f'superseded webhook must not look up {path}')

    monkeypatch.setattr(billing_routes, 'stripe_get', unexpected_stripe_get)
    event = {
        'id': 'evt_old_checkout_delivery',
        'type': 'checkout.session.completed',
        'data': {'object': checkout_session(subscription='sub_previous')},
    }

    class Request:
        headers = {'stripe-signature': 'verified'}
        url = SimpleNamespace(hostname='askcrump.com')

        async def body(self):
            return json.dumps(event).encode('utf-8')

    response = await billing_routes.stripe_webhook(Request())

    assert response == {'received': True}
    assert fake_db.updates == []
    assert fake_db.events == []


@pytest.mark.asyncio
async def test_checkout_reconciliation_allows_resubscription_after_terminal_state(monkeypatch):
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_previous',
        'subscription_tier': 'free',
        'subscription_status': 'canceled',
        'subscription_provider': 'stripe',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def stripe_get(path):
        assert path == 'subscriptions/sub_current'
        return stripe_subscription(
            status='active',
            price_id='price_professional',
            subscription_id='sub_current',
        )

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    reconciled = await billing_routes.reconcile_stripe_checkout_session(
        user=user,
        session=checkout_session(subscription='sub_current'),
        request=request_stub(),
    )

    assert reconciled['entitled'] is True
    assert reconciled['tier'] == 'professional'
    assert fake_db.updates[0][1]['stripe_subscription_id'] == 'sub_current'
    assert fake_db.updates[0][2] == {
        'id': 'eq.user-1',
        'stripe_customer_id': 'eq.cus_owner',
        'stripe_subscription_id': 'eq.sub_previous',
        'subscription_tier': 'eq.free',
        'subscription_status': 'eq.canceled',
        'subscription_provider': 'eq.stripe',
        'subscription_current_period_end': 'is.null',
    }
    assert fake_db.events[0]['p_event_name'] == 'SubscriptionCheckoutCompleted'


@pytest.mark.asyncio
async def test_checkout_reconciliation_cas_loss_preserves_newer_subscription(monkeypatch):
    original_user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_previous',
        'subscription_tier': 'free',
        'subscription_status': 'canceled',
        'subscription_provider': 'stripe',
    }
    winning_user = {
        **original_user,
        'stripe_subscription_id': 'sub_newer',
        'subscription_tier': 'enterprise',
        'subscription_status': 'active',
        'subscription_current_period_end': '2027-02-01T08:00:00+00:00',
    }

    class RacingBillingDB(BillingDB):
        async def update(self, table, payload, *, filters):
            self.updates.append((table, dict(payload), dict(filters)))
            self.user = winning_user
            return []

    fake_db = RacingBillingDB(user=original_user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def stripe_get(path):
        assert path == 'subscriptions/sub_candidate'
        return stripe_subscription(
            status='active',
            price_id='price_professional',
            subscription_id='sub_candidate',
        )

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    reconciled = await billing_routes.reconcile_stripe_checkout_session(
        user=original_user,
        session=checkout_session(subscription='sub_candidate'),
        request=request_stub(),
    )

    assert reconciled['entitled'] is True
    assert reconciled['tier'] == 'enterprise'
    assert reconciled['status'] == 'active'
    assert fake_db.updates[0][2]['stripe_subscription_id'] == 'eq.sub_previous'
    assert fake_db.events == []


@pytest.mark.asyncio
async def test_checkout_reconciliation_cas_loss_preserves_same_subscription_lifecycle(
    monkeypatch,
):
    original_user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_current',
        'subscription_tier': 'professional',
        'subscription_status': 'active',
        'subscription_provider': 'stripe',
        'subscription_current_period_end': '2027-01-15T08:00:00+00:00',
    }
    winning_user = {
        **original_user,
        'subscription_tier': 'free',
        'subscription_status': 'canceled',
        'subscription_current_period_end': '2026-12-01T08:00:00+00:00',
    }

    class RacingBillingDB(BillingDB):
        async def update(self, table, payload, *, filters):
            self.updates.append((table, dict(payload), dict(filters)))
            self.user = winning_user
            return []

    fake_db = RacingBillingDB(user=original_user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def stripe_get(path):
        assert path == 'subscriptions/sub_current'
        return stripe_subscription(
            status='active',
            price_id='price_professional',
            subscription_id='sub_current',
        )

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    reconciled = await billing_routes.reconcile_stripe_checkout_session(
        user=original_user,
        session=checkout_session(subscription='sub_current'),
        request=request_stub(),
    )

    assert reconciled['entitled'] is False
    assert reconciled['tier'] == 'free'
    assert reconciled['status'] == 'canceled'
    assert fake_db.updates[0][2]['subscription_status'] == 'eq.active'
    assert fake_db.updates[0][2]['subscription_tier'] == 'eq.professional'
    assert fake_db.events == []


@pytest.mark.asyncio
async def test_checkout_reconciliation_cas_loss_records_exact_winning_subscription(
    monkeypatch,
):
    original_user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_previous',
        'subscription_tier': 'free',
        'subscription_status': 'canceled',
        'subscription_provider': 'stripe',
        'subscription_current_period_end': None,
    }
    winning_user = {
        **original_user,
        'stripe_subscription_id': 'sub_current',
        'subscription_tier': 'professional',
        'subscription_status': 'active',
        'subscription_current_period_end': '2027-01-15T08:00:00+00:00',
    }

    class RacingBillingDB(BillingDB):
        async def update(self, table, payload, *, filters):
            self.updates.append((table, dict(payload), dict(filters)))
            self.user = winning_user
            return []

    fake_db = RacingBillingDB(user=original_user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())

    async def stripe_get(path):
        assert path == 'subscriptions/sub_current'
        return stripe_subscription(
            status='active',
            price_id='price_professional',
            subscription_id='sub_current',
        )

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    reconciled = await billing_routes.reconcile_stripe_checkout_session(
        user=original_user,
        session=checkout_session(subscription='sub_current'),
        request=request_stub(),
    )

    assert reconciled['entitled'] is True
    assert reconciled['tier'] == 'professional'
    assert reconciled['status'] == 'active'
    assert len(fake_db.events) == 1
    assert fake_db.events[0]['p_event_name'] == 'SubscriptionCheckoutCompleted'
    assert fake_db.events[0]['p_event_key'] == 'cs_live_reconcile'
    assert fake_db.events[0]['p_plan'] == 'professional'


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


def reset_price_resolution_caches(monkeypatch):
    monkeypatch.setattr(billing_routes, '_STRIPE_PRICE_TIER_CACHE', {})
    monkeypatch.setattr(billing_routes, '_STRIPE_TIER_PRODUCT_CACHE', {})


@pytest.mark.asyncio
async def test_exact_configured_price_mapping_remains_provider_call_free(monkeypatch):
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    reset_price_resolution_caches(monkeypatch)

    async def unexpected_stripe_get(path):
        raise AssertionError(f'exact configured price must not look up {path}')

    monkeypatch.setattr(billing_routes, 'stripe_get', unexpected_stripe_get)

    assert await billing_routes.stripe_price_tier('price_professional') == (
        'professional'
    )
    assert await billing_routes.stripe_price_tier('price_enterprise') == 'enterprise'
    assert billing_routes._STRIPE_PRICE_TIER_CACHE == {}
    assert billing_routes._STRIPE_TIER_PRODUCT_CACHE == {}


@pytest.mark.asyncio
async def test_checkout_reconciliation_resolves_rotated_price_by_product(monkeypatch):
    """An entitled subscription on a rotated (legacy) price keeps its tier.

    Regression test for the Free-while-Pro sync gap: the old code mapped any
    price ID outside the configured catalog to 'free' even while Stripe
    reported the subscription as active.
    """
    fake_db = BillingDB()
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    reset_price_resolution_caches(monkeypatch)

    async def stripe_get(path):
        if path == 'subscriptions/sub_legacy':
            return stripe_subscription(
                status='active',
                price_id='price_legacy_professional_20',
                subscription_id='sub_legacy',
            )
        if path == 'prices/price_legacy_professional_20':
            return {'id': 'price_legacy_professional_20', 'product': 'prod_pro_legacy'}
        if path == 'prices/price_professional':
            return {'id': 'price_professional', 'product': 'prod_pro_legacy'}
        if path == 'prices/price_enterprise':
            return {'id': 'price_enterprise', 'product': 'prod_ent'}
        raise AssertionError(f'unexpected Stripe lookup {path}')

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
        session=checkout_session(subscription='sub_legacy'),
        request=request_stub(),
    )

    assert result['entitled'] is True
    assert result['tier'] == 'professional'
    assert fake_db.updates[0][1]['subscription_tier'] == 'professional'
    assert fake_db.updates[0][1]['subscription_status'] == 'active'
    assert fake_db.events[0]['p_plan'] == 'professional'


@pytest.mark.asyncio
async def test_subscription_event_preserves_paid_tier_when_price_unresolvable(monkeypatch):
    """An entitled subscription on a fully unrecognized price keeps its tier.

    When even product-level resolution fails, reconciliation must fail closed
    on entitlements: it preserves the stored paid tier instead of writing
    'free' while Stripe still bills the customer.
    """
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
    reset_price_resolution_caches(monkeypatch)

    async def stripe_get(path):
        if path == 'subscriptions/sub_paid':
            return stripe_subscription(status='active', price_id='price_mystery')
        if path == 'prices/price_mystery':
            return {'id': 'price_mystery', 'product': 'prod_unknown'}
        if path == 'prices/price_professional':
            return {'id': 'price_professional', 'product': 'prod_pro'}
        if path == 'prices/price_enterprise':
            return {'id': 'price_enterprise', 'product': 'prod_ent'}
        raise AssertionError(f'unexpected Stripe lookup {path}')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)
    applied = await billing_routes.reconcile_stripe_subscription_event(
        event_object=stripe_subscription(status='active', price_id='price_mystery'),
        event_id='evt_unknown_price',
        event_type='customer.subscription.updated',
        request=request_stub(),
    )

    assert applied is True
    assert fake_db.updates[0][1]['subscription_tier'] == 'professional'
    assert fake_db.updates[0][1]['subscription_status'] == 'active'


@pytest.mark.asyncio
async def test_subscription_event_still_defaults_free_for_unentitled_unknown_price(monkeypatch):
    """Preservation never grants a paid tier: unknown price + no entitlement stays free."""
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_paid',
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    reset_price_resolution_caches(monkeypatch)

    async def stripe_get(path):
        if path == 'subscriptions/sub_paid':
            return stripe_subscription(status='incomplete_expired', price_id='price_mystery')
        if path == 'prices/price_mystery':
            return {'id': 'price_mystery', 'product': 'prod_unknown'}
        if path == 'prices/price_professional':
            return {'id': 'price_professional', 'product': 'prod_pro'}
        if path == 'prices/price_enterprise':
            return {'id': 'price_enterprise', 'product': 'prod_ent'}
        raise AssertionError(f'unexpected Stripe lookup {path}')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)
    applied = await billing_routes.reconcile_stripe_subscription_event(
        event_object=stripe_subscription(
            status='incomplete_expired', price_id='price_mystery'
        ),
        event_id='evt_unknown_price_expired',
        event_type='customer.subscription.updated',
        request=request_stub(),
    )

    assert applied is True
    assert fake_db.updates[0][1]['subscription_tier'] == 'free'
    assert fake_db.updates[0][1]['subscription_status'] == 'incomplete_expired'


@pytest.mark.asyncio
async def test_transient_price_lookup_webhook_retries_and_recovers_in_warm_process(
    monkeypatch,
):
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_paid',
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    monkeypatch.setattr(billing_routes, 'verify_stripe_signature', lambda *_args: True)
    reset_price_resolution_caches(monkeypatch)
    rotated_attempts = 0

    async def stripe_get(path):
        nonlocal rotated_attempts
        if path == 'subscriptions/sub_paid':
            return stripe_subscription(
                status='active',
                price_id='price_rotated_professional',
                subscription_id='sub_paid',
            )
        if path == 'prices/price_rotated_professional':
            rotated_attempts += 1
            if rotated_attempts == 1:
                raise billing_routes.StripeAPIError('temporary price outage')
            return {
                'id': 'price_rotated_professional',
                'product': 'prod_professional',
            }
        if path == 'prices/price_enterprise':
            return {'id': 'price_enterprise', 'product': 'prod_enterprise'}
        if path == 'prices/price_professional':
            return {'id': 'price_professional', 'product': 'prod_professional'}
        raise AssertionError(f'unexpected Stripe lookup {path}')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)
    event = {
        'id': 'evt_rotated_price',
        'type': 'customer.subscription.updated',
        'data': {
            'object': stripe_subscription(
                status='active',
                price_id='price_rotated_professional',
                subscription_id='sub_paid',
            )
        },
    }

    class Request:
        headers = {'stripe-signature': 'verified'}
        url = SimpleNamespace(hostname='askcrump.com')

        async def body(self):
            return json.dumps(event).encode('utf-8')

    first = await billing_routes.stripe_webhook(Request())

    assert first.status_code == 503
    assert fake_db.updates == []
    assert fake_db.events == []
    assert billing_routes._STRIPE_PRICE_TIER_CACHE == {}

    second = await billing_routes.stripe_webhook(Request())

    assert second == {'received': True}
    assert rotated_attempts == 2
    assert fake_db.updates[0][1]['subscription_tier'] == 'professional'
    assert fake_db.updates[0][1]['subscription_status'] == 'active'
    assert fake_db.events[0]['p_event_key'] == 'evt_rotated_price'
    assert billing_routes._STRIPE_PRICE_TIER_CACHE == {
        'price_rotated_professional': 'professional'
    }


@pytest.mark.asyncio
async def test_finalize_checkout_retries_nested_catalog_failure_in_warm_process(
    monkeypatch,
):
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': None,
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
        'subscription_provider': 'stripe',
        'subscription_current_period_end': None,
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    reset_price_resolution_caches(monkeypatch)
    rotated_attempts = 0

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user)

    async def stripe_get(path):
        nonlocal rotated_attempts
        if path == 'checkout/sessions/cs_live_reconcile':
            return checkout_session(subscription='sub_paid')
        if path == 'subscriptions/sub_paid':
            return stripe_subscription(
                status='active',
                price_id='price_rotated_professional',
                subscription_id='sub_paid',
            )
        if path == 'prices/price_rotated_professional':
            rotated_attempts += 1
            if rotated_attempts == 1:
                raise billing_routes.StripeAPIError('temporary price outage')
            return {
                'id': 'price_rotated_professional',
                'product': 'prod_professional',
            }
        if path == 'prices/price_enterprise':
            return {'id': 'price_enterprise', 'product': 'prod_enterprise'}
        if path == 'prices/price_professional':
            return {'id': 'price_professional', 'product': 'prod_professional'}
        raise AssertionError(f'unexpected Stripe lookup {path}')

    class Request:
        headers = {}

        async def json(self):
            return {'sessionId': 'cs_live_reconcile'}

    monkeypatch.setattr(billing_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    first = await billing_routes.finalize_checkout(Request())

    assert first.status_code == 502
    assert b'BILLING_PROVIDER_UNAVAILABLE' in first.body
    assert fake_db.updates == []
    assert fake_db.events == []
    assert billing_routes._STRIPE_PRICE_TIER_CACHE == {}

    second = await billing_routes.finalize_checkout(Request())

    assert second['success'] is True
    assert second['entitled'] is True
    assert second['tier'] == 'professional'
    assert rotated_attempts == 2
    assert fake_db.updates[0][1]['subscription_tier'] == 'professional'
    assert fake_db.events[0]['p_event_key'] == 'cs_live_reconcile'


@pytest.mark.asyncio
async def test_transient_configured_product_lookup_does_not_poison_warm_cache(monkeypatch):
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    reset_price_resolution_caches(monkeypatch)
    professional_attempts = 0

    async def stripe_get(path):
        nonlocal professional_attempts
        if path == 'prices/price_rotated_professional':
            return {
                'id': 'price_rotated_professional',
                'product': 'prod_professional',
            }
        if path == 'prices/price_enterprise':
            return {'id': 'price_enterprise', 'product': 'prod_enterprise'}
        if path == 'prices/price_professional':
            professional_attempts += 1
            if professional_attempts == 1:
                raise billing_routes.StripeAPIError('temporary product outage')
            return {'id': 'price_professional', 'product': 'prod_professional'}
        raise AssertionError(f'unexpected Stripe lookup {path}')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    with pytest.raises(billing_routes.StripeAPIError):
        await billing_routes.stripe_price_tier('price_rotated_professional')

    assert billing_routes._STRIPE_PRICE_TIER_CACHE == {}
    assert billing_routes._STRIPE_TIER_PRODUCT_CACHE == {
        'enterprise': 'prod_enterprise'
    }

    tier = await billing_routes.stripe_price_tier('price_rotated_professional')

    assert tier == 'professional'
    assert professional_attempts == 2
    assert billing_routes._STRIPE_TIER_PRODUCT_CACHE['professional'] == (
        'prod_professional'
    )
    cached_tier = await billing_routes.stripe_price_tier(
        'price_rotated_professional'
    )
    assert cached_tier == 'professional'
    assert professional_attempts == 2


@pytest.mark.asyncio
async def test_successful_unknown_price_still_uses_negative_cache(monkeypatch):
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    reset_price_resolution_caches(monkeypatch)
    paths = []

    async def stripe_get(path):
        paths.append(path)
        products = {
            'prices/price_unknown': 'prod_unknown',
            'prices/price_enterprise': 'prod_enterprise',
            'prices/price_professional': 'prod_professional',
        }
        if path in products:
            return {'id': path.rsplit('/', 1)[-1], 'product': products[path]}
        raise AssertionError(f'unexpected Stripe lookup {path}')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    assert await billing_routes.stripe_price_tier('price_unknown') is None
    first_paths = list(paths)
    assert await billing_routes.stripe_price_tier('price_unknown') is None

    assert paths == first_paths
    assert billing_routes._STRIPE_PRICE_TIER_CACHE == {'price_unknown': None}


@pytest.mark.asyncio
async def test_deleted_subscription_resource_missing_bypasses_catalog_lookup(monkeypatch):
    user = {
        'id': 'user-1',
        'stripe_customer_id': 'cus_owner',
        'stripe_subscription_id': 'sub_paid',
        'subscription_tier': 'professional',
        'subscription_status': 'active',
        'subscription_provider': 'stripe',
    }
    fake_db = BillingDB(user=user)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(billing_routes, 'settings', settings_stub())
    reset_price_resolution_caches(monkeypatch)
    paths = []

    async def stripe_get(path):
        paths.append(path)
        if path == 'subscriptions/sub_paid':
            raise billing_routes.StripeAPIError(
                'subscription was deleted',
                status_code=404,
                code='resource_missing',
                param='subscription',
            )
        raise AssertionError(f'deletion must not require catalog lookup: {path}')

    monkeypatch.setattr(billing_routes, 'stripe_get', stripe_get)

    applied = await billing_routes.reconcile_stripe_subscription_event(
        event_object=stripe_subscription(
            status='canceled',
            price_id='price_legacy_professional',
            subscription_id='sub_paid',
        ),
        event_id='evt_deleted_current',
        event_type='customer.subscription.deleted',
        request=request_stub(),
    )

    assert applied is True
    assert paths == ['subscriptions/sub_paid']
    assert fake_db.updates[0][1]['subscription_status'] == 'canceled'
    assert fake_db.updates[0][1]['subscription_tier'] == 'free'
    assert fake_db.events[0]['p_event_key'] == 'evt_deleted_current'
    assert fake_db.events[0]['p_plan'] is None
    assert billing_routes._STRIPE_PRICE_TIER_CACHE == {}
    assert billing_routes._STRIPE_TIER_PRODUCT_CACHE == {}
