import hashlib
import hmac
from pathlib import Path
import re
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

from backend.credits_catalog import by_code, by_native_product, packs
from backend.routes import credits as credit_routes


ROOT = Path(__file__).parents[1]


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
    calls = []
    pack = SimpleNamespace(code='credits_150', credits=150, stripe_price_id='price_credits_150')

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'user-1'})

    async def ensure_customer(_user):
        return 'cus_owner'

    async def stripe_post(path, payload, *, idempotency_key=None):
        calls.append((path, dict(payload), idempotency_key))
        return {'id': 'cs_credit_opened', 'url': 'https://checkout.stripe.com/c/pay/test'}

    async def record_event(_database, **kwargs):
        events.append(kwargs)
        return True

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, '_ensure_stripe_customer', ensure_customer)
    monkeypatch.setattr(credit_routes, '_stripe_post', stripe_post)
    monkeypatch.setattr(credit_routes, 'by_code', lambda _code: pack)
    monkeypatch.setattr(credit_routes, 'record_product_event', record_event)

    request_payload = {
        'pack': 'credits_150',
        'attemptId': 'web:11111111-2222-4333-8444-555555555555',
    }
    first = await credit_routes.checkout(CreditRequest(request_payload))
    second = await credit_routes.checkout(CreditRequest(request_payload))

    assert first['success'] is True
    assert first['sessionId'] == second['sessionId'] == 'cs_credit_opened'
    assert calls[0][0] == calls[1][0] == 'checkout/sessions'
    assert calls[0][1] == calls[1][1]
    assert calls[0][2] == calls[1][2]
    assert calls[0][2].startswith('askcrump_credit_')
    assert re.fullmatch(
        r'askcrump_credits_[a-z]{8}',
        calls[0][1]['integration_identifier'],
    )
    expected_event = {
        'user_id': 'user-1',
        'event_name': 'CreditCheckoutOpened',
        'event_key': 'cs_credit_opened',
        'request': ANY,
        'source': 'credits_150',
    }
    assert events == [expected_event, expected_event]


def test_credit_checkout_payload_uses_dynamic_methods_and_current_api_version(monkeypatch):
    pack = SimpleNamespace(code='credits_50', credits=50, stripe_price_id='price_credits_50')
    monkeypatch.setattr(
        credit_routes,
        'settings',
        SimpleNamespace(app_url='https://www.askcrump.com'),
    )

    payload = credit_routes._checkout_payload(
        user_id='user-1',
        customer_id='cus_owner',
        pack=pack,
        integration_suffix='abcdefgh',
    )

    assert payload['mode'] == 'payment'
    assert payload['integration_identifier'] == 'askcrump_credits_abcdefgh'
    assert 'payment_method_types' not in payload
    assert credit_routes.STRIPE_API_VERSION == '2026-07-29.dahlia'


@pytest.mark.asyncio
async def test_credit_stripe_post_sends_version_and_provider_retry_identity(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {'id': 'cs_credit_retry_safe'}

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

    monkeypatch.setattr(credit_routes.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(
        credit_routes,
        'settings',
        SimpleNamespace(stripe_secret_key='fixture-secret'),
    )

    result = await credit_routes._stripe_post(
        'checkout/sessions',
        {'mode': 'payment'},
        idempotency_key='askcrump_credit_retry_identity',
    )

    assert result['id'] == 'cs_credit_retry_safe'
    assert captured['headers']['Stripe-Version'] == credit_routes.STRIPE_API_VERSION
    assert captured['headers']['Idempotency-Key'] == 'askcrump_credit_retry_identity'
    assert captured['auth'] == ('fixture-secret', '')


@pytest.mark.asyncio
async def test_credit_checkout_rejects_invalid_client_retry_identity(monkeypatch):
    pack = SimpleNamespace(code='credits_50', credits=50, stripe_price_id='price_credits_50')

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'user-1'})

    async def unexpected_customer(*_args, **_kwargs):
        raise AssertionError('invalid attempts must stop before provider work')

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, 'by_code', lambda _code: pack)
    monkeypatch.setattr(credit_routes, '_ensure_stripe_customer', unexpected_customer)

    response = await credit_routes.checkout(
        CreditRequest({'pack': 'credits_50', 'attemptId': 'contains customer content'}),
    )

    assert response.status_code == 400
    assert b'INVALID_CHECKOUT_ATTEMPT' in response.body


@pytest.mark.asyncio
async def test_credit_checkout_rejects_invalid_provider_destination_without_event(monkeypatch):
    events = []
    pack = SimpleNamespace(code='credits_50', credits=50, stripe_price_id='price_credits_50')

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user={'id': 'user-1'})

    async def ensure_customer(_user):
        return 'cus_owner'

    async def stripe_post(_path, _payload, *, idempotency_key=None):
        assert idempotency_key
        return {'id': 'not-a-session', 'url': 'https://untrusted.example/leave'}

    async def record_event(*_args, **_kwargs):
        events.append(_kwargs)

    monkeypatch.setattr(credit_routes, 'authenticate_request', authenticate)
    monkeypatch.setattr(credit_routes, '_ensure_stripe_customer', ensure_customer)
    monkeypatch.setattr(credit_routes, '_stripe_post', stripe_post)
    monkeypatch.setattr(credit_routes, 'by_code', lambda _code: pack)
    monkeypatch.setattr(credit_routes, 'record_product_event', record_event)

    response = await credit_routes.checkout(
        CreditRequest(
            {
                'pack': 'credits_50',
                'attemptId': 'web:11111111-2222-4333-8444-555555555555',
            }
        ),
    )

    assert response.status_code == 502
    assert b'STRIPE_CHECKOUT_INVALID' in response.body
    assert events == []


def test_all_web_credit_launchers_reuse_one_retry_identity():
    manager = (ROOT / 'public' / 'billing-manager.js').read_text(encoding='utf-8')
    owners = (
        (ROOT / 'public' / 'crump-billing-5.1.js').read_text(encoding='utf-8'),
        (ROOT / 'public' / 'crump-5.2.js').read_text(encoding='utf-8'),
        (ROOT / 'public' / 'crump-5.2.2.js').read_text(encoding='utf-8'),
    )

    assert 'creditCheckoutAttempt' in manager
    assert 'completeCreditCheckoutAttempt' in manager
    for source in owners:
        assert 'creditCheckoutAttempt?.(' in source
        assert re.search(r'JSON\.stringify\(\{\s*pack:\s*[^,}]+,\s*attemptId\s*\}\)', source)
        assert 'completeCreditCheckoutAttempt?.(' in source


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
