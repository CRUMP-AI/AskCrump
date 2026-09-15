# AI report queue production-readiness verification

Date: 2026-09-15

## Outcome

Ask Crump's in-app **Report** control has a verified production moderation destination. The
production `public.ai_content_reports` table exists, row-level security is enabled, browser-facing
roles cannot read or write it, and the backend service role retains the required moderation access.
The matching public API route remains authentication-gated.

This closes the stale readiness question about whether migration
`migrations/014_ai_content_reports.sql` still needed to be applied. It does not claim that a signed
mobile build has completed a legitimate report submission or a failed-network retry.

## Production evidence

A read-only schema and privilege inspection on 2026-09-15 verified:

- the moderation table exists;
- row-level security is enabled;
- `anon` has neither `SELECT` nor `INSERT`;
- `authenticated` has neither `SELECT` nor `INSERT`;
- `service_role` has the required table CRUD privileges;
- no permissive table policy exists; and
- the queue contained zero total and zero open reports at inspection time.

A credential-free POST to `https://www.askcrump.com/api/safety/reports` returned HTTP 401. No row
was inserted. This proves the public route rejects an unauthenticated caller without manufacturing a
safety report or exposing customer content.

The Supabase security advisor reported only the expected informational no-policy notice for this
deny-by-default service table. The performance advisor reported its per-user index as unused, which
is consistent with an empty queue and is not evidence that the release index should be removed.

## Preserved boundary

No customer account, conversation, response, report, moderation status, credential, policy, grant,
database row, store record, purchase, upload, or submission was created or changed. The first
legitimate signed-device report, failed-network recovery, moderator review, and final console
declaration remain part of the owner-controlled store test plan.
