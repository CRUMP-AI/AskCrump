import hashlib
import hmac
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

from backend.credits_catalog import by_code, by_native_product, packs
from backend.routes import credits as credit_routes


def test_credit_catalog_is_stable():
    values = packs()
    assert [item.credits for item in values] == [50, 150, 400]
    assert len({item.code for item in values}) == 3
    assert len({item.native_product_id for item in values}) == 3


def test_credit_catalog_lookup():
    assert by_code('credits_150').credits == 150
    assert by_native_product('askcrump_credits_400').credits == 400
    assert by_code('nope') is None


def _stripe_header(secret: str, body: bytes) -> str:
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode(),
        timestamp.encode() + b'.' + body,
        hashlib.sha256,
    ).hexdigest()
    return f't={timestamp},v1={signature}'


def test_credit_webhook_accepts_existing_plural_secret_alias(monkeypatch):
    body = b'{"type":"checkout.session.expired"}'
    monkeypatch.delenv('STRIPE_CREDITS_WEBHOOK_SECRET', raising=False)
    monkeypatch.setenv('STRIPE_CREDITS_WEBHOOK_SECRETS', 'whsec_credits')
    monkeypatch.setattr(
        credit_routes,
        'settings',
        replace(credit_routes.settings, stripe_webhook_secret='whsec_subscription'),
    )

    assert credit_routes._verify_stripe_signature(
        body,
        _stripe_header('whsec_credits', body),
    )
    assert not credit_routes._verify_stripe_signature(
        body,
        _stripe_header('whsec_subscription', body),
    )


def test_credit_webhook_prefers_documented_singular_secret(monkeypatch):
    body = b'{"type":"checkout.session.expired"}'
    monkeypatch.setenv('STRIPE_CREDITS_WEBHOOK_SECRET', 'whsec_current')
    monkeypatch.setenv('STRIPE_CREDITS_WEBHOOK_SECRETS', 'whsec_legacy')

    assert credit_routes._verify_stripe_signature(
        body,
        _stripe_header('whsec_current', body),
    )
    assert not credit_routes._verify_stripe_signature(
        body,
        _stripe_header('whsec_legacy', body),
    )


class CreditRequest:
    def __init__(self, payload=None):
        self.headers = {}
        self.url = SimpleNamespace(hostname='askcrump.com')
        self._payload = payload or {}

    async def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_credit_checkout_records_only_the_server_session_and_fixed_pack(monkeypatch):
    events = []
    pack = SimpleNamespace(code='credits_150', credits=150, stripe_price_id='price_credits_150')

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'user-1'})

    async def ensure_customer(_user):
        return 'cus_owner'

    async def stripe_post(_path, _payload):
        return {'id': 'cs_credit_opened', 'url': 'https://checkout.stripe.com/c/pay/test'}

    async def record_event(_database, **kwargs):
        events.append(kwargs)
        return True

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, '_ensure_stripe_customer', ensure_customer)
    monkeypatch.setattr(credit_routes, '_stripe_post', stripe_post)
    monkeypatch.setattr(credit_routes, 'by_code', lambda _code: pack)
    monkeypatch.setattr(credit_routes, 'record_product_event', record_event)

    result = await credit_routes.checkout(CreditRequest({'pack': 'credits_150'}))

    assert result['success'] is True
    assert result['sessionId'] == 'cs_credit_opened'
    assert events == [{
        'user_id': 'user-1',
        'event_name': 'CreditCheckoutOpened',
        'event_key': 'cs_credit_opened',
        'request': ANY,
        'source': 'credits_150',
    }]


@pytest.mark.asyncio
async def test_credit_completion_uses_the_same_session_identity_and_no_payment_details(monkeypatch):
    events = []
    pack = SimpleNamespace(code='credits_50', credits=50, stripe_price_id='price_credits_50')

    async def grant(**_kwargs):
        return {'ledgerId': 'ledger-1', 'balance': 62, 'duplicate': False}

    async def record_event(_database, **kwargs):
        events.append(kwargs)
        return True

    monkeypatch.setattr(credit_routes, 'by_code', lambda _code: pack)
    monkeypatch.setattr(credit_routes, '_grant', grant)
    monkeypatch.setattr(credit_routes, 'record_product_event', record_event)
    request = CreditRequest()
    session = {
        'id': 'cs_credit_complete',
        'payment_status': 'paid',
        'metadata': {
            'purchase_type': 'credits',
            'user_id': 'user-1',
            'pack': 'credits_50',
            'credits': '50',
        },
    }

    result = await credit_routes._finalize_stripe_session(
        user_id='user-1',
        session=session,
        request=request,
    )

    assert result == {
        'pack': 'credits_50',
        'credits': 50,
        'ledgerId': 'ledger-1',
        'balance': 62,
        'duplicate': False,
    }
    assert events[0]['event_name'] == 'CreditCheckoutCompleted'
    assert events[0]['event_key'] == 'cs_credit_complete'
    assert events[0]['source'] == 'credits_50'
    assert set(events[0]) == {'user_id', 'event_name', 'event_key', 'request', 'source'}
