import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from backend.routes import billing as billing_routes
from backend.revenuecat_catalog import (
    credit_product_id,
    event_subscription_tier,
    subscription_product_id,
    subscription_tier,
)


ROOT = Path(__file__).resolve().parents[1]


def test_authoritative_revenuecat_catalog_is_complete_and_unique():
    catalog = json.loads(
        (ROOT / 'backend' / 'revenuecat_catalog.json').read_text(encoding='utf-8')
    )
    product_ids = [*catalog['subscriptions'].values(), *catalog['credits'].values()]

    assert catalog['entitlementId'] == 'professional'
    assert set(catalog['subscriptions']) == {'professional', 'enterprise'}
    assert set(catalog['credits']) == {'credits_50', 'credits_150', 'credits_400'}
    assert all(product_ids)
    assert len(product_ids) == len(set(product_ids))


def test_subscription_catalog_requires_exact_entitlement_and_product_ids(monkeypatch):
    monkeypatch.delenv('REVENUECAT_ENTITLEMENT', raising=False)
    monkeypatch.delenv('REVENUECAT_PROFESSIONAL_PRODUCT_ID', raising=False)
    monkeypatch.delenv('REVENUECAT_ENTERPRISE_PRODUCT_ID', raising=False)

    professional = subscription_product_id('professional')
    enterprise = subscription_product_id('enterprise')
    assert subscription_tier('professional', professional) == 'professional'
    assert subscription_tier('professional', enterprise) == 'enterprise'
    assert subscription_tier('unrelated', professional) is None
    assert subscription_tier('professional', f'{professional}_lookalike') is None
    assert event_subscription_tier([], enterprise) == 'enterprise'
    assert event_subscription_tier(['unrelated'], enterprise) is None


def test_credit_catalog_uses_exact_configurable_product_ids(monkeypatch):
    monkeypatch.setenv('REVENUECAT_CREDITS_150_PRODUCT_ID', 'askcrump.credits.150.live')
    assert credit_product_id('credits_150') == 'askcrump.credits.150.live'
    assert credit_product_id('credits_999') == ''


def test_native_client_never_guesses_billing_products_from_package_names():
    source = (ROOT / 'public' / 'billing-manager.js').read_text(encoding='utf-8')
    assert "label.includes('pro')" not in source
    assert "label.includes('enterprise')" not in source
    assert 'packageId.includes(pack.productId)' not in source
    assert 'productId === values.revenueCatProfessionalProductId' in source
    assert 'productId === values.revenueCatEnterpriseProductId' in source


def test_native_build_and_release_verifier_share_the_catalog_loader():
    build = (ROOT / 'scripts' / 'build-native.mjs').read_text(encoding='utf-8')
    verify = (ROOT / 'scripts' / 'verify-native-release.mjs').read_text(encoding='utf-8')
    for source in (build, verify):
        assert "from './revenuecat-catalog.mjs'" in source
        assert 'loadRevenueCatCatalog' in source
    assert 'does not match the authoritative RevenueCat catalog' in verify


@pytest.mark.asyncio
async def test_unknown_active_revenuecat_entitlement_fails_fully_closed(monkeypatch):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {
                'subscriber': {
                    'entitlements': {
                        'unrelated': {
                            'product_identifier': 'unrelated_pro_plan',
                            'expires_date': '2099-01-01T00:00:00Z',
                        },
                    },
                },
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return Response()

    class DB:
        def __init__(self):
            self.payload = None

        async def update(self, _table, payload, *, filters):
            self.payload = dict(payload)
            return [dict(payload)]

    fake_db = DB()
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **_kwargs: Client())
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(
        billing_routes,
        'settings',
        SimpleNamespace(revenuecat_secret_api_key='secret'),
    )

    result = await billing_routes.sync_revenuecat_customer('user-1')

    assert result['subscription_tier'] == 'free'
    assert result['subscription_status'] == 'inactive'
    assert result['subscription_provider'] is None
    assert fake_db.payload == result


class RevenueCatRequest:
    def __init__(self, payload):
        self.headers = {'authorization': 'Bearer webhook-secret'}
        self.payload = payload

    async def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class RevenueCatDB:
    def __init__(self):
        self.updates = []

    async def update(self, table, payload, *, filters):
        self.updates.append((table, dict(payload), dict(filters)))
        return [dict(payload)]


