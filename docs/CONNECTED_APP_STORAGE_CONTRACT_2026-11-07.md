# Connected-app storage contract — local checkpoint (2026-11-07)

Status: **local only, uncommitted, unapplied, source lock false, not a release candidate**.

This checkpoint adds a proposed durable control plane for connected mail and
calendar adapters. It does not connect an account, store a credential, call a
provider, change production schema, or enable a route. The host has no
authenticated/version-preserving Supabase CLI path. A preserved local
PostgreSQL 17.11 runtime was used for a fresh first apply, exact and hostile
search-path reapply, nineteen drift-refusal/no-repair cases, and the disposable
owner-operator behavior gate in
`tests/postgres/test_connected_app_operator_control_plane.sql`, the atomic
action-preparation behavior gate, and the same-request two-connection race
gate; all passed.
This is local evidence only, not an application or release claim.

## Privacy and authority boundary

The private schema stores control metadata, hashes, UUID fences, timestamps,
and an opaque external credential-broker reference. It deliberately stores no
provider access or refresh token, authorization code, OAuth state value, PKCE
verifier, email address, mail subject/body/recipient, calendar event text,
prompt, or message content. `state_sha256` and the PKCE challenge are allowed;
the state value and verifier are not.

All thirteen relations have RLS enabled and forced, no policies, and no direct
privilege for any non-owner role. Public RPCs
are `SECURITY DEFINER`, have an empty `search_path`, are owned by `postgres`,
and are executable only by `service_role`. Seven private helpers are not
executable by any non-owner role. Hardening enumerates every database role to
neutralize inherited global/default grants, and postflight inspects raw ACL
grantees rather than a fixed role list. Postflight rejects manifest, owner, ACL, search-path,
RLS, hidden policy/trigger/rule, forbidden-column, and logical-publication
drift with SQLSTATE `55000`.

## Durable objects

- `action_authority`: database-owned exact allowlist mapping each implemented
  action to its resource, mutability, and approval class. Callers do not supply
  or downgrade these facts.
- `connections`: owner binding, provider/resource/account kind, immutable
  connection incarnation, database-allocated authorization revision, current
  OAuth-flow fence, exact granted-action set and canonical action-set hash,
  authorization snapshot, and opaque broker reference.
- `oauth_flows`: pending/consumed/exchanged/completed flow state with only
  digests, challenge, expiry, exact base-authority fences, and an immutable
  terminal completion ID/credential hash/revision snapshot. Exact completion
  replay does not depend on a later connection `current_flow_nonce`.
- `oauth_exchange_permits`: CSPRNG capability digest, one exchange attempt
  fence, and terminal receipt.
- `credential_cleanup_outbox`: unlinked opaque broker reference and hashes;
  it has no owner/user/connection/task/action key, survives owner cascade, and
  has bounded terminal retention plus bounded purge and explicit
  failed-permanent recovery RPCs. An expired eighth lease is atomically
  terminalized and exposed instead of overflowing the attempt counter. Exact
  retry of an expired lease reclaims that same row before any new scan, and a
  completed cleanup remains readable by the exact recovery request ID.
- `credential_ref_tombstones`: permanent content-free retirement hashes for
  broker credential references. Activation, cleanup recording, and cleanup
  claim share a credential-scoped advisory lock; a retired handle cannot be
  made live again, and a cleanup worker refuses to revoke a handle currently
  attached to live authority.
- `task_grants`: exact task/turn/connection authorization snapshot, allowed
  action set plus its canonical hash, task-state revision, revocation, and
  expiry. A sibling action with the same OAuth scopes is not substitutable.
- `approvals`: exact one-use effect approval, parameter/resource-version
  binding, class, and a maximum 15-minute lifetime.
- `approval_reviews`: pending/approved/denied operator review metadata with
  an opaque encrypted-payload UUID, exact authority/action bindings, and no
  plaintext preview, recipient, subject, event, or provider content.
- `action_preparations`: one owner/request-idempotent, content-free ordinary-
  language preparation. It binds a database-authored one-action grant, action
  identity, encrypted payload identity/reference binding, keyed parameter
  commitment, and either a ready read or an exact pending write review. It
  never creates or claims an action-ledger operation and retains no raw
  session ID or plaintext target digest.
