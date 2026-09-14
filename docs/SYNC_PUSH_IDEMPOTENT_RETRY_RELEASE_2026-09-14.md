# Sync push idempotent retry release — 2026-09-14

## Decision

Ask Crump now retries only the two cross-device sync writes whose replay safety is
authoritatively proven:

- `apply_chat_sync`, an atomic compare-and-apply RPC keyed by the owning user and
  conversation; and
- the `user_settings` upsert, keyed by the owning user and replayed with the same
  already-normalized payload.

All other database writes remain single-attempt unless their caller separately proves
idempotency and explicitly opts in.

## Production evidence that triggered the change

The production reliability window contained recurring upstream database HTTP 504s:

- scheduled check-in reads exhausted their bounded retry path at 13:00 and 15:00 UTC on
  2026-09-13;
- a scheduled manuscript read exhausted the same path at 08:00 UTC; and
- one `/api/sync/push` returned HTTP 503 at 00:05 UTC on 2026-09-14 because its database
  write received HTTP 504 and was still classified as non-retryable.

The browser's durable user-scoped queue protected the sync payload: the immediately
preceding push returned 200, the failed batch stayed queued, and another push returned
200 eight seconds later. That proved recovery, but it also showed an avoidable interval
where cross-device work remained unsynchronized. The repeated 504 pattern across reads
and the sync write met the operating backlog's evidence gate for revisiting the
one-attempt policy.

Supabase's current performance advisor reported informational unused-index findings only;
it did not identify a missing-index or query-performance warning that would justify a
schema mutation. This release therefore improves transient transport recovery without
changing tables, functions, indexes, or data.

## Safety boundary

The general database transport still defaults every POST, PATCH, and DELETE to one
attempt. A caller must pass `retry_transient=True` explicitly. The sync service does so
only after normalizing the payload and only for the two operations above.

If the first database attempt committed but its response was lost, `apply_chat_sync`
returns an already-applied revision as ignored on replay instead of duplicating a
conversation. The settings upsert receives the identical user key, values, and timestamp
on every server-side attempt. The browser clears its durable queue only after the whole
push returns success, preserving the existing partial-batch recovery contract.

No account, conversation, setting, Project, file, payment, provider, credential, or
customer-content record was read or changed while validating this release. Production
logs were reviewed only as route/status/error aggregates, and the growth refresh used
content-free service-role functions.

## Verification

- focused sync, database-transport, and recovery checks: 32 passed;
- complete Python product suite: 1,055 passed;
- JavaScript validation: 54 files passed;
- complete real-browser control matrix: 47/47 passed, including the exact failed-push
  queue preservation and identical replay fixture;
- Ruff and diff-integrity checks: passed.

Production acceptance requires the exact commit to deploy successfully, both GitHub CI
tracks to pass, the health route and canonical app to return HTTP 200, and the initial
release window to contain no new sync-push error cluster.
