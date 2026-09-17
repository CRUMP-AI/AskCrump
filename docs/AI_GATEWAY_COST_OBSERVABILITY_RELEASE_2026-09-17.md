# AI Gateway provider-cost observability release

Date: 2026-09-17

## Release identity

- Production source commit: `d2aa8573792f39d8687a314bf151c67de3fa7898`
- Production deployment: `dpl_62sdMJva7hRG3yo5gee3i4aWg4i4`
- Verified preview deployment: `dpl_YCkkYeRE6E71KXSML4qgTLqJ6pJs`
- Supabase migration: `20260917233900 ai_gateway_cost_observability`
- Production health at verification: HTTP 200, Ask Crump `5.9.76`
- Vercel runtime errors for the post-release verification window: none

## What shipped

Every free Vercel AI Gateway completion routed through `AIService._gateway_completion` now claims and settles a content-free provider-cost receipt. The receipt records operational metadata only: purpose, environment, exact deployment and commit, model, provider, authentication lane, status/error classification, token counts, Vercel Gateway gross cost metadata, and latency.

The production path fails closed before a provider request when the exact release identity or receipt allocation is unavailable. Missing usage or cost metadata remains visibly incomplete and is never converted to zero. Failed settlement leaves an incomplete claimed receipt so the aggregate also fails closed.

The database table is protected by RLS with no direct client policies or table grants. Claim, settlement, and aggregate functions are `SECURITY DEFINER`, use an empty `search_path`, and are executable only by `service_role`.

## Verification evidence

- Full Python suite: passed
- Focused provider-cost suite: 14 passed
- JavaScript contract suite: 54 files passed
- Attribution contract: 24/24 passed
- Word/PDF contract: 10/10 passed
- Resume contract: 10/10 passed
- Store self-test: 21/21 passed
- Ruff, Python compilation, native bundle, client-secret boundary, production preflight, and diff checks: passed
- Database schema, constraints, grants, and function security properties: verified against production

Production function fingerprints:

- Aggregate: `3eac884ed6c30e7647b41a0214bba1ce`
- Claim: `1840f56dc2af09d4ee6c61d7e12c6d9b`
- Settle: `73549dd92d8e27215b3f7f97d446f7ff`

## Natural-production evidence gate

Verification window opened at `2026-09-17T23:42:30.145Z` and is half-open through the query execution time. The exact production aggregate was queried with:

- Environment: `production`
- Deployment: `dpl_62sdMJva7hRG3yo5gee3i4aWg4i4`
- Commit: `d2aa8573792f39d8687a314bf151c67de3fa7898`

Result: no aggregate row exists yet because no natural production Gateway completion has occurred in that exact release window.

Decision: **HOLD — awaiting the first natural production free-Gateway completion.** This is an evidence hold, not an implementation failure. The closure verifier must not receive a fabricated or synthetic receipt. Re-run the exact aggregate after a real user completion. It may pass only when allocation, usage, and actual Gateway gross-cost metadata are all complete.

No synthetic receipt, synthetic model request, advertising action, provider-budget change, payment action, or spend action was created for this release.

## Privacy-safe external-account reconciliation

The third chronologically ranked verified, nondeleted account with no internal tier is classified as product-evidence external:

- Production registration and production-only activity
- Terms accepted, one active session
- Six product events including account creation and activation
- Four message-usage rows and two chats
- No project, file, Stripe subscription, or paid state
- No match to known operator email, founder-name pattern, named tester, explicit test/demo/QA marker, internal device/network, or internal user agent

No identity, email address, raw identifier, customer content, or mutation was used in the handoff. Under current server evidence, the accepted north-star verified-external count is **3**. An off-platform personal relationship cannot be disproved technically, but there is no product evidence supporting exclusion.

## Authority boundary

This receipt does not authorize advertising, campaign publication, paid media, provider-budget changes, price changes, or any payment action.
