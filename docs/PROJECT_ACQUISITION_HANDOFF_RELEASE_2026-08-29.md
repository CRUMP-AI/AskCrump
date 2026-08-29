# Public Projects acquisition handoff release

Date: 2026-08-29

## Outcome

Ask Crump now has a canonical public Projects page and a fixed, content-free path from that page
through signup or sign-in into the authenticated Projects workspace. A returning user can then select
a named Project and enter the dedicated workspace released earlier the same day.

## Evidence basis

The protected external growth, artifact-journey, and plan-conversion aggregates contained no current
external transitions. The public homepage already positioned Projects as the product's continuity
layer, but its discovery grid exposed only presentation, document, résumé, and video pages. The
authentication handoff likewise rejected every intent except those four categories. Acquisition was
therefore pointing at individual creation tools without a public path into Ask Crump's clearest
durable-work differentiator.

## Correction

- `/ai-project-workspace` is a canonical, indexable page with unique title, description, social
  metadata, structured data, truthful plan limits, internal links, and a responsive Projects story.
- The homepage gives Projects the wide lead card in a balanced discovery grid, and every existing
  capability page links back to Projects.
- Every Projects signup or sign-in CTA carries the fixed `projects` intent. It never carries a
  prompt, Project ID, file, conversation ID, or other customer content.
- Authentication preserves that category for at most 24 hours, explains the Projects destination,
  and offers a public Projects explainer before registration.
- After the authenticated workspace runtime is ready, the five-destination navigation opens
  `Projects`, emits one categorical `CreationIntentContinued` event, acknowledges the handoff, and
  clears it. No Project is created and no generation starts automatically.
- The new route is included in the Ask Crump sitemap and permanently redirects from the Clever
  Crump host to the canonical Ask Crump domain.
- Web, PWA, and native bundles use explicit Projects-entry identities for the changed auth,
  navigation, and landing-style assets.

## Verification

- Commit: `1e36c63` (`Open Projects from public acquisition flow`)
- Production deployment: `dpl_EVUDxSqkkx64oNrFRdwJarNywkzA`
- The deployment is `READY` on all six production aliases with no alias error.
- A real browser loaded the styled public page at desktop width with its unique headline, six fixed
  Projects CTAs, no failed image, and no horizontal overflow. A 390-by-844 responsive evaluation
  kept both hero actions visible with no horizontal overflow.
- A real-controller authenticated fixture consumed `intent=projects`, called the existing product
  workspace with tab `projects`, emitted exactly one categorical continuation event, cleared the
  pending handoff, and reported zero browser errors.
- The live canonical page renders the correct title and headline with two stylesheets, six Projects
  CTAs, no horizontal overflow, and no browser warning or error.
- The canonical page, exact auth controller, exact navigation script, exact landing stylesheet, and
  sitemap each returned HTTP 200 and contained the expected release marker.
- All 479 Python tests passed. Python lint and explicit backend compilation passed.
- All 45 JavaScript files and the production preflight passed. The native web build contains the
  Projects page and exact Projects-entry assets. Store metadata checks still pass.
- Native submission remains gated by the already-recorded external requirements: the iOS project
  and Xcode/macOS path, both RevenueCat public SDK keys, and Android `google-services.json`.
- Production health returned HTTP 200 for Ask Crump 5.9.76. The first inspected deployment window
  contained two HTTP 200 responses and no warning, error, or fatal log.

## Outcome boundary

This release verifies discoverability, routing, visual delivery, and the non-generating handoff. It
does not prove acquisition, activation, retention, or revenue lift. The next valid evidence is a
legitimate external Projects visitor who creates or signs into an account, opens Projects, keeps
useful work, and later returns. No synthetic account, Project, event, artifact, or checkout was
created for this release.
