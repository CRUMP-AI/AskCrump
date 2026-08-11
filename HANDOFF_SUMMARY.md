# Ask Crump Production Hardening — Manual Release Handoff

**Prepared:** 2026-08-11  
**Audited repository:** `CRUMP-AI/CRUMP-AI`  
**Audited main commit:** `f8e73eb22021fe2e24f8f9b948b1e4837de4db2c`  
**Purpose:** Final foundation hardening before additional feature expansion.

## Handoff status

This package contains the complete manual code handoff for the accepted release-blocking findings:

1. Stripe Enterprise cancellation entitlement bug — fixed.
2. Signup failure after account creation when transactional email fails — fixed with controlled recovery behavior.
3. Same-device session race — fixed with atomic PostgREST upsert behavior.
4. Production/CI dependency parity — fixed and regression-tested.
5. Frontend/backend password-policy mismatch — fixed through guarded frontend patching and tests.
6. Production Supabase hardening missing from repository migrations — represented as numbered migrations.
7. Regression tests — added for the critical hardening behaviors.

No web, image, video, product redesign, or speculative feature work is included.

## Why the frontend is applied by a guarded patch

`public/app.html` and `public/auth-controller.js` are large, actively edited UI files. Rather than ship stale whole-file replacements that could overwrite unrelated UI changes, `APPLY_HANDOFF.py` verifies the exact audited baseline fragments and applies only the required changes. If those fragments have changed in your local repository, it stops instead of guessing.

A human-readable unified diff is included at `PATCHES/frontend-hardening.diff`.

## Recommended commit package

### Commit title

`Harden auth, billing, sessions, and release gates`

### Commit summary

Hardens Ask Crump's production foundation by making device-session rotation atomic, containing transactional email provider failures without stranding signup UX, correcting paid subscription entitlement handling, aligning CI/runtime dependencies, matching frontend password validation to the server contract, and recording the live Supabase security migrations in source control. Adds focused regression coverage for the release-blocking failures found during the production-readiness audit.

### Commit body / PR bullets

- make same-installation login session rotation atomic via `device_id` upsert
- add Resend idempotency keys, bounded transient retries, and typed delivery errors
- return a recoverable pending-account state when verification email delivery fails
- guide the registration UI into resend-verification instead of encouraging duplicate signup
- align registration/reset password UI with the 10-character + letter + number server policy
- prevent canceled/inactive Enterprise subscriptions from retaining paid usage entitlement
- preserve legitimate cancel-at-period-end access only while the paid period remains valid
- return controlled Stripe provider errors and recover stale checkout customer IDs once
- synchronize `requirements.txt` with `pyproject.toml` production runtime dependencies
- add dependency-parity, email, session, entitlement, webhook, and frontend regression tests
- add repo migrations representing the live Supabase Data API lockdown and credit-ledger index
- add a source-control guard ensuring the unique `sessions.device_id` key required by atomic session rotation

# Files changed

| Path | Action | Why | Risk / follow-up |
|---|---|---|---|
| `backend/email_service.py` | Modified | Adds typed delivery errors, deterministic Resend idempotency keys, bounded retry for network/429/5xx failures, and avoids leaking provider response bodies. | Requires existing valid `RESEND_API_KEY`; no new env var. |
| `backend/auth_service.py` | Modified | Replaces read-then-write device session creation with atomic upsert on `device_id`. | Requires unique `sessions.device_id`; migration 008 guards this. |
| `backend/routes/auth.py` | Modified | Converts verification-email provider failures into a recoverable 503 pending-account response; hardens resend/reset logging. | Fresh-user email flow must be tested after deployment. |
| `backend/routes/billing.py` | Modified | Fixes canceled Enterprise entitlement persistence, adds controlled Stripe errors, and one-time stale-customer checkout recovery. | Test with Stripe test-mode webhook before go-live. |
| `backend/usage_service.py` | Modified | Adds defense-in-depth effective entitlement evaluation so stale terminal paid labels cannot grant paid usage. | `canceling` and `billing_issue` retain paid access only with a future period end. |
| `requirements.txt` | Modified | Brings CI-installed runtime libraries into exact parity with `pyproject.toml`. | Reinstall Python dependencies locally/CI. |
| `public/app.html` | Modified by `APPLY_HANDOFF.py` | Changes 8-character password copy/constraints to the actual server policy. | Guarded exact patch; script aborts on baseline mismatch. |
| `public/auth-controller.js` | Modified by `APPLY_HANDOFF.py` | Adds matching client password validation and explicit recovery UX for account-created/email-send-failed responses. | Guarded exact patch; script aborts on baseline mismatch. |
| `tests/test_release_hardening.py` | Created | Regression tests for Resend failures/retries, pending-account signup recovery, atomic sessions, Stripe cancellation, and usage entitlement. | None. |
| `tests/test_dependency_parity.py` | Created | Prevents `requirements.txt` and `pyproject.toml` from drifting again. | None. |
| `tests/test_frontend_auth_policy.py` | Created | Prevents password-policy copy/validation regression and verifies email-failure recovery UI. | Run after frontend patch. |
| `migrations/006_lock_public_data_api_to_service_role.sql` | Created | Represents the critical Data API lockdown already applied in production. | **Already applied in production. Do not need to rerun there.** |
| `migrations/007_index_credit_ledger_related_ledger.sql` | Created | Represents the missing FK/reconciliation index already added in production. | **Already applied in production.** |
| `migrations/008_ensure_atomic_device_session_key.sql` | Created | Ensures clean environments have the unique key required by session upsert. | Production already has equivalent unique index; source-control guard. Fails safely if duplicates exist elsewhere. |
| `APPLY_HANDOFF.py` | Created handoff utility | Safely copies replacements and patches the two large frontend files after exact baseline validation. | Handoff-only; do not commit unless you intentionally want the utility in the repo. |
| `PATCHES/frontend-hardening.diff` | Created handoff reference | Human-readable frontend diff. | Handoff-only. |

