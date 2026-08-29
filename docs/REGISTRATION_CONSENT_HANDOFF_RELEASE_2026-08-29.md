# Registration consent handoff release

Date: 2026-08-29

## Outcome

Current registrations now collect explicit age, Terms, and Privacy consent before the account is
created. The server records only the published `2026-08-01` legal version on the new or pending
account, so a verified user can enter the workspace without an avoidable second consent
interruption. The authenticated consent modal remains as a compatibility fallback for older
clients, existing accounts, and registrations without explicit current-version consent.

## Why this was selected

The trailing seven-day acquisition sample remained below the operating decision boundary:
122 visitors, 503 pageviews, 55% bounce, 32 signup-intent visitors, two signup starts, and zero
comparable external accounts in the server-owned growth report. That sample does not justify an
authentication rewrite. The deterministic defect was narrower: the public legal page was effective
August 1 while the browser sent a July 30 version, and a current registration still encountered a
second legal gate after verification.

## Safety and compatibility

- The server accepts the canonical published version only; arbitrary legal-version strings are
  rejected by the request schema.
- No consent is inferred from visiting, opening a verification link, or signing in.
- Legacy registration requests remain compatible and continue into the existing authenticated
  consent fallback.
- The pending-account sign-in fallback now states that it is for a person who already verified on
  another device.
- No synthetic production account, registration event, email, or session was created for release
  verification.

## Verification

- Commit: `b5283be` (`Record consent during account creation`)
- Final production deployment: `dpl_w7qv72UP7SWXwbY99HJrq1jYMsEX`
- 479 Python tests passed.
- Python lint and explicit compilation passed.
- All 45 JavaScript files passed the runtime contract checker.
- Production preflight and native web-bundle build passed.
- Store metadata source validation passed; native submission gates remain unchanged.
- An isolated 390 by 700 browser run proved the checkbox is present, required, unchecked by
  default, browser-validity-blocking, fully visible with the submit action, and free of horizontal
  overflow or browser errors.
- Canonical production health returned HTTP 200 with service `Ask Crump` and version `5.9.76`.
- Canonical `app.html`, the independently versioned auth controller, and the legal page returned
  HTTP 200 and contained the required consent control, `2026-08-01` contract, registration payload,
  another-device copy, and published effective date.
- The first exact-deployment runtime window contained two HTTP 200 responses and no
  warning, error, or fatal log.

## Outcome boundary

This release proves the delivery path, not conversion lift. The next evidence is the first
legitimate current-version registration that verifies, receives a session, opens the workspace,
and reaches an activated outcome. Re-evaluate broader authentication changes only after the
existing 14-day or 50-additional-social-visitor boundary.
