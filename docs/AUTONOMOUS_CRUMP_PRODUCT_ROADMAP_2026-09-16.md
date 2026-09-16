# Autonomous Crump product roadmap

Date: 2026-09-16

## Brand and positioning

The customer-facing product name is **Autonomous Crump**. The compact navigation label is
**Autonomous** and the full accessible name is **Autonomous Crump**. Stable implementation
contracts remain `crump_code`, `code_workspace`, `/api/code/**`, existing database/RPC names,
environment variables, source filenames, and content-free operational event names. Current dated
evidence remains historically accurate; forward-looking documents may say **Autonomous Crump
(formerly Crump Code; internal identifier `crump_code`)** once when migration context matters.

Until the launch gates below pass, Autonomous Crump is not shown on landing pages, onboarding,
store listings, public pricing, or campaign creative. The truthful first-release description is:

> Autonomous Crump private preview: plan and produce reviewable patches for supported public
> GitHub repositories in an isolated workspace.

This is not evidence of parity with Codex, Claude Code, or any other coding agent.

## Verified foundation

The disabled foundation already provides Project-attached tasks, public GitHub checkout, plan and
implement modes, bounded file tools, an isolated temporary Sandbox contract, durable task rows and
worker leases, cancellation/refund scaffolding, reconnectable status, file-scoped diff review,
verification output, and patch download. Two independent controls keep it unavailable publicly:
the checked-in source release lock and the operator environment switch.

The current foundation is a safety-first public-repository patch preview. It is not yet a general
coding workspace: it has no private-repository connection, structured plan approval, follow-up
turns, dependency setup, branch/commit/PR flow, inline review, durable working branch, or task URL.

## P0 — required before any invite-only activation

1. Keep the activation verifier unable to approve release from caller-authored JSON. Require a
   trusted owner-controlled attestation, a reviewed source decision, and a separate reviewed change
   to both release controls.
2. Make task/project selection generation-owned so a slow response cannot replace the current task
   or expose Run/Cancel for the wrong record.
3. Deliver the current navigation, loader, and workspace to returning PWA clients with an explicit
   service-worker and asset revision. Keep disabled capability copy out of public billing.
4. Make every result truthful: a failed check is failed and refundable; zero-check, unsupported,
   partial-check, and no-change outcomes are explicitly unverified or no-change, never simply Ready.
5. Make run submission and metering one crash-safe, idempotent logical action. Concurrent requests
   must create one allowance/credit event, one retained dispatch, and no refund of the winning run.
6. Resolve and display an immutable source SHA before any charge. Every retry must clone that SHA;
   an invalid repository or ref fails without metering.
7. Guarantee artifact integrity. Reject an oversized patch instead of truncating or rewriting it;
   visibly mark bounded reads/searches/inventories; never overwrite a whole file from incomplete
   context.
8. Close source-data bypasses with prompt-injection, credential-shape, `.env.*`, history-object,
   symlink, oversized-file, and malicious-script fixtures. Remove or tightly constrain `git show`.
9. Add per-user active-task, global queue/concurrency, and daily model/Sandbox cost stops. Code work
   must not starve manuscript work on a shared worker.
10. Preserve a safe failure stage, check evidence, refund state, and remediation message without
    customer content in logs. Do not advertise runtime approvals until one exact-scope, expiring,
    replay-safe capability actually uses them.
11. Pass one protected exact-revision live drill for OIDC, deny-all networking, empty environment,
    destruction, cancellation, expiry, refund, monitoring, rollback, repeatability, holdouts,
    latency, and actual unit cost. Keep both activation controls closed until independent review.

## P1 — credible beta

1. Add a least-privilege GitHub App, repository/branch picker, private-repository support, exact
   permission disclosure, and one default repository bound to an Ask Crump Project.
2. Add a structured plan with affected files, risks, and checks; clarification turns; and an exact
   plan-to-implementation approval bound to the pinned source SHA.
3. Support follow-up instructions and repair loops against a durable checkpoint rather than
   restarting from a fresh clone.
4. Add safe lockfile-bound dependency/test setup using approved registries or trusted snapshots.
5. Add targeted edits, delete/rename, conflict detection, large-file handling, and a final diff
   cryptographically bound to the verified workspace.
6. After an explicit action-time approval, create a branch and open a pull request. Keep credentials
   outside the model and Sandbox; do not merge or push the default branch automatically.
7. Add inline review, per-file or per-hunk acceptance, selected-change regeneration, risk/check
   summaries, and visible base/head SHAs.
8. Add task deep links, a desktop three-pane review workspace, a mobile status/approval view,
   opted-in completion notification, and a redacted downloadable run report.
9. Add a content-free operations view for queue age, stage duration, result truth state,
   cancellation latency, refunds, provider cost, and failure-code distribution.

## P2 — later product depth

- Large-repository and monorepo maps.
- Local CLI or IDE handoff with user-controlled filesystem permissions.
- Sandboxed development-server previews and visual regression checks.
- GitHub issue intake, PR review, CI repair, and merge-queue awareness.
- Multi-repository and budgeted multi-agent tasks.
- Scheduled maintenance with pause/resume approvals.
- Organization policy, audit export, managed secrets, roles, and retention controls.
- Provider routing/fallback and a substantially broader hidden evaluation suite.

## Release rule

No public activation, paid campaign, competitor-comparison claim, or store promise is authorized by
this roadmap. A feature branch may be pushed for review while the capability remains disabled. An
invite-only preview requires every P0 software gate, independent adversarial review, the protected
live drill, measured unit economics, monitoring, rollback, and a deliberate action-time release
decision.