def revenuecat_webhook_settings():
    return SimpleNamespace(revenuecat_webhook_auth='Bearer webhook-secret')


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [ValueError('broken'), [], {'event': []}])
async def test_revenuecat_webhook_rejects_authenticated_non_event_payloads(
    monkeypatch,
    payload,
):
    monkeypatch.setattr(billing_routes, 'settings', revenuecat_webhook_settings())

    response = await billing_routes.revenuecat_webhook(RevenueCatRequest(payload))

    assert response.status_code == 400
    assert b'Invalid webhook payload.' in response.body


@pytest.mark.asyncio
async def test_revenuecat_transfer_retries_when_any_current_state_lookup_fails(monkeypatch):
    calls = []

    async def sync(user_id):
        calls.append(user_id)
        return None if user_id == 'user-b' else {'subscription_tier': 'free'}

    monkeypatch.setattr(billing_routes, 'settings', revenuecat_webhook_settings())
    monkeypatch.setattr(billing_routes, 'sync_revenuecat_customer', sync)
    response = await billing_routes.revenuecat_webhook(
        RevenueCatRequest(
            {
                'event': {
                    'type': 'TRANSFER',
                    'transferred_from': ['user-a', 'user-a'],
                    'transferred_to': ['user-b'],
                },
            },
        ),
    )

    assert response.status_code == 503
    assert calls == ['user-a', 'user-b']


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'event_type',
    ['REFUND', 'REFUND_REVERSED', 'SUBSCRIPTION_EXTENDED', 'PURCHASE_REDEEMED'],
)
async def test_revenuecat_provider_state_events_retry_instead_of_being_lost(
    monkeypatch,
    event_type,
):
    async def unavailable(_user_id):
        return None

    monkeypatch.setattr(billing_routes, 'settings', revenuecat_webhook_settings())
    monkeypatch.setattr(billing_routes, 'sync_revenuecat_customer', unavailable)
    response = await billing_routes.revenuecat_webhook(
        RevenueCatRequest({'event': {'type': event_type, 'app_user_id': 'user-a'}}),
    )

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_revenuecat_cancellation_has_safe_signed_event_fallback(monkeypatch):
    async def unavailable(_user_id):
        return None

    fake_db = RevenueCatDB()
    monkeypatch.setattr(billing_routes, 'settings', revenuecat_webhook_settings())
    monkeypatch.setattr(billing_routes, 'sync_revenuecat_customer', unavailable)
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    result = await billing_routes.revenuecat_webhook(
        RevenueCatRequest(
            {
                'event': {
                    'type': 'CANCELLATION',
                    'app_user_id': 'user-a',
                    'entitlement_ids': ['professional'],
                    'product_id': subscription_product_id('professional'),
                    'expiration_at_ms': 1_800_000_000_000,
                },
            },
        ),
    )

    assert result == {'success': True}
    assert fake_db.updates[0][1]['subscription_status'] == 'canceling'
    assert fake_db.updates[0][1]['subscription_tier'] == 'professional'
    assert fake_db.updates[0][2] == {'id': 'eq.user-a'}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'event',
    [
        {'type': 'TRANSFER', 'transferred_from': {}, 'transferred_to': []},
        {
            'type': 'INITIAL_PURCHASE',
            'app_user_id': 'user-a',
            'entitlement_ids': {},
        },
        {'type': 'INITIAL_PURCHASE', 'app_user_id': ['user-a']},
        {
            'type': 'INITIAL_PURCHASE',
            'app_user_id': 'user-a',
            'entitlement_ids': [],
            'product_id': [],
        },
    ],
)
async def test_revenuecat_webhook_rejects_malformed_event_fields(monkeypatch, event):
    async def unavailable(_user_id):
        return None

    monkeypatch.setattr(billing_routes, 'settings', revenuecat_webhook_settings())
    monkeypatch.setattr(billing_routes, 'sync_revenuecat_customer', unavailable)
    response = await billing_routes.revenuecat_webhook(
        RevenueCatRequest({'event': event}),
    )

    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize('provider_payload', [ValueError('broken'), [], {'subscriber': []}])
async def test_revenuecat_customer_sync_rejects_invalid_provider_payload(
    monkeypatch,
    provider_payload,
):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            if isinstance(provider_payload, Exception):
                raise provider_payload
            return provider_payload

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return Response()

    fake_db = RevenueCatDB()
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **_kwargs: Client())
    monkeypatch.setattr(billing_routes, 'db', fake_db)
    monkeypatch.setattr(
        billing_routes,
        'settings',
        SimpleNamespace(revenuecat_secret_api_key='secret'),
    )

    assert await billing_routes.sync_revenuecat_customer('user-a') is None
    assert fake_db.updates == []
