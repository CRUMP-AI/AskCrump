# Ask Crump connected operator: outside release runbook

Status: build/runbook only. Every source, provider, schema, and public release
lock remains false. This document does not authorize creating accounts,
purchasing services, storing secrets, applying production migrations, or
enabling the feature.

The connected operator is not complete merely because its local tests pass.
This runbook is the required outside half of the release: provider
registrations, short-lived key custody, version-preserving schema application,
real-account verification, physical-device testing, and an explicit release
decision.

## Non-negotiable handling rules

- Never paste client secrets, refresh tokens, Vercel OIDC assertions, KMS
  plaintext, Supabase credentials, passwords, OTPs, or recovery links into a
  chat, ticket, log, repository, browser URL, or screenshot.
- Use distinct development/staging and production Google projects and Microsoft
  registrations. Production redirect URIs must never point at preview hosts.
- The browser receives only an authorization URL and opaque state. OAuth code,
  state, tokens, connection IDs, account identity, and provider errors are
  removed before returning to `/app`.
- Do not enable either release lock until the exact composition manifest,
  migration set, provider registrations, KMS policy, and smoke receipts match.
- A failed provider write is never blindly repeated. “Uncertain” remains an
  explicit terminal/reconciliation state.

## 1. Freeze the exact release candidate

1. Record the exact Git commit, composition-manifest SHA-256, migration file
   names and SHA-256 values, web/PWA cache versions, and reviewed provider scope
   catalog.
2. Require the full local Python/JavaScript/PostgreSQL/browser suite and two
   independent no-P0–P3 reviews on that exact tree.
3. Confirm all checked-in locks remain false in the candidate. The later lock
   flip is a separate reviewed change after the outside gates pass.
4. Reject any provider or schema configuration whose attestation differs from
   the frozen manifest. Generate a new candidate rather than editing an
   attestation in place.

## 2. Google OAuth production registration

1. Use a dedicated production Google Cloud project. Enable the Gmail API and
   Google Calendar API only.
2. Configure a Web application OAuth client with the exact redirect URI:
   `https://www.askcrump.com/api/connected-apps/oauth/callback/google`.
3. Configure the consent screen with the canonical Ask Crump home page,
   privacy policy, terms, support address, verified domain, current operator
   contacts, and an accurate explanation of mail/calendar use and deletion.
4. Request scopes incrementally from the reviewed server catalog. Google
   identity uses `openid email`; background access uses the provider's offline
   flow. Do not request `https://mail.google.com/` or permanent deletion.
5. Gmail read/compose/modify scopes are restricted. Before public production,
   complete Google's required verification and, when server-side restricted
   data is stored or transmitted, the applicable independent security
   assessment. Calendar and send-only scopes still require the applicable
   sensitive-scope review.
6. Test with dedicated non-customer accounts first. Prove consent denial,
   partial consent, incremental expansion, downgrade, revocation, reconnect,
   wrong account, expired flow, callback replay, and account deletion.

Official references:

- https://developers.google.com/identity/protocols/oauth2/policies
- https://developers.google.com/identity/openid-connect/openid-connect
- https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification
- https://developers.google.com/workspace/gmail/api/auth/scopes

## 3. Microsoft production registration

1. Create a production Microsoft Entra app registration for the supported
   account population. Ask Crump distinguishes personal accounts from
   work/school accounts and must exercise both paths before claiming both.
2. Register the Web redirect URI exactly as
   `https://www.askcrump.com/api/connected-apps/oauth/callback/microsoft`.
3. Use authorization-code flow with PKCE and delegated permissions only. The
   reviewed catalog adds `offline_access` and `User.Read`, then requests the
   least mail/calendar permissions required by the actions the owner chose.
4. Do not substitute application-wide mailbox permissions. Verify tenant
   restrictions, user/admin consent behavior, personal-account support, token
   revocation, reconnect, and organization-policy denial.
5. Prove `Mail.ReadWrite` is never treated as send authority by itself and
   `Mail.Send` is never treated as readback/draft authority by itself.

Official references:

- https://learn.microsoft.com/en-us/entra/identity-platform/v2-app-types
- https://learn.microsoft.com/en-us/entra/identity-platform/reply-url
- https://learn.microsoft.com/en-us/graph/permissions-reference

## 4. Vercel OIDC and Google Cloud KMS custody

