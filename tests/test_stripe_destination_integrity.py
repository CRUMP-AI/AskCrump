from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.routes import billing as billing_routes
from backend.stripe_security import (
    stripe_checkout_destination,
    stripe_portal_destination,
)


@pytest.mark.parametrize(
    ("value", "validator", "expected"),
    [
        (
            "https://checkout.stripe.com/c/pay/cs_fixture?prefilled_email=test%40example.test",
            stripe_checkout_destination,
            "https://checkout.stripe.com/c/pay/cs_fixture?prefilled_email=test%40example.test",
        ),
        (
            "https://billing.stripe.com/p/session/bps_fixture",
            stripe_portal_destination,
            "https://billing.stripe.com/p/session/bps_fixture",
        ),
        ("https://checkout.stripe.com.evil.test/c/pay/cs_fixture", stripe_checkout_destination, None),
        ("https://checkout.stripe.com@evil.test/c/pay/cs_fixture", stripe_checkout_destination, None),
        ("http://checkout.stripe.com/c/pay/cs_fixture", stripe_checkout_destination, None),
        ("https://checkout.stripe.com:444/c/pay/cs_fixture", stripe_checkout_destination, None),
        ("https://billing.stripe.com.evil.test/p/session/bps_fixture", stripe_portal_destination, None),
        ("javascript:alert(1)", stripe_checkout_destination, None),
        ("not a url", stripe_portal_destination, None),
    ],
)
def test_stripe_destinations_require_the_exact_https_origin(value, validator, expected):
    assert validator(value) == expected


@pytest.mark.asyncio
async def test_subscription_checkout_rejects_a_deceptive_stripe_hostname(monkeypatch):
    user = {
        "id": "user-1",
        "email": "owner@example.test",
        "stripe_customer_id": "cus_owner",
        "subscription_tier": "free",
        "subscription_status": "inactive",
    }
    monkeypatch.setattr(
        billing_routes,
        "settings",
        SimpleNamespace(
            app_url="https://www.askcrump.com",
            is_production=False,
            stripe_professional_price_id="price_professional",
            stripe_enterprise_price_id="price_enterprise",
        ),
    )

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user)

    async def stripe_post(*_args, **_kwargs):
        return {
            "id": "cs_valid_shape",
            "url": "https://checkout.stripe.com.evil.test/c/pay/cs_valid_shape",
        }

    async def unexpected_event(*_args, **_kwargs):
        raise AssertionError("invalid provider destinations must not record checkout intent")

    monkeypatch.setattr(billing_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(billing_routes, "stripe_post", stripe_post)
    monkeypatch.setattr(billing_routes, "record_product_event", unexpected_event)
    request = SimpleNamespace(headers={}, url=SimpleNamespace(hostname="askcrump.com"))

    response = await billing_routes.create_checkout(
        billing_routes.CheckoutRequest(
            tier="professional",
            attemptId="web:11111111-2222-4333-8444-555555555555",
        ),
        request,
    )

    assert response.status_code == 502
    assert b"BILLING_PROVIDER_UNAVAILABLE" in response.body


@pytest.mark.asyncio
async def test_customer_portal_rejects_a_non_stripe_destination(monkeypatch):
    user = {
        "id": "user-1",
        "stripe_customer_id": "cus_owner",
        "subscription_tier": "professional",
    }

    async def authenticate(*_args, **_kwargs):
        return SimpleNamespace(user=user)

    async def ensure_configuration():
        return "bpc_fixture"

    async def stripe_post(*_args, **_kwargs):
        return {"id": "bps_fixture", "url": "https://billing.stripe.com.evil.test/session"}

    async def unexpected_event(*_args, **_kwargs):
        raise AssertionError("invalid portal destinations must not record an opened portal")

    monkeypatch.setattr(billing_routes, "authenticate_request", authenticate)
    monkeypatch.setattr(billing_routes, "ensure_customer_portal_configuration", ensure_configuration)
    monkeypatch.setattr(billing_routes, "stripe_post", stripe_post)
    monkeypatch.setattr(billing_routes, "record_product_event", unexpected_event)
    request = SimpleNamespace(headers={}, url=SimpleNamespace(hostname="askcrump.com"))

    response = await billing_routes.customer_portal(request)

    assert response.status_code == 502
    assert b"BILLING_PROVIDER_UNAVAILABLE" in response.body
