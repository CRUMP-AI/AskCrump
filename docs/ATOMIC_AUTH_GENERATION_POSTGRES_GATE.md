# Atomic auth PostgreSQL gate

This gate applies every repository migration through
`20260916214309_atomic_auth_generation.sql` to a freshly created disposable database and exercises
the credential-generation boundary with real PostgreSQL transactions.

## Safety boundary

The harness accepts only an explicit loopback PostgreSQL host (`localhost`, `127.0.0.1`, or `::1`)
and validates the server-reported address before doing any work. Those address checks reject direct
remote endpoints, but they cannot detect a loopback proxy or tunnel. The operator must therefore set
an exact ownership attestation confirming that the endpoint is an owned disposable local cluster,
not a route to staging, production, Supabase Cloud, or any other shared database.

It requires the local `postgres` superuser and creates a random `askcrump_atomic_auth_*` database.
Cleanup tracks whether `CREATE DATABASE` actually succeeded; a merely selected or colliding name is
never a drop target. If the three Supabase API roles are absent, it creates them temporarily and
removes only those roles that it created after dropping the database.

The stock-PostgreSQL bootstrap supplies only the Supabase objects used by this migration ledger:
`anon`, `authenticated`, and `service_role`, the service-role default privileges, and the columns of
`storage.buckets` referenced by the file-storage migrations. It never substitutes for a later
owner-controlled Supabase staging check.

## Local run

Install the isolated harness dependency, start a disposable PostgreSQL 15-or-newer server, and pass
the server's local admin URL. For example:

```powershell
python -m pip install -r requirements-postgres-test.txt
$env:ASKCRUMP_POSTGRES_ADMIN_URL = 'postgresql://postgres:postgres@127.0.0.1:5432/postgres'
$env:ASKCRUMP_DISPOSABLE_POSTGRES_ACK = 'I_OWN_THIS_DISPOSABLE_LOCAL_CLUSTER'
python scripts/verify_atomic_auth_generation_postgres.py
```

The script verifies:

- all 57 migrations apply in ledger order through the target migration;
- both `auth_generation` columns and nonnegative constraints have the expected shape;
- both functions are security-invoker, have an empty fixed search path, return `jsonb`, deny
  `PUBLIC`/`anon`/`authenticated`, and allow only `service_role` plus the owner;
- login-before-reset blocks on the user row and the reset then revokes that session;
- reset-before-login blocks the stale login and the stale generation persists no session;
- two concurrent uses of one reset token produce exactly one password/generation update;
- an active session with an old generation cannot match the current credential generation; and
- rolling back either reset or session persistence leaves none of its changes behind.

The `atomic-auth-postgres` CI job owns its PostgreSQL 15 container and starts it with host networking,
`listen_addresses=127.0.0.1`, and a dedicated port. The connection and the server both therefore see
a genuine runner-loopback address instead of a service-container bridge address. The job always
stops and removes that container.

The source-review host used to add this gate had no Docker, PostgreSQL binaries/service, Supabase CLI,
or installed WSL distribution, so it could not execute the database portion locally. A successful CI
run (or the exact attested local command above) is required evidence; source-only tests are not a
substitute.
