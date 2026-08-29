# Entry quality release — 2026-08-29

Status: verified in production; repeat-device and signup outcomes pending

## Decision

Correct two deterministic entry defects without changing authentication policy, session ownership,
pricing, entitlements, customer data, or funnel definitions:

1. keep the branded loading cover in place until the authenticated workspace has completed its
   first stable render; and
2. give a cold registration visitor a restrained, contextual route back to the capability that
   brought them to Ask Crump when they are not ready to enter credentials.

## Evidence before the change

- An owner-observed refresh showed the loading screen glitch immediately before the workspace
  appeared.
- The preceding three-hour production runtime window contained no warning, error, or fatal log and
  the observed request group contained 480 HTTP 200 responses. This ruled out a server failure.
- A signed-in browser trace showed the loading gate begin its fade as soon as the deferred runtime
  reported ready. Source inspection then confirmed that the gate could release before
  initializeApp, authenticated initialization, and authenticated-ready listeners had completed
  their first visual work.
- Registration offered account creation and sign-in but no secondary route to evaluate the product.
  Qualified document, presentation, résumé, and video intent was already allowlisted and preserved,
  so this gap could be corrected without collecting a new property or changing auth behavior.

## Change

- Workspace-gate release now occurs only after the base application initializer, authenticated
  initializer, and authenticated-ready dispatch complete.
- Two browser paint frames are committed before the existing 200-millisecond cover fade begins.
  The bounded five-second safety release remains intact.
- Registration now includes one subtle, progressively enhanced exploration link.
- The link defaults to the Ask Crump product page and maps the existing allowlisted intent to the
  matching public page:
  - document → AI document generator;
  - presentation → AI presentation maker;
  - résumé → AI résumé builder; and
  - video → Video Studio.
- No account, verification, session, payment, analytics-event, entitlement, provider, schema, or
  private-data contract changed.

## Executable and browser proof

- The startup contract now requires loading-gate release to follow both application initialization
  and the authenticated-ready dispatch.
- The delayed-session fixture uses the real auth controller, a bounded deferred runtime, and
  credential-free authenticated markers. It proves runtime-ready, application initialization, and
  authenticated initialization without a production account or write.
- A clean local browser run reached signed-in, application-started, and runtime-ready states before
  the gate completed hiding. Busy and inert state cleared, with no console warning or error.
- The deployed signed-in workspace was refreshed once. It returned to the complete Ask surface with
  the expected launch heading, a hidden completed gate, runtime-ready state, no busy or inert
  residue, and no browser warning or error.
- Read-only production asset checks confirmed the default exploration link, all four intent
  destinations, and the stable-reveal implementation.

## Verification

- Feature commit: 54ad911 (Stabilize workspace reveal and cold signup).
- Production deployment: dpl_3GNcGWaZz2K8DCg7v1EzGAognKi1, READY on all six Ask Crump and
  Clever Crump aliases with no alias error.
- All 441 automated tests passed.
- All 45 JavaScript files validated.
- Production preflight, native web-bundle creation, and store-metadata checks passed.
- Canonical health returned HTTP 200, Cache-Control: no-store, and version 5.9.75.
- The inspected deployment window contained 51 HTTP 200 responses and no warning, error, or fatal
  runtime log.
- Verification submitted no registration form and created no account, conversation, message,
  artifact, Project, payment, social publication, or Search Console change.

## Outcome boundary

The deterministic reveal race and missing exploration route are corrected. Do not claim improved
conversion or retention until legitimate visitors use the new path and the owner confirms smooth
refresh behavior across the affected real devices.
