from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True, slots=True)
class CreditPack:
    code: str
    credits: int
    title: str
    subtitle: str
    web_price_label: str
    stripe_price_id: str | None
    native_product_id: str


def _pack(
    code: str,
    credits: int,
    title: str,
    subtitle: str,
    price_label: str,
) -> CreditPack:
    suffix = str(credits)
    return CreditPack(
        code=code,
        credits=credits,
        title=title,
        subtitle=subtitle,
        web_price_label=os.getenv(f'WEB_CREDITS_{suffix}_PRICE_LABEL', price_label),
        stripe_price_id=os.getenv(f'STRIPE_CREDITS_{suffix}_PRICE_ID') or None,
        native_product_id=os.getenv(
            f'REVENUECAT_CREDITS_{suffix}_PRODUCT_ID',
            f'askcrump_credits_{suffix}',
        ),
    )


def packs() -> tuple[CreditPack, ...]:
    return (
        _pack('credits_50', 50, '50 Credits', 'A little more runway.', '$4.99'),
        _pack('credits_150', 150, '150 Credits', 'Best for regular overflow.', '$9.99'),
        _pack('credits_400', 400, '400 Credits', 'Maximum value for heavy use.', '$19.99'),
    )


def by_code(code: str) -> CreditPack | None:
    normalized = str(code or '').strip().lower()
    return next((item for item in packs() if item.code == normalized), None)


def by_native_product(product_id: str) -> CreditPack | None:
    value = str(product_id or '').strip()
    return next((item for item in packs() if item.native_product_id == value), None)


def public_catalog(native: bool = False) -> list[dict[str, Any]]:
    return [
        {
            'code': item.code,
            'credits': item.credits,
            'title': item.title,
            'subtitle': item.subtitle,
            'price': item.web_price_label,
            'nativeProductId': item.native_product_id,
            'available': True if native else bool(item.stripe_price_id),
        }
        for item in packs()
    ]