# Supabase migration handoff

## Migration order

Apply in this source order after migrations 001–005:

1. `006_lock_public_data_api_to_service_role.sql`
2. `007_index_credit_ledger_related_ledger.sql`
3. `008_ensure_atomic_device_session_key.sql`

## Production status

### 006 — already applied in production

Production Supabase migration name: `lock_public_data_api_to_service_role`.

It revokes direct application-table/sequence/function access from `anon` and `authenticated`, removes two misleading historical permissive policies, and prevents future `postgres`-owned application objects from reopening those grants by default.

**Do not rerun it merely because you add this file to GitHub.** The file exists so a clean rebuild/staging environment matches production.

### 007 — already applied in production

Production Supabase migration name: `index_credit_ledger_related_ledger`.

Adds the `credit_ledger_related_ledger_idx` partial index used by refund/reconciliation relationships.

### 008 — production already has equivalent state

Production already has `sessions_device_id_unique`. This migration makes that requirement explicit for clean/staging environments and refuses to silently delete/merge duplicate sessions.

## Non-production caution

Migration 006 intentionally disables direct Supabase Data API access for `anon` and `authenticated`. That matches Ask Crump's server-only database architecture. If a separate staging/dev build directly uses a browser Supabase client, 006 will break that direct-access pattern by design.

Migration 008 aborts if duplicate non-null `device_id` values exist. Resolve duplicates intentionally before retrying; do not blindly delete production-like session data.

# Manual apply instructions

## Recommended automatic handoff path — Windows / GitHub Desktop

1. Download and extract this handoff ZIP **outside** your CRUMP-AI repository.
2. Close any local Ask Crump dev server.
3. Open PowerShell in the extracted handoff folder.
4. Run:

```powershell
py APPLY_HANDOFF.py "C:\path\to\your\CRUMP-AI"
```

If `py` is unavailable:

```powershell
python APPLY_HANDOFF.py "C:\path\to\your\CRUMP-AI"
```

5. The script:
   - validates audited Git blob hashes for the backend replacement files;
   - validates the two frontend files against the audited baseline fragments;
   - creates backups inside the extracted handoff folder;
   - copies the backend/test/migration/requirements replacements into the correct repo paths;
   - patches only the required frontend fragments.
6. Open GitHub Desktop and inspect the diff before committing.
7. Do **not** commit the extracted handoff folder or its generated `BACKUP-*` folder; only commit files inside your actual CRUMP-AI repository.

## Manual copy alternative

Copy these package paths directly over the same paths in the repo:

```text
backend/email_service.py
backend/auth_service.py
backend/routes/auth.py
backend/routes/billing.py
backend/usage_service.py
requirements.txt
tests/test_release_hardening.py
tests/test_dependency_parity.py
tests/test_frontend_auth_policy.py
migrations/006_lock_public_data_api_to_service_role.sql
migrations/007_index_credit_ledger_related_ledger.sql
migrations/008_ensure_atomic_device_session_key.sql
```

Then apply `PATCHES/frontend-hardening.diff` to:

```text
public/app.html
public/auth-controller.js
```

The automatic script is safer because it validates every frontend baseline replacement.

