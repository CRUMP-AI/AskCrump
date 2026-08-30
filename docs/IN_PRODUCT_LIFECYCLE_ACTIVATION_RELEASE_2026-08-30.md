# In-product lifecycle activation release

Date: 2026-08-30

## Outcome

Ask Crump now offers restrained, contextual guidance that helps eligible users reach a first useful response, keep continuing work in a Project, create an editable artifact, or share the public workspace after a proven useful outcome.

The system is in-product only. It does not send lifecycle email or create a second push/check-in scheduler. Existing optional check-ins remain a separate user-controlled system.

This release verifies deterministic delivery, privacy boundaries, and measurement readiness. It does not claim improved activation, retention, referrals, or revenue before legitimate users produce those outcomes.

## Decision and frequency contract

The authenticated server selects from five fixed message families:

- `starter-assist`;
- `first-value-assist`;
- `continuity-assist`;
- `artifact-assist`; and
- `referral-ask`.

Eligibility uses only allowlisted account and milestone facts. The client cannot select a message key, invent copy, or override the server decision. Unknown intent values are discarded.

Every message family has an account-stable 20% holdout, a separate kill switch, stale-state revalidation before display, and family-specific cooldowns. The global cap is one shown prompt per page session and two shown prompts in any seven-day window. Page-session identifiers are one-way hashed with the authenticated session before storage.

## Product behavior

All text is static reviewed copy. Guidance appears as a nonblocking inline region, does not steal focus, honors reduced-motion preferences, and is withheld during typing, generation, upload, recovery, authentication, billing, or modal work. Choosing an action opens the existing Projects or Create destination. The referral action shares only the public Ask Crump link and never includes the conversation or files.

Successful referral delivery records the existing allowlisted `ResponseShared` milestone with the accepted `response-share:` key. Cancelled or failed sharing records no success.

## Privacy and security boundary

Migration `20260830175952_in_product_lifecycle_activation.sql` adds three content-free tables and four service-role-only functions. Stored fields are limited to fixed message keys, fixed intent/surface/platform labels, prompt/holdout cohort, action/suppression category, timestamps, UUIDs, and a one-way session hash.

No prompt, response, Project name or ID, conversation ID, filename, file ID, email, URL, rendered copy, arbitrary metadata, or notification body is stored.

Production verification proved:

- all three tables have row-level security enabled;
- table and routine privileges are limited to `postgres` and `service_role`;
- all five controls are enabled with the required 20% holdout;
- nonexistent users and decisions fail closed without creating rows; and
- the initial production state and event tables contain zero rows.

The Supabase security advisor reports only the expected informational notice that the intentionally service-role-only RLS tables have no client policies. The performance advisor reports only expected unused-index notices before lifecycle traffic exists.

## Aggregate evidence

`product_weekly_lifecycle_export` returns content-free weekly cohort and suppression rows grouped by message key, fixed intent, prompt/holdout cohort, and fixed suppression category. It excludes deleted and internal accounts and enforces the server-derived environment boundary. It exposes explicit eligible, shown, acted, target-completed-within-24-hours, D7-eligible, D7-returned, dismissed, and suppression counts without returning an account identifier.

## Verification

- Full Python suite: 607 passed.
- Focused lifecycle suite: 9 passed.
- JavaScript integration contract: 47 files validated.
- Python lint: passed.
- Production preflight: passed.
- Native web bundle: passed.
- Git whitespace integrity: passed.
- Applied Supabase migration: `20260830175952 in_product_lifecycle_activation`.

## Safe rollback

Disable delivery without deleting evidence:

```sql
update public.lifecycle_prompt_controls
set enabled = false, updated_at = now();
```

The client treats an unavailable decision service as no prompt, so disabling the controls or rolling back the app does not block normal Ask Crump work.

## Remaining evidence gate

Observe legitimate eligible users across prompt and holdout cohorts before making an activation or retention claim. Keep lifecycle email off. Do not add email eligibility from Terms acceptance, and do not publish or send lifecycle messages outside the app without a separate consent, suppression, and authorization release.
