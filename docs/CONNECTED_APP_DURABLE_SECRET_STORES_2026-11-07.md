# Connected-app durable encrypted-store contract

Status: local-only engineering checkpoint. Source and release locks remain false.
This is not applied, deployed, connected to a KMS, or authorized for provider
traffic.

The forward migration pins predecessor source SHA256
`E7CA1FB4AD5CD5BE19109CEAE76A1B19535BD3B05D2D7750E49BE8B86EE48678`
and dependency-scoped catalog fingerprint
`8052016e79f8049ccdab9785409c7820`. Missing, drifted, partial-target, and
already-target states refuse with SQLSTATE `55000`; the migration does not
repair an unexpected catalog.

## Stored data boundary

`20261107230000_connected_app_secret_payload_stores.sql` creates six private,
forced-RLS relations. Direct table authority is revoked from every non-owner
role. The only Data API surface is eleven exact-shape `SECURITY DEFINER` RPCs with
an empty `search_path`, granted only to `service_role`.

The payload and credential envelope tables contain ciphertext, nonce material,
wrapped data keys, key IDs, AAD/binding digests, expiry/revision metadata, and
content-free authority identifiers. They never contain plaintext message,
calendar, approval-preview, OAuth state, PKCE verifier, refresh token, or access
token values. Refresh tokens exist only inside the credential ciphertext. Access
tokens are short-lived in-memory values and are never accepted by a store RPC.

Payload and credential deletion install permanent, account-unlinked tombstones.
The tombstone is written before the live envelope can disappear, including on
account cascade. A tombstone permanently wins over a delayed create. The stored
`record_existed` result makes an exact idempotent erase retry a crash-safe
readback after a lost response.

Credential rotation uses a record-binding CAS and monotonically increasing
secret revision. Provider refresh is serialized across hosts through a bounded
database-time lease tied to the exact credential record binding. Claim and
finish are idempotent under their lease ID; callers re-open the encrypted
credential after claiming before contacting the provider. Host clocks do not
decide whether a competing lease is active. A provider response whose refresh
effect is unknowable permanently quarantines the exact credential generation;
the broker never retries a possibly consumed rotating refresh token.

Credential read, refresh claim, and replacement acquire the canonical
owner-to-connection-to-credential locks and revalidate the current ACTIVE
connection incarnation, authorization revision/snapshot, granted action and
scope commitments, external-account hash, expiry, and exact credential
reference. Disconnect, revoke, or credential replacement atomically installs a
permanent tombstone and removes local ciphertext in the same transaction. The
two winner orders for revoke versus read, refresh claim, and replacement are
covered by bounded two-connection PostgreSQL races.

After process restart, callers recover an exact immutable `ConnectedPayloadRef`
through the service-role-only owner/connection/action/provider/action lookup
RPC. It returns nonsecret reference metadata only, under the same payload lock;
it never returns ciphertext or a caller-supplied reconstructed reference. A
tombstoned payload is a terminal error, and every expected dimension is checked
before metadata is returned.

## OAuth state, PKCE, and provisional credential custody

`20261107231500_connected_app_oauth_secret_custody.sql` adds four more private,
forced-RLS relations and nine service-role-only exact-shape RPCs. The durable
broker envelope-encrypts OAuth state and the PKCE verifier before the ordinary
control plane creates the pending flow. SQL stores only their public hashes or
challenge plus key ID, nonce, wrapped-key, ciphertext, AAD binding, expiry, and
content-free flow authority. Authorization codes and provider access tokens are
never accepted by an RPC and are never persisted.

Before provider dispatch, the broker commits a one-use flow/exchange/attempt
fence. The same attempt can recover a lost database response; every competing
attempt receives `fresh=false` and cannot redispatch the code. A successful
provider exchange writes its refresh token directly into provisional encrypted
custody before returning a credential handle. An unknown exchange effect is a
durable ambiguous terminal. If account identification fails after exchange,
the refresh token remains encrypted in quarantined custody rather than being
exposed or retried.

Only an exact ACTIVE `OAuthCompletion` may promote a provisional token into the
normal credential vault. Final credential creation is an exact CAS; replay
repairs a crash after credential creation and before provisional erasure. The
provisional row is then permanently tombstoned. Denial, expiry, abort, and
connection/account deletion erase flow and provisional ciphertext through
permanent identity-bound tombstones. PostgreSQL races prove exactly one exchange
fence winner plus grant-versus-abort in both winner orders.

## Request and preview commitments

The durable payload `payload_sha256` is a keyed HMAC commitment produced by the
payload vault. It is the only request-parameter commitment permitted in SQL. A
plain deterministic provider request target hash would be dictionary-testable
for low-entropy actions and must not be added to any store or control-plane row.

The encrypted action envelope must use a versioned shape equivalent to:

```text
{
  kind: connectedActionRequestV1,
  request: <typed provider request>,
  requestTargetBindingSha256: <plain exact request binding>
}
```

All three fields are inside AES-GCM ciphertext. On open, runtime must first
reconstruct the typed provider request and verify its intrinsic target binding
against the encrypted `requestTargetBindingSha256`. Separately, the vault
recomputes the keyed commitment and verifies it against durable
`parameters_sha256`. The plain binding is ephemeral and must never be copied
into SQL, logs, receipts, telemetry, or an approval row.

`preview_sha256` has the same dictionary risk if it is a plain digest of a
predictable preview. The durable value must therefore be a keyed preview
commitment. If an exact plain preview hash is needed for rendering validation,
it belongs only inside the encrypted review payload and is checked after
decryption.

## Explicit release blockers

The following are not supplied by this slice and remain release blockers:

- External KMS/KEK configuration, key lifecycle, version availability, audit
  evidence, and a tested recovery/rotation procedure. Local static key material
  is test-only.
- Concrete provider revocation and cleanup execution with durable response-loss
  readback. A database cleanup request alone does not revoke a provider grant.
- Provider-result reconciliation when account or connection deletion wins
  after a provider exchange but before encrypted provisional custody commits.
  The local database correctly refuses custody without its owner/connection,
  but the provider grant may then require an out-of-band revocation attempt.
- A continuously invoked expiry/abort reconciler that tombstones abandoned
  encrypted OAuth flow/provisional custody and drives provider cleanup with
  bounded retry, telemetry, and operator-visible terminal outcomes.
- Production callback/start/refresh composition using the concrete Supabase
  adapters, with no fallback to in-memory stores and no secret-bearing logs,
  traces, exception strings, or telemetry.
- Exact final predecessor/target attestation, version-preserving schema
  application, converged PostgREST cache, production composition, and an
  authenticated bounded preview smoke.

Until every blocker is closed, no connection, callback, scheduled action,
provider call, approval execution, or public capability may be enabled.
