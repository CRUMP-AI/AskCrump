# Ask Crump 5.1 — Billing & Crump Credits

## Product model

Ask Crump has two complementary ways to keep using the service:

1. **Subscriptions** increase the included daily allowance.
2. **Crump Credits** are a durable overflow balance. One request consumes one credit only after the included allowance is exhausted.

Purchased credits do not expire. The wallet is server-authoritative and follows the signed-in Ask Crump account across devices.

## Payment rails

### Web
Subscriptions continue through Stripe Checkout in `backend/routes/billing.py`.

Credit packs use one-time Stripe Checkout Sessions:
- `credits_50`
- `credits_150`
- `credits_400`

Create one-time Stripe Prices for the three packs and set:
- `STRIPE_CREDITS_50_PRICE_ID`
- `STRIPE_CREDITS_150_PRICE_ID`
- `STRIPE_CREDITS_400_PRICE_ID`

The browser return path finalizes a paid Checkout Session immediately. For durable recovery if a user closes the browser before returning, also create a Stripe webhook endpoint pointed at:

`POST https://www.askcrump.com/api/billing/credits/stripe-webhook`

Subscribe that endpoint to `checkout.session.completed` and store that endpoint's signing secret as `STRIPE_CREDITS_WEBHOOK_SECRET`.

Stripe must call the canonical `www` URL directly. Do not register the apex-domain form: it
redirects to `www`, and Stripe treats redirect responses as failed webhook deliveries.

The ledger's `(user_id, provider, external_id)` unique index makes both the browser finalizer and webhook safe to run for the same purchase.

### iOS and Android
Digital credits in the native app must use the platform store purchase system. Configure three **consumable** products in App Store Connect / Google Play and attach them to the current RevenueCat Offering:

- `askcrump_credits_50`
- `askcrump_credits_150`
- `askcrump_credits_400`

The product identifiers are configurable through:
- `REVENUECAT_CREDITS_50_PRODUCT_ID`
- `REVENUECAT_CREDITS_150_PRODUCT_ID`
- `REVENUECAT_CREDITS_400_PRODUCT_ID`

The committed non-secret source of truth is `backend/revenuecat_catalog.json`. Native builds and
server reconciliation both load that catalog, then apply the same environment-variable overrides.
Subscription entitlement and product identifiers, and consumable product identifiers, are matched
exactly; package-name guessing is intentionally rejected. Run the native release verifier after
supplying any overrides so a build cannot ship with a stale catalog.

After the SDK purchase succeeds, Ask Crump calls the server. The server queries RevenueCat's customer record and reconciles each non-subscription transaction ID into the local credit ledger exactly once.

Consumable purchases are not treated as subscription entitlements. The Ask Crump account ledger is what preserves already-delivered credits across devices.

## Wallet guarantees

- Credits never have an expiration timestamp.
- Every grant, spend, and refund is recorded.
- Spending uses a database advisory lock so two devices cannot overspend the same balance.
- Purchase grants are idempotent by payment-provider transaction ID.
- Failed AI requests refund a credit through the same existing `refund_usage` path.
- Browser roles cannot read or write credit tables directly.
- Service-role RPC functions are the only mutation path.

## Included allowance compatibility

The 5.1 `/api/usage/check` route exposes an effective ceiling of:

`daily included limit + current credit balance`

This intentionally keeps the 5.0 composer compatible. The backend remains authoritative: when the daily RPC reports the included allowance exhausted, `consume_usage` atomically spends one credit.

## Beta QA grant

Migration `005_credit_wallet.sql` deposits 100 non-expiring promotional QA credits into accounts that exist at migration time. The grant uses external ID `ask-crump-5.1-beta` and is therefore idempotent per user. This is intended only to let the existing beta owner test the new multimodal stack without a self-purchase.

Remove the grant block before applying the migration if that behavior is not desired.

## App Review notes

In App Review notes, explain:
- Ask Crump subscriptions provide ongoing AI usage.
- Crump Credits are consumable digital credits used only after included usage is exhausted.
- Native credit purchases use Apple/Google in-app purchase through RevenueCat.
- Purchased credits never expire.
- Restore Purchases restores subscriptions; already-delivered consumable credits remain attached to the Ask Crump account.
- Reviewer credentials should have enough included usage or a test credit balance to exercise AI functionality.
