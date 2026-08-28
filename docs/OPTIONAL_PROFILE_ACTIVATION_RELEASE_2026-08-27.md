# Optional profile activation release — 2026-08-27

## Decision

Ship the verified-account first-workspace correction as Ask Crump 5.9.38. Keep the legally
required, server-saved terms gate unchanged, but stop requiring a display name before the user can
reach the task-oriented launchpad. Offer name setup as a compact, dismissible personalization
prompt instead.

This is a delivery correction, not evidence of improved activation. A legitimate new account still
has to complete the measured account-created → workspace-opened → starter-intent path before an
outcome claim is warranted.

## Reproducible defect

New registration intentionally creates an account without `fullName`. After verification and terms
acceptance, the client always routed that account into a mandatory name modal and returned before
starting the workspace. The launchpad itself does not require a name, and Profile settings already
support adding one later, so this was a nonessential commitment between verification and first
value.

## Bounded correction

- Terms acceptance remains mandatory, server-saved, and ahead of workspace entry.
- A verified user who has accepted terms now reaches the launchpad even without a display name.
- The launchpad offers Add your name and Not now actions; dismissal is scoped to that account on
  the device.
- The optional dialog is keyboard-focused, Escape-dismissible, length-bounded, resistant to double
  submission, and explicit about server save failures.
- Saving a name in Settings is now reported as successful only after the profile endpoint accepts
  it. A confirmed save removes the optional prompt immediately.
- `OnboardingCompleted` remains server-authoritative and is emitted only when the backend accepts
  the account's first nonempty name.
- Registration, verification, password, pricing, entitlement, and payment behavior did not change.

## Source and release identity

- Application commit: `81b39be1fe5980cea9704c2d88163fbea0f9d04e`
- Production deployment: `dpl_G7oecbc71CPp6913TWvDoacTxsSv`
- Production version: 5.9.38
- Native build: 50938
- Service-worker cache: `ask-crump-new-body-v1-r72`
- Production aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the Vercel production aliases

## Verification evidence

Local release verification passed before publication:

- 320 backend/contract tests
- backend/test lint
- all 42 JavaScript source validations
- JavaScript syntax checks for the edited workspace and authentication controllers
- production build preflight
- native web-bundle generation
- Android 5.9.38/build 50938/API 36 source verification
- store metadata and mobile signing-source controls
- clean patch and release-version/cache consistency checks

Hosted verification passed on the exact application commit:

- CI: [run 33137238298](https://github.com/CRUMP-AI/AskCrump/actions/runs/33137238298)
- Android unsigned App Bundle: [run 33137238297](https://github.com/CRUMP-AI/AskCrump/actions/runs/33137238297)
- iOS unsigned Release compile: [run 33137238319](https://github.com/CRUMP-AI/AskCrump/actions/runs/33137238319)

The Android and iOS workflows generated and verified the release source, passed tracked signing
controls, and compiled unsigned candidates. They did not sign, upload, submit, or use store
credentials.

## Production verification

- The exact Git commit produced a `READY` production deployment with no alias error.
- `https://askcrump.com/api/health` returned HTTP 200, `Cache-Control: no-store`, and version
  5.9.38.
- The live app shell, workspace controller, authentication controller, stylesheet, and service
  worker returned HTTP 200. The shell contained the optional profile surface, the controller
  contained the nonblocking route, and the service worker contained cache revision 72.
- The release-scoped scan found no runtime error cluster and no warning, error, or fatal log.
- The inspected deployment returned only HTTP 200 responses. The visible request paths were the
  explicit `/api/health` probe and existing `/api/cron/manuscripts` maintenance traffic; no signup,
  profile, terms, account, or activation request was generated for verification.
- The owner's remembered-device path reached the signed-in workspace. A fresh credential-entry test
  after explicit sign-out remains the final human session-handoff check.

## Measurement boundary and rollback

No synthetic account, profile update, terms acceptance, activation event, or funnel event was
created. Delivery is verified; activation lift is unproven. Observe the next legitimate account's
content-free `AccountCreated`, `WorkspaceOpened`, and `StarterIntent` progression before deciding
whether this reduced first-value friction.

Rollback is the prior application commit and cache revision. Terms enforcement and backend profile
semantics were not weakened, so no data migration or cleanup is required.
