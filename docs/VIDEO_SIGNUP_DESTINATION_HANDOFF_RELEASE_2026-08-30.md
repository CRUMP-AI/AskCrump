# Video signup destination handoff release

Date: 2026-08-30
Production version: `5.9.76`

## Outcome

A visitor choosing Video now receives the same storage promise throughout the public page,
registration handoff, workspace guide, and signed-in product: completed clips remain available
through **Projects → Files**. Registration no longer tells the visitor that video is placed in the
private Library, which is reserved for manuscripts and books.

This closes a deterministic expectation gap at the highest-intent account-entry boundary. The
correction does not claim a signup-rate improvement; it makes the promise accurate before the
existing observation gate is evaluated.

## Decision evidence

The production analytics review continued to show that nearly all signup-intent visitors reached
the app through a direct signup link and that mobile represented the majority of that directional
traffic. The current window remains too small and crosses recent attribution boundaries, so it was
not treated as a conversion rate or used to justify an authentication rewrite.

Source inspection instead found a concrete contradiction. The public Video page and the released
five-destination contract correctly sent completed clips to Projects → Files, while the dynamic
Video registration description still promised a private-Library result.

## Product contract

- Video intent still opens the existing Video Studio after verification.
- The registration screen still discloses Crump Credit cost and free account creation.
- Completed clips are described as available through Projects → Files.
- Library remains solely the private bookshelf for manuscripts and books.
- The primary registration action, password rules, consent, verification, pricing, acquisition,
  and creation-intent semantics are unchanged.

No authentication API, session authority, account creation, email delivery, Project/file storage,
generation, entitlement, billing, price, checkout, provider, database, or private-data behavior
changed.

## Verification

- All 522 Python tests passed.
- All 45 JavaScript files passed the repository integration validator.
- Production preflight and the native web-bundle build passed.
- Diff integrity passed.
- The real cold-entry controller fixture loaded Video intent, focused Email, displayed the exact
  Projects → Files promise, retained the Video exploration link and primary continuation action,
  and remained stable after the signed-out session result.
- Automated destination guards require the new promise and reject the superseded private-Library
  sentence.
- The canonical app source, versioned authentication controller, and service worker returned HTTP
  200 from production with the expected release identifiers.

## Production release

- Feature commit: `3ab94c0`
- Deployment: `dpl_DD3AhukZY5xL3kfXbuYTaSw3eLaf`
- Deployment state: `READY`
- Alias state: six production aliases, no alias error
- Service-worker cache: `ask-crump-new-body-v1-r148`
- Authentication-controller boundary: `5.9.76-video-files-handoff-1`
- Framework: other / Vercel Functions

No production account, credential, login, signup submission, funnel event, message, Project, file,
video generation, checkout, payment, or subscription was created for verification. Production
signup JavaScript was not executed merely to prove copy because that would manufacture a
`SignupIntent` event; the dynamic behavior was proven in the credential-free local fixture and the
deployed static assets were verified independently.

## Next operating decision

Keep authentication and the five-destination structure stable. Continue the existing decision
boundary: review the SignupIntent → SignupStarted journey after at least 14 elapsed days and 50
legitimate socially referred visitors, or diagnose a sooner consented real attempt. In parallel,
focus acquisition on contextual public pages rather than sending context-free social traffic
directly into registration.
