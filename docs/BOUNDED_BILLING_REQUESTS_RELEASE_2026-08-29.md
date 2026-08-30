# Bounded billing requests release

Date: 2026-08-29

Feature commit: `a822fe7`

Production deployment: `dpl_DwRLpxKCDfSvFf97pFWCQ6gRSSLD`

## Outcome

Ask Crump's active web credit checkout, subscription checkout, customer-portal, billing-state, and
payment-return requests now have a 15-second upper bound that includes both the network response and
JSON parsing. A stalled provider or connection can no longer leave a purchase control disabled
indefinitely.

Timeouts restore the affected control and explain that billing took too long so the user can check
the connection and try again. The payment-return path also removes Stripe's `billing` and
`session_id` parameters from the browser address after a stalled finalization attempt, preventing a
refresh loop while retaining the normal reconciliation and retry paths.

No Stripe product, price, customer, subscription, credit, webhook, tax, environment variable, or
provider setting changed in this release. Verification did not create a checkout, payment, customer,
or production record.

## Verification

- The complete 488-test regression suite passed.
- All 45 browser JavaScript files passed validation.
- Production preflight, generated-native web bundling, and canonical store-metadata verification
  passed.
- A credential-free browser ran the three real final billing layers with only the matching request
  stalled and the 15-second timer safely accelerated. Credit checkout, subscription checkout, and
  payment return each made one request, aborted it once, displayed the exact recovery message, and
  produced zero browser errors.
- Credit and subscription controls returned to their enabled labels after the timeout. Payment
  return reduced its address to `?surface=return`, proving that both Stripe return parameters were
  cleared even though finalization stalled.
- The canonical production host returns HTTP 200 for the service worker, runtime loader, and all
  three independently versioned billing assets. Production serves cache revision `r136` and the
  `billing-timeout-1` asset identities.
- A signed-in, read-only production check loaded the current workspace and the complete Plan &
  credits center, including current allowance, catalog, subscription choices, and ledger. No
  purchase or account mutation was attempted.
- The exact commit reached `READY` on all six production aliases with no alias error. Vercel reported
  no runtime-error cluster in the inspected hour and no error/fatal log for the deployment.

## Product decision

This closes a deterministic availability failure at the point where a user is most likely to pay or
return from payment. The next valid revenue evidence is a legitimate customer checkout and provider
reconciliation; Ask Crump will not create a synthetic purchase to manufacture that proof.
