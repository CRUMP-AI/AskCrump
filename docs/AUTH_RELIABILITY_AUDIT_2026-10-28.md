# Authentication reliability audit — October 28, 2026

Scope: signed-out entry, guest-to-account sign-in, credential submission, session confirmation, workspace loading, account isolation, error recovery, and web/native/PWA asset parity. This patch contains no schema, provider, billing, or Autonomous feature release.

## Findings and corrections

1. Login analytics could throw before the submit control changed state. Busy/disabled/aria-busy now precede telemetry; synchronous throws and asynchronous rejection do not block authentication.
2. Validation feedback could sit below a phone keyboard. Login errors precede Submit and scroll into the visible viewport; credentials are preserved during failure/retry.
3. Optional settings reads used the database client's long retry budget after authentication succeeded, delaying the actual cookie-bearing response. Login and session confirmation now give optional settings one second, then return the validated account with `settings: null, settingsUnavailable: true`. Existing preferences are not overwritten; essential authentication and renewal remain mandatory.
4. Session checks translated non-401 authentication-service failures into a successful signed-out response. Only an authoritative 401 is now translated; owner conflicts and temporary service failures retain their non-2xx result.
5. The browser swallowed malformed successful JSON and interpreted incomplete session responses as signed-out. Invalid JSON/shapes now preserve identity and report temporary unavailability. Only explicit successful `authenticated: false` permits local clearing.
6. Aborting a request did not guarantee that an overridden fetch or body reader settled. An independently rejecting deadline bounds the complete fetch/body promise. Ambiguous timeout or malformed login response performs one matching account/email readback without replaying credentials. Mismatched owners are rejected.
7. Successful credentials could wait indefinitely for workspace CSS/scripts. Web and native loaders now bound each asset and the entire load, clean waiters, retain completed assets, and show session-preserving recovery. A timed-out classic script requires document reload; the loader never reinserts an ambiguously executed script or announces a false ready state. Reload retries workspace loading without repeating the credential POST.
8. Known registered devices could return to guest entry after session loss. A content-free registered-account hint directs recovery to explicit sign-in, including restored Free URLs. An actual public Free click carries a consumed, 30-second session intent so deliberate guest preview remains available without removing the registered hint. These hints are routing only, never authorization.
9. Invalid credentials lacked an actionable recovery hint. The generic rejection now points existing account holders to Forgot password without disclosing account existence. Security-required inbox password setup remains enforced; there is no password or verification bypass.
10. A recovered, verified session that still required initial password setup could pass the login handoff directly into workspace loading. A shared setup gate now holds bootstrap, login response recovery, and guest handoff on the setup form before any workspace asset loads.

## Verification

Regression coverage includes optional settings delay/failure, essential session errors, malformed response preservation, committed-response loss, owner mismatch, ignored abort signals, hung stylesheet/script recovery, real production shell plus all workspace scripts, telemetry failure, mobile keyboard-sized touch input, account persistence and known-account session loss. Tests use synthetic identities and loopback APIs, with no AI/provider calls. Asset tokens and the service-worker cache advance together.

The release requires Python/JavaScript/CI, browser-control and accessibility gates, independent review, a READY deployment, served-version/cache verification, and bounded production health/log inspection. A merge or READY state alone does not establish real-account success.

## Limits requiring device confirmation

Actual Playwright WebKit is distinct from Chromium with a Safari user agent. Neither proves an installed iPhone PWA process restart or the real Safari software keyboard. Those device checks remain OPEN until verified. Closing a surviving tab is also distinct from destroying all private-session storage: destroyed sessions must reauthenticate explicitly, with no silent guest fallback where a registered-device hint survives.

Native secure-storage readiness remains a separate platform dependency; this web/PWA release does not claim to certify native store binaries. Password recovery requires the account holder to choose a new password privately through the official email link. No account credentials, reset tokens, private content, or account identifiers belong in this audit or its evidence.
