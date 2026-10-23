import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.routes import credits as credit_routes


ROOT = Path(__file__).parents[1]


class CreditRequest:
    def __init__(self, payload=None, *, native=False):
        self.headers = {'x-crump-client': 'native'} if native else {}
        self.url = SimpleNamespace(hostname='askcrump.com')
        self._payload = payload or {}

    async def json(self):
        return self._payload


def response_json(response):
    return json.loads(response.body.decode('utf-8'))


def paid_user(user_id='paid-user'):
    return {
        'id': user_id,
        'subscription_tier': 'professional',
        'subscription_status': 'active',
    }


def revenuecat_subscriber(
    *,
    native_product='askcrump_credits_50',
    transaction_id='rc-credit-transaction-1',
    transaction_date='2026-10-22T00:00:00Z',
    period_start='2026-10-01T00:00:00Z',
    period_end='2026-11-01T00:00:00Z',
    duplicate=False,
):
    transaction = {
        'id': transaction_id,
        'store': 'app_store',
        'is_sandbox': True,
    }
    if transaction_date is not None:
        transaction['purchase_date'] = transaction_date
    transactions = [transaction]
    if duplicate:
        transactions.append(dict(transaction))
    subscription = {}
    if period_start is not None:
        subscription['purchase_date'] = period_start
    if period_end is not None:
        subscription['expires_date'] = period_end
    return {
        'subscriptions': {'askcrump_professional_monthly': subscription},
        'non_subscriptions': {native_product: transactions},
    }


@pytest.mark.asyncio
async def test_free_web_credit_checkout_stops_before_catalog_customer_or_stripe(monkeypatch):
    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'free-user', 'subscription_tier': 'free'})

    def unexpected_catalog(*_args, **_kwargs):
        raise AssertionError('Free credit checkout must stop before catalog or provider work.')

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, 'by_code', unexpected_catalog)
    monkeypatch.setattr(credit_routes, '_ensure_stripe_customer', unexpected_catalog)
    monkeypatch.setattr(credit_routes, '_stripe_post', unexpected_catalog)

    response = await credit_routes.checkout(
        CreditRequest({'pack': 'credits_50', 'attemptId': 'web:blocked-free-user-0001'}),
    )

    assert response.status_code == 403
    body = response_json(response)
    assert body['code'] == 'CREDIT_PURCHASE_REQUIRES_SUBSCRIPTION'
    assert body['requiredTier'] == 'professional'
    assert 'Subscribe to Professional or Enterprise' in body['error']


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'user',
    [
        paid_user(),
        {'id': 'internal-user', 'internal_tier': 'professional'},
    ],
)
async def test_native_credit_purchase_preflight_allows_paid_and_internal_accounts(
    monkeypatch,
    user,
):
    pack = SimpleNamespace(code='credits_150')

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user)

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, 'by_code', lambda _code: pack)

    result = await credit_routes.purchase_eligibility(
        CreditRequest({'pack': 'credits_150'}, native=True),
    )

    assert result == {
        'success': True,
        'pack': 'credits_150',
        'creditPurchasesAllowed': True,
    }


@pytest.mark.asyncio
async def test_native_credit_purchase_preflight_blocks_free_before_store_lookup(monkeypatch):
    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'free-user', 'subscription_tier': 'free'})

    def unexpected_catalog(*_args, **_kwargs):
        raise AssertionError('Free native preflight must stop before store lookup.')

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, 'by_code', unexpected_catalog)

    response = await credit_routes.purchase_eligibility(
        CreditRequest({'pack': 'credits_50'}, native=True),
    )

    assert response.status_code == 403
    assert response_json(response)['code'] == 'CREDIT_PURCHASE_REQUIRES_SUBSCRIPTION'


@pytest.mark.asyncio
async def test_revenuecat_credit_sync_recovers_purchase_after_local_entitlement_lapses(monkeypatch):
    pack = SimpleNamespace(
        code='credits_50',
        credits=50,
        native_product_id='askcrump_credits_50',
    )
    grants = []

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={
            'id': 'lapsed-user',
            'subscription_tier': 'professional',
            'subscription_status': 'inactive',
        })

    async def customer(user_id):
        assert user_id == 'lapsed-user'
        return revenuecat_subscriber(
            native_product=pack.native_product_id,
            transaction_date='2026-09-15T12:00:00Z',
            period_start='2026-09-01T00:00:00Z',
            period_end='2026-10-01T00:00:00Z',
        )

    async def grant(**kwargs):
        grants.append(kwargs)
        return {'duplicate': False}

    async def no_event(*_args, **_kwargs):
        return None

    async def wallet(*_args, **_kwargs):
        return {'balance': 50}

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, '_revenuecat_customer', customer)
    monkeypatch.setattr(credit_routes, 'by_native_product', lambda product_id: pack if product_id == pack.native_product_id else None)
    monkeypatch.setattr(credit_routes, '_grant', grant)
    monkeypatch.setattr(credit_routes, 'record_product_event', no_event)
    monkeypatch.setattr(credit_routes, 'credit_status', wallet)
    monkeypatch.setattr(credit_routes, 'public_catalog', lambda *, native: [{'code': pack.code}])

    result = await credit_routes.revenuecat_sync(CreditRequest(native=True))

    assert result['success'] is True
    assert result['granted'] == 50
    assert len(grants) == 1
    assert grants[0]['external_id'] == 'rc-credit-transaction-1'


