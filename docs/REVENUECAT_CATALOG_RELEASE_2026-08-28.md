# Ask Crump 5.9.72 native billing catalog release

## Outcome

Ask Crump now uses one committed, non-secret RevenueCat catalog for the native client build and
server reconciliation. Subscription entitlements, subscription products, and consumable credit
products are matched by exact identifier. Package names and partial words such as `pro` or
`enterprise` can no longer grant or route a purchase.

This release did not create or change a store product, entitlement, price, credential, billing
account, signed build, or store submission.

## Safety behavior

- An active entitlement grants Professional or Enterprise only when both its configured entitlement
  ID and exact product ID match.
- An unknown active entitlement leaves the Ask Crump account at Free / inactive with no billing
  provider.
- Native package discovery ignores lookalike package names and unrecognized product IDs.
- Credit reconciliation recognizes only exact catalog product IDs and remains idempotent by
  provider transaction ID.
- The release verifier rejects malformed or duplicate catalog IDs and rejects a native runtime built
  from stale IDs.

## Verification

- Feature commit: `7543093`
- Production deployment: `dpl_5dHGpkcZ3MgmQF8FjywtnBtXLqYp`
- CI: [33230117812](https://github.com/CRUMP-AI/AskCrump/actions/runs/33230117812)
- Android unsigned App Bundle: [33230117806](https://github.com/CRUMP-AI/AskCrump/actions/runs/33230117806)
- iOS unsigned Release compile: [33230117811](https://github.com/CRUMP-AI/AskCrump/actions/runs/33230117811)
- All 421 Python tests and 44 JavaScript validations passed.
- Production health returned HTTP 200 for 5.9.72 and the live service worker returned cache
  `ask-crump-new-body-v1-r106`.
- The deployment-scoped warning/error/fatal log query and the release-window runtime-error query
  were empty.
- A negative release check supplied an intentional product-ID mismatch and the verifier failed with
  `Native runtime revenueCatProfessionalProductId does not match the authoritative RevenueCat catalog.`

## Remaining owner gates

The exact products and entitlement still must be created or confirmed in App Store Connect, Google
Play, and RevenueCat; the iOS and Android public SDK keys must be supplied only to the relevant
release builds; and purchases, restore, renewal, cancellation, expiration, billing issue, transfer,
and consumable reconciliation must be tested on signed physical-device builds. Pricing and store
configuration remain owner-approved actions.
