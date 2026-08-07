"""Crump Credits billing routes.

Subscriptions remain in billing.py. This module adds a durable one-time credit
wallet without disturbing the proven subscription reconciliation paths.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request
from ..credits_catalog import by_code, by_native_product, public_catalog
from ..db import eq
from ..runtime import db, settings
from ..security import iso_now
from ..usage_service import credit_status

router = APIRouter(prefix='/api/billing/credits', tags=['billing'])
logger = logging.getLogger('askcrump.credits')


def _is_native(request: Request) -> bool:
    return request.headers.get('x-crump-client', '').lower() == 'native'


async def _stripe_post(path: str, data: dict[str, str]) -> dict[str, Any]:
    if not settings.stripe_secret_key:
        raise RuntimeError('Stripe is not configured.')
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.post(
            f'https://api.stripe.com/v1/{path}',
            auth=(settings.stripe_secret_key, ''),
            data=data,
        )
    if response.status_code >= 400:
        logger.error('Stripe credits error %s: %s', response.status_code, response.text[:500])
        raise RuntimeError('Stripe rejected the credit purchase request.')
    return response.json()


async def _stripe_get(path: str) -> dict[str, Any]:
    if not settings.stripe_secret_key:
        raise RuntimeError('Stripe is not configured.')
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.get(
            f'https://api.stripe.com/v1/{path}',
            auth=(settings.stripe_secret_key, ''),
        )
    if response.status_code >= 400:
        logger.error('Stripe credits lookup error %s: %s', response.status_code, response.text[:500])
        raise RuntimeError('Stripe could not verify the purchase.')
    return response.json()


async def _grant(
    *,
    user_id: str,
    amount: int,
    provider: str,
    external_id: str,
    product_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = await db.rpc(
        'grant_credits',
        {
            'p_user_id': user_id,
            'p_amount': int(amount),
            'p_reason': 'credit_purchase',
            'p_provider': provider,
            'p_external_id': external_id,
            'p_product_id': product_id,
            'p_metadata': metadata or {},
        },
    )
    row = result[0] if isinstance(result, list) and result else (result or {})
    return {
        'ledgerId': row.get('ledger_id'),
        'balance': max(0, int(row.get('balance') or 0)),
        'duplicate': bool(row.get('duplicate')),
    }


async def _ensure_stripe_customer(user: dict[str, Any]) -> str:
    customer_id = user.get('stripe_customer_id')
    if customer_id:
        return str(customer_id)
    customer = await _stripe_post(
        'customers',
        {
            'email': str(user.get('email') or ''),
            'metadata[user_id]': str(user['id']),
        },
    )
    customer_id = str(customer['id'])
    await db.update(
        'users',
        {'stripe_customer_id': customer_id, 'updated_at': iso_now()},
        filters={'id': eq(user['id'])},
    )
    return customer_id


def _verify_stripe_signature(body: bytes, header: str) -> bool:
    webhook_secret = os.getenv('STRIPE_CREDITS_WEBHOOK_SECRET') or settings.stripe_webhook_secret
    if not webhook_secret or not header:
        return False
    values: dict[str, list[str]] = {}
    for part in header.split(','):
        if '=' in part:
            key, value = part.split('=', 1)
            values.setdefault(key, []).append(value)
    timestamp = (values.get('t') or [None])[0]
    signatures = values.get('v1') or []
    if not timestamp or not signatures:
        return False
    try:
        if abs(datetime.now(timezone.utc).timestamp() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False
    signed = timestamp.encode() + b'.' + body
    expected = hmac.new(
        webhook_secret.encode(),
        signed,
        hashlib.sha256,
    ).hexdigest()
    return any(hmac.compare_digest(expected, signature) for signature in signatures)


async def _finalize_stripe_session(*, user_id: str, session: dict[str, Any]) -> dict[str, Any]:
    metadata = session.get('metadata') or {}
    if str(metadata.get('purchase_type') or '') != 'credits':
        raise ValueError('This checkout session is not a credit purchase.')
    if str(metadata.get('user_id') or '') != str(user_id):
        raise PermissionError('This credit purchase belongs to another account.')
    if str(session.get('payment_status') or '').lower() != 'paid':
        raise RuntimeError('The payment has not completed yet.')

    pack = by_code(str(metadata.get('pack') or ''))
    if not pack:
        raise ValueError('Unknown credit pack.')
    recorded_credits = int(metadata.get('credits') or 0)
    if recorded_credits != pack.credits:
        raise ValueError('Credit purchase metadata did not match the catalog.')

    grant = await _grant(
        user_id=user_id,
        amount=pack.credits,
        provider='stripe',
        external_id=str(session.get('id') or ''),
        product_id=pack.stripe_price_id,
        metadata={
            'pack': pack.code,
            'stripe_customer_id': session.get('customer'),
            'payment_intent': session.get('payment_intent'),
        },
    )
    return {'pack': pack.code, 'credits': pack.credits, **grant}


@router.get('/status')
async def status(request: Request):
    auth = await authenticate_request(request, db, settings)
    wallet = await credit_status(db, auth.user['id'])
    history = await db.select(
        'credit_ledger',
        columns='id,delta,balance_after,reason,provider,product_id,created_at',
        filters={'user_id': eq(auth.user['id'])},
        order='created_at.desc',
        limit=20,
    )
    return {
        'success': True,
        'credits': wallet,
        'catalog': public_catalog(native=_is_native(request)),
        'history': [
            {
                'id': row.get('id'),
                'delta': int(row.get('delta') or 0),
                'balanceAfter': int(row.get('balance_after') or 0),
                'reason': row.get('reason'),
                'provider': row.get('provider'),
                'productId': row.get('product_id'),
                'createdAt': row.get('created_at'),
            }
            for row in history
        ],
        'creditsNeverExpire': True,
    }


@router.post('/checkout')
async def checkout(request: Request):
    if _is_native(request):
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'error': 'Use the App Store or Google Play purchase sheet for credits.',
                'code': 'NATIVE_BILLING_REQUIRED',
            },
        )
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    pack = by_code(str((payload or {}).get('pack') or '')) if isinstance(payload, dict) else None
    if not pack:
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Unknown credit pack.', 'code': 'UNKNOWN_CREDIT_PACK'},
        )
    if not pack.stripe_price_id:
        return JSONResponse(
            status_code=503,
            content={
                'success': False,
                'error': 'This credit pack is not configured for web checkout yet.',
                'code': 'CREDIT_PACK_NOT_CONFIGURED',
            },
        )
    customer_id = await _ensure_stripe_customer(auth.user)
    session = await _stripe_post(
        'checkout/sessions',
        {
            'mode': 'payment',
            'customer': customer_id,
            'line_items[0][price]': pack.stripe_price_id,
            'line_items[0][quantity]': '1',
            'success_url': (
                f'{settings.app_url}/app?billing=credits-success'
                '&session_id={CHECKOUT_SESSION_ID}'
            ),
            'cancel_url': f'{settings.app_url}/app?billing=credits-cancelled',
            'client_reference_id': auth.user['id'],
            'metadata[user_id]': auth.user['id'],
            'metadata[purchase_type]': 'credits',
            'metadata[pack]': pack.code,
            'metadata[credits]': str(pack.credits),
            'allow_promotion_codes': 'true',
        },
    )
    return {
        'success': True,
        'url': session.get('url'),
        'sessionId': session.get('id'),
        'pack': pack.code,
        'credits': pack.credits,
    }


@router.post('/finalize')
async def finalize(request: Request):
    auth = await authenticate_request(request, db, settings)
    payload = await request.json()
    session_id = str((payload or {}).get('sessionId') or '').strip() if isinstance(payload, dict) else ''
    if not session_id.startswith('cs_'):
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Invalid checkout session.', 'code': 'INVALID_SESSION'},
        )
    try:
        session = await _stripe_get(f'checkout/sessions/{quote(session_id, safe="")}')
        purchase = await _finalize_stripe_session(user_id=auth.user['id'], session=session)
        return {'success': True, **purchase}
    except PermissionError as exc:
        return JSONResponse(status_code=403, content={'success': False, 'error': str(exc)})
    except (ValueError, RuntimeError) as exc:
        return JSONResponse(status_code=409, content={'success': False, 'error': str(exc)})


@router.post('/stripe-webhook')
async def stripe_webhook(request: Request):
    body = await request.body()
    if not _verify_stripe_signature(body, request.headers.get('stripe-signature', '')):
        return JSONResponse(status_code=400, content={'success': False, 'error': 'Invalid webhook signature.'})
    event = json.loads(body)
    if str(event.get('type') or '') != 'checkout.session.completed':
        return {'received': True}
    session = ((event.get('data') or {}).get('object') or {})
    metadata = session.get('metadata') or {}
    if str(metadata.get('purchase_type') or '') != 'credits':
        return {'received': True}
    user_id = str(metadata.get('user_id') or session.get('client_reference_id') or '')
    if not user_id:
        return {'received': True}
    try:
        await _finalize_stripe_session(user_id=user_id, session=session)
    except Exception:
        logger.exception('Could not finalize Stripe credit webhook')
        # A non-2xx response makes Stripe retry, which is exactly what we want.
        return JSONResponse(status_code=503, content={'success': False})
    return {'received': True}


async def _revenuecat_customer(user_id: str) -> dict[str, Any] | None:
    if not settings.revenuecat_secret_api_key:
        return None
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f'https://api.revenuecat.com/v1/subscribers/{quote(user_id, safe="")}',
            headers={
                'Authorization': f'Bearer {settings.revenuecat_secret_api_key}',
                'Accept': 'application/json',
            },
        )
    if response.status_code >= 400:
        logger.error('RevenueCat credit sync rejected: %s %s', response.status_code, response.text[:300])
        return None
    return response.json().get('subscriber') or {}


@router.post('/revenuecat/sync')
async def revenuecat_sync(request: Request):
    auth = await authenticate_request(request, db, settings)
    subscriber = await _revenuecat_customer(auth.user['id'])
    if subscriber is None:
        return JSONResponse(
            status_code=503,
            content={
                'success': False,
                'error': 'Mobile credit verification is not configured yet.',
                'code': 'REVENUECAT_NOT_CONFIGURED',
            },
        )

    granted = 0
    purchases = subscriber.get('non_subscriptions') or {}
    if isinstance(purchases, dict):
        for product_id, transactions in purchases.items():
            pack = by_native_product(str(product_id))
            if not pack or not isinstance(transactions, list):
                continue
            for transaction in transactions:
                if not isinstance(transaction, dict):
                    continue
                transaction_id = str(transaction.get('id') or '').strip()
                if not transaction_id:
                    continue
                grant = await _grant(
                    user_id=auth.user['id'],
                    amount=pack.credits,
                    provider='revenuecat',
                    external_id=transaction_id,
                    product_id=pack.native_product_id,
                    metadata={
                        'pack': pack.code,
                        'store': transaction.get('store'),
                        'is_sandbox': bool(transaction.get('is_sandbox')),
                        'purchase_date': transaction.get('purchase_date'),
                    },
                )
                if not grant['duplicate']:
                    granted += pack.credits

    wallet = await credit_status(db, auth.user['id'])
    return {
        'success': True,
        'granted': granted,
        'credits': wallet,
        'catalog': public_catalog(native=True),
    }
