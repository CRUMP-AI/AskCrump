# Chats accessibility language release

Date: 2026-08-30
Production version: `5.9.76`

## Outcome

Ask Crump now names its conversation drawer **Chats** consistently in visible controls,
accessible names, and mobile open/close state. The correction removes the remaining
“conversation library” terminology from the live shell, so Library continues to mean only the
books-and-manuscripts destination while Chats remains a utility under Ask.

This is a narrow reliability and comprehension release. It does not change the five-destination
information architecture, rename compatibility hooks, or claim an acquisition or conversion
improvement.

## Decision evidence

A product-wide destination-promise audit followed the Video signup correction. Public pages,
registration, onboarding, and the store-facing destination map already agreed that generated and
uploaded work belongs in Projects → Files and Library is solely for manuscripts and books.

The audit found one remaining customer-facing inconsistency: the workspace visibly displayed
Chats while its legacy rail, sidebar region, close control, and mobile menu still announced
“conversation library.” The mobile menu also kept a static Open label while the drawer was
expanded. Internal class names and APIs that still contain “library” are retained as compatibility
wiring and are not exposed as product language.

## Product contract

- The conversation region is named Chats.
- Desktop conversation controls announce **Hide Chats** or **Show Chats** from real drawer state.
- The mobile menu announces **Open Chats** or **Close Chats** from real drawer state.
- Selecting Settings, Plan & credits, or Projects on mobile executes the destination before
  closing Chats, then restores the Open Chats state.
- Ask remains the sole primary active destination while Chats remains its subordinate drawer.
- Library remains the books-and-manuscripts destination; Projects → Files remains the location for
  generated and uploaded work.

No authentication, account, conversation, Project, file, manuscript, generation, billing,
checkout, subscription, analytics, database, storage, provider, or private-data behavior changed.

## Verification

- All 523 Python tests passed.
- All 45 JavaScript files passed the repository integration validator.
- Production preflight and the generated native web-bundle build passed.
- Diff integrity passed.
- A credential-free real-runtime mobile fixture proved collapsed, expanded, direct-close, and
  Settings-selection states. The destination executed once before the drawer closed.
- A credential-free real-runtime desktop fixture proved the permanent control moves between
  Hide Chats and Show Chats, uses the quieter open state, and leaves Ask as the primary
  destination.
- All browser verification tabs were closed and the temporary local server was stopped.
- All six production aliases and the deployed app, runtime loader, versioned navigation assets,
  and service worker returned HTTP 200 with the expected contract.

## Production release

- Feature commit: `3ad9ffc`
- Deployment: `dpl_9b6WGbeRPPXKodJvZPYFw2JMRMV2`
- Deployment state: `READY`
- Alias state: six production aliases, no alias error
- Service-worker cache: `ask-crump-new-body-v1-r149`
- Asset boundary: `5.9.76-chats-language-1`
- Framework: other / Vercel Functions
- Post-release observation: no runtime-error cluster, no warning/error/fatal deployment log, and
  only HTTP 200 in the observed deployment status-code sample

No production account, credential, login, signup submission, funnel event, message, Project, file,
generation, checkout, payment, or subscription was created for verification.

## Next operating decision

Keep the five-destination structure and authentication path stable. Preserve the existing
legitimate-traffic observation gate before changing authentication, and continue prioritizing
deterministic first-use, continuing-work, and conversion defects that can be proven without
manufacturing production behavior.
