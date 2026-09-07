# Public account-entry and guide-cache release — 2026-09-07

## Outcome

The public creation surfaces now preserve the user's intended destination through account
entry, and the newly accepted guide evidence renders immediately in existing browser and
PWA sessions.

The homepage **Try Video Studio** action previously carried the Professional-plan review
but omitted the Video intent. That made the account screen generic even though the user had
chosen Video. It now opens the exact Video account-entry handoff and retains its truthful
Professional review boundary. Registration does not create checkout or grant paid access.

The two current-product guides replaced older screenshots at the same asset paths. The
service worker correctly revalidated those paths, but an existing PWA could display its old
cached image on the first visit. Every accepted guide reference now uses one immutable
version query. Social metadata, structured data, and visible images therefore resolve to the
same current evidence without a broad service-worker cache reset.

## Button and destination proof

- A static HTML inventory validates every account-entry CTA on the Project, presentation,
  document, résumé, and Video creation pages.
- Each CTA must target `/app`, retain the page's exact intent, agree with its `data-plan`,
  and preserve its signup-versus-sign-in meaning.
- The homepage Video action must carry `signup=1`, `source=video`, `plan=professional`, and
  `intent=video`.
- A real-browser fixture uses the production landing and account controllers at 390 by 844
  to prove the Video-specific title, explanation, exploration route, submit action, focus,
  and lack of horizontal overflow.
- The live production action was clicked after deployment. It opened
  `/app?signup=1&source=video&plan=professional&intent=video&acquisition=direct`, displayed
  **Open your Video Studio**, and exposed **Explore Video Studio first**.

This proof complements the authenticated workspace inventory in
`docs/BUTTON_INTEGRITY_RELEASE_2026-09-07.md`. Destructive controls remain verified only
through their confirmation boundary; no user record or content was changed.

## Current guide package

The product-accepted package includes the current rough-idea workflow guide, Project-memory
guide, authentic fictional-product captures, recovery notes, and their executable tests.
The image files retain their reviewed hashes and 1280-by-720 dimensions. Only their HTML
delivery URLs changed for cache safety.

In the already-open production PWA session that had reproduced the stale first view, the
versioned guide loaded all three current images at natural size 1280 by 720. The second guide
also loaded its current Project image at 1280 by 720. Both pages remained within the desktop
viewport, and their primary calls to action retained their measured guide destinations.

## Automated proof

- 852 Python tests collected: 850 passed and two environment-dependent tests skipped.
- All 49 JavaScript files passed the integration, duplicate-action, attribution, version,
  and cache contracts; all 6 attribution runtime cases passed.
- The focused guide and public-destination suite passed all 12 tests.
- Ruff, Python compilation, production preflight, native web-bundle creation, and diff
  integrity passed.
- The account-entry browser verifier passed all five creation surfaces plus the homepage
  Video handoff at phone width.

## Production acceptance

The release consists of commits `4c9bef2`, `4e33d82`, `cbdec51`, and cache-delivery
correction `ba24c82`. The final production deployment is
`dpl_GD3tMH9E5XhLb62yj2mCFVtFACtV` and Vercel reports it READY with all six production
aliases and no alias error.

The four public domains retain their canonical Ask Crump/Clever Crump behavior. Exact live
checks on `www.askcrump.com` proved the Video account-entry destination, both guide pages,
their current Open Graph evidence, the versioned visible images, and 1280-by-720 natural
dimensions. The first post-release runtime-error query returned no clusters, and the
deployment-scoped warning/error/fatal query returned no entries.

No account, prompt, Project, conversation, file, generation, payment, credit, provider job,
database object, or customer content was created or mutated for this release proof.
