"""Authoritative non-secret RevenueCat identifiers for native billing."""

from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def _defaults() -> dict[str, Any]:
    path = Path(__file__).with_name('revenuecat_catalog.json')
    return json.loads(path.read_text(encoding='utf-8'))


def entitlement_id() -> str:
    return str(os.getenv('REVENUECAT_ENTITLEMENT') or _defaults()['entitlementId']).strip()


def subscription_product_id(tier: str) -> str:
    normalized = str(tier or '').strip().lower()
    if normalized not in {'professional', 'enterprise'}:
        return ''
    variable = f'REVENUECAT_{normalized.upper()}_PRODUCT_ID'
    return str(os.getenv(variable) or _defaults()['subscriptions'][normalized]).strip()


def subscription_tier(entitlement: str, product_id: str) -> str | None:
    if str(entitlement or '').strip() != entitlement_id():
        return None
    normalized_product = str(product_id or '').strip()
    products = {tier: subscription_product_id(tier) for tier in ('enterprise', 'professional')}
    if any(not value for value in products.values()) or len(set(products.values())) != len(products):
        return None
    return next((tier for tier, configured in products.items() if normalized_product == configured), None)


def event_subscription_tier(entitlements: list[Any], product_id: str) -> str | None:
    supplied = {str(item or '').strip() for item in entitlements if item}
    expected = entitlement_id()
    if supplied and expected not in supplied:
        return None
    return subscription_tier(expected, product_id)


def credit_product_id(code: str) -> str:
    normalized = str(code or '').strip().lower()
    credits = _defaults().get('credits') or {}
    if normalized not in credits:
        return ''
    suffix = normalized.removeprefix('credits_')
    return str(os.getenv(f'REVENUECAT_CREDITS_{suffix}_PRODUCT_ID') or credits[normalized]).strip()
