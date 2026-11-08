# Connected OAuth runtime-authority and restart contract

Status: local-only engineering checkpoint. Source and release locks remain
false. Nothing in this slice is committed, pushed, applied to a hosted
database, connected to provider credentials, or enabled for provider traffic.

## Closed authority mismatch

`20261108050000_connected_oauth_runtime_authority.sql` keeps the OAuth
completion replay identity and the runtime authorization identity separate.
The flow continues to store its exact `completion_binding_sha256` for replay,
while the connection and completed flow separately store the exact
`ConnectedAuthorizationSnapshot.snapshot_sha256`. The exact authorization
`issued_at` is also stored on both rows. A credential-vault create must bind to
the authorization snapshot hash; the unrelated completion replay hash is
refused.

The service-role-only `connected_app_get_binding_v2` projection exposes the
nonsecret fields needed to reconstruct a `ConnectedAuthorizationSnapshot`
after process restart: owner, connection, provider, resource, account kind,
revision, state, issue/expiry instants, exact action set and action hash, scope
hash, account hash, and opaque credential-reference hash. Application code
deterministically rebuilds the exact delegated scopes from provider, actions,
and account kind, then independently verifies the action hash, scope hash,
credential-reference hash, and reconstructed snapshot hash. Any mismatch fails
closed.

The issued-at compatibility constraint deliberately permits an active snapshot
to become revoked while retaining its historical issue instant. The existing
revocation RPC therefore continues to work and durably queues credential
cleanup instead of failing a new-column check constraint.

## Concrete repositories and secret custody

`backend/connected_app_oauth_supabase.py` supplies concrete
`OAuthFlowRepository` and `OAuthCompletionRepository` implementations over the
reviewed service-role RPC boundary. It also composes the existing
`SupabaseOAuthSecretStore`, so denial, expiry, abort, and stale-flow cleanup use
the existing encrypted state/PKCE/provisional-credential custody rather than a
new plaintext or in-memory path.

The short-lived exchange-permit capability is envelope-encrypted before it is
persisted in a new private, forced-RLS table. Ordinary roles, including
`service_role`, have no direct table access. Only exact-shape `SECURITY DEFINER`
RPCs can write, live-revalidate, read, or consume it. A valid restart can
recover the capability using the configured key ring. A stale, revoked,
replaced, expired, or consumed permit returns no capability, and its encrypted
custody is erased. The first exact dispatch-fence winner alone receives
`claimed=true`; an exact replay receives a content-free terminal readback and
cannot redispatch.

Completion response-loss recovery reads the exact replay binding. Inactive
completion outcomes use the existing durable cleanup outbox, and cleanup
readback is exact and content-free. Returned completion rows are independently
checked against the requested consumption, exchange, incarnation, account,
credential, action, scope, issue/expiry, snapshot, and replay bindings.

## Schema attestation and validation

The migration accepts only dependency-scoped predecessor fingerprint
`b370daab7379a1e09a620719948d6699` or exact target fingerprint
`cfd262b61a4f8c408b74b2ca18d97d8d`. Its target fingerprint covers the new
columns, table and constraints, all nine v2 function definitions, function
owners/ACLs/comments, the disabled v1 entry-point ACLs, relation
owner/ACL/RLS/comment, policies, non-internal triggers, rules, and logical
publication exposure. Partial, mixed, or drifted targets refuse with SQLSTATE
`55000`; the migration does not repair unexpected state.

Fresh PostgreSQL 17.11 ordered application passed on the exact full predecessor
stack through `20261108043000_connected_dispatch_execution_outbox.sql`. Exact reapply,
hostile `search_path`/quoted-identifier reapply, behavior/rollback, revocation
compatibility, encrypted permit restart recovery, one-winner replay refusal,
completion/authorization separation, credential-vault activation, and restart
snapshot reconstruction passed. Predecessor function-config drift refused with
SQLSTATE `55000`, left zero target objects, and remained drifted. Target
function-config drift likewise refused with SQLSTATE `55000` and remained
drifted after rollback, proving no hidden repair.
The owned adapter/storage/core suite passed 147 tests, and seven related
durable-OAuth tests passed. One upstream static contract was concurrently being
updated by its owner for idempotent migration syntax, so the final combined
collection remains an integration rerun for the root lane. Ruff and
`py_compile` passed.

## Remaining release blockers

This slice does not close provider-side cleanup when account deletion wins
after a provider grant exists but before provisional encrypted custody is
durably committed. Database cascades remove local rows, but they cannot revoke
an external provider grant whose handle was never durably captured. That case
still needs a successor provider-reconciliation design and tests.

External KMS/KEK lifecycle, production composition, continuously invoked
cleanup/reconciliation workers, provider contract proof, bounded authenticated
provider preview smoke, version-preserving schema application, converged
PostgREST cache, and a deliberate release decision also remain mandatory. No
provider call, callback route, connected-account action, scheduled action, or
public capability may be enabled from this checkpoint.