# Dependency installation

No new product dependency was introduced beyond dependencies that **already exist in `pyproject.toml`**. The release fixes the incomplete `requirements.txt` so CI installs the same runtime libraries as production.

From the repo root on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm install --ignore-scripts --no-audit --no-fund
```

If you already have a healthy Python 3.12 virtual environment, do not recreate it; just rerun the `pip install -r requirements-dev.txt` command.

# Environment/configuration handoff

## No new environment-variable names are required

Verify these existing production variables before deployment:

- `APP_ENV=production`
- `APP_URL` points to the intended canonical Ask Crump host
- `COOKIE_SECURE=true`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `ANTHROPIC_API_KEY`
- `RESEND_API_KEY`
- `FROM_EMAIL` if overriding the default
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PROFESSIONAL_PRICE_ID`
- `STRIPE_ENTERPRISE_PRICE_ID`
- `CRON_SECRET`

## Vercel Cron — required manual external fix

The audit observed the hourly `/api/cron/check-ins` request returning 401. Before releasing:

1. Vercel → Ask Crump project → **Settings → Environment Variables**.
2. Confirm `CRON_SECRET` exists for **Production** and contains the intended secret.
3. Do not rotate it casually if other automation depends on it.
4. Redeploy after any env change.
5. Confirm the next scheduled `/api/cron/check-ins` invocation returns 200 rather than 401.

This handoff intentionally does not contain the secret value.

## Resend

No DNS/domain changes are included. The domain/key were healthy at the end of the audit. Confirm `RESEND_API_KEY` remains present in Vercel Production before the fresh-account smoke test.

# Local verification

Run from the CRUMP-AI repo root after applying the handoff.

## Python / backend

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\ruff.exe check app.py backend tests
.\.venv\Scripts\python.exe -m compileall -q app.py backend
.\.venv\Scripts\python.exe -m pytest -q
```

## JavaScript / frontend

```powershell
npm install --ignore-scripts --no-audit --no-fund
npm test
```

## Optional packaging/native confidence checks

```powershell
npm run build
npm run native:verify
```

Use the native verification step if you are preparing an App Store/Google Play build in the same release.

# CI verification

The existing GitHub Actions workflow should run automatically after your push to `main` or on a PR. Its effective commands should remain:

```bash
pip install -r requirements-dev.txt
ruff check app.py backend tests
python -m compileall -q app.py backend
pytest -q
npm install --ignore-scripts --no-audit --no-fund
npm test
```

`tests/test_dependency_parity.py` now makes CI fail if the production dependency declaration and requirements file drift apart again.

# Pre-deploy smoke tests

Before pushing/deploying:

- [ ] 8-character password is rejected with the correct 10-character message.
- [ ] 10+ character password with a letter and number is accepted by client validation.
- [ ] password confirmation mismatch still blocks submission.
- [ ] registration UI still opens/closes normally.
- [ ] login UI still opens normally.
- [ ] reset-password form enforces the same password rule.
- [ ] `pytest -q` passes.
- [ ] `npm test` passes.
- [ ] GitHub Desktop diff contains only expected hardening changes.

# Post-deploy smoke tests

## Fresh user / onboarding — launch blocker

Use a real email address that is not already an Ask Crump account.

1. Open Ask Crump in a private/incognito browser.
2. Create a new account with a valid 10+ character password containing a letter and number.
3. Confirm registration reports that verification mail was sent.
4. Confirm the verification email arrives.
5. Open the verification link.
6. Confirm the browser lands back on Ask Crump with verification success.
7. Sign in.
8. Complete Terms/onboarding if shown.
9. Send one normal AI message and receive a response.
10. Reload the page; confirm the session and conversation survive.
11. Close/reopen the browser/app; confirm persistent login works as intended.
12. Sign out.
13. Sign back in.
14. Run Forgot password.
15. Confirm reset email arrives, reset the password, and verify old sessions are revoked.

## Same-device session race

Open two tabs on the same browser installation, sign out, then submit successful login from both as close together as practical. Expected result: no 500/duplicate-key error. At most one of two concurrently-issued tokens may become the final valid token because the last atomic rotation wins; the database must retain one row for the installation.

## Stripe Enterprise cancellation — launch blocker for paid release

In Stripe **test mode**:

1. Complete an Enterprise test subscription through Ask Crump.
2. Verify Ask Crump reports Enterprise/active.
3. Deliver a `customer.subscription.deleted` test webhook for that subscription (or cancel it immediately in test mode so Stripe sends the event).
4. Confirm the webhook returns 2xx.
5. Query `/api/billing/status` as that user.
6. Expected: `tier = free` and terminal/canceled status; Enterprise daily allowance must no longer apply.
7. Also test a normal cancel-at-period-end path: while Stripe still reports `active`, access remains paid until the terminal deletion/expiration event.

## Cron

After verifying the Production `CRON_SECRET`, confirm Vercel runtime logs show the scheduled `/api/cron/check-ins` invocation returning 200. Check-ins can remain disabled for users; the scheduler itself must authenticate successfully.

# Supabase verification queries

After applying migrations to a **new/staging** environment, verify the intended trust boundary:

```sql
select grantee, table_name, privilege_type
from information_schema.role_table_grants
where table_schema = 'public'
  and grantee in ('anon', 'authenticated')
