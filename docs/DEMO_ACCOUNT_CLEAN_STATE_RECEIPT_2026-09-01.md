# Demo-account clean-state receipt — 2026-09-01

## Outcome

Ask Crump now has a fail-closed, repeatable way to prove that its fixed internal recording
account is safe to use for authentic product captures. The operator tool verifies the generic
profile, default workspace settings, and the absence of user-owned rows across every current
product category before it calls the account recording-ready.

This release hardens the workflow; it does **not** claim that the live demo account has already
been reset. No backend service credential was configured in the development workspace, so no
remote inspection, replacement, or customer-data operation was attempted.

## Changes

- Commit `de96b14` adds exact profile/default-settings verification to the fixed
  `demo@askcrump.com` identity.
- A versioned `ask-crump-demo-clean-state/v1` JSON receipt can be created after a read-only
  inspection or replacement, but only when the account passes every recording-readiness guard.
- Receipts contain only the fixed identity, timestamp, internal/preview exclusion flags, clean
  category names, and an aggregate removed-file count. They never contain an account ID,
  password, prompt, response, filename, billing identifier, or customer content.
- Receipt destinations are checked before remote work, existing evidence is never overwritten,
  and a missing destination folder fails before account mutation.
- A migration-parity test discovers every current table whose `user_id` cascades from
  `public.users` and requires it to appear in the clean-state inspection contract, except the
  separately verified default `user_settings` row.
- Replacement still requires a backend-only Supabase secret/service-role credential, the exact
  typed acknowledgement, and a twice-entered hidden password. Private Storage objects are still
  deleted through the file service before the service-role-only account deletion function runs.

## Verification

- `12/12` focused demo-account workflow tests passed.
- All `732` Python tests passed.
- All `47` JavaScript validation files passed.
- Python compilation and the production build preflight passed.
- Diff integrity passed.
- Supabase's current reference confirms that admin user deletion requires a service-role key;
  its Storage guidance retains explicit delete authorization. The implementation keeps those
  privileges exclusively in the local operator workflow.

## Boundaries and next evidence

- No website/PWA/native runtime changed, so no Vercel deployment is required for this commit.
- No customer, founder, or demo account was read or changed.
- No product event, activation, retention, payer, revenue, refund, credit, or generation record
  was created.
- No campaign was published and no paid spend was authorized.
- The marketing demo-account blocker remains open until an authorized operator supplies backend
  credentials locally, performs the guarded reset immediately before capture, preserves the
  content-free receipt, and records only rights-cleared fictional material.

