# RevenueCat webhook retry release — 2026-09-13

## Outcome

Ask Crump's native-subscription webhook no longer acknowledges an entitlement-changing delivery
when the authoritative RevenueCat customer lookup fails. Commit
`2094388e15bef9d5c28fe230f8a35de042e772e6` makes transfer, refund, refund-reversal,
subscription-extension, and purchase-redemption deliveries return HTTP 503 when current provider
state cannot be retrieved. RevenueCat can therefore retry instead of treating an unreconciled
delivery as complete.

Transfer handling now reconciles each unique affected account deterministically and requests a
retry if any lookup fails. Ordinary lifecycle events such as cancellation retain the existing
signed-event fallback when the provider lookup is unavailable. The handler also rejects malformed
authenticated JSON, root/event shapes, transfer arrays, account identifiers, entitlement arrays,
product identifiers, and expiration timestamps with a controlled HTTP 400. Malformed provider
responses no longer reach the database.

This matches RevenueCat's current documentation: webhook bodies contain an `event` object; fields
must be parsed defensively; and any non-200 response is treated as a failed delivery and retried.
References: [event types and fields](https://www.revenuecat.com/docs/integrations/webhooks/event-types-and-fields)
and [webhook delivery and retry behavior](https://www.revenuecat.com/docs/integrations/webhooks).

## Verification

- Sixteen new cases cover malformed authenticated payloads and provider responses, transfer
  deduplication and partial failure, four provider-state-dependent event types, malformed event
  fields, and the safe cancellation fallback.
- Focused native-commerce, account-deletion, and subscription-reconciliation coverage passed
  51/51.
- The complete Python suite passed 1,049/1,049.
- JavaScript validation passed 54/54.
- The production build preflight, native-web bundle, client-credential boundary, and Ruff passed.
- The complete real-browser control matrix passed 45/45 on the exact release, including all
  navigation, Projects, Files/viewers, image editing/stability, Video/reference images, Library,
  Settings, account entry/recovery, plans, credits, and checkout recovery.
- GitHub Actions run `34782439886` passed for Python 3.12 and JavaScript.
- Production deployment `dpl_2L9V7w51cX2n1AaGon5VnStByErm` is READY with no alias error across
  the six expected Ask Crump, Clever Crump, and Vercel aliases.
- Canonical health returned HTTP 200 at version 5.9.76, an unauthorized malformed webhook probe
  returned HTTP 401 before parsing, and the initial one-hour runtime-error scan was empty.

## Deliberate boundaries

No RevenueCat product, entitlement, app, API key, authorization header, HMAC setting, webhook
configuration, Apple/Google store state, purchase, refund, subscription, database row, or customer
data was changed for verification. No provider delivery was manufactured. Current authorization-
header verification remains intact; enabling RevenueCat's optional HMAC signing is a separate
credential and provider-configuration action that must be performed and verified atomically.

This release prevents delivery loss; it does not prove a real store purchase, refund, restore,
transfer, or entitlement reconciliation. Those remain signed-device/provider acceptance gates
before store submission or native-commerce claims.
