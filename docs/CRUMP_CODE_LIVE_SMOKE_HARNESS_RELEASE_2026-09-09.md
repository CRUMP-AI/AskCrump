# Crump Code live-smoke harness release

Date: 2026-09-09

## Outcome

Crump Code now has a fail-closed operator harness for the first live Vercel Sandbox proof while the
customer feature remains disabled. The production runner and the harness share one provisioning
function, so the proof exercises the same project identity, source checkout, resource limits,
network policy, environment boundary, persistence setting, and destruction-on-exit contract that a
real task will use.

This release did **not** run a live Sandbox. It used no Vercel OIDC token, model call, database row,
customer content, production task, credit, or paid compute. Public Crump Code remains disabled.

## Guarded proof contract

The default command is non-networked and cannot authorize live compute:

```powershell
python scripts/run_crump_code_sandbox_smoke.py --dry-run
```

A future live run requires all of the following at action time:

- an owner-approved maximum cost of exactly one cent;
- the exact source acknowledgement `public-no-secret-fixture`;
- a short-lived `VERCEL_OIDC_TOKEN` in the process environment, never a command-line argument;
- token claims matching the Ask Crump Vercel project and team;
- `CRUMP_ENABLE_CODE_WORKSPACE` absent or false;
- the fixed public `octocat/Hello-World` fixture pinned to commit
  `7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`.

After those conditions are independently approved and supplied, the one permitted command is:

```powershell
python scripts/run_crump_code_sandbox_smoke.py --live --confirm-max-cost-cents 1 --confirm-source public-no-secret-fixture
```

The harness provisions at most one 30-second Sandbox with 2 vCPU, 4096 MB, no injected environment
variables, deny-all networking, no persistence, and destruction on context exit. It makes no model
call and writes no application database record. Its fixed checks prove the pinned checkout,
temporary workspace write/read/delete, clean repository state, absence of named application secrets,
blocked outbound networking, reported deny-all policy, and successful cleanup. Output is a bounded,
content-free JSON receipt; it never prints the OIDC token, repository URL, command output, or an
arbitrary exception message.

## Verification

- The harness defaults to dry-run and rejects `--live` without the exact cost acknowledgement.
- Gate fixtures reject a missing or wrong budget, missing or wrong source acknowledgement, an
  enabled customer feature, missing OIDC, and the wrong Vercel project scope before provisioning.
- Runtime fixtures reject allowed networking and exposed sensitive environment names.
- A provisioning-parity test proves production and smoke use the exact same resource, source,
  network, environment, persistence, tag, identity, and destruction contract.
- Focused Crump Code coverage passed. The complete Python suite collected **974 tests**
  (**972 passed**, two environment-dependent skips); the **49-file** JavaScript contract and all
  **21/21** rough-to-useful attribution cases passed. Button ownership passed **22/22** across
  **275** rendered and programmatic construction sites, and the fail-closed browser matrix passed
  **36/36** workflow verifiers. Ruff, Python compilation, production preflight, native web-bundle
  construction, store metadata, native privacy, mobile signing-source controls, and diff integrity
  also passed.
- Commit **7607cbd** passed CI run **34414256968**. Production deployment
  **dpl_9t9qSD2FQoKTnR8Ro1czuTG1RjTh** reached READY on all six aliases with no alias error. All four
  custom-domain health checks returned 200 at version 5.9.76; unauthenticated `/api/features`
  remained fail-closed at 401. Initial project runtime-error, deployment 5xx, and `crump_code` log
  queries were empty.

## Remaining gate and rollback

The owner-approved live run, externally confirmed Sandbox destruction, cancellation, expiry,
refund, operational-signal, rollback-timing, quality, latency, and actual unit-cost proofs remain
open. This harness is preparation, not activation or a parity claim.

Rollback is to revert the shared provisioning extraction, the operator script, its tests, and this
record. Keep `CRUMP_ENABLE_CODE_WORKSPACE=false`; no database or provider rollback is required.
