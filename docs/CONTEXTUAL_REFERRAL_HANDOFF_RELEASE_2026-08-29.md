# Contextual referral handoff release

Date: 2026-08-29

## Outcome

An Ask Crump response-share link now gives a new visitor product context before asking for an
account. Existing browser and installed-PWA sessions also receive the dedicated Project-opening
runtime through an explicit asset version.

## Root cause

The response-share path sent a cold visitor directly to `/app?signup=1`. That repeated the same
high-friction registration boundary seen in earlier acquisition data: a person could be asked to
create an account before seeing enough of the product to understand why.

The Project-opening interaction was already corrected in the product runtime and worked in a clean
production session, but the loader still requested the Project JavaScript and CSS at their original
unversioned URLs. A browser or installed PWA with an older loaded runtime therefore had no explicit
asset identity telling it that the Project behavior had changed.

## Correction

- Response-share text now links to `https://www.askcrump.com/` with the aggregate
  `acquisition=referral` channel and fixed `source=response-share` placement.
- The public product page preserves that allowlisted placement across its signup and sign-in CTAs,
  so the visitor can understand the product before crossing the authentication boundary.
- Only `response-share` qualifies as a placement. Arbitrary source values are not copied into the
  app handoff.
- The Project workspace JavaScript and CSS use the explicit
  `5.9.76-project-workspaces-2` identity in web, service-worker, and native loaders.
- Service-worker cache revision `ask-crump-new-body-v1-r125` distributes the new assets.

## Privacy boundary

The shared URL contains no account, user, conversation, message, Project, content, filename, or
referrer identifier. Registration continues to persist only the existing aggregate `referral`
acquisition channel. `response-share` remains a fixed UI placement used by the anonymous funnel,
not a free-form or server-authoritative customer field.

## Verification

- All 469 Python tests passed.
- All 45 JavaScript files passed the integration validator.
- Explicit Python compilation and production preflight passed.
- The native web bundle rebuilt successfully and store metadata source checks passed.
- A credential-free browser fixture rewrote signup and sign-in CTAs to preserve exactly
  `acquisition=referral` and `source=response-share`, retained both values for the session, emitted
  the existing marketing events, made no network write, and produced zero browser errors.
- The real Project fixture opened `Launch Operations` into its detail workspace, started a scoped
  Project chat, and produced zero browser errors.
- Signed-in production opened `The Last Distance` as `Ask Crump Project: The Last Distance` with
  Project files, conversations, and `New chat in this Project` available.
- Production returned HTTP 200 for the public product page, contextual landing runtime, response
  sharing runtime, explicitly versioned Project runtime, service worker, and canonical health.
- The exact production deployment had 40 successful responses in the first inspected window and
  no 4xx, 5xx, warning, error, fatal, or deployment-specific runtime error log.
- A separate three-occurrence database 503 group in the project-level 15-minute view ended on the
  immediately prior deployment; it did not occur on this release.

## Release

- Code commit: `5ea65e2885578643e10a7c2b25fecc50c30f1694`
- Production deployment: `dpl_6fGicVAbJCimz9bSpiNPQGgecqZa`
- Production aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`, and
  `www.clevercrump.com`

## Outcome gate

Delivery is verified. Business impact remains unproven until legitimate external traffic produces
the sequence from response sharing to referral visit, signup intent, account creation, and
activation. No account, event, message, artifact, share, or checkout was manufactured for proof.