@pytest.mark.asyncio
async def test_revenuecat_credit_sync_rejects_direct_post_lapse_purchase(monkeypatch):
    pack = SimpleNamespace(
        code='credits_50',
        credits=50,
        native_product_id='askcrump_credits_50',
    )

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'lapsed-user', 'subscription_tier': 'free'})

    async def customer(*_args, **_kwargs):
        return revenuecat_subscriber(
            native_product=pack.native_product_id,
            transaction_date='2026-10-02T00:00:00Z',
            period_start='2026-09-01T00:00:00Z',
            period_end='2026-10-01T00:00:00Z',
        )

    async def unexpected_grant(**_kwargs):
        raise AssertionError('A post-lapse transaction must never grant credits.')

    async def wallet(*_args, **_kwargs):
        return {'balance': 0}

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, '_revenuecat_customer', customer)
    monkeypatch.setattr(credit_routes, 'by_native_product', lambda product_id: pack if product_id == pack.native_product_id else None)
    monkeypatch.setattr(credit_routes, '_grant', unexpected_grant)
    monkeypatch.setattr(credit_routes, 'credit_status', wallet)
    monkeypatch.setattr(credit_routes, 'public_catalog', lambda *, native: [{'code': pack.code}])

    result = await credit_routes.revenuecat_sync(CreditRequest(native=True))

    assert result['success'] is True
    assert result['granted'] == 0
    assert result['rejectedTransactions'] == 1
    assert result['settlementLimited'] is True
    assert result['settlementCode'] == 'REVENUECAT_PAID_INTERVAL_NOT_PROVEN'


@pytest.mark.asyncio
async def test_revenuecat_credit_sync_grants_verified_consumable_for_current_paid_account(monkeypatch):
    transaction_id = 'rc-credit-transaction-1'
    pack = SimpleNamespace(
        code='credits_50',
        credits=50,
        native_product_id='askcrump_credits_50',
    )
    grants = []

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=paid_user())

    async def customer(user_id):
        assert user_id == 'paid-user'
        return revenuecat_subscriber(
            native_product=pack.native_product_id,
            transaction_id=transaction_id,
        )

    async def grant(**kwargs):
        grants.append(kwargs)
        return {'duplicate': False}

    async def record(*_args, **_kwargs):
        return None

    async def wallet(*_args, **_kwargs):
        return {'balance': 50}

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, '_revenuecat_customer', customer)
    monkeypatch.setattr(credit_routes, 'by_native_product', lambda product_id: pack if product_id == pack.native_product_id else None)
    monkeypatch.setattr(credit_routes, '_grant', grant)
    monkeypatch.setattr(credit_routes, 'record_product_event', record)
    monkeypatch.setattr(credit_routes, 'credit_status', wallet)
    monkeypatch.setattr(credit_routes, 'public_catalog', lambda *, native: [{'code': pack.code}])

    result = await credit_routes.revenuecat_sync(CreditRequest(native=True))

    assert result == {
        'success': True,
        'granted': 50,
        'credits': {'balance': 50},
        'catalog': [{'code': 'credits_50'}],
    }
    assert len(grants) == 1
    assert grants[0]['user_id'] == 'paid-user'
    assert grants[0]['external_id'] == transaction_id
    assert grants[0]['provider'] == 'revenuecat'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('transaction_date', 'period_start', 'period_end'),
    [
        (None, '2026-10-01T00:00:00Z', '2026-11-01T00:00:00Z'),
        ('not-a-date', '2026-10-01T00:00:00Z', '2026-11-01T00:00:00Z'),
        ('2026-10-22T00:00:00Z', None, '2026-11-01T00:00:00Z'),
        ('2026-10-22T00:00:00Z', '2026-10-01T00:00:00Z', '2026-11-01T00:00:00'),
        ('2026-10-22T00:00:00Z', '2026-11-01T00:00:00Z', '2026-10-01T00:00:00Z'),
    ],
)
async def test_revenuecat_credit_sync_fails_closed_on_missing_or_malformed_dates(
    monkeypatch,
    transaction_date,
    period_start,
    period_end,
):
    pack = SimpleNamespace(
        code='credits_50',
        credits=50,
        native_product_id='askcrump_credits_50',
    )

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=paid_user())

    async def customer(*_args, **_kwargs):
        return revenuecat_subscriber(
            native_product=pack.native_product_id,
            transaction_date=transaction_date,
            period_start=period_start,
            period_end=period_end,
        )

    async def unexpected_grant(**_kwargs):
        raise AssertionError('Unproven provider dates must never grant credits.')

    async def wallet(*_args, **_kwargs):
        return {'balance': 0}

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, '_revenuecat_customer', customer)
    monkeypatch.setattr(credit_routes, 'by_native_product', lambda product_id: pack if product_id == pack.native_product_id else None)
    monkeypatch.setattr(credit_routes, '_grant', unexpected_grant)
    monkeypatch.setattr(credit_routes, 'credit_status', wallet)
    monkeypatch.setattr(credit_routes, 'public_catalog', lambda *, native: [{'code': pack.code}])

    result = await credit_routes.revenuecat_sync(CreditRequest(native=True))

    assert result['granted'] == 0
    assert result['rejectedTransactions'] == 1
    assert result['settlementCode'] == 'REVENUECAT_PAID_INTERVAL_NOT_PROVEN'


