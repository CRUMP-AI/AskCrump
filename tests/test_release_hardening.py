from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import httpx
import pytest

from backend.auth_service import create_session
from backend.email_service import EmailDeliveryError, EmailService
from backend.routes import auth as auth_routes
from backend.routes import billing as billing_routes
from backend.schemas import RegisterRequest
from backend.usage_service import tier_name


def email_settings() -> SimpleNamespace:
    return SimpleNamespace(
        resend_api_key='re_test',
        from_email='Ask Crump <noreply@askcrump.com>',
        support_email='support@askcrump.com',
        app_name='Ask Crump',
        app_url='https://www.askcrump.com',
    )


@pytest.mark.asyncio
async def test_email_401_is_controlled_and_not_retried():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={'message': 'unauthorized'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = EmailService(email_settings(), client=client)
        with pytest.raises(EmailDeliveryError) as captured:
            await service.send_verification('user@example.com', 'User', 'token-value')

    assert captured.value.status_code == 401
    assert captured.value.retryable is False
    assert len(calls) == 1
    assert calls[0].headers['idempotency-key'].startswith('ask-crump-verify-')


@pytest.mark.asyncio
async def test_email_503_retries_with_the_same_idempotency_key():
    calls = []
    sleeps = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503, json={'message': 'temporarily unavailable'})
        return httpx.Response(200, json={'id': 'email_123'})

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = EmailService(email_settings(), client=client, sleep=fake_sleep)
        sent = await service.send_password_reset(
            'user@example.com',
            'User',
            'reset-token',
        )

    assert sent is True
    assert len(calls) == 3
    assert len(sleeps) == 2
    assert len({request.headers['idempotency-key'] for request in calls}) == 1


class RegistrationDB:
    def __init__(self) -> None:
        self.inserted_user = None
        self.settings_created = False

    async def select_one(self, table, **kwargs):
        if table == 'users':
            return None
        return None

    async def insert(self, table, payload):
        assert table == 'users'
        self.inserted_user = dict(payload)
        return [dict(payload)]

    async def upsert(self, table, payload, *, on_conflict):
        assert table == 'user_settings'
        assert on_conflict == 'user_id'
        self.settings_created = True
        return [dict(payload)]

    async def update(self, *args, **kwargs):
        return []


class FailedVerificationEmail:
    async def send_verification(self, *args, **kwargs):
        raise EmailDeliveryError(status_code=401, retryable=False)


@pytest.mark.asyncio
async def test_registration_email_failure_returns_recoverable_pending_account(monkeypatch):
    fake_db = RegistrationDB()
    recorded_events = []

    async def allow_rate_limit(*args, **kwargs):
        return None

    async def capture_product_event(*args, **kwargs):
        recorded_events.append(dict(kwargs))
        return True

    monkeypatch.setattr(auth_routes, 'db', fake_db)
    monkeypatch.setattr(auth_routes, 'email_service', FailedVerificationEmail())
    monkeypatch.setattr(auth_routes, 'enforce_auth_rate_limit', allow_rate_limit)
    monkeypatch.setattr(auth_routes, 'hash_password', lambda password: 'hashed-password')
    monkeypatch.setattr(auth_routes, 'record_product_event', capture_product_event)

    payload = RegisterRequest(
        email='new-user@example.com',
        password='StrongPass1',
        fullName='New User',
        source='instagram',
    )
    request = SimpleNamespace()
    response = await auth_routes.register(payload, request)
    body = json.loads(response.body)

    assert response.status_code == 503
    assert body['success'] is False
    assert body['accountCreated'] is True
    assert body['needsVerification'] is True
    assert body['code'] == 'EMAIL_DELIVERY_UNAVAILABLE'
    assert fake_db.inserted_user['email'] == 'new-user@example.com'
    assert fake_db.settings_created is True
    assert [event['event_name'] for event in recorded_events] == [
        'AccountCreated',
        'OnboardingCompleted',
    ]
    assert all(event['source'] == 'instagram' for event in recorded_events)


class AtomicSessionDB:
    def __init__(self) -> None:
        self.rows_by_device = {}
        self.upsert_conflicts = []
        self.next_id = 1

    async def upsert(self, table, payload, *, on_conflict):
        assert table == 'sessions'
        self.upsert_conflicts.append(on_conflict)
        device_id = payload['device_id']
        existing = self.rows_by_device.get(device_id, {})
        row = {**existing, **payload}
        if not row.get('id'):
            row['id'] = f'session-{self.next_id}'
            self.next_id += 1
        self.rows_by_device[device_id] = row
        return [dict(row)]

    async def insert(self, table, payload):
        return [dict(payload)]

    async def select(self, *args, **kwargs):
        return []

    async def select_one(self, table, *, filters, **kwargs):
        for row in self.rows_by_device.values():
            if filters.get('device_id') == f"eq.{row['device_id']}":
                return dict(row)
        return None

    async def update(self, *args, **kwargs):
        return []


