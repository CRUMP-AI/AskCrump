# Immutable workspace lockup release — 2026-08-29

## Outcome

The visible Ask Crump workspace lockup now uses the current social positioning,
**“An AI workspace for work that continues,”** from a dedicated immutable asset URL.
The desktop conversation-library lockup and compact header are both available at
the first rendered workspace frame without a late decode or legacy cached descriptor.

Production release:

- commit: `2775c515d1c16dcbce7648a9975cce3561ae0748`
- Vercel deployment: `dpl_CdyMyRqjeusMX9uic9RnPctrC11R`
- deployment state: `READY`
- production aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project aliases
- custom Python/static framework; build duration approximately 39.6 seconds

## Reported issue

The larger startup transition no longer flashed, but the small top Ask Crump lockup
still appeared to move very slightly after refresh. The owner also wanted that
surface unambiguously aligned with the official Facebook identity rather than the
legacy **“AI Virtual Assistant”** descriptor.

## Root cause

The compact artwork itself had already been updated to the approved positioning,
but it still used the same long-lived path as the prior legacy bitmap. An installed
PWA could therefore retain the old response while its service-worker cache changed.
The visible desktop conversation-library image was also the one top-level brand
image still declared with `loading="lazy"` and `decoding="async"`; the compact main
header had already been promoted to critical loading.

## Correction

- Published the approved compact lockup as
  `/assets/brand/crump-workspace-lockup-light.png`.
- Kept the artwork deterministic and non-generative. Its SHA-256 is
  `32831F47A67416D9864D17C0788D354382A829AB1092C7317C6ED70674541F71`, identical
  to the approved current compact artwork.
- Updated every app-shell wordmark surface to the immutable workspace asset.
- Made both visible top-logo locations eager, synchronously decoded, high priority,
  and intrinsically sized at 1200 by 296 pixels.
- Extended the in-place V1 brand guard to normalize the conversation-library image
  without replacing its node.
- Advanced the service-worker cache to revision `r123` and precached the new URL.

The full Facebook cover was used as the identity reference, not compressed into the
toolbar. Its larger message hierarchy would be unreadable at a 198-by-50 header size;
the compact approved lockup preserves the same product positioning cleanly.

## Verification

- 458 Python regression tests passed.
- 45 JavaScript files passed syntax and integration validation.
- Production build preflight passed.
- Native web bundle rebuilt successfully.
- Store metadata source verification passed.
- The asset generator produced the same SHA-256 on consecutive runs.
- The real local sign-in surface loaded the new asset successfully.
- The exact authenticated production deployment exposed the new source with
  `loading="eager"`, `decoding="sync"`, `fetchpriority="high"`, and 1200-by-296
  intrinsic dimensions.
- In the signed-in 1280-pixel production trace, the runtime gate cleared after
  approximately 2.52 seconds. The first visible 220-by-62-pixel logo crop was
  byte-for-byte identical to the same crop four seconds later while navigation
  remained ready and the image source stayed unchanged.
- The deployment reached `READY` with all six aliases and no alias error.
- The observed release window contained 84 HTTP 200 responses, no 4xx or 5xx
  response, and no runtime error cluster.

## Remaining real-device check

The production and browser proofs are complete. A physical installed-PWA refresh is
still useful as owner confirmation because the new service worker must activate once
on each device before revision `r123` removes the prior Ask Crump cache.
