# Brand image delivery release — 2026-09-14

## Outcome

Ask Crump now serves lossless WebP derivatives of the two canonical brand images used by the
application shell. The visible artwork, dimensions, transparency, accessible names, layout, and
button behavior are unchanged. The original PNG files remain in the repository as canonical
masters and for any compatibility surface that still needs them.

The two startup assets shrink from 496,998 bytes to 348,494 bytes, saving 148,504 bytes (29.9%)
before transfer compression:

| Asset | PNG | WebP | Reduction |
| --- | ---: | ---: | ---: |
| Crump mark | 353,713 bytes | 243,926 bytes | 31.0% |
| Workspace lockup | 143,285 bytes | 104,568 bytes | 27.0% |

Automated image decoding proves that each derivative has the same dimensions and exactly the same
RGBA pixel bytes as its PNG source. The application shell, sign-in experience, navigation,
onboarding, runtime-created branding, company landing page, service worker, and native web bundle
all reference the WebP derivatives. A contract guard rejects a future partial rollback to the PNG
startup paths. The service worker precaches the visible shell lockup but leaves the mark on demand,
preserving the established cache-budget boundary.

## Why this release

Three cold mobile `/app` runs under constrained 4G and four-times CPU throttling measured FCP at
1,336–1,492 ms and LCP at 1,620–1,776 ms with zero CLS. The brand mark transferred about 354 KB and
completed near 2.9 seconds; the lockup transferred about 144 KB and completed near 1.9 seconds.
Those two images were the clearest remaining startup bytes that could be reduced without changing
the experience or the activation funnel.

## Verification before deployment

- Full backend and product suite: 1,086/1,086 passed.
- JavaScript integration contract: 54/54 files passed, including all attribution fixtures and the
  store-packet self-test.
- Browser control matrix: 48/48 passed across phone, tablet, and desktop flows.
- Public accessibility matrix: 33/33 passed across phone, tablet, and desktop.
- Production build preflight and native web-bundle build passed.
- Client credential scan passed for both public and native web artifacts.
- Local Edge decoding loaded both WebP resources successfully at their exact 640×714 and 1200×300
  dimensions.
- `git diff --check` passed.

The separate native store-project verifier remains intentionally out of scope: this repository does
not contain generated Android or iOS projects, and RevenueCat public store keys have not been
configured. No store submission claim is made by this release.

## Production acceptance

Pending deployment. Accept only after the production deployment is Ready, both WebP URLs return
HTTP 200 with an image WebP content type, served hashes match the reviewed files, a cold mobile app
load uses the derivatives without browser errors, and the full control matrix remains represented
by the immutable pre-deployment test result above.

## Boundaries

This release does not change button destinations, image content, authentication, customer data,
analytics semantics, AI providers, generation behavior, payments, pricing, database objects, or
marketing publication. It does not claim retention or revenue lift. The first valid D1 cohort read
still begins on 2026-09-15 UTC and remains the next funnel decision boundary.
