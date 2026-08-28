# Ask Crump 5.9.51 single-owner synchronization release

Date: 2026-08-28

## Outcome

Ask Crump now has one owner for authenticated startup and reconnection synchronization. The clean
starter-conversation experience no longer schedules a blind push while the authoritative startup
pull is in flight, and the presence layer no longer launches a second synchronization when the
browser returns online.

Normal user-created conversations still request an immediate save. Offline work still uses the
existing account-scoped pending queue, and the synchronization engine retains its ordered
pull/merge, push, and confirmation-pull convergence sequence.

## Root causes

Two independent call chains were responsible for the observed duplicate traffic:

1. Application startup created or promoted a blank starter conversation and called the ordinary
   save path. That scheduled a push 500 milliseconds later even though authenticated startup had
   already begun its own synchronization.
2. Both `chat-sync.js` and `presence-manager.js` responded to the same browser `online` event by
   starting conversation synchronization. The in-flight guard serialized the work, but deliberately
   replayed the second request, producing two complete cycles.

The two pulls inside one cycle are not duplicate triggers. They preserve the existing convergence
contract: establish server-authoritative state before pushing, then confirm the resulting server
state. This release removes the redundant owners without weakening that contract.

## Automated verification

- 364 backend and product tests passed.
- All 44 browser JavaScript files passed syntax and integration validation.
- Ruff, Python compilation, production preflight, native web-bundle generation, store metadata,
  and signing-secret controls passed.
- Android release source verification passed for Ask Crump 5.9.51, build 50951, and API 36.
- Expected local store blockers remain explicit: RevenueCat public SDK keys, Android
  `google-services.json`, signing credentials, signed archives, physical-device billing/push proof,
  and store-console declarations are not present in the release shell.

## Browser verification

Credential-free real-browser checks used the production application shell and mocked only the API
boundary:

- Restored session: exactly `pull -> push -> confirmation pull`.
- Fresh login: one login request, one session-confirmation request, and exactly one synchronization
  sequence.
- Stalled first pull: zero competing pushes during the stall; the single sequence completed after
  the pull recovered.
- Offline startup: zero synchronization requests while offline; exactly one sequence after the
  browser returned online.

These checks used fixture-only identities and passwords and did not create a production account,
session, conversation, event, or payment.

## Hosted release evidence

- Feature commit: `f17b3f62a609ea716abfc1d83ce0bee170ffdb8f`
- Production deployment: `dpl_EoWF3UipaBDMcCaqyct8dJssdMk5` (`READY`)
- General CI: GitHub run `33159045825` (`success`)
- Android Store Bundle Verification: GitHub run `33159045783` (`success`)
- iOS Store Source Verification: GitHub run `33159045809` (`success`)
- A new signed-out production browser received HTTP 200, Ask Crump 5.9.51, service-worker cache
  `ask-crump-new-body-v1-r85`, and versioned presence/sync assets. It made one successful
  `/api/auth/check-session` request, no protected request, and produced no script or console error.
- Vercel reported no runtime error cluster in the inspected 30-minute window and no error/fatal log
  for the 5.9.51 deployment.

## Human proof still required

The owner should fully close any installed PWA page, reopen Ask Crump, sign out, and manually sign
in with the real account. This is the only valid proof of the actual credential, cookie, mobile OS,
and installed-PWA boundary. No password should be shared with automation or placed in release
evidence.
