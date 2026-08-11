# Ask Crump Production Hardening — Engineering Change Record
Date: 2026-08-11

## Live changes successfully applied

### Supabase migration: lock_public_data_api_to_service_role
Purpose: close unintended direct Data API access to application tables/RPCs and remove misleading unconditional RLS policies.

```sql
revoke all privileges on all tables in schema public from anon, authenticated;
revoke all privileges on all sequences in schema public from anon, authenticated;
revoke execute on all functions in schema public from anon, authenticated;

alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public revoke execute on functions from anon, authenticated;

drop policy if exists "Service role full access users" on public.users;
drop policy if exists "Service role full access settings" on public.user_settings;
```

Verified after migration:
- `anon` and `authenticated` have no application-table privileges.
- Only `service_role` retains application table/RPC access.
- Existing Ask Crump server traffic continued returning successful Supabase API responses.
- No user data was changed.

### Supabase migration: index_credit_ledger_related_ledger
Purpose: index the credit-ledger self-reference used by refund/reconciliation relationships.

```sql
create index if not exists credit_ledger_related_ledger_idx
on public.credit_ledger (related_ledger_id)
where related_ledger_id is not null;
```

## Code changes identified and ready to implement
These could not be committed because the GitHub integration returned HTTP 403 for both branch creation and file update operations.

### 1. Transactional email hardening
Files:
- `backend/email_service.py`
- `backend/routes/auth.py`
- tests for provider failure/retry behavior

Required behavior:
- Translate Resend/provider/network failures into a controlled application error instead of allowing `httpx.HTTPStatusError` to become an unhandled 500.
- Use Resend idempotency keys for verification/reset messages.
- Retry only transient network/429/5xx/concurrent-idempotency failures with bounded backoff.
- Do not log verification/reset tokens or provider response bodies containing sensitive details.
- Registration may leave a pending account when delivery is temporarily unavailable, but the API must return a clear retryable result and the resend-verification path must recover it.

### 2. Atomic installation-session rotation
File:
- `backend/auth_service.py`

Current defect:
- Login does SELECT-by-device-id followed by UPDATE or INSERT.
- Concurrent logins on the same installation can race and violate the unique `device_id` constraint.

Required behavior:
- For a stable `device_id`, use a single atomic upsert keyed on `device_id`.
- Continue issuing a fresh session token after each successful password login.
- Preserve existing max-active-session cleanup.

### 3. Password-policy UX parity
Files:
- `public/app.html`
- optionally client-side auth validation/tests

Current UI:
- “Minimum 8 characters.”

Server requirement:
- minimum 10 characters, at least one letter and at least one number.

Required UI:
- `minlength="10"`
- copy equivalent to “At least 10 characters with a letter and a number.”

### 4. Stripe subscription entitlement correction
Files:
- `backend/routes/billing.py`
- `backend/usage_service.py`
- targeted billing tests

Critical logic correction:
- A non-active/deleted Enterprise subscription must never retain `subscription_tier='enterprise'`.
- Compute active entitlement before price/tier mapping.
- Add defense-in-depth so explicitly inactive/canceled/expired/paused paid rows cannot receive paid usage limits.
- Preserve legitimate end-of-period access semantics for `canceling` subscriptions.

Also:
- bring subscription checkout/customer-portal stale-customer recovery up to the same standard already implemented in the credits flow.

### 5. Vercel Cron configuration
Files/config:
- Vercel production `CRON_SECRET`
- `backend/config.py`

Observed:
- `/api/cron/check-ins` returns 401 approximately hourly.
- Check-ins are currently disabled for all stored preferences, so there is no active end-user loss today.

Required:
- confirm/set matching Vercel production `CRON_SECRET`;
- after configuration is correct, make production startup validation require it when the cron route is deployed;
- verify at least one scheduled invocation returns 200.

### 6. CI / production dependency parity
Files:
- `requirements.txt` / `requirements-dev.txt` / `pyproject.toml`
- `.github/workflows/ci.yml`

Current drift:
- production `pyproject.toml` contains document/artifact libraries;
- CI installs the smaller `requirements.txt`;
- application startup imports those artifact libraries.

Required:
- choose one canonical dependency declaration or explicitly make CI install the production package definition;
- ensure CI imports the application, runs Ruff, compileall, pytest, and JavaScript validation against the same runtime dependency surface Vercel uses.

### 7. Regression coverage to add
Minimum targeted tests:
- Resend 401/429/5xx/network outage does not produce an uncontrolled signup failure.
- verification resend recovers a pending account.
- concurrent same-installation login resolves to one session row.
- canceled/deleted Enterprise Stripe subscription becomes non-entitled.
- active/trialing/canceling entitlement semantics remain intentional.
- frontend password copy/constraints match backend policy.
- production config rejects a missing cron secret once the live env is repaired.

## Release gate
Do not call the current build fully production-ready until:
1. the blocked code fixes above are committed;
2. CI passes with dependency parity;
3. a controlled fresh-user signup -> verification -> login test succeeds;
4. password reset succeeds end-to-end;
5. the hourly cron returns 200;
6. Stripe cancellation/expiration entitlement regression tests pass;
7. Vercel runtime errors remain clean after deployment.
