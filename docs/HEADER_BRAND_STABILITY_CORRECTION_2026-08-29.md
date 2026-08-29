# Header brand stability correction — 2026-08-29

## Outcome

The signed-in Ask Crump header now presents the current official positioning,
**“An AI workspace for work that continues,”** from its first rendered frame. The
header image remains stable while the rest of the workspace runtime finishes
loading.

Production release:

- commit: `38edb79fde5592cdb12284cc23a9e3f728d2adf7`
- Vercel deployment: `dpl_3o8xUdoJVUnZVw914NDcosMGTv88`
- deployment state: `READY`
- production aliases include `askcrump.com` and `www.askcrump.com`
- build duration: approximately 37 seconds
- production runtime error/fatal scan after release: no matching logs

## Reported issue

After the larger startup-screen correction, the small header wordmark still
appeared to twitch during refresh. It also retained the legacy
“AI Virtual Assistant” descriptor instead of the current positioning used on
the approved Ask Crump Facebook cover.

## Root cause

The header was rendered correctly in the initial HTML, then replaced by three
different runtime branding routines:

1. the 4.3 compatibility layer replaced it with a mark-and-text header;
2. the 5.0 compatibility layer replaced that with a second legacy header;
3. the current V1 body layer replaced the result with another image node.

The final image used asynchronous decoding and had no intrinsic dimensions when
created dynamically. The visible result was a small late image swap even though
the final source URL matched the original markup.

## Correction

- Updated the canonical horizontal wordmark to use the current positioning from
  the approved social identity.
- Preserved the existing mark and “ASK CRUMP” artwork; only the descriptor area
  is rebuilt by a deterministic Pillow generator. No generative image redraw is
  involved.
- Preloaded the horizontal wordmark and made the visible header instance eager,
  synchronous, high-priority, and intrinsically sized at 1200×296.
- Prevented the two legacy shell layers from replacing the V1 header.
- Changed the V1 brand guard to normalize the existing image in place.
- Preserved later workspace-context children instead of destroying them.
- Aligned the Clever Crump product-card accessible label with the current
  positioning.
- Advanced the service-worker cache from `r116` to `r117`.

## Verification

- 445 Python regression tests passed.
- 45 JavaScript files passed the integration and syntax contract.
- Production build preflight passed.
- Native web bundle rebuilt successfully.
- Store metadata source verification passed.
- New brand-asset generator produced the same SHA-256 hash on repeated runs.
- Production deployment reached `READY` with no alias error.
- Production mobile-sized refresh trace at 390×844:
  - first sample at 250 ms: image decoded and complete;
  - image geometry: x=108, y=16, width=170, height=40;
  - geometry and source stayed unchanged through the eight-second trace;
  - a later workspace-context child was added without replacing or moving the
    logo.

## Existing mobile-release gates

The native release verifier continues to report pre-existing store submission
gates: the iOS project has not been added, RevenueCat public SDK keys were not
present during the local native build, and Android Firebase configuration is
missing. These do not affect the deployed web/PWA correction.

## Desktop rail-handoff follow-up

A later 1280-pixel signed-in refresh trace exposed one remaining desktop-only
settle that the phone-width proof could not reveal: the initial V1 shell
reserved a 74-pixel navigation rail, then the deferred five-destination layer
changed that rail to 94 pixels. The decoded wordmark did not resize or swap,
but its library column moved 20 pixels after the navigation runtime became
ready.

Commit `af99087` makes the initial and final rail declarations both 94 pixels
and advances the service-worker cache to `r121`. Deployment
`dpl_5sinMLpbfLYZLH36GPVDZ8LjXp1f` reached `READY` with all six production
aliases and no alias error. The corrected live trace found the decoded
198-by-50 wordmark at x=111/y=16 at 200 ms, 1 second, 3.2 seconds, and 8 seconds;
the position remained identical while the navigation state changed from
loading to ready. All 455 Python tests, 45 JavaScript validations, production
preflight, and the native web build passed. The release window contained 60
HTTP 200 responses, no warning/error/fatal log, and no runtime error cluster.
