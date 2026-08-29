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
