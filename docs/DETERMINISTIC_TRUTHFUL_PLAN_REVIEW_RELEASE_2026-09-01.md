# Deterministic and truthful plan review release

Date: 2026-09-01

## Outcome

A Professional or Enterprise intent now reaches one matching **Plan & credits** review even when authentication, the workspace runtime, the billing consumer, or billing data finishes in an unexpected order. The user’s selection remains visible after either billing renderer replaces the plan cards.

Enterprise is positioned only as the highest-capacity current individual tier. The signed-in product no longer calls it suitable for organization workflows or implies team administration, SSO, procurement, SLA, dedicated support, or enterprise security.

## User contract

- The exact paid intent is retained in page memory and local storage.
- Delivery retries until a matching plan and capture timestamp are acknowledged.
- A stored intent is cleared only after that acknowledgement.
- The consumer reuses an already-open legacy or current billing center instead of creating a second panel.
- The selected-plan status appears before a slow billing response completes.
- Card replacement by either billing owner restores the selected highlight.
- Plan-intent telemetry is idempotent for the exact delivery.
- No plan-intent path starts checkout. Purchase still requires a separate user action and provider confirmation.

## Scope boundary

This release changes no price, allowance, entitlement, provider, product identifier, checkout, subscription, refund, credit pack, credit charge, or database behavior. The separate credit-truth candidate and its exact action-time approval remain held. The private API v0.50 candidate remains unintegrated while production serves v0.49.1.

## Verification

- Automated browser matrix: 40 of 40 cases passed across Professional and Enterprise, 390×844 and 1280×720 viewports, ten delayed-consumer timings, a legacy-to-current billing-owner switch, billing delayed beyond a retry interval, and a post-ack plan-card replacement.
- Signed-in production plan acceptance: 10 of 10 repeated runs showed one visible panel, one matching status, and one persistent selected card without checkout navigation.
- Final signed-in Enterprise acceptance showed one visible panel, the exact individual-capacity summary, zero organization-workflow claims, and one selected Enterprise card.
- Full Python suite: 695 tests passed.
- JavaScript integration contract: 47 files validated.
- Production preflight, native web bundle, exact asset parity, and git whitespace integrity passed.
- Final commit: `e124be5caf3df14fca394b9716a85f1f01f9637e`.
- Final deployment: `dpl_DdZu533vPvX3x3Qqwh9eVffuez4G`, READY with all six aliases and no alias error.
- Production release window: no runtime-error cluster and no 4xx or 5xx deployment log.

## Remaining evidence gate

Observe a legitimate non-internal user reaching a relevant post-value Professional review, then either deliberately returning to work or explicitly entering checkout. Do not claim conversion lift from internal QA. Credit truth, commerce reconciliation, refunds, unit cost, and finance-authoritative recognized revenue remain open.
