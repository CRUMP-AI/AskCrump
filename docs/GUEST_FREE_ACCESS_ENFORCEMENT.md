# Guest and Free access enforcement

## Product rule

- A signed-out visitor may start a real guest session and use standard text chat.
- Guest and registered Free accounts share **five text messages per rolling 24 hours**.
- Guest sends are also bounded to **25 messages per observed network per
  rolling 24 hours**. Registered Free accounts do not use the network budget.
- Registering upgrades the same user row. It preserves the conversation and the
  existing allowance; it does not grant another five messages.
- More messages and advanced tools require a currently verified paid entitlement.
- Professional, Enterprise, and internal accounts retain their separately
  verified entitlements.

## Server authority

`public.usage_events` remains the single message ledger. The additive,
service-role-only `reserve_free_message_v2` function preserves the v1 account
rule and atomically attaches a guest-only network receipt. V1 remains installed
for rollback compatibility, but the guest-aware application calls v2. The
function owns both hard-coded limits, rolling windows, deterministic account-
then-network locks, and retry identity. It stores a message UUID and a one-way
content fingerprint, not message text, filenames, referrer URLs, or response
content.

`public.guest_network_message_events` contains only an independent opaque
receipt UUID, an optional refundable usage-event link, a 64-character keyed
digest, and its timestamp. Account deletion removes the identifiable usage
event and sets that optional link to null; it deliberately retains only the
de-identified receipt UUID, keyed digest, and timestamp until the 25-hour purge,
so delete-and-recreate cannot replenish a shared network bucket. The backend canonicalizes IPv4
as `/32` and IPv6 as `/64`, then applies HMAC-SHA256 with the dedicated
`GUEST_NETWORK_HASH_KEY`. The network receipt itself and its logs never contain
the raw address or subnet, and the older unkeyed rate-limit digest is never
reused. Preview and production point at the same Supabase project and therefore
must use the same stable key; a per-deployment or per-environment key would
split one real network into multiple quota buckets. Existing session-security
metadata is unchanged and may still contain
the canonical client address; this control does not claim anonymity from a
privileged database operator. A database-native named pg_cron job runs every 15
minutes and drains unlocked keyed receipts older than 25 hours. The hourly
application check-in invokes the same private purge RPC as defense in depth.
This leaves substantial alert/recovery margin before the 48-hour live-table
privacy SLO, and an application rollback retains the database scheduler.
Database downtime can delay logical deletion, so operations must monitor the
exact job and page before the SLO is breached. PostgreSQL WAL and backup
retention remain separate platform policies.

The backend derives effective tier from server-managed subscription lifecycle or
internal entitlement fields. Client-provided tier labels never authorize paid
tools. Advanced operations are rejected before provider work or allowance
consumption.

## Anonymous enforcement boundary

Guest enforcement is account/session based, guest creation is additionally
bounded by the existing privacy-respecting admission rate limit, and message
sends have the keyed network ceiling above. This is not person-level identity.
Shared networks can legitimately reach the ceiling, while changing networks
can move a guest to another bucket. Ask Crump must not claim it identified an
individual or that either limit is impossible to evade.

The implementation deliberately does not add invasive browser fingerprinting.
If abuse becomes material, use aggregate abuse evidence and proportionate
controls such as verified-account requirements or conservative network-level
mint limits; do not collect customer content for quota enforcement.

## Failure and retry rules

- Chat-job cache/reconciliation runs before message reservation.
- An exact retry reuses its receipt and has no refundable event ID.
- Exact replay is resolved before either account or network quota denial.
- A network denial creates neither receipt, releases the owned chat claim, and
  returns HTTP 429 plus a five-minute-rounded, upward-only `Retry-After` and
  `GUEST_NETWORK_LIMIT_REACHED`. It does not expose the shared bucket's exact
  next-available timestamp. Recovery copy neutrally offers sign-in or
  verified-account creation.
- A newly owned reservation may be refunded only after a confirmed
  pre-persistence failure. The service-only refund RPC row-locks and verifies
  the exact owned usage event and optional child, deletes the parent first so
  its FK action de-identifies the child, then deletes that exact captured child
  in the same transaction. It deliberately does not join quota advisory locks:
  a concurrent removal can only conservatively underfill or false-deny, while
  avoiding a cycle with the established account-deletion path. Only that path restores one
  network slot; ordinary account deletion merely severs the nullable link and
  preserves the de-identified receipt until retention purge.