@pytest.mark.asyncio
async def test_revenuecat_credit_sync_deduplicates_payload_and_retries_idempotently(monkeypatch):
    pack = SimpleNamespace(
        code='credits_50',
        credits=50,
        native_product_id='askcrump_credits_50',
    )
    granted_ids = set()
    grant_calls = []

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=paid_user())

    async def customer(*_args, **_kwargs):
        return revenuecat_subscriber(native_product=pack.native_product_id, duplicate=True)

    async def grant(**kwargs):
        transaction_id = kwargs['external_id']
        duplicate = transaction_id in granted_ids
        granted_ids.add(transaction_id)
        grant_calls.append(transaction_id)
        return {'duplicate': duplicate}

    async def no_event(*_args, **_kwargs):
        return None

    async def wallet(*_args, **_kwargs):
        return {'balance': 50}

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, '_revenuecat_customer', customer)
    monkeypatch.setattr(credit_routes, 'by_native_product', lambda product_id: pack if product_id == pack.native_product_id else None)
    monkeypatch.setattr(credit_routes, '_grant', grant)
    monkeypatch.setattr(credit_routes, 'record_product_event', no_event)
    monkeypatch.setattr(credit_routes, 'credit_status', wallet)
    monkeypatch.setattr(credit_routes, 'public_catalog', lambda *, native: [{'code': pack.code}])

    first = await credit_routes.revenuecat_sync(CreditRequest(native=True))
    second = await credit_routes.revenuecat_sync(CreditRequest(native=True))

    assert first['granted'] == 50
    assert second['granted'] == 0
    assert grant_calls == ['rc-credit-transaction-1', 'rc-credit-transaction-1']


@pytest.mark.asyncio
async def test_free_credit_status_preserves_wallet_catalog_and_history(monkeypatch):
    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'free-user', 'subscription_tier': 'free'})

    async def wallet(*_args, **_kwargs):
        return {'balance': 42}

    async def select(*_args, **_kwargs):
        return [{
            'id': 'ledger-1',
            'delta': 42,
            'balance_after': 42,
            'reason': 'credit_purchase',
            'provider': 'stripe',
            'product_id': 'price_previous',
            'created_at': '2026-10-01T00:00:00Z',
        }]

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, 'credit_status', wallet)
    monkeypatch.setattr(credit_routes.db, 'select', select)
    monkeypatch.setattr(
        credit_routes,
        'public_catalog',
        lambda *, native: [{'code': 'credits_50', 'credits': 50, 'available': True}],
    )

    result = await credit_routes.status(CreditRequest())

    assert result['credits'] == {'balance': 42}
    assert result['catalog'][0]['code'] == 'credits_50'
    assert result['history'][0]['balanceAfter'] == 42
    assert result['creditPurchasesAllowed'] is False
    assert result['creditPurchaseRequirement']['code'] == 'CREDIT_PURCHASE_REQUIRES_SUBSCRIPTION'


def test_credit_purchase_frontend_is_fail_closed_and_subscribe_first():
    manager = (ROOT / 'public' / 'billing-manager.js').read_text(encoding='utf-8')
    billing = (ROOT / 'public' / 'crump-billing-5.1.js').read_text(encoding='utf-8')
    billing52 = (ROOT / 'public' / 'crump-5.2.js').read_text(encoding='utf-8')
    repair = (ROOT / 'public' / 'crump-5.2.2.js').read_text(encoding='utf-8')

    purchase = manager[manager.index('async function purchaseCredits(packCode)') :]
    assert purchase.index('/api/billing/credits/purchase-eligibility') < purchase.index('await configure()')
    assert purchase.index('/api/billing/credits/purchase-eligibility') < purchase.index('purchasePackage')
    assert "eligibility.creditPurchasesAllowed !== true" in purchase
    assert "Number(data.rejectedTransactions || 0) > 0" in manager
    assert "REVENUECAT_PAID_INTERVAL_NOT_PROVEN" in manager

    for source in (billing, billing52):
        assert 'creditData.creditPurchasesAllowed === true' in source
        assert 'Subscribe first' in source
        assert 'Your current balance and credit history stay available.' in source

    assert "else article.dataset.creditPurchaseLocked = 'true'" in billing52
    assert "if (purchasesAllowed) article.dataset.crumpPack" in billing52
    assert "window.BillingManager?.isNative?.()" in repair
    assert 'await window.BillingManager.purchaseCredits(code)' in repair