@pytest.mark.asyncio
async def test_same_installation_logins_converge_on_atomic_upsert():
    fake_db = AtomicSessionDB()
    settings = SimpleNamespace(session_days=365)
    request = SimpleNamespace(
        headers={
            'x-installation-id': 'installation-123',
            'x-crump-client': 'web',
            'x-crump-platform': 'web',
            'user-agent': 'pytest',
        },
        client=SimpleNamespace(host='127.0.0.1'),
    )
    user = {'id': 'user-1'}

    results = await asyncio.gather(
        create_session(fake_db, settings, user, request),
        create_session(fake_db, settings, user, request),
    )

    assert len(fake_db.rows_by_device) == 1
    assert fake_db.upsert_conflicts == ['device_id', 'device_id']
    assert results[0][0] != results[1][0]
    assert fake_db.rows_by_device['installation-123']['token_hash']


def test_canceled_enterprise_stripe_subscription_has_no_paid_entitlement(monkeypatch):
    monkeypatch.setattr(
        billing_routes,
        'settings',
        SimpleNamespace(
            stripe_enterprise_price_id='price_enterprise',
            stripe_professional_price_id='price_professional',
        ),
    )

    assert billing_routes.stripe_entitlement_tier('canceled', 'price_enterprise') == 'free'
    assert billing_routes.stripe_entitlement_tier('inactive', 'price_enterprise') == 'free'
    assert billing_routes.stripe_entitlement_tier('active', 'price_enterprise') == 'enterprise'
    assert billing_routes.stripe_entitlement_tier('trialing', 'price_professional') == 'professional'
    assert billing_routes.stripe_entitlement_tier('active', 'unknown-price') == 'free'


def test_usage_tier_defense_in_depth_rejects_terminal_paid_labels():
    assert tier_name({
        'subscription_tier': 'enterprise',
        'subscription_status': 'canceled',
    }) == 'free'


def test_internal_qa_entitlement_is_separate_from_billing_state():
    assert tier_name({
        'internal_tier': 'enterprise',
        'subscription_tier': 'free',
        'subscription_status': 'inactive',
    }) == 'enterprise'
    assert tier_name({
        'internal_tier': 'invalid',
        'subscription_tier': 'enterprise',
        'subscription_status': 'canceled',
    }) == 'free'
    assert tier_name({
        'subscription_tier': 'professional',
        'subscription_status': 'paused',
    }) == 'free'


def test_usage_tier_honors_canceling_period_until_expiry():
    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    assert tier_name({
        'subscription_tier': 'enterprise',
        'subscription_status': 'canceling',
        'subscription_current_period_end': future,
    }) == 'enterprise'
    assert tier_name({
        'subscription_tier': 'enterprise',
        'subscription_status': 'canceling',
        'subscription_current_period_end': expired,
    }) == 'free'


class WebhookDB:
    def __init__(self) -> None:
        self.updates = []

    async def update(self, table, payload, *, filters):
        self.updates.append((table, dict(payload), dict(filters)))
        return [dict(payload)]


@pytest.mark.asyncio
async def test_deleted_enterprise_webhook_persists_free_tier(monkeypatch):
    fake_db = WebhookDB()
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(
        billing_routes,
        'settings',
        SimpleNamespace(
            stripe_webhook_secret='whsec_test',
            stripe_enterprise_price_id='price_enterprise',
            stripe_professional_price_id='price_professional',
        ),
    )
    monkeypatch.setattr(billing_routes, 'verify_stripe_signature', lambda body, header: True)

    event = {
        'type': 'customer.subscription.deleted',
        'data': {
            'object': {
                'id': 'sub_123',
                'customer': 'cus_123',
                'status': 'canceled',
                'items': {'data': [{'price': {'id': 'price_enterprise'}}]},
                'current_period_end': 1_800_000_000,
            }
        },
    }
    request = SimpleNamespace(
        headers={'stripe-signature': 'test'},
        body=lambda: None,
    )

    async def body():
        return json.dumps(event).encode('utf-8')

    request.body = body
    result = await billing_routes.stripe_webhook(request)

    assert result == {'received': True}
    assert len(fake_db.updates) == 1
    table, values, filters = fake_db.updates[0]
    assert table == 'users'
    assert values['subscription_tier'] == 'free'
    assert values['subscription_status'] == 'canceled'
    assert filters['stripe_customer_id'] == 'eq.cus_123'
