# Credit checkout idempotency release — 2026-09-08

## Outcome

Credit-pack checkout retries now preserve one action-scoped identity across every active web
launcher. If a browser times out after Stripe accepts the first request, retrying the same purchase
reuses the same provider idempotency key instead of risking a second Checkout Session. A successful
handoff clears that identity before navigation so a later deliberate purchase remains a new action.

## Defect and repair

Subscription checkout already carried an action-scoped attempt ID through a deterministic Stripe
idempotency key, but credit-pack checkout did not. The three active credit launch owners could each
repeat an indistinguishable provider request after a network failure. The backend also accepted an
unvalidated provider destination and logged raw Stripe response text on error.

The credit route now validates a content-free client attempt ID, derives stable and separate
idempotency keys for the initial request and missing-customer recovery, sends the current pinned
Stripe API version, and adds a stable integration identifier. It accepts only an HTTPS
`checkout.stripe.com` destination paired with a `cs_` session ID. Provider errors are reduced to
structured code, parameter, path, and status fields; raw response bodies are not logged. All three
active browser launch owners use the same session-scoped retry contract.

The implementation continues to let Stripe choose eligible payment methods and does not add
`payment_method_types`. It makes no pricing, catalog, entitlement, refund, discount, tax, or
subscription-policy change. Automatic tax remains unchanged; Stripe Tax must not be enabled until
the business's registrations and obligations are verified.

## Verification

- The credit-pack browser proof passed at 390×844 and 1280×720. All three neutral pack cards had
  unique accessible buttons, two simulated failed clicks reused one valid attempt ID, successful
  completion cleared it, and the page reported zero console or runtime errors.
- Focused commerce, disclosure, versioning, accessibility, and retry coverage passed **108 tests**.
- The complete Python suite collected **909 tests**: **907 passed** and two
  environment-dependent tests skipped; there were no failures or errors.
- All **49 JavaScript files** and all six attribution runtime cases passed. Ruff, Python
  compilation, production preflight, native web-bundle generation, source-privacy checks, store
  metadata checks, signing-source checks, and diff integrity passed.
- Main CI run **34279679583**, Android verification run **34279679462**, and iOS source
  verification run **34279679666** completed successfully.
- The isolated Windows worktree did not contain generated Android/iOS folders, so its local native
  verifier correctly deferred platform compilation to hosted CI. Both hosted platform gates passed.

## Production evidence

- Feature commit: **ff599f459240ab5830abe1434603867db6af3bdf**.
- Automatic production deployment: **dpl_Bhv33izEiLdARE32kWVAHnfmY3bZ**.
- The deployment reached READY with all six configured aliases and no alias error.
- Exact live bytes for the billing manager, all three credit launch owners, runtime loader, and
  service worker matched the feature commit. API health returned HTTP 200 at version **5.9.76**.
- An unauthenticated credit-checkout probe returned HTTP 401 before provider access. It created no
  checkout, charge, entitlement, credit mutation, or product event.
- Deployment-scoped logs contained only the expected 200 responses and the 401 probe. The
  credit-checkout route had no runtime-error cluster.
- The current production credit-truth verifier passed **18/18** checks. The earlier **5/18** result
  remains historical evidence and must not be presented as current production behavior.

## Remaining commerce boundary

This release proves retry identity, disclosure, confirmation, destination validation, delivery, and
native-source compilation. It does not prove the live Stripe catalog, tax configuration, a completed
checkout, provider-reconciled entitlement, refund/dispute recovery, duplicate-event handling,
recognized revenue, or variable cost. The Stripe account connection also requires reauthentication
before a new live-account read can be performed. RevenueCat public keys remain an owner-controlled
store-readiness gate. No real checkout or charge was initiated, and no campaign, study, publication,
or acquisition spend is authorized by this release.