- Once a reply is durably stored, or persistence is ambiguous, the reservation
  remains so a retry cannot produce duplicate provider work.
- The UI may display the server-provided next-available timestamp for a user's
  own five-message allowance. A rolling window releases messages individually,
  so it must not promise a single daily reset.

## Guest synchronization acknowledgement contract

A guest sync request may contain at most 20 conversations and 20 conversation
tombstones. The backend validates both counts before any conversation RPC or
settings write. It must never truncate an oversized array and then return
success. An oversized direct or outdated-client request fails closed with HTTP
413 and the stable code `GUEST_SYNC_BATCH_TOO_LARGE`; its envelope states that
the work remains queued and reports both the allowed and received counts.

The browser compacts pending state, divides it into FIFO batches within those
server-owned bounds, and submits one batch at a time. A successful response
acknowledges only that queue entry; later entries and entries added while the
request was in flight remain queued. A failed response removes nothing. The
browser also removes only the exact tombstone snapshot covered by a completed
drain, preserving any deletion recorded concurrently. Local queue-storage
failure is explicit (`SYNC_QUEUE_STORAGE_FAILED`) rather than silently dropping
the oldest changes. Replaying an uncertain batch remains safe through the
database compare-and-apply contract.

## Release boundary

Guest database objects remain inert until the matching application build is
released. `guest_mode_control` is created disabled, and only its service-role
RPC may read or change it. The database rejects creation or reactivation of a
guest session while disabled; disabling also revokes every active guest session
in the same transaction. Guest authentication also re-reads the control, so an
already-issued guest token fails closed if the singleton is missing, malformed,
disabled, or temporarily unreadable. Registered sessions do not depend on that
guest-only read. Disable-and-drain marks the exact database-owned revocation
timestamp on each session it closes. Registration alone may use an unexpired
active guest token or that exact marked token to upgrade the same user row;
logout and other revocations remain final. This narrow conversion path never
re-enables guest features and never resets the shared usage ledger.

Email verification is transition-gated for both ordinary and converted guest
accounts. Only the request that changes `is_verified` from false to true may
mint and set the verification session. Ordinary accounts use a conditional
update constrained by user ID, token hash, unexpired token, and
`is_verified = false`; a racing loser re-reads the row. Guest conversion uses
the locked database RPC. For 15 minutes the retained hash permits an accurate
`verification=already_verified` redirect, but a replay never creates, rotates,
or sets a session—even when the browser already carries another account's
cookie. Installation IDs, IP addresses, and user-agent strings are metadata,
not authentication factors.

The singleton's shared transaction lock is also the first lock taken by guest
message reservation, browser sync, and reply persistence. Disable takes the
exclusive side before draining sessions. A write already holding the shared
lock finishes before disable can commit; a write that starts after disable
commits sees the disabled state and persists nothing. Registered-session
updates resolve the account type before touching this guest-only lock, so an
operator-held or damaged guest control cannot interrupt signed-in accounts.

`user_settings` has the same fail-closed write boundary. Its database trigger
locks the owning user row for the transaction, returns registered accounts
before touching guest control, and takes the shared guest-mode lock for guest
inserts and updates. A missing or disabled control rejects the settings write
with `GX003`. Guest `/sync/push` settings no longer use a generic table upsert:
they call the service-role-only `apply_guest_user_settings_v1` RPC, which takes
the shared control lock before the owner lock and keeps both through the
upsert. A settings request admitted as guest therefore either commits before
verification or, after waiting for verification, observes `not_guest` and
persists nothing. The reverse ordering makes verification wait until the guest
write commits. Disable uses the exclusive side of the same control lock, so it
also serializes without leaving a post-disable settings write. Ordinary
registered settings continue through the existing direct upsert. The trigger
and RPC grant browser roles no new table or function capability. A stale
settings-only request returns `GUEST_SETTINGS_AUTHORITY_CHANGED`; an all-stale
mixed batch returns `GUEST_SYNC_AUTHORITY_CHANGED`. Both remain queued and are
marked retryable after sign-in finishes rather than being mislabeled as a
storage-limit rejection.

