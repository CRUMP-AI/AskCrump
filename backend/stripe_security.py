"""Small, fail-closed validators for Stripe-hosted browser destinations."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit


STRIPE_CHECKOUT_HOST = "checkout.stripe.com"
STRIPE_PORTAL_HOST = "billing.stripe.com"


def stripe_https_destination(value: Any, *, host: str) -> str | None:
    """Return a normalized Stripe URL only when its origin is exactly approved."""
    candidate = str(value or "").strip()
    if not candidate:
        return None
    try:
        parsed = urlsplit(candidate)
        if (
            parsed.scheme.lower() != "https"
            or (parsed.hostname or "").lower() != host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port is not None
            or not parsed.path.startswith("/")
        ):
            return None
    except (TypeError, ValueError):
        return None
    return candidate


def stripe_checkout_destination(value: Any) -> str | None:
    return stripe_https_destination(value, host=STRIPE_CHECKOUT_HOST)


def stripe_portal_destination(value: Any) -> str | None:
    return stripe_https_destination(value, host=STRIPE_PORTAL_HOST)
