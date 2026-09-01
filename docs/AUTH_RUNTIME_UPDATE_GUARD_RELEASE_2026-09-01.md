# Auth runtime-update guard release — 2026-09-01

## Outcome

Ask Crump's signed-out runtime updater can again distinguish an untouched account-entry screen from
real in-progress form work. The prior guard read every input's string value. An unchecked checkbox
still has the browser-default value `on`, so the always-present Terms checkbox made every signed-out
screen appear dirty. A ready sign-in or reliability update therefore displayed a fixed overlay
instead of performing the intended safe one-time refresh.

The corrected guard now interprets controls by their actual semantics:

- checkbox and radio inputs count as work only when deliberately checked;
- file inputs count as work only when a file is selected;
- disabled controls do not count;
- typed fields continue to count as work; and
- a busy authentication form continues to block automatic refresh.

An untouched signed-out page can safely adopt the current runtime. Typed credentials, deliberately
checked consent, and in-flight authentication remain under the person's control and receive the
existing explicit **Reload now** or **Later** choice.

## Boundaries

- No authentication endpoint, password rule, verification flow, credential, cookie, session,
  account, database, analytics, attribution, billing, entitlement, credit, model, provider, or
  customer-data contract changed.
- No credential or personal value is logged, stored, inspected, or sent by the update guard.
- The refresh remains bounded by the existing 15-second session guard.
- This repair removes false form-work detection. It does not claim more registrations, successful
  authentication, activation, retention, or revenue.

## Verification

- All **780 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Ruff, explicit Python compilation, production preflight, native web-bundle creation, store
  metadata, mobile signing-source controls, and diff integrity passed.
- A 390×430 real-browser fixture exercised the exact released updater:
  - the clean form contained an unchecked checkbox with default value `on`, performed one safe
    reload, set the reload guard, and rendered no update notice;
  - the typed-email form did not reload, preserved its value, and rendered one update notice;
  - the deliberately checked Terms form did not reload, preserved checked state, and rendered one
    update notice; and
  - all three scenarios produced zero console or page errors.
- The ordinary signup surface was inspected at 1,440×900, 390×844, 390×667, and 390×430. Email,
  password, Terms, and submit controls remained reachable; the software-keyboard-height stage kept
  a real vertical scroll owner.
- The live `install-prompt.js` and `sw.js` matched the committed SHA-256 bytes.
- The live `/app` HTML referenced `5.9.76-auth-update-guard-1` and cache `r210` was current.
- `/api/health` returned HTTP 200 and version 5.9.76.
- After settlement, the exact deployment contained two HTTP 200 observations, no
  warning/error/fatal log, and no runtime-error cluster.
- Verification created no production account, signup event, credential, session, Project, file,
  payment, credit, provider request, or customer-data mutation.

## Release identity

- Feature commit: `76da12a6e1d6cc4cc859712647819a77df5df3be`
- Production deployment: `dpl_CLCrBzFcQGKjiH54jjr5vjrnrQLp`
- Status: `READY`
- Build duration: about 35 seconds
- Canonical aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and both Vercel production aliases

## Remaining acceptance work

1. Observe legitimate registration, verification, sign-in, and recovery outcomes; do not infer
   conversion from delivery alone.
2. Repeat the update transition with an untouched form, typed credentials, and checked consent on
   exact signed iPhone and Android candidates before final store screenshots.
3. Preserve the current zero-spend gate until a legitimate matched account reaches useful work,
   Project continuity, an editable artifact, and an eligible return.
