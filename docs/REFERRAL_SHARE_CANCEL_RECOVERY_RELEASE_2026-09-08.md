# Referral share cancel recovery — 2026-09-08

## Outcome

Canceling the phone's native share sheet no longer produces a false **Sharing is unavailable**
error from an in-product referral prompt. Ask Crump now distinguishes three outcomes:

- the user cancels: close quietly, record no share, and show no error;
- every available share mechanism fails: say that sharing is unavailable and confirm nothing was
  posted or sent; and
- native or clipboard delivery succeeds: show success and only then record `ResponseShared`.

The existing response-share URL, share text, privacy boundary, prompt eligibility, frequency cap,
holdout behavior, lifecycle action record, and public recipient landing remain unchanged.

## Evidence and defect boundary

A source-level referral review found that `shareAskCrumpWorkspace()` returned `false` for an
`AbortError`, while its lifecycle caller treated every falsey value as a transport failure. This
made a deliberate Cancel action indistinguishable from genuine share and clipboard unavailability.

The share helper now returns `null` for a native user cancellation and retains `false` only for a
real delivery failure. The lifecycle caller shows its error only for strict `false`. Neither state
records a share. This is a UI truthfulness repair, not a new lifecycle campaign or eligibility
change.

## Browser acceptance

The credential-free `scripts/verify-lifecycle-referral-recovery.cjs` ran the real lifecycle share
and manager assets at 390×844 against three controlled browser states:

- **Cancel:** one native-share attempt, zero clipboard attempt, zero analytics event, zero toast,
  and the expected `shown` / `acted` lifecycle actions.
- **Unavailable:** one native attempt and one failed clipboard attempt, zero share event, and the
  exact failure message once.
- **Clipboard success:** one native attempt, one successful clipboard write containing the fixed
  content-free referral URL, one `ResponseShared` event after delivery, and one success message.

The existing lifecycle Project-continuity browser proof also passed unchanged, and both fixtures
reported zero console or page errors.

## Automated and release verification

- Full Python suite: **895 collected**, **893 passed**, two environment-dependent tests skipped.
- Focused lifecycle/product-analytics/static-assets/button suite: **98 passed**.
- JavaScript integration contract: **49 files** and **6/6** attribution runtime cases passed.
- Ruff, Python compilation, production preflight, native web build, and diff integrity passed.
- Main CI `34263086359`: success.
- Android Store Bundle Verification `34263086186`: success.
- iOS Store Source Verification `34263086179`: success.
- Production deployment `dpl_E1u7cgFzZAdqYAbfs99eDxoQEDzd`: READY on all six aliases with no
  alias error.
- Exact live lifecycle assets, runtime loader, and service worker matched the feature commit.
- Canonical `/api/health`: HTTP 200, Ask Crump `5.9.76`.
- Initial 30-minute runtime-error query: empty.

## Release identity and exact bytes

- Feature commit: `dd74a66d0390d9e9479b9f55ed108024d2715bdb`
- Base: `0c77e04bd9ef2e7285e738b94f9fac92e80e515d`
- `public/lifecycle-share.js` live/local SHA-256:
  `4693DD2A01DE559414F090EA89E3CEFABF75F20B1B332A4AA97DB1AB469BD575`
- `public/lifecycle-manager.js` live/local SHA-256:
  `019183CF350C37786C842402EB85482F1C9438AA685BA7D78C3D92C2546E5114`
- `public/runtime-body-v1.js` live/local SHA-256:
  `28ABD77B0D6F7FB83CFB782C3FD3CF29F038E5298A947A979EBCEE813B5B3898`
- `public/sw.js` live/local SHA-256:
  `A14F6559A3B7FEC07EC5CC6BDBA4C02C2F28746CD0716BF01B2B302F7E73E3DD`
- `scripts/verify-lifecycle-referral-recovery.cjs` SHA-256:
  `E613E15D6882E28AA3B5BFF9C9F7D1D0DB57B94FBE3071AB371DC288B3335DA0`

## Boundary and next evidence

No production lifecycle prompt, share sheet, clipboard write, analytics event, account, message,
Project, signup, publication, social action, checkout, payment, or customer-data operation was
created during this release. The fixture proves truthful control behavior; it does not prove a
referral was sent, received, activated, retained, or converted.

Observe the first legitimate referral delivery → recipient visit → account creation → activation
journey before changing share copy or claiming referral lift.