- `action_ledger`: database fencing token, idempotency key, authority hashes,
  and the monotonic `claimed -> access_granted -> effect_possible -> terminal`
  state machine. READ, PREOBSERVE, EFFECT, and POSTOBSERVE have distinct nonce,
  exact expiry, and database-owned one-use consumption state. A child
  credential must be atomically consumed immediately before its provider phase
  and cannot be replayed after response loss. Expired access can be recovered
  only before an effect is possible; effects are never automatically retried.
  Calendar update/cancel settles only after POSTOBSERVE. Mail
  send/draft/reply and calendar create may settle from a typed provider receipt
  only because those adapters
  perform authoritative reconciliation before returning it; the original
  create request cannot identify the newly created provider object. Immediate
  ambiguous settlement remains separate.
- `schedules`: payload reference and hash only, task revision, bounded cadence,
  timezone/quiet window, durable `requires_approval_every_run`, claim lease,
  and completion readback fence. Every scheduled write requires that flag.
- `operator_commands`: content-free idempotency/readback records for exact
  disconnect, schedule-create, and schedule-transition commands.

Every `parameters_sha256` stored in approval/action/schedule state is
contractually a keyed payload-vault HMAC commitment, never the predictable
SHA-256 of plaintext request fields. `approval_reviews.preview_sha256` is
likewise a keyed preview commitment. The SQL treats these as opaque bindings;
the application/runtime contract must complete the corresponding HMAC-only
composition before release.

The explicit `public.users` `BEFORE DELETE` trigger copies only an opaque
broker reference, provider, and non-identity hashes into the cleanup outbox
before account-linked rows cascade away. At trigger entry it acquires the same
canonical owner advisory lock used by OAuth/revoke/action paths before reading
any connected-app row or enqueueing cleanup. It persists no customer identity
or content. The full account-deletion lock graph has not been behavior-tested
in this checkpoint.

## Atomic RPC surface

The migration defines 47 service-role-only RPCs covering:

- connection create/read/revoke;
- OAuth create/replay/consume, permit issue/consume, finalize replay, stale
  credential cleanup, cleanup claim/finish/failed-permanent recovery/purge;
- task-grant creation/revocation, exact approval creation/consumption;
- action claim, READ/PREOBSERVE access, pre-effect access recovery,
  approval-bound effect fence, phase-specific one-use credential consumption,
  POSTOBSERVE fence, terminal settlement, and response-loss readback; and
- schedule put, bounded `SKIP LOCKED` claim scanning with nonblocking owner
  advisory-lock acquisition, quiet-window advance,
  invalid-authority pause, and idempotent finish; and
- owner-operator list/get projections for connections, current authority,
  schedules, action history, and approvals; atomic disconnect, schedule
  create/transition, approval-review creation and exact approval decision;
  atomic action preparation plus owner/request response-loss readback; and
  response-loss readbacks for each operator mutation.

Authorization revisions and action fencing tokens are allocated in the
database. Callers cannot select the next authorization revision or fencing
token. Action mutability and approval class come from the private allowlist,
not request booleans. `begin_effect` re-reads the exact live grant, task-state
revision, action authority, connection, and consumed approval. Every mutating
path uses the owner-scoped transaction advisory lock and then exact row fences.
Read and pre-observation access issuance/recovery also recheck the connection's
authorization expiry. OAuth permit expiry stores its exact request fence so a
lost expired response is replay-readable. Fresh OAuth finalize detects an
already-active external identity before the partial unique index, durably
queues the provisional credential for cleanup, and returns a content-free
refusal instead of rolling back the cleanup record. Cleanup bindings are
separate canonical command hashes, not aliases of credential-reference hashes.
The cleanup and scheduler workers use bounded leases, and terminal/readback
bindings prevent a lost response from authorizing a second effect.

Atomic action preparation first acquires the canonical owner advisory lock,
then row-locks and revalidates the exact `public.sessions` authority
(`id`, owner, non-revoked, nonexpired) before connection state. The raw session
ID is an input-only lock key and is not persisted or returned. The same
transaction rechecks the ACTIVE current connection revision, authorization
snapshot, granted-action hash, granted-scope hash, exact action membership and
expiry; authors the one-action grant hash from the database allowlist; and
stores the durable preparation. Reads become `ready`. Writes atomically add a
pending review with a separate encrypted preview reference and keyed preview
commitment. Same-request replay is exact, drift and sibling UUID reuse fail
closed, and no provider execution occurs.

`backend/connected_app_supabase_control_plane.py` now implements the complete
application-facing connection/disconnect/schedule/action/approval RPC surface
with exact result shapes, bounded lists, no private-table REST fallback,
read-only transport retry only, non-retried writes, and authoritative durable
readback after ambiguous application calls. OAuth is deliberately delegated to
the typed `ConnectedAppOAuthControl` boundary because the real coordinator
must own secrets and provider exchange; a database adapter is not an OAuth
implementation.

