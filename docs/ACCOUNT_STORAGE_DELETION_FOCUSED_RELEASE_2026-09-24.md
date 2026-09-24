# Account Storage Deletion Focused Release — 2026-09-24

## Outcome

This isolated release closes the account-deletion privacy gap in which deleting
the database user cascaded away `user_files` metadata without removing the
underlying private Supabase Storage objects.

The new flow:

1. verifies the password and confirms required billing cancellation exactly as
   before;
2. atomically inserts a content-free Storage deletion obligation before the
   user row is deleted;
3. removes account access, synchronized records, and sessions in the same
   database transaction;
4. returns HTTP `202` with `deletionStatus: scheduled` and clears the local
   session;
5. gives the existing minute cron first opportunity to claim one deletion job;
6. recursively deletes only the canonical `<account UUID>/` prefix through
   the Supabase Storage API in batches of at most 1,000;
7. performs an immediate sweep, retains the durable job for a sweep at least
   27 hours later, and deletes the job only after two empty observations at
   least five minutes apart.

The queue intentionally has no foreign key to `users`; the cleanup obligation
must survive the account cascade.

## Safety properties

- Storage objects are removed through the Storage API. No migration deletes
  rows from `storage.objects`.
- Owner identifiers must parse as canonical UUIDs.
- The stored prefix must equal `user_id::text || '/'`; partial-prefix and
  cross-bucket cleanup is rejected.
- Every path returned by Storage is checked against the exact owner boundary
  before deletion.
- Directory listings always restart at offset zero after mutation, preventing
  pagination skips as objects shift.
- Claims use `FOR UPDATE SKIP LOCKED`, expiring leases, and a UUID token.
- Release and completion are fenced by both job ID and lease token.
- The queue table has RLS enabled, no user policies, explicit public/anon/
  authenticated revokes, and only service-role grants.
- Provider errors stored on the job are categorical codes, never URLs, object
  paths, or customer content.

## Files

- `migrations/20260924210000_durable_account_storage_deletion.sql`
- `backend/account_deletion_service.py`
- `backend/file_service.py`
- `backend/routes/account.py`
- `backend/routes/manuscripts.py`
- account-deletion product and privacy copy under `public/`
- `tests/test_account_storage_deletion.py`

## Deployment order

This is a migration-first release:

1. revalidate the remote migration ledger immediately before action time;
2. apply `20260924210000_durable_account_storage_deletion.sql`;
3. verify the table, indexes, RLS, grants, and five function signatures;
4. deploy the matching application commit;
5. run the staging acceptance below;
6. only then promote and validate production.

Do not deploy the application before the migration: the minute cron calls the
new claim RPC. No remote database or deployment action was performed while
preparing this candidate.

This patch must land before the pending document-delivery release. Because that
release currently carries an earlier, not-yet-applied `20260924` migration
timestamp, its branch must be rebased and its pending migration order
reconciled before the next remote migration action. Do not apply an older
timestamp behind this migration without an explicit ledger plan.

## Staging acceptance gates

Use a disposable staging account and private bucket objects only.

1. Seed a direct object, a nested object, a retired version, and an object with
   no `user_files` row under the test account UUID.
2. Seed a second account whose UUID is similar and confirm its objects remain.
3. Delete the test account and verify:
   - HTTP `202`;
   - `deletionStatus = scheduled`;
   - the session cookie is cleared;
   - sign-in/session reuse fails;
   - exactly one queue row exists with the canonical trailing-slash prefix;
   - the user row and synchronized records are gone.
4. Invoke the existing manuscript cron with its normal authorization and
   confirm the account-storage worker runs before code/manuscript work.
5. Confirm every target object is absent through the Storage API, the neighbor
   account is intact, and the queue row remains scheduled for the delayed
   sweep.
6. In disposable staging only, advance `final_sweep_after`, add one late
   object, and confirm the next pass removes it and restarts the five-minute
   verification window.
7. Advance the verification window, run one more empty pass, and confirm the
   queue row is deleted.
8. Force one Storage API failure and one expired lease; confirm retry/backoff,
   takeover with a new token, and rejection of a stale release/completion
   token.
9. Inspect logs to confirm they contain only categorical status/error codes and
   no object paths, signed URLs, prompts, filenames, or customer content.

## Local evidence

- Focused account/storage and route suite: 29 passed.
- Expanded backend/runtime/static regression suite: 69 passed.
- Full repository pytest suite: 1,164 passed.
- JavaScript integration contract: 54 files validated.
- Store packet self-test: 21/21 passed.
- PostgreSQL parser: 23 migration statements parsed.
- Ruff focused check and `git diff --check`: passed.

The staging gates above remain mandatory because local tests do not exercise a
real Supabase Storage service or concurrent PostgreSQL workers.
