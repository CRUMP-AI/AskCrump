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


def stripe_subscription(*, status='active', price_id='price_professional'):
    return {
        'id': 'sub_paid',
        'customer': 'cus_owner',
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
    assert result['tier'] == 'free'
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


def test_subscription_return_frontend_finalizes_and_retries_once():
    source = (ROOT / 'public' / 'crump-billing-5.1.js').read_text(encoding='utf-8')

    assert "billing === 'success' && sessionId" in source
    assert "'/api/stripe/finalize-checkout'" in source
    assert 'for (let attempt = 0; attempt < 2; attempt += 1)' in source
    assert "'SUBSCRIPTION_PENDING'" in source
    assert "url.searchParams.delete('session_id')" in source