The runtime must not store a service-account key or plaintext root key. Vercel
Functions supply their rotating assertion on the request header
`x-vercel-oidc-token`; it is not a stable module-level runtime environment
secret.

1. Keep Vercel OIDC in team-issuer mode. Create a Google Workload Identity Pool
   and provider whose issuer, audience, subject mapping, project, and production
   environment condition match only the Ask Crump production deployment.
   Because the Python function consumes Vercel's request header directly, set
   the provider's allowed subject-token audience to the exact
   `https://vercel.com/<TEAM_SLUG>` team audience. The STS request still names
   the full Google provider resource. Do not select Google's default provider
   audience unless the runtime is changed to mint a custom-audience Vercel
   token for every invocation.
2. Create one service account with no user-managed keys. Allow the exact WIF
   principal to impersonate it. Grant that service account decrypt permission
   only on the one connected-operator CryptoKey.
3. Prefer an HSM-protected symmetric key. Pin the expected protection level,
   reviewed CryptoKey resource, primary-key requirement, WIF audience, service
   account, and IAM-policy attestation in the composition manifest.
4. Generate one random 32-byte data root in a controlled local ceremony. Encrypt
   it with Cloud KMS using the 32 raw bytes of the composition-manifest SHA-256
   as additional authenticated data. Store only the KMS ciphertext in Vercel's
   protected production configuration, then destroy the plaintext ceremony
   copy.
5. At request time, exchange the Vercel assertion through Google STS, impersonate
   the service account with a short-lived `cloudkms`-only token, decrypt the
   manifest-bound ciphertext, verify CRC32C/primary/protection level, derive
   separate keys for every vault domain (including the isolated
   `readiness_attestation` HMAC domain), and expire the in-process root in at
   most ten minutes.
6. Prove wrong team/project/environment/audience, stale assertion, non-primary
   key, protection-level drift, manifest drift, CRC drift, and IAM downgrade all
   fail closed without exposing or logging tokens.

### Memory-only sealing ceremony

The reviewed helper is `scripts/provision-connected-operator-secrets.py`. Run
it only from a controlled, interactive local terminal after the exact release
manifest, Google KMS CryptoKey, IAM policy, and both production OAuth
registrations have been independently reviewed. It uses hidden terminal input
for both client IDs and secrets, generates the 32-byte root in process memory,
derives the manifest-bound `host_configuration` key domain, seals the exact
Google/Microsoft registration JSON, and asks Cloud KMS to encrypt the root with
the raw manifest SHA-256 bytes as AAD. It never writes or prints the plaintext
root or either provider secret.

Before the ceremony, authenticate the user-controlled `gcloud` CLI identity
that is authorized to encrypt with the exact reviewed key. Do not pass a client
ID or secret as an argument, environment variable, redirected file, clipboard
snippet, or shell-history entry. Invoke only the nonsecret identifiers:

```powershell
python scripts/provision-connected-operator-secrets.py `
  --manifest-sha256 <FROZEN_COMPOSITION_MANIFEST_SHA256> `
  --root-key-id <REVIEWED_ROOT_KEY_ID_MAX_31_CHARACTERS> `
  --crypto-key-resource <REVIEWED_KMS_CRYPTO_KEY_RESOURCE> `
  --custody-attestation-sha256 <REVIEWED_KMS_IAM_ATTESTATION_SHA256> `
  --vercel-project-dir <ABSOLUTE_PATH_TO_EXACT_LINKED_PROJECT> `
  --expected-vercel-org-id <REVIEWED_VERCEL_ORG_ID> `
  --expected-vercel-project-id <REVIEWED_VERCEL_PROJECT_ID> `
  --vercel-operation add `
  --vercel-cli <ABSOLUTE_PATH_TO_VERCEL_CLI_59_6_OR_NEWER>
