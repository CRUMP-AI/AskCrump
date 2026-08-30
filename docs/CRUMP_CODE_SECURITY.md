# Crump Code security and release boundary

Last reviewed: 2026-08-30

## Product scope

Crump Code is a disabled-by-default foundation for project-scoped repository work. The first
release supports public GitHub repositories, planning, patch-based implementation, bounded
verification, durable task history, and explicit approval records. It is not yet a public
Codex- or Claude Code-equivalent product and must not be described that way until benchmarked.

## Trust and execution boundary

- The browser never receives provider, Supabase service-role, or Vercel credentials.
- The API derives the account from the authenticated session and checks project ownership.
- Repository sources are limited to credential-free `https://github.com/owner/repository` URLs
  and a restricted optional revision.
- Every run uses a new, non-persistent Vercel Sandbox with two vCPUs, 4 GB memory, a 30–240
  second limit, an empty environment, deny-all networking, and destruction on exit.
- The sandbox contains only the requested public repository. It receives no production
  database, billing, provider, email, push, or storage credentials.
- The model can use a small allowlist of file, search, edit, and verification tools. Write tools
  are unavailable in plan mode. Verification commands are allowlisted and bounded.
- Paths are resolved inside the workspace. Traversal, `.git`, environment/credential names,
  and common binary file types are rejected.
- Returned tool text is scrubbed for environment assignments, private keys, bearer tokens,
  JWT-like values, and common provider token patterns.

## Lifecycle and approvals

Tasks use optimistic state transitions plus an idempotent dispatch token and a private,
time-limited worker lease:

`queued → provisioning → running → verifying → completed`

They may also move to `awaiting_approval`, `failed`, or `cancelled` where allowed by the state
graph. Approval records are designed for network access, credential access, destructive source
writes, publishing, or extended runtime. None of those actions is granted by the initial runner.

Nonterminal tasks expire after seven days and pending approvals expire after 30 minutes. Owner
reads reconcile stale records into durable terminal states, while atomic claim and approval filters
enforce the boundary even before reconciliation. Expiry is checked before entitlement evaluation,
claim, charging, Sandbox identity resolution, and provisioning. Cancellation or expiry is checked
again after provisioning and around the remaining model, verification, and patch boundaries.

Cancellation prevents a queued task from starting, clears its lease, and records the decision.
The worker checks task status and lease ownership again around expensive boundaries. A running
sandbox is also bounded by its execution deadline and destruction-on-exit contract. Terminal
refunds are reconciled before any new compute, including while the feature flag is off. The
initial release returns a patch; it does not push, merge, publish, deploy, or mutate the source
repository. Rollback therefore consists of declining the patch or reverting an applied patch
outside the sandbox.

## Stored data

The server stores the task objective, public repository URL/ref, lifecycle state, bounded result
summary, patch, verification receipt, credit receipt, idempotent dispatch state, private worker
lease state, retry counters, and content-free audit metadata. Public API responses omit account
IDs, sandbox identifiers, dispatch tokens, lease tokens, and internal usage receipts. Database
audit events and operational logs use separate allowlists and do not store prompts, source file
bodies, repository URLs, model output, secrets, account/task identifiers, or arbitrary errors.

The three tables use row-level security without client policies. `anon` and `authenticated` have
no access. The server role can manage tasks, append but not modify/delete audit events, and create
or decide but not delete approvals.

## Release gates

The API and database foundation may deploy with `CRUMP_ENABLE_CODE_WORKSPACE=false`. Public
activation requires all of the following:

1. A real no-secret sandbox smoke test confirms OIDC, resource limits, deny-all networking, and
   automatic destruction.
2. End-to-end tests cover creation, run, cancellation, failure/refund, patch review, and expiry.
   Automated coverage now proves task and approval expiry, late-decision rejection, pre-provision
   cancellation, idempotent dispatch, replay-safe leases, bounded retry, refund-before-compute,
   disabled-state refund reconciliation, and content-free operational logging. Live Sandbox
   execution remains gated by item 1.
3. A user interface makes mode, source, cost, diff, verification, and approval state explicit.
4. A benchmark set measures task completion, patch validity, security, latency, and unit cost.
5. Monitoring and a one-click kill switch are verified in production.

## Known limitations

- Only public GitHub repositories are accepted; private repositories and user credentials are
  intentionally unsupported.
- Execution is accepted asynchronously and processed by the existing minute worker. The current
  worker claims one Crump Code task per shared cron invocation, so throughput and manuscript
  fairness must be measured under representative load before wider activation.
- Expiry reconciliation is lazy on owner list/detail reads and execution boundaries rather than a
  background scheduler. Atomic run and approval guards remain authoritative.
- Approval records exist, but the initial runner never requests elevated capabilities.
- The model and verification suite can still miss defects. Every patch remains user-reviewable.
