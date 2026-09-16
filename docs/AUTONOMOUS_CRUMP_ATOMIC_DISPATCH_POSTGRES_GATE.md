# Autonomous Crump atomic-dispatch PostgreSQL gate

Status: **candidate-only, disabled, undeployed, and not yet executed against PostgreSQL**.

This gate applies all 57 repository migrations through
`20260916231500_autonomous_crump_atomic_dispatch.sql` to a freshly created disposable PostgreSQL
15 database, then executes the billing-and-dispatch boundary with real roles, transactions, locks,
and simultaneous connections. It does not enable Autonomous Crump and confers no merge, release, or
deployment authority.

## Safety boundary

The harness accepts only an explicit loopback host (`localhost`, `127.0.0.1`, or `::1`) and checks
the server-reported address. Those checks reject directly addressed remote servers, but they cannot
detect a loopback proxy or tunnel. The operator must therefore provide the exact ownership
attestation only for a locally owned disposable cluster—not staging, production, Supabase Cloud, or
another shared database.

The harness requires the local `postgres` superuser, PostgreSQL 15 exactly, and a random
`askcrump_autonomous_atomic_*` database. Cleanup records a database as owned only after `CREATE
DATABASE` succeeds, so an existing or colliding name is never a drop target. It removes only API
roles that it created itself and always force-drops its owned test database.

The stock-PostgreSQL bootstrap creates only the Supabase-compatible API roles, default service-role
grants, and `storage.buckets` shape needed by this migration ledger. This is a transaction and
privilege gate, not a substitute for a later owner-controlled Supabase staging verification.

## Exact database evidence required

`scripts/verify_autonomous_atomic_dispatch_postgres.py` verifies:

- the atomic function is `SECURITY INVOKER`, has an empty fixed search path, grants execution only
  to its owner and `service_role`, rejects `anon` and `authenticated` by actual execution, and leaves
  the legacy two-step dispatch function revoked from `service_role`;
- a wrong pinned SHA, expired task, non-queued task, or missing task creates no usage event, credit
  ledger entry, claim event, owner token, receipt, or task transition;
- one dispatch token replays the exact committed task and receipt while producing exactly one
  allowance event and one `task.claimed` event;
- simultaneous distinct tokens for one task produce one acceptance and one `task_not_ready` result;
- simultaneous tasks competing for one remaining included slot produce one included acceptance and
  one confirmation-required result;
- an exhausted allowance with valid confirmation deducts 12 credits once, while token replay adds no
  second ledger, allowance, or claim fact;
- missing confirmation and insufficient balance preserve the queued task and create no debit or
  claim event;
- a trigger-injected task-update failure after allowance consumption or credit deduction rolls back
  the entire statement, including the allowance event or ledger/balance change;
- an internal-tier run creates no allowance event and no credit deduction; and
- unpaid queued work is invisible to the worker, while accepted work exposes the exact persisted
  receipt and private owner token and supports one replay-safe worker lease.

## Local command

```powershell
python -m pip install -r requirements-postgres-test.txt
$env:ASKCRUMP_POSTGRES_ADMIN_URL = 'postgresql://postgres:postgres@127.0.0.1:5432/postgres'
$env:ASKCRUMP_DISPOSABLE_POSTGRES_ACK = 'I_OWN_THIS_DISPOSABLE_LOCAL_CLUSTER'
python scripts/verify_autonomous_atomic_dispatch_postgres.py
```

## Evidence state

The source-review Windows host has no Docker, PostgreSQL client/server, Supabase CLI, or installed
WSL distribution. Source-only validation is not database evidence. The new CI job is present on this
candidate branch, but this workflow runs only for `main` or pull requests. A CI-only mirror or pull
request is therefore required to execute the owned PostgreSQL 15 gate without altering production.

No production database, Supabase project, provider, feature flag, user account, or deployment was
accessed or changed while constructing this candidate.