The current wait-for dependencies cannot cycle under these lock modes:

- Guest settings RPC: shared control, shared owner, then the settings row.
- Guest verification: exclusive owner, then session rows; it never requests
  the control lock.
- Disable-and-drain: exclusive control, then session rows; it never locks an
  owner row.
- A generic settings update already owns its settings row before the trigger
  takes a shared owner lock and, only for a guest, a shared control lock.
  Application guest writes no longer enter through that generic path; inside
  the RPC, the control and owner locks are already held and the trigger's
  acquisitions are re-entrant. Concurrent RPC and trigger locks are mutually
  compatible, so a generic writer can release the settings row before the RPC
  proceeds. Registered direct upserts return from the trigger before requesting
  control. A legacy direct guest write can wait behind disablement, and
  verification can wait behind that writer, but disablement has no owner or
  settings-row dependency, so that wait chain terminates rather than cycling.

## Production migration runner contract

For this release, the approved production runner is Supabase
`apply_migration`, backed by the Management API
`POST /v1/projects/{ref}/database/migrations`. Do not substitute the SQL editor
or `execute_sql`: those paths do not provide the same automatic migration-history
record. Supabase documents that this endpoint creates the migration entry and
rolls back the schema changes if the migration fails. Supabase also documents
that its runner owns the transaction wrapper and that an embedded `BEGIN` or
`COMMIT` can cause partial schema state without a matching history entry:

- https://supabase.com/docs/guides/integrations/supabase-for-platforms#make-database-changes
- https://supabase.com/kb/troubleshooting/partial-migrations-and-schema-inconsistencies-from-embedded-transactions

Apply each reviewed file as one `apply_migration` call, in the order below,
using the filename suffix as the snake-case migration name. Before each call,
record the exact file SHA-256 and re-read the remote ledger. After each call,
re-read `supabase_migrations.schema_migrations` and verify the expected catalog,
function signatures, ACLs, and fail-closed state before continuing. The MCP
runner assigns the remote version at action time, so the release evidence must
bind that remote version and name to the reviewed local file hash. An uncertain
tool outcome must be reconciled against the ledger and catalog before any retry.

The repository's PostgreSQL workflow independently executes every migration
with `ON_ERROR_STOP` and applies each migration file under one transaction. A
static contract also rejects top-level transaction-control commands while
allowing PL/pgSQL function bodies. This protects the transaction-wrapper
assumption but does not authorize or perform a production migration.

For the already-live guest service, the network-budget release order is
mandatory:

1. Preflight the live prerequisite schema, v1 function, migration ledger, and
   absence of v2/table name collisions without mutating customer data. Also
   verify pg_cron is installed and active and that the exact retention job name
   is absent or already matches this migration.
2. Apply only the reviewed additive migration. Verify the exact
   reservation/refund/purge signatures, owner, ACLs, indexes, one exact active
   15-minute retention job, account-deletion invariance, retention contract,
   and unchanged v1 behavior. Existing application
   instances continue to use v1.
3. Provision the same stable dedicated server-only HMAC key in both preview and
   production—never a generated-per-deployment value—then require an exact-head
   green preview before the application release.
4. Deploy the matching application and monitor content-free denial, retention,
   and runtime-failure telemetry. Do not create synthetic production guests or
   provider work solely to exercise the limit.

An application rollback retains the additive table, functions, and database
retention job and restores the prior v1 behavior, reopening this preventive
loophole without deleting data. Guest-mode disable-and-drain remains the
stronger emergency control only for a verified reservation, privacy, or
authentication failure; it is not a routine prerequisite for this additive
release.

Emergency rollback is disable-and-drain first: call
`set_guest_mode_enabled_v1(false)`, verify the returned disabled state and zero
active guest sessions, and only then promote a pre-guest application build. A
captured guest token must fail while a registered token still works. Raw
`ad49403a` is never a one-click rollback target after guest mode has been
enabled because it does not understand `users.is_guest`.

Rollback preserves the additive schema and all users, conversations, receipts,
and usage history. It does not drop `is_guest`, delete guest rows, resurrect
revoked sessions, or restore retired browser-accessible RPC permissions. If the
disable-and-drain pre-step cannot be guaranteed, operations must use a prepared
compatibility build that retains guest-aware authentication enforcement.
