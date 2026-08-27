import hashlib
import hmac
import time
from dataclasses import replace

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
