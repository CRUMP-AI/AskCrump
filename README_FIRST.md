# Ask Crump — Phase 1 Auth + Session Persistence Hardening

## Scope
Only Phase 1 foundation work. No feature additions and no UI redesign.

## Copy/replace
Copy the contents of this ZIP into the root of the CRUMP-AI repository.

Replace these existing files:
- `public/auth-controller.js`
- `public/device-auth.js`
- `tests/test_frontend_auth_policy.py`

Add this new regression test:
- `tests/test_auth_session_persistence.py`

No apply script is required.

## Fixes included
- Frontend password policy is made consistent with the backend 10–256 character + letter + number rule at runtime before auth interaction.
- Signup email-delivery failure is treated as a recoverable pending account instead of a generic failed signup.
- Same-page duplicate login submissions are serialized.
- A successful login is immediately confirmed against `/api/auth/check-session`; a stale same-installation result is retried once.
- Transient session-check failures no longer clear persisted local identity state or imply an actual logout.
- Bootstrap tells the user the saved sign-in was preserved when verification is temporarily unavailable.
- Explicit logout still clears native secure token and local account cache.

## Intentionally unchanged
- Visual layout, colors, spacing, navigation, composer, settings layout.
- Backend session storage, token hashing, cookie policy, rate limits, verification/reset routes.
- Billing, cron/check-ins, product features.

## Verification after copy
From repository root:

```powershell
node --check public\auth-controller.js
node --check public\device-auth.js
.\.venv\Scripts\python.exe -m pytest -q tests\test_release_hardening.py tests\test_frontend_auth_policy.py tests\test_auth_session_persistence.py
npm test
```

Then commit/push. After Vercel finishes, ask Echo to verify GitHub `main`, the production deployment SHA, static files, Vercel auth runtime logs, and Supabase session state.

## Commit title
Harden auth and session persistence

## Commit summary
Harden Ask Crump authentication and session persistence without changing the established UI/UX. Align the frontend password contract with the backend, recover cleanly when signup email delivery fails, serialize and confirm same-device logins, preserve valid credentials across transient session-check failures, and add targeted regression coverage for auth/session stability.

## Commit body
- align frontend password validation with the backend auth contract
- recover pending signup accounts when verification email delivery fails
- serialize duplicate same-page login attempts
- confirm newly issued sessions and retry stale same-installation races once
- preserve saved credentials during transient session verification failures
- keep explicit logout behavior destructive and deterministic
- add auth/session persistence regression tests
