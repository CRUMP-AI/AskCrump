# Lifecycle idle-action delivery release — 2026-09-13

## Outcome

Ask Crump can now deliver a server-approved, in-product workspace guide while the composer is
genuinely idle. The normal empty-composer state deliberately disables **Send** because there is
nothing to submit. The lifecycle client was also interpreting that disabled control as active work,
so it returned before requesting a lifecycle decision and then repeated the same suppression check
before revealing any approved card.

The repaired state boundary no longer uses the disabled Send control as evidence of active work.
A typed draft, a visible attachment preview, or an active Crump presence indicator still suppresses
guidance. Recovery dialogs and busy application surfaces retain their separate suppression path.
This preserves the person's draft and in-flight work while allowing an otherwise idle workspace to
receive the existing, frequency-capped help.

## Evidence that selected this repair

A content-free, service-role production refresh found one comparable September account through
verification, workspace entry, starter intent, and activation. All five lifecycle controls were
enabled with their configured 20% account-stable holdout, but the weekly lifecycle export was empty
and the trailing production request sample contained no lifecycle-decision request. The client state
inspection then reproduced the cause without reading a prompt, response, filename, or customer
record: the empty composer had a disabled Send control, and that alone made `activeWork()` true.

This evidence identifies a deterministic delivery defect; it does not establish engagement or
retention lift. No event, account, decision, prompt, holdout assignment, or customer activity was
created to make the report look populated.

## Regression boundary

The phone-width browser fixture now matches production by starting with an empty, disabled Send
control. It proves all four relevant states:

- idle + disabled Send requests exactly one decision, displays **Keep it in a Project**, records
  `shown` and `acted`, and completes the existing private Project handoff;
- a typed, unsent draft makes no decision request and displays no card;
- a visible attachment preview makes no decision request and displays no card; and
- an active Crump presence indicator makes no decision request and displays no card.

The lifecycle asset uses the exact `5.9.76-lifecycle-idle-send-1` URL. Service-worker cache `r240`
replaces the prior cache so returning browser and PWA sessions receive the corrected state logic.
The overall application version remains 5.9.76.

## Automated validation

- Focused lifecycle tests passed **9/9**.
- The complete Python suite passed **1,049/1,049**.
- JavaScript validation passed **54/54**.
- The fail-closed button inventory remains **182 rendered + 94 programmatic = 276** reviewed button
  construction sites.
- The complete real-browser control matrix passed **45/45** flows, including the corrected idle
  lifecycle state and the existing continuity action.
- The public accessibility matrix passed **22/22** phone/desktop scenarios.
- Ruff, production preflight, native-web bundling, client-credential scanning, Python dependency
  audit, and diff integrity passed.

## Production evidence

- Feature commit `5cf00efaa15a34251793cf5d6a772257b048fa0c` is on `main`.
- Production deployment `dpl_7VFbBAy8kAhCZcezk9T6xQAVUTdX` is Ready and identifies that exact
  commit as its production source.
- GitHub Actions CI `34787538217`, Android verification `34787538207`, and iOS source verification
  `34787538228` completed successfully.
- `www.askcrump.com`, `askcrump.com`, `www.clevercrump.com`, and `clevercrump.com` each returned HTTP
  200 from `/api/health` at version 5.9.76.
- Live `runtime-body-v1.js`, `lifecycle-manager.js`, and `sw.js` bytes match the committed files by
  SHA-256. The live runtime names the new lifecycle asset, the live lifecycle manager omits the
  disabled-Send guard, and the live service worker identifies cache `r240`.
- The initial deployment log review contained seven HTTP 200 requests, no HTTP 4xx/5xx response,
  and no grouped runtime error.

## Operating boundary

The server remains authoritative for eligibility, static copy, account-stable holdout, one prompt
per session, two prompts per seven days, action idempotency, and suppression. This release does not
enable lifecycle email or push, bypass consent, force a prompt for an account, inspect customer
content, or claim that a lifecycle action caused activation, retention, referral, or revenue.
Observe the next legitimate eligible session and the first elapsed D1/D7 cohort before making any
behavioral claim.
