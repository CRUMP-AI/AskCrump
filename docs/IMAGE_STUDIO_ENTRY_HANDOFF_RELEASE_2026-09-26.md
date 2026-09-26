# Image Studio entry handoff release evidence — 2026-09-26

Status: local release candidate verified; hosted CI, merge, production deployment, and live probes
remain required before this is called shipped

## Product outcome

The public Ask Crump page now exposes Image Studio as a visible fifth creation path. A visitor can
create an account, verify the email, and arrive in the existing Professional Image Studio with the
intended destination preserved. Existing signed-in users open the studio directly. The handoff is
consumed once, removed from local storage and the URL, and does not replay after reload.

This entry path supports the already-released reference-fidelity workflow. It does not claim that
a generative provider can reproduce logos, wordmarks, mascots, typography, or layouts pixel for
pixel. Exact Overlay remains the deterministic path when original pixels must remain unchanged.

## Safety and privacy boundary

- The handoff carries only fixed, allowlisted destination and plan labels. It contains no prompt,
  filename, reference image, file identifier, conversation, response, or customer content.
- Registration and verification accept exactly `document`, `image`, `presentation`, `resume`,
  `video`, or `projects` as creation destinations.
- `image` remains excluded from the five-value server-authoritative acquisition-intent vocabulary.
  Server normalization therefore records no acquisition intent for this navigation-only handoff.
- Image Studio opens only through `CrumpImageStudio.open()`. The generic command fallback was
  removed so a missing studio fails closed instead of opening a different surface.
- Merely opening the studio starts no API mutation, provider call, generation, upload, checkout,
  billing action, or credit use.
- Creation consumption is correlated by both `kind` and `capturedAt`. A stale or unrelated event
  cannot clear a newer pending destination.
- The Professional plan review is suppressed while Image Studio is opening and discarded only
  after the exact image handoff is consumed. A temporarily unavailable runtime preserves both
  pending records and recovers on reload without opening checkout.
- Successful consumption removes `intent`, `plan`, `signup`, and the handoff-only `source` from the
  URL. An authenticated reload cannot fall back into the signup screen or reopen Image Studio.
- No database migration, entitlement, price, checkout, provider, media-job, usage, or credit code
  changed in this release.

## Delivery boundary

- Browser/PWA/native asset token: `5.9.76-image-studio-entry-1`
- Service-worker cache: `ask-crump-new-body-v1-r253`
- The landing runtime and server attribution registry remain on their existing versions because
  neither changed.
- Dedicated cache proofs cover the document-delivery path from r249 to r253 and the complete Image
  Studio entry transition from r252 to r253, including eviction of the stale runtime, navigation,
  and authentication URLs.

## Verification

- Complete Python suite: **1,506/1,506 passed**.
- JavaScript release contract: **54/54 files validated**, including 24/24, 10/10, and 10/10
  attribution/runtime fixtures and the 21/21 store-packet self-test.
- Browser-control matrix: **51/51 passed** in installed Microsoft Edge.
- The focused handoff browser proof covers signed-out same-tab entry, cross-device verification,
  an already-authenticated full CTA, invalid-intent rejection, unavailable-runtime persistence and
  reload recovery, an existing presentation-plus-plan path, and no replay after reload.
- Real browser request monitoring observed zero non-GET, cross-origin, `/api/**`, media, feature,
  billing, provider, checkout, upload, generation, or credit request during entry.
- Production build preflight passed.
- Native web bundle generation passed using the repository's locked dependency installation.
- Public/native client-secret boundary passed.
- `git diff --check` passed.

## Production gate and next action

Push the isolated branch, open a pull request, and require hosted CI plus native Android/iOS source
checks. After merge, verify the exact production deployment is Ready; probe the public page,
workspace, service worker, authentication controller, and health endpoint; then inspect the first
post-deploy runtime-error window. Record those hosted identifiers before calling the release
shipped. The next product decision remains evidence-led: observe legitimate Image Studio entry →
confirmed reference plan → generated or deterministically overlaid output, without storing content
in analytics or inferring conversion from internal QA traffic.