```

Enter the Google and Microsoft client registrations only at the four hidden
prompts. The ceremony requires the Google Web client ID to end in
`.apps.googleusercontent.com`, the Microsoft application ID to be a canonical
lowercase UUID, and the two provider secrets to be distinct; it aborts before
generating a root if any of those exact registration checks fails. Capture
neither the prompts nor standard output. Before asking for a secret, the helper
requires an interactive non-CI terminal, validates the exact
`.vercel/project.json` organization/project IDs, requires Vercel CLI 59.6.0 or
newer, and runs `vercel project inspect --non-interactive` from that exact
linked directory. It then streams each ciphertext over child-process stdin
directly to these protected production-secret entries:

- `CRUMP_CONNECTED_KMS_ENCRYPTED_ROOT_B64`;
- `CRUMP_CONNECTED_HOST_CONFIGURATION_CIPHERTEXT`.

The ciphertexts never appear in argv, environment variables, ordinary files,
CLI output, or terminal output. The Vercel child's stdout and stderr are
discarded. Standard output contains only a hash-only receipt identifying the
exact Vercel target, variable names, root key ID, exact CryptoKeyVersion,
custody-attestation SHA-256, ciphertext SHA-256 values, and generation time.
Use `--vercel-operation add` only for verified-absent entries. If an entry
already exists, or a prior attempt installed only one of the two entries, stop,
inspect the protected Vercel state without displaying a value, and rerun the
whole memory-only ceremony with `--vercel-operation update`. Never mix `add`
and `update` inside one ceremony. Keep both source release locks false and do
not deploy after any partial or failed installation.

Pin
the reviewed project number, WIF pool/provider, service account, CryptoKey,
root key ID, protection level, root TTL, and custody-attestation SHA-256 in the
source constants beside the composition manifest. Do not supply or override
those identities through deployment variables. The host accepts only the two
ciphertexts above plus Vercel's platform-authored deployment ID and commit SHA
from runtime configuration. It must not contain plaintext OAuth secrets,
service-account JSON, a persistent root key, or a runtime
`VERCEL_OIDC_TOKEN` fallback. The Vercel assertion is accepted only from the
current request's `x-vercel-oidc-token` header.

This repository change did not run the ceremony, create a key, register an
OAuth client, or store any ciphertext. Those remain user-controlled outside
actions.

### One-shot release-preview harness

The reviewed boundary has four parts:

- `backend/connected_app_release_bootstrap.py` performs the visible,
  user-controlled dedicated-account OAuth bootstrap;
- `backend/routes/connected_apps.py` exposes only the source-locked,
  same-deployment internal POST `/api/connected-apps/internal/release-preview`;
- `backend/connected_app_release_preview_supervisor.py` claims one durable
  invocation and supervises a bounded child; and
- `backend/connected_app_release_preview_child.py` composes the exact sealed
  production harness and exits after emitting one content-free receipt.

The checked-in `CONNECTED_APPS_RELEASE_PREVIEW_SOURCE_RELEASED`,
`CONNECTED_APPS_PUBLIC_RELEASED`, and
`CONNECTED_MULTI_STEP_SOURCE_RELEASED` values all remain `False`. While any is
false, the route returns before origin checks, authentication, body parsing,
release-only imports, database work, KMS, provider, or gateway I/O. A reviewed
release candidate must change all three to `True` together and ship with the
production environment enablement already true. The ordinary connected graph
still fails closed because its exact database/KMS readiness does not exist
until this ceremony succeeds. The internal route bypasses that ordinary graph,
records readiness for the exact same deployment and commit, and only then can
a later request acquire the public graph. Never make a post-ceremony lock
change, commit, redeploy, or environment-only deployment: that would create a
different immutable tuple and invalidate the readiness evidence.

#### Pre-release OAuth and account attestation

From the exact candidate deployment, use the visible bootstrap flow to connect
only dedicated non-customer accounts. It creates six resource bindings:

1. Google personal mail;
2. Google personal calendar;
3. Microsoft personal mail;
4. Microsoft personal calendar;
5. Microsoft work/school mail; and
6. Microsoft work/school calendar.

The two resources for each account must resolve to the same provider-owned
external-account hash, and the three account groups must remain distinct.
Microsoft personal and work/school authority is constrained by the provider's
`consumers` and `organizations` endpoints. Google account type is checked
against the provider-authored hosted-domain claim. The bootstrap must fail on
an ambiguous or mismatched account rather than trusting a dropdown choice.

OAuth callback codes are untrusted, short-lived bearer secrets. After callback
validation, the service-role-only control plane atomically stores a
purpose-specific AES-GCM envelope bound to the owner, session, provider, flow,
callback consumption, exchange identity, PKCE/redirect commitments, and expiry.
Plaintext authorization codes never enter SQL, logs, URLs, receipts, or error
responses. Recovery may open the envelope only while no conflicting exchange
fence or terminal outcome exists. Terminal success, denial, quarantine, and
deadline cleanup erase the envelope and leave only a content-free tombstone.

After all six exact bindings are re-read, the operator must review the visible
three-account/six-resource matrix and type the exact dedicated-account claim.
One in-memory action-time permit writes a service-role-only attestation receipt
bound to the ceremony UUID, owner, active session, canonical descriptor matrix,
three account hashes, and exact claim. A sealed SHA by itself is not sufficient
evidence and the harness must recompute and re-read this receipt.

#### Same-deployment ceremony

The operator then invokes the internal route from a signed-in page on the same
production origin. The request must carry all of the following:

- exact HTTPS Host and Origin for `askcrump.com` or `www.askcrump.com`;
- `Sec-Fetch-Site: same-origin`;
- the custom same-origin CSRF header;
- the exact expected-owner precondition and a current registered-account
  session;
- the exact typed confirmation phrase; and
- Vercel's request-authored `x-vercel-oidc-token` assertion.

The route derives a domain-separated session binding and calls the
service-role-only claim RPC. The source-pinned operator-owner hash, Vercel
deployment ID, Git commit, and sealed-host-ciphertext hash must match. The RPC
returns one unexpired lease of at most 15 minutes. It cannot mint a second
invocation for a retry.

The supervisor starts a child with an exact environment allowlist and a maximum
240-second lifetime. The request OIDC assertion is sent only over the child's
stdin; it is never accepted from argv or the environment. Stdout is capped at
4096 bytes, stderr is discarded, and timeout, cancellation, malformed output,
or a child that remains alive fails closed. Process exit is the destruction
boundary for immutable Python root/token/client-secret bytes.

The child requires the exact fixed-destination Supabase, Google KMS, Google,
Microsoft, and Vercel AI Gateway implementations; caller-injected probes are
not accepted. It must prove:

- the frozen catalog, ACL/RLS/publication, migration-target, host-registration,
  KMS custody, deployment, commit, and provider-contract tuple;
- read/search/get against each dedicated mailbox and list/get against each
  dedicated calendar;
- Google and Microsoft work/school free/busy; Microsoft personal free/busy is
  explicitly unsupported rather than simulated;
- exact-preview mail draft/send/reply, with the bounded send and reply retained
  as clearly labeled dedicated release-test artifacts;
- exact-preview calendar create/update/cancel with cleanup proof;
- durable effect intents before each provider write, readback after ambiguous
  responses, rotated-refresh-token quarantine/recovery, credential retirement,
  and zero unsettled effect rows before readiness;
- one request-OIDC AI Gateway planning call pinned to
  `openai/gpt-oss-20b` through `groq`, with per-request zero-data-retention and
  no-prompt-training routing; and
- the returned gateway routing audit naming the pinned final provider and a
  nonempty planning reason. A successful model response without that audit is
  not evidence.

The external preview is idempotent only through the durable ledger. On a host
crash or lost response, the claim RPC may issue a fresh short lease for the
same invocation and markers with `recovery=true`. Recovery first reconciles
the same effect rows; it cannot mint new provider markers or repeat a settled
write. Success makes the invocation permanently inert. Readiness cannot be
recorded until all six effects are settled and preview credentials are retired.

The one-use readiness record RPC is never blindly retried. After response loss,
the harness re-reads the exact live readiness tuple/HMAC. An absent receipt, an
older receipt, unsettled effect, reusable credential, or catalog/lease drift
fails closed. The route returns only invocation ID and lease times; it never
returns KMS material, tokens, account/provider identifiers, registration data,
provider bodies, or receipt hashes.

Before considering the outside gate passed, run this exact child once on the
authenticated exact production candidate and capture proof that the
Python runtime can create, supervise, terminate, and bound the subprocess under
the deployed Vercel Function limits. Documentation alone is not subprocess
proof. This repository run did not flip any of the three source locks, connect
an account, run a provider or gateway request, apply schema, execute the
ceremony, or spend money.

Official references:

- https://vercel.com/docs/oidc
- https://vercel.com/docs/oidc/gcp
- https://docs.cloud.google.com/kms/docs/reference/rest/v1/projects.locations.keyRings.cryptoKeys/decrypt
- https://docs.cloud.google.com/kms/docs/data-integrity-guidelines

## 5. Version-preserving Supabase application

1. Use a user-controlled, authenticated, linked, scoped Supabase CLI or CI
   identity. Never apply these migrations through an ad-hoc SQL editor or an
   unversioned `apply_migration` call.
2. Compare repository and remote history with `supabase migration list
   --remote`. Do not insert, delete, rename, backdate, or “repair” history to
   force a match.
3. Run `supabase db push --dry-run --remote`. It must list exactly the frozen,
   reviewed pending versions in ascending order and nothing else.
4. Stop on any missing, extra, reordered, or already-present version. Reconcile
   the repository and remote history without rewriting either.
5. Apply once from the approved operator/CI lane. Do not include seed data.
6. Wait for the PostgREST schema cache to converge, then run exact catalog,
   owner/ACL/RLS, publication, function-body, search-path, predecessor/target,
   and hostile reapply attestations before deploying application writers.
   Prove the bounded retention worker physically removes expired encrypted read
   payloads, cryptographically erases expired plan envelopes, leaves unexpired
   records untouched, and remains idempotent against concurrent workers and
   account deletion.
7. Drain every old writer instance before enabling a schema-dependent app. Once
   a new writer has produced durable state, do not roll back beneath its
   compatibility floor.
8. Do not separately issue a challenge, call a provider/gateway smoke, record
   readiness, or query readiness after these schema/deployment steps. Those are
   child-owned internals of the **single** same-deployment internal-route
   invocation documented in “Same-deployment ceremony” above. The child
   obtains and consumes the one-use challenge, performs exactly one bounded
   Google/Microsoft/AI smoke set, records the HMAC-bound readiness receipt, and
   proves the fresh readiness lease. Running any of those operations as an
   additional operator command could duplicate real mail/calendar effects and
   invalidate the one-use ceremony.
9. The provider smoke is durable only for the exact immutable deployment tuple;
    normal graph renewal must not touch user providers. A new deployment,
    commit, schema target, provider contract, encrypted registration envelope,
    or KMS root key ID requires a fresh challenge and both previews. Per-account
    revocation, permission loss, and provider outage remain connection-health
    failures and must not be disguised as global deployment readiness.

Official references:

- https://supabase.com/docs/guides/deployment/database-migrations
- https://supabase.com/docs/guides/local-development/cli-workflows

## 6. Dedicated-account and physical-device matrix

Use dedicated Google personal, Microsoft personal, and Microsoft work/school
test accounts. Never use customer mail or calendars for release probes.

For each supported provider/account kind, prove:

- initial connect, denial, partial consent, reconnect, and scope expansion;
- same-provider/resource double-connect refusal, abandoned-expired start
  recovery, and both concurrent callback winner orders with durable cleanup of
  the losing provisional grant;
- ordinary-language mail search/get and calendar list/get/free-busy;
- exact-preview approve/deny/expire/replay for draft/send/reply and event
  create/update/cancel;
- fresh approval for every scheduled write occurrence;
- multi-step read-to-write tasks pause at the exact approval boundary, survive
  force-close/reopen and a new deployment, and never repeat a completed effect;
- disconnect/revoke, response loss, host crash, cleanup retry, and zero raw
  provider identifiers in content-free tombstones;
- owner A to owner B to guest switching with no content, approval, connection,
  result, schedule, or task bleed;
- Safari, installed PWA, Chromium, mobile keyboard/focus, offline reopen,
  notification deep-link, and service-worker upgrade behavior; and
- served commit, release, cache, manifest, database versions, provider app IDs,
  KMS key/version, and bounded production logs captured in one evidence packet.

## 7. Release and rollback decision

1. Review the final evidence packet and unresolved limitations with Gregory.
2. In one reviewed release-candidate change, set the preview, public connected
   app, and durable multi-step source locks to `True`, pin the exact composition
   identities, and enable only the production environment. Deploy that exact
   commit once. Ordinary connected routes must remain readiness-blocked until
   the same deployment's internal ceremony succeeds. Do not make another
   source, environment, commit, or deployment change between ceremony and
   release; multi-step is part of this release and may not be silently staged.
3. Observe bounded health, provider, auth, cleanup, scheduler, approval, and
   uncertain-effect signals without inspecting customer content.
4. A rollback may disable entry points and drain workers. It must never deploy a
   writer below the established schema/action compatibility floor or blindly
   replay an uncertain provider effect.
5. If any outside gate is missing, keep the product hidden/inert and report the
   exact blocker. Local readiness is not a live-capability claim.
