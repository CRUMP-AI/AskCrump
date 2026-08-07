# Ask Crump 5.2.3 — Stripe Customer Recovery

- Fixes web credit checkout after migrating to a different Stripe account.
- Detects Stripe `resource_missing` errors for stale saved customer IDs.
- Creates a replacement customer in the currently configured Stripe account.
- Persists the replacement customer ID and retries checkout once.
- Converts Stripe checkout failures into controlled JSON responses instead of unhandled 500 errors.
- Does not modify the 5.2.2 scrolling layer, multimodal handling, document reading, or artifact generation.

No database migration is required.
No Vercel environment-variable changes are required.