order by grantee, table_name, privilege_type;
```

Expected for Ask Crump application tables: no direct grants.

```sql
select indexname, indexdef
from pg_indexes
where schemaname = 'public'
  and indexname in (
    'credit_ledger_related_ledger_idx',
    'sessions_device_id_unique'
  );
```

Both indexes should be present.

# Release closeout checklist

## Import / code

- [ ] Handoff ZIP downloaded and extracted outside repo.
- [ ] `APPLY_HANDOFF.py` completed successfully.
- [ ] GitHub Desktop shows the expected file list only.
- [ ] Frontend password copy says 10+ characters + letter + number.

## Dependencies / tests

- [ ] Python 3.12 environment active.
- [ ] `pip install -r requirements-dev.txt` completed.
- [ ] `ruff check app.py backend tests` passes.
- [ ] `python -m compileall -q app.py backend` passes.
- [ ] `pytest -q` passes.
- [ ] `npm install --ignore-scripts --no-audit --no-fund` completed.
- [ ] `npm test` passes.
- [ ] `npm run build` passes if used by your release workflow.

## Database

- [ ] migrations 006–008 committed to repository.
- [ ] **Do not re-run 006/007 in production solely for source-control parity; they are already live.**
- [ ] staging/new environments apply 006 → 007 → 008 after 001–005.
- [ ] `sessions_device_id_unique` verified.
- [ ] direct `anon`/`authenticated` application-table grants remain closed.

## External configuration

- [ ] Vercel Production `RESEND_API_KEY` present.
- [ ] Stripe production/test env values match the environment being tested.
- [ ] Vercel Production `CRON_SECRET` present and intentional.
- [ ] no secret values committed to GitHub.

## Deployment

- [ ] commit created with reviewed diff.
- [ ] push to GitHub completed.
- [ ] GitHub CI green.
- [ ] Vercel production deployment READY.
- [ ] `/api/health` returns 200.
- [ ] no new production 5xx cluster appears after deployment.
- [ ] next scheduled cron invocation returns 200.

## End-to-end release gates

- [ ] fresh signup succeeds.
- [ ] verification email arrives and link works.
- [ ] login/session persistence works.
- [ ] first AI message works and persists.
- [ ] logout/login works.
- [ ] password reset works and revokes old sessions.
- [ ] same-device concurrent login produces no unique-constraint 500.
- [ ] Enterprise cancellation test drops entitlement to free.

## Final go / no-go

**GO** only when CI is green, fresh-user onboarding/password reset succeeds, cron returns 200, and Stripe Enterprise terminal cancellation removes paid entitlement.

**NO-GO** if any of those four gates fail. Do not add the next major feature until they are green.

# Verification performed while preparing this handoff

- Python syntax compilation of all replacement Python modules/tests/apply utility: **PASS**.
- Guarded frontend patch function verification: **PASS**.
- Isolated release-hardening regression suite: **8 passed**.
- End-to-end mock apply of the handoff script plus frontend/dependency tests: **3 passed**.
- Ruff was not installed in the handoff execution container, so the real repository's Ruff/complete pytest/npm suite must be run locally/CI using the commands above.

# Assumptions

1. Your local repository still contains the audited frontend fragments from main commit `f8e73eb22021fe2e24f8f9b948b1e4837de4db2c`. The apply script validates this instead of assuming it.
2. Supabase production still contains the two live migrations applied during the audit and the existing `sessions_device_id_unique` index.
3. Ask Crump continues to use the Python API/service-role database boundary rather than a browser Supabase client.
4. Stripe cancellation semantics remain: `active`/`trialing` are entitled; terminal states are not. RevenueCat `canceling`/`billing_issue` receive grace only through a future `subscription_current_period_end`.
5. The production Resend sending domain remains verified; no domain/DNS change is part of this package.
