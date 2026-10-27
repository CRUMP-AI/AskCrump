# Server policy-consent rollout

Status: draft engineering plan only. This change is not live and does not make
legal conclusions.

## Release blocker: compatible native binary

Do not merge or deploy this enforcement change until a compatible Capacitor
binary that can submit the exact current bundle and all four explicit
attestations is available through the native release path, and the company has
chosen a safe adoption/transition threshold. Existing installed binaries embed
the earlier consent payload and cannot receive these source changes from a web
deployment; enforcing the new contract first would strand those users behind
422/403 responses. Do not bypass this gate with a client-supplied platform
header or fabricate receipts for older clients.

## Release order

1. Run the PostgreSQL migration in one transaction.
2. Read back the exact manifest, receipt constraints, RLS state, zero direct
   table grants, service-role-only RPC grants, and account-deletion cascade.
3. Deploy the application only after that readback is clean.
4. Monitor the content-free `POLICY_ACCEPTANCE_REQUIRED` outcome count and
   ordinary error telemetry. Do not use synthetic provider traffic or customer
   content for release proof.

The migration is schema-first and additive. Existing users and guests do not
receive fabricated receipts from the legacy timestamp. They must explicitly
accept the exact current bundle before protected product, data, or provider
routes proceed. Session inspection, logout, recovery, acceptance, and account
deletion remain available.

Durable code tasks are held with a bounded, attempt-neutral retry before any
runner call when acceptance is missing. Durable manuscript runs enter their
existing paused state and can resume only through the consent-gated account
route. Proactive and reconciliation workers must perform the same exact-current
check before reading user content or contacting a provider. A transient receipt
verification outage also fails closed: code and manuscript claims release their
lease, restore the claimed attempt, and queue a bounded retry without provider
or usage mutation.

## Application rollback

If application behavior fails, roll application code back to the exact PR #122
head while leaving the additive manifest and receipt tables in place. The
receipt RPC mirrors its database timestamp and bundle ID into the legacy
`users.terms_accepted_at` and `users.terms_version` fields, so the prior
application can read the accepted state. Do not drop or rewrite receipt history.
A later corrective migration is the database rollback path.

The exact PR #122 application predates append-only receipts. During an
emergency application rollback it can still accept a legacy timestamp, but
that acceptance will not create a receipt. Keep the rollback interval short
and recorded; after the fixed application returns, affected accounts fail
closed and must explicitly accept the current bundle again. Do not backfill a
receipt from a legacy timestamp.

If the schema migration itself fails, its single transaction must leave no
partial table, function, trigger, manifest row, or grant.

## Explicitly unresolved retention decision (P3)

Receipts are kept only while the account exists and are deleted by the same
`users` foreign-key cascade as the account. The non-personal policy manifest is
retained. Whether law, dispute preservation, or another documented purpose
requires a different receipt-retention period is a separate counsel and company
policy decision. This engineering change intentionally does not silently choose
or implement a different retention rule.
