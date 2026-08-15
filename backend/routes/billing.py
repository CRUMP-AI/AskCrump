"""Web and native subscription reconciliation endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth_service import authenticate_request, public_user
from ..db import eq
from ..runtime import db, settings
from ..schemas import CheckoutRequest
from ..security import iso_now

router = APIRouter(tags=["billing"])
logger = logging.getLogger("askcrump.billing")

STRIPE_ENTITLED_STATUSES = {'active', 'trialing'}

# Stripe Price IDs are public identifiers, not credentials. Environment variables
# remain authoritative; these production fallbacks prevent a missing deployment
# variable from silently disabling an otherwise configured paid tier.
LIVE_PROFESSIONAL_PRICE_ID = 'price_1U3Q4DRvssW2wqC4j1BkbvCk'
LIVE_ENTERPRISE_PRICE_ID = 'price_1U3Q4LRvssW2wqC452s98nkz'
_portal_configuration_id: str | None = None


def subscription_price_id(tier: str) -> str | None:
    normalized = str(tier or '').lower()
    if normalized == 'professional':
        return settings.stripe_professional_price_id or (
            LIVE_PROFESSIONAL_PRICE_ID if settings.is_production else None
        )
    if normalized == 'enterprise':
        return settings.stripe_enterprise_price_id or (
            LIVE_ENTERPRISE_PRICE_ID if settings.is_production else None
        )
    return None


class StripeAPIError(RuntimeError):
    def __init__(
        self,
        message: str = 'Stripe rejected the billing request.',
        *,
        status_code: int | None = None,
        code: str | None = None,
        param: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.param = param

    @property
    def missing_customer(self) -> bool:
        return self.code == 'resource_missing' and self.param == 'customer'


async def stripe_post(path: str, data: dict[str, str]) -> dict[str, Any]:
    if not settings.stripe_secret_key:
        raise StripeAPIError('Stripe is not configured.')
    import httpx

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                f'https://api.stripe.com/v1/{path}',
                auth=(settings.stripe_secret_key, ''),
                data=data,
            )
    except httpx.HTTPError as exc:
        logger.exception('Stripe network request failed path=%s', path)
        raise StripeAPIError('Billing provider is temporarily unavailable.') from exc

    if response.status_code >= 400:
        try:
            error = (response.json().get('error') or {})
        except (ValueError, AttributeError):
            error = {}
        code = str(error.get('code') or '') or None
        param = str(error.get('param') or '') or None
        logger.error(
            'Stripe request rejected path=%s status=%s code=%s param=%s',
            path,
            response.status_code,
            code,
            param,
        )
        raise StripeAPIError(
            status_code=response.status_code,
            code=code,
            param=param,
        )
    return response.json()


async def stripe_get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    if not settings.stripe_secret_key:
        raise StripeAPIError('Stripe is not configured.')
    import httpx

    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.get(
                f'https://api.stripe.com/v1/{path}',
                auth=(settings.stripe_secret_key, ''),
                params=params or {},
            )
    except httpx.HTTPError as exc:
        logger.exception('Stripe network request failed path=%s', path)
        raise StripeAPIError('Billing provider is temporarily unavailable.') from exc

    if response.status_code >= 400:
        try:
            error = (response.json().get('error') or {})
        except (ValueError, AttributeError):
            error = {}
        code = str(error.get('code') or '') or None
        param = str(error.get('param') or '') or None
        logger.error(
            'Stripe request rejected path=%s status=%s code=%s param=%s',
            path,
            response.status_code,
            code,
            param,
        )
        raise StripeAPIError(
            status_code=response.status_code,
            code=code,
            param=param,
        )
    return response.json()


async def create_stripe_customer(user: dict[str, Any]) -> str:    customer = await stripe_post(
        'customers',
        {
            'email': user['email'],
            'metadata[user_id]': user['id'],
        },
    )
    customer_id = str(customer['id'])
    await db.update(
        'users',
        {'stripe_customer_id': customer_id, 'updated_at': iso_now()},
        filters={'id': eq(user['id'])},
    )
    user['stripe_customer_id'] = customer_id
    return customer_id


def checkout_payload(customer_id: str, user_id: str, tier: str, price_id: str) -> dict[str, str]:
    return {
        'mode': 'subscription',
        'customer': customer_id,
        'line_items[0][price]': price_id,
        'line_items[0][quantity]': '1',
        'success_url': f'{settings.app_url}/app?billing=success',
        'cancel_url': f'{settings.app_url}/app?billing=cancelled',
        'client_reference_id': user_id,
        'metadata[user_id]': user_id,
        'metadata[purchase_type]': 'subscription',
        'metadata[tier]': tier,
        'allow_promotion_codes': 'true',
    }

async def ensure_customer_portal_configuration() -> str:
    global _portal_configuration_id
    if _portal_configuration_id:
        return _portal_configuration_id

    configurations = await stripe_get(
        'billing_portal/configurations',
        {'active': 'true', 'limit': '100'},
    )
    for configuration in configurations.get('data') or []:
        metadata = configuration.get('metadata') or {}
        if (
            metadata.get('app') == 'ask_crump'
            and metadata.get('purpose') == 'subscriptions_v1'
            and configuration.get('active')
        ):
            _portal_configuration_id = str(configuration['id'])
            return _portal_configuration_id

    professional_price_id = subscription_price_id('professional')
    enterprise_price_id = subscription_price_id('enterprise')
    if not professional_price_id or not enterprise_price_id:
        raise StripeAPIError('Subscription catalog is not configured.')

    professional_price = await stripe_get(f'prices/{professional_price_id}')
    enterprise_price = await stripe_get(f'prices/{enterprise_price_id}')
    professional_product_id = str(professional_price.get('product') or '')
    enterprise_product_id = str(enterprise_price.get('product') or '')
    if not professional_product_id or not enterprise_product_id:
        raise StripeAPIError('Subscription catalog products could not be resolved.')

    data = {
        'default_return_url': f'{settings.app_url}/app',
        'business_profile[headline]': 'Manage your Ask Crump subscription',
        'business_profile[privacy_policy_url]': f'{settings.app_url}/legal.html#privacy',
        'business_profile[terms_of_service_url]': f'{settings.app_url}/legal.html#terms',
        'features[customer_update][enabled]': 'false',
        'features[invoice_history][enabled]': 'true',
        'features[payment_method_update][enabled]': 'true',
        'features[subscription_cancel][enabled]': 'true',
        'features[subscription_cancel][mode]': 'at_period_end',
        'features[subscription_cancel][proration_behavior]': 'none',
        'features[subscription_cancel][cancellation_reason][enabled]': 'true',
        'features[subscription_cancel][cancellation_reason][options][0]': 'too_expensive',
        'features[subscription_cancel][cancellation_reason][options][1]': 'missing_features',
        'features[subscription_cancel][cancellation_reason][options][2]': 'switched_service',
        'features[subscription_cancel][cancellation_reason][options][3]': 'unused',
        'features[subscription_cancel][cancellation_reason][options][4]': 'other',
        'features[subscription_update][enabled]': 'true',
        'features[subscription_update][default_allowed_updates][0]': 'price',
        'features[subscription_update][proration_behavior]': 'create_prorations',
        'features[subscription_update][products][0][product]': professional_product_id,
        'features[subscription_update][products][0][prices][0]': professional_price_id,
        'features[subscription_update][products][1][product]': enterprise_product_id,
        'features[subscription_update][products][1][prices][0]': enterprise_price_id,
        'metadata[app]': 'ask_crump',
        'metadata[purpose]': 'subscriptions_v1',
    }
    configuration = await stripe_post('billing_portal/configurations', data)
    configuration_id = str(configuration.get('id') or '')
    if not configuration_id:
        raise StripeAPIError('Stripe did not return a customer portal configuration.')
    _portal_configuration_id = configuration_id
    return configuration_id


def billing_provider_failure() -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            'success': False,
            'error': 'Billing is temporarily unavailable. Please try again shortly.',
            'code': 'BILLING_PROVIDER_UNAVAILABLE',
        },
    )


@router.post('/api/stripe/create-checkout-session')
async def create_checkout(payload: CheckoutRequest, request: Request):
    if request.headers.get('x-crump-client', '').lower() == 'native':
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'error': 'Use the App Store or Google Play purchase screen in the mobile app.',
                'code': 'NATIVE_BILLING_REQUIRED',
            },
        )
    auth = await authenticate_request(request, db, settings)
    tier = payload.tier.lower()
    price_id = subscription_price_id(tier)

    if not price_id:
        return JSONResponse(
            status_code=400,
            content={
                'success': False,
                'error': 'That subscription tier is not configured.',
            },
        )

    existing_tier = str(auth.user.get('subscription_tier') or 'free').lower()
    existing_status = str(auth.user.get('subscription_status') or 'inactive').lower()
    existing_provider = str(auth.user.get('subscription_provider') or '').lower() or None
    if (
        existing_tier in {'professional', 'enterprise'}
        and existing_status not in {'inactive', 'canceled', 'expired'}
    ):
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'error': 'You already have a paid Ask Crump subscription. Manage the existing plan instead.',
                'code': 'SUBSCRIPTION_ALREADY_ACTIVE',
                'provider': existing_provider,
            },
        )

    customer_id = auth.user.get('stripe_customer_id')
    try:
        if not customer_id:
            customer_id = await create_stripe_customer(auth.user)

        try:
            checkout = await stripe_post(
                'checkout/sessions',
                checkout_payload(customer_id, auth.user['id'], tier, price_id),
            )
        except StripeAPIError as exc:
            if not exc.missing_customer:
                raise
            # A customer ID can become stale if Stripe test/live state changes or
            # an old customer was removed. Recreate it once and retry checkout.
            customer_id = await create_stripe_customer(auth.user)
            checkout = await stripe_post(
                'checkout/sessions',
                checkout_payload(customer_id, auth.user['id'], tier, price_id),
            )
    except StripeAPIError:
        return billing_provider_failure()

    return {
        'success': True,
        'url': checkout.get('url'),
        'sessionId': checkout.get('id'),
    }


@router.post('/api/stripe/customer-portal')
async def customer_portal(request: Request):
    if request.headers.get('x-crump-client', '').lower() == 'native':
        return JSONResponse(
            status_code=409,
            content={
                'success': False,
                'error': 'Manage mobile subscriptions through your device subscription settings.',
                'code': 'NATIVE_BILLING_REQUIRED',
            },
        )
    auth = await authenticate_request(request, db, settings)
    customer_id = auth.user.get('stripe_customer_id')
    if not customer_id:
        return JSONResponse(
            status_code=404,
            content={
                'success': False,
                'error': 'No web subscription was found.',
            },
        )
    try:
        configuration_id = await ensure_customer_portal_configuration()
        portal = await stripe_post(
            'billing_portal/sessions',
            {
                'customer': customer_id,
                'return_url': f'{settings.app_url}/app',
                'configuration': configuration_id,
            },
        )
    except StripeAPIError as exc:
        if exc.missing_customer:
            # Do not mutate entitlement state merely because portal lookup failed;
            # a wrong Stripe environment/credential can also make a valid customer
            # appear missing. Surface a controlled recovery state instead.
            return JSONResponse(
                status_code=409,
                content={
                    'success': False,
                    'error': (
                        'Your web billing profile could not be opened. '
                        'Start checkout again or contact support if you already have a subscription.'
                    ),
                    'code': 'STRIPE_CUSTOMER_STALE',
                },
            )
        return billing_provider_failure()
    return {'success': True, 'url': portal.get('url')}


def verify_stripe_signature(body: bytes, header: str) -> bool:
    if not settings.stripe_webhook_secret or not header:
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
        settings.stripe_webhook_secret.encode(),
        signed,
        hashlib.sha256,
    ).hexdigest()
    return any(hmac.compare_digest(expected, signature) for signature in signatures)


def stripe_entitlement_tier(status: str, price_id: str | None) -> str:
    """Return the paid tier only when Stripe says the subscription is entitled."""
    if status not in STRIPE_ENTITLED_STATUSES:
        return 'free'
    if price_id == subscription_price_id('enterprise'):
        return 'enterprise'
    if price_id == subscription_price_id('professional'):
        return 'professional'
    return 'free'


@router.post('/api/stripe/webhook')
async def stripe_webhook(request: Request):
    body = await request.body()
    if not verify_stripe_signature(body, request.headers.get('stripe-signature', '')):
        return JSONResponse(
            status_code=400,
            content={'success': False, 'error': 'Invalid webhook signature.'},
        )
    event = json.loads(body)
    event_type = event.get('type')
    obj = ((event.get('data') or {}).get('object') or {})
    customer_id = obj.get('customer')

    if event_type == 'checkout.session.completed':
        metadata = obj.get('metadata') or {}
        # Credit purchases have their own verified/idempotent webhook. Never let
        # a one-time credit Checkout session mutate subscription entitlements.
        if str(metadata.get('purchase_type') or '') != 'subscription':
            return {'received': True}
        if str(obj.get('mode') or '') != 'subscription' or not obj.get('subscription'):
            return {'received': True}
        tier = str(metadata.get('tier') or '').lower()
        if tier not in {'professional', 'enterprise'}:
            return {'received': True}
        user_id = metadata.get('user_id') or obj.get('client_reference_id')
        if user_id:
            await db.update(
                'users',
                {
                    'stripe_customer_id': customer_id,
                    'stripe_subscription_id': obj.get('subscription'),
                    'subscription_tier': tier,
                    'subscription_status': 'active',
                    'subscription_provider': 'stripe',
                    'updated_at': iso_now(),
                },
                filters={'id': eq(user_id)},
            )
    elif event_type in {'customer.subscription.updated', 'customer.subscription.deleted'} and customer_id:
        status = (
            'canceled'
            if event_type == 'customer.subscription.deleted'
            else str(obj.get('status') or 'inactive').lower()
        )
        price_id = (
            (((obj.get('items') or {}).get('data') or [{}])[0].get('price') or {}).get('id')
        )
        tier = stripe_entitlement_tier(status, price_id)
        await db.update(
            'users',
            {
                'stripe_subscription_id': obj.get('id'),
                'subscription_tier': tier,
                'subscription_status': status,
                'subscription_provider': 'stripe',
                'subscription_current_period_end': (
                    datetime.fromtimestamp(
                        obj.get('current_period_end'),
                        timezone.utc,
                    ).isoformat()
                    if obj.get('current_period_end')
                    else None
                ),
                'updated_at': iso_now(),
            },
            filters={'stripe_customer_id': eq(customer_id)},
        )
    return {'received': True}


async def sync_revenuecat_customer(user_id: str) -> dict[str, Any] | None:
    if not settings.revenuecat_secret_api_key:
        return None
    import httpx

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                f"https://api.revenuecat.com/v1/subscribers/{quote(user_id, safe='')}",
                headers={
                    'Authorization': f'Bearer {settings.revenuecat_secret_api_key}',
                    'Accept': 'application/json',
                },
            )
    except httpx.HTTPError:
        logger.exception('RevenueCat customer lookup failed')
        return None
    if response.status_code >= 400:
        logger.error(
            'RevenueCat customer lookup rejected: status=%s',
            response.status_code,
        )
        return None

    subscriber = (response.json().get('subscriber') or {})
    entitlements = subscriber.get('entitlements') or {}
    now = datetime.now(timezone.utc)
    active: list[tuple[str, dict[str, Any], datetime | None]] = []
    for entitlement_id, entitlement in entitlements.items():
        if not isinstance(entitlement, dict):
            continue
        expires_at = entitlement.get('expires_date') or entitlement.get('grace_period_expires_date')
        parsed_expiry = None
        if expires_at:
            try:
                parsed_expiry = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
                if parsed_expiry.tzinfo is None:
                    parsed_expiry = parsed_expiry.replace(tzinfo=timezone.utc)
            except ValueError:
                parsed_expiry = None
        if not expires_at or (parsed_expiry and parsed_expiry > now):
            active.append((str(entitlement_id), entitlement, parsed_expiry))

    tier = 'free'
    product_id = None
    period_end = None
    for entitlement_id, entitlement, expiry in active:
        product = str(entitlement.get('product_identifier') or '')
        label = f'{entitlement_id} {product}'.lower()
        candidate = 'enterprise' if 'enterprise' in label else 'professional'
        if candidate == 'enterprise' or tier == 'free':
            tier = candidate
            product_id = product or product_id
        if expiry and (period_end is None or expiry > period_end):
            period_end = expiry

    values = {
        'subscription_tier': tier,
        'subscription_status': 'active' if active else 'inactive',
        'subscription_provider': 'revenuecat' if active else None,
        'store_product_id': product_id,
        'subscription_current_period_end': period_end.isoformat() if period_end else None,
        'updated_at': iso_now(),
    }
    await db.update('users', values, filters={'id': eq(user_id)})
    return values


@router.post('/api/billing/revenuecat/sync')
async def revenuecat_sync(request: Request):
    auth = await authenticate_request(request, db, settings)
    values = await sync_revenuecat_customer(auth.user['id'])
    if values is None:
        return JSONResponse(
            status_code=503,
            content={
                'success': False,
                'error': 'Mobile subscription verification is not configured.',
                'code': 'REVENUECAT_NOT_CONFIGURED',
            },
        )
    auth.user.update(values)
    return {'success': True, 'user': public_user(auth.user)}


@router.get('/api/billing/status')
async def billing_status(request: Request):
    auth = await authenticate_request(request, db, settings)
    return {
        'success': True,
        'tier': auth.user.get('subscription_tier') or 'free',
        'status': auth.user.get('subscription_status') or 'inactive',
        'provider': auth.user.get('subscription_provider')
        or ('stripe' if auth.user.get('stripe_customer_id') else None),
        'user': public_user(auth.user),
    }


@router.post('/api/billing/revenuecat/webhook')
async def revenuecat_webhook(request: Request):
    configured = getattr(settings, 'revenuecat_webhook_auth', None)
    supplied = request.headers.get('authorization', '')
    if not configured or not hmac.compare_digest(configured, supplied):
        return JSONResponse(status_code=401, content={'success': False})
    payload = await request.json()
    event = payload.get('event') or {}
    event_type = str(event.get('type') or '').upper()

    if event_type == 'TRANSFER':
        affected = {
            str(item)
            for item in (event.get('transferred_from') or []) + (event.get('transferred_to') or [])
            if item
        }
        for affected_user_id in affected:
            await sync_revenuecat_customer(affected_user_id)
        return {'success': True}

    user_id = event.get('app_user_id')
    if not user_id:
        return {'success': True}

    reconciled = await sync_revenuecat_customer(str(user_id))
    if reconciled is not None:
        return {'success': True}

    entitlement_ids = event.get('entitlement_ids') or []
    product_id = str(event.get('new_product_id') or event.get('product_id') or '').lower()
    active_types = {
        'INITIAL_PURCHASE',
        'RENEWAL',
        'UNCANCELLATION',
        'PRODUCT_CHANGE',
        'NON_RENEWING_PURCHASE',
        'TEMPORARY_ENTITLEMENT_GRANT',
    }
    if event_type not in active_types | {
        'EXPIRATION',
        'CANCELLATION',
        'BILLING_ISSUE',
        'SUBSCRIPTION_PAUSED',
    }:
        return {'success': True}
    entitlement_text = ' '.join(str(item).lower() for item in entitlement_ids)
    purchased_tier = (
        'enterprise'
        if 'enterprise' in product_id or 'enterprise' in entitlement_text
        else 'professional'
    )
    if event_type == 'EXPIRATION':
        tier, status, provider = 'free', 'inactive', None
    elif event_type == 'CANCELLATION':
        tier, status, provider = purchased_tier, 'canceling', 'revenuecat'
    elif event_type == 'BILLING_ISSUE':
        tier, status, provider = purchased_tier, 'billing_issue', 'revenuecat'
    elif event_type == 'SUBSCRIPTION_PAUSED':
        tier, status, provider = purchased_tier, 'paused', 'revenuecat'
    else:
        tier, status, provider = purchased_tier, 'active', 'revenuecat'
    expiration_ms = event.get('expiration_at_ms')
    await db.update(
        'users',
        {
            'subscription_tier': tier,
            'subscription_status': status,
            'subscription_provider': provider,
            'store_product_id': event.get('new_product_id') or event.get('product_id'),
            'subscription_current_period_end': (
                datetime.fromtimestamp(
                    int(expiration_ms) / 1000,
                    timezone.utc,
                ).isoformat()
                if expiration_ms
                else None
            ),
            'updated_at': iso_now(),
        },
        filters={'id': eq(user_id)},
    )
    return {'success': True}