Three application-composition blockers remain explicit:

1. The real OAuth coordinator must atomically consume state and the exchange
   permit, exchange the code, verify stable external identity and exact scopes,
   persist the refresh credential through the vault, finalize the connection,
   and queue provisional-credential cleanup on every lost/failed path. Provider
   denial/cancel needs its own state-bound, no-exchange durable terminal and
   response-loss readback; provider `error_description` is never persisted or
   trusted.
2. Scheduler finish currently lacks a separate completion ledger carrying the
   exact completion ID/outcome/operation/next-run/finished binding required by
   the worker's response-loss protocol. It must be added or the scheduler
   durable adapter must remain uncomposed.
3. Settled read actions have no encrypted result reference in the action
   ledger. A retry therefore cannot return the prior provider result and must
   fail `CONNECTED_READ_CONTENT_NOT_RETAINED`; a later settle/readback contract
   is required before chat retries can promise result durability without a
   second provider read.

The SQL makes no fixed-schema call to `pgcrypto.digest`. All broker-derived
credential, completion, binding, and authority digests cross this boundary as
exact lowercase prehashed inputs; the database stores the opaque broker UUID
reference and its supplied digest but never a provider bearer credential.
Every account-linked cascade foreign key has a supporting full index.

## Exact reapply hardening checkpoint

The base migration now computes the reviewed full-target catalog fingerprint
`3700cbb8e9d67dab331d090b26a70510` before any syntactically idempotent DDL can
run.  That manifest pins the private schema; tables, columns, types, defaults,
constraints, indexes and sequence parameters; public/private function
identities, bodies, configuration, owners and ACLs; comments; RLS; policies;
rules; the account-deletion trigger; default privileges; the database-owned
action allowlist; publication exposure; and effective API-role access.  An
exact target may take the no-op reapply path.  A partial, mixed, overloaded, or
drifted target fails SQLSTATE `55000` before mutation and is not repaired.

PostgreSQL 17.11 gates passed fresh first apply, normal and hostile-search-path
exact reapply, and nineteen planted drift cases: column default, constraint,
index definition, function body/configuration/overload, table and column ACL,
comment, trigger state, hidden rule, publication, sequence parameters, owner,
extra table/type, policy, RLS, and default ACL.  Each refusal preserved an
identical pre/post schema dump.  The existing operator behavior gate and the
23:00 -> 23:15 -> 23:30 successor-migration predecessor fingerprints also
passed.  This resolves the former exact-reapply blocker locally; it does not
apply the migration or satisfy the separate version-preserving production
path, provider, credential, or release gates.

## Mandatory gates before any PR or application

On a fresh, exact-current-main integration branch with a version-preserving,
scoped Supabase CLI/CI path:

1. Preserve the now-passing PostgreSQL 17 fresh first apply, catalog postflight,
   and operator behavior gate in required CI.
2. Preserve the now-passing exact-target no-op reapply and nineteen-case drift
   refusal/no-repair gate in required CI.
3. Prove hostile `search_path`, role inheritance/effective privileges,
   function overload, relation/type/sequence collision, column ACL, trigger,
   rule, policy, and publication refusal gates.
4. Run two-connection races in both winner orders for OAuth flow replacement,
   permit issue/consume/expiry, terminal finalize replay after a newer flow,
   revoke/finalize, account deletion/finalize, task grant
   revocation/action claim, concurrent same-request action preparation,
   session revocation/expiry versus preparation, approval consume/effect begin, action claim/access
   recovery/effect begin/settle, cleanup lease/eighth-crash/recovery/finish,
   credential cleanup/finalize in both winner orders, duplicate active
   identity cleanup, tombstoned credential-reference reuse refusal, and bounded
   multi-row schedule claim/owner-busy skip/quiet/invalid-authority/finish.
5. Prove transaction rollback and response-loss replay for every RPC, plus no
   orphan rows after revocation, deletion, expiry, and rollback.
6. Prove the deletion trigger enqueues each outstanding broker reference before
   cascade and does not retain owner identity/content; prove bounded purge only
   removes terminal cleanup rows after `delete_after`; prove failed-permanent
   cleanup is observable and recoverable before bounded retention expires.
7. Converge PostgREST schema cache and prove every RPC's exact argument/result
   contract from the application layer.
8. Reconcile remote migration history without rewriting it and run a dry run
   proving the exact versioned pending set. Do not use `apply_migration` or
   hand-edit migration history.

Until all of those gates pass, this file is a reviewed design candidate only;
it is not evidence of executable SQL behavior, production readiness, provider
access, autonomous email/calendar capability, or account-deletion safety.
