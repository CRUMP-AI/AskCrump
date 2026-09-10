# Returning workspace cache release — 2026-09-10

Source commit: `753cc655cc3465b145ff493a9c80acafd59a150a`

Production deployment: `dpl_81jjQfD1J4zfZaXHavLrqamRW2eX`

## Outcome

Returning web and PWA sessions now receive the pre-cached boot-critical workspace
assets immediately instead of waiting for an origin revalidation for every one.
The navigated HTML shell, `/app.html`, and the main `/app.js` controller retain
network-first behavior so a returning session can still discover a new release.

## Evidence that justified the change

A read-only production header check found `public, must-revalidate, max-age=0` on
the app shell, runtime loader, representative workspace stylesheet, and
representative workspace script. The previous service worker also classified 43
asset paths as boot-critical but sent that entire class through `networkFirst`.
That made its completed pre-cache ineffective for online returning loads and
created deterministic network work even though the workspace had already been
installed.

This was a concrete delivery bottleneck adjacent to the seven-day desktop `/app`
Speed Insights observation of RES 79 across 156 events. The sample is too small
and lacks individual field-vital detail, so the field score is not presented as
proof that this cache behavior caused the score.

## Released boundary

- Service-worker cache revision `r228` installs a fresh reviewed cache.
- Navigations, `/app.html`, and `/app.js` stay network-first.
- Other boot-critical files use cache-first delivery and fall back to the
  network on a cache miss.
- APIs remain direct-to-network and never enter this cache.
- Non-critical same-origin files retain stale-while-revalidate behavior.

## Automated proof

The new real-browser verifier starts an isolated loopback origin and runs the
actual production service worker. After installation and control are complete,
it clears the origin counters and reloads the controlled page. The second load
records:

- zero origin requests for the versioned runtime loader;
- zero origin requests for a versioned boot-critical workspace stylesheet;
- exactly one origin request for the HTML shell; and
- zero console or page errors.

The verifier is now the required 40th member of the fail-closed browser matrix;
adding or removing a browser verifier without reviewing the matrix inventory
fails CI.

Validation for the source release:

- complete Python suite: 997/997 passed;
- JavaScript validation: 49/49 files passed;
- browser control/performance matrix: 40/40 passed;
- production preflight and native web build passed;
- client credential boundary passed for `public` and generated `dist`;
- GitHub CI `34520092228` passed;
- Android verification `34520092216` passed; and
- iOS verification `34520092142` passed.

## Production proof

Vercel marked deployment `dpl_81jjQfD1J4zfZaXHavLrqamRW2eX` `READY` on all six
expected aliases. The deployed `/sw.js` SHA-256 is
`6216A796211F22A5259B111488FEFD95E03F9B54F53423CF7C911FBC19D2B5BF`, exactly
matching the committed file, and contains cache revision `r228`, the cache-first
path, and the fresh-shell exception. The homepage, `/app`, and `/api/health`
returned HTTP 200. The release window contained no grouped runtime error and no
warning, error, or fatal deployment log.

## Decision boundary

This proves delivery and regression prevention, not a field-performance lift.
First-time visitors still need the initial network delivery, and physical iPhone
and Android returning-load performance remains unmeasured. Recheck the field
route after a comparable sample accumulates; do not claim a faster score from the
deterministic fixture alone.
