# Autonomous Crump activation candidate

Date: 2026-09-16

Production base: `7833d89e2e5ee419fd27757f82c4fff92beed295`

Branch: `candidate/crump-code-activation-20260916`

## Outcome

The disabled coding-agent foundation now has a customer-facing name and a review experience that
more closely matches the standard expected of a serious autonomous coding workspace. The visible
product is **Autonomous Crump**. Stable implementation contracts remain `crump_code`,
`code_workspace`, `/api/code/**`, `CRUMP_ENABLE_CODE_WORKSPACE`, the existing database objects, and
the existing source filenames.

This candidate does not enable, advertise, push, deploy, purchase, provision, charge, or call a
live provider. Both independent compute stops remain closed: the checked-in
`CODE_WORKSPACE_PUBLIC_RELEASED` lock is `False`, and no operator environment switch was changed.

## Customer experience advanced

- The gated destination uses the short visible rail label **Autonomous**, with the full accessible
  label **Autonomous Crump** and the locked label **Autonomous Crump — Professional plan**.
- The workspace, gated plan policy, API error copy, model persona, default result copy, and
  downloaded patch filename use the new customer brand. Always-loaded billing does not mention or
  price the disabled feature.
- A five-stage, Project-backed progress view distinguishes Prepared, Accepted, Working, Verifying,
  and Review required without inventing a percentage or implying that a result is safe to apply.
- The active view states that the private worker continues if the user closes the window or explores
  elsewhere. A failed status refresh now shows a truthful reconnecting state, uses bounded backoff,
  and immediately reconciles on browser visibility or online recovery.
- Completed implementations expose a file-scoped diff console, changed-file count, addition and
  deletion totals, per-file navigation, added/removed/hunk highlighting, and the existing complete
  `.patch` download.
- Verification rows expose the exact recorded command, pass/fail result, and bounded recorded output
  in expandable controls. No verification claim is manufactured by the client.
- A late Project or task response can no longer replace the current selection; local browser proof
  delays Project A and Task A while selecting faster Project B and Task B, then proves run and cancel
  target only Task B.
- The complete patch is rejected rather than truncated or rewritten. Protected paths, symlink reads,
  incomplete reads, incomplete listings, history-oriented Git commands, and verification-created
  mutations fail closed before a patch can be presented.
- Public repository contents and check output may be sent to the configured coding model. The UI now
  states that no Ask Crump/account credentials are injected and instructs people to use only source
  they are authorized and prepared to share.
- The button inventory now explicitly owns the new diff-file control, raising the locked programmatic
  inventory from 94 to 95 and the total reviewed button inventory from 276 to 277.

## Activation decision gate

`scripts/verify_autonomous_crump_activation.py` is an offline, fail-closed decision tool. Its normal
run executes the existing Sandbox dry contract and the fixed orchestration benchmark, validates the
two-stop source boundary, validates the lazy-load and review-console proofs, and emits a bounded JSON
receipt. It reports separate fields for `localSourceChecksPassed`, `sourceCandidateReady`,
`liveEvidenceChecklistSatisfied`, `trustedLiveAttestationVerified`, and `publicActivationReady`.
It also requires a resolved full Git revision and a clean tracked/untracked source tree, so live
evidence cannot accidentally authorize a dirty checkout that differs from its recorded revision.

The verified local receipt reported:

- `localSourceChecksPassed=true` after a clean committed-tree run;
- `sourceCandidateReady=false` because documented P0 activation holds remain;
- `publicActivationReady=false`;
- zero verifier network requests, model calls, database writes, or provider spend;
- Sandbox dry receipt: pinned `octocat-hello-world` revision, deny-all networking, five fixed
  non-sensitive test/runtime-hardening environment variables, non-persistent workspace, destruction
  enabled, no customer data, and no live-run authorization;
- fixed offline benchmark: 4/4 cases passed, mean score 100 against threshold 90.

`--require-public-activation` fails closed unless a fresh, exact-revision, content-free live evidence
object satisfies every OIDC, isolation, destruction, cancellation, expiry, refund, monitoring,
rollback, repeatability, holdout, cost-envelope, and operator-decision field. Even checklist-perfect
self-authored JSON cannot authorize activation: trusted owner-signature verification and a reviewed
source decision are deliberately unimplemented. The evidence parser rejects credential-, token-,
key-, password-, and secret-named fields.

## Local feature-status proof

The real loader and workspace assets were exercised in Edge without a product account or production
request:

- disabled: two destinations remained hidden; the 33 KB workspace script and 13 KB stylesheet were
  not fetched or constructed;
- configured but not entitled: both destinations became visible and locked with the full
  Professional-plan accessible label;
- configured and entitled: both destinations became visible and available with the full accessible
  name;
- each configured branch loaded the workspace script and stylesheet exactly once;
- the new review console passed axe at 1280×760 and 390×844 with two-file selection, exact `+3/−1`
  totals, expandable passing verification output, no horizontal shell overflow, and no browser error;
- a forced status-read interruption showed **Reconnecting**, retained the last durable activity,
  recovered through the online event, progressed through Verifying, and rendered the completed diff.

## Validation

- Complete Python suite: **1,183 passed, 1 host-permission symlink fixture skipped**.
- Focused Autonomous Crump / internal Code suite: **98 passed, 1 host-permission symlink fixture
  skipped**.
- JavaScript integration contract: **54 files passed**.
- Fail-closed browser-control inventory: **49/49 passed**.
- Public accessibility matrix: **33/33 passed**.
- Offline orchestration benchmark: **4/4**, mean **100/100**.
- Sandbox smoke harness: dry-run only, exact safety receipt passed.
- Ruff and Python compilation passed.
- Production build preflight, native web-bundle construction, and client credential scan passed.
- Git diff whitespace integrity passed.

## Naming boundary

Customer-facing runtime strings in the feature workspace, loader, navigation, plan policy, API
errors, and runner persona no longer contain the retired customer name. Always-loaded billing
contains neither the old nor new feature price while it is disabled. An executable inventory guard
scans public billing, landing pages, sitemaps, onboarding, store listing, and marketing guides; it
also confines the full current brand to the gated runtime assets. The intentional legacy references
are internal identifiers and file
paths (`crump_code`, `code_workspace`, `/api/code`, `crump-code-*`, database and environment names),
historical dated evidence, and the current runbook's one migration note:
**Autonomous Crump (formerly Crump Code; internal identifier `crump_code`)**.

Landing pages, sitemap, store listing, onboarding, and marketing were not changed and do not teach
the still-disabled destination.

## Remaining live-only gates

Public activation is still held until all of the following are implemented or recorded against the
exact reviewed source revision:

1. one service-role Postgres transaction that locks the task, validates the pinned SHA, atomically
   consumes included allowance or credits, persists the exact receipt and owner token, transitions
   to provisioning, and records one claimed event; replay must return that retained result;
2. owner-token-bound atomic refund settlement, database invariants, worker receipt verification, and
   real concurrent Postgres crash-window tests for both included allowance and credits;
3. per-user active-task, global queue/concurrency, daily model/Sandbox budget circuit breakers, and
   fair scheduling so code work cannot starve other durable jobs;
4. a reviewed first-preview policy for project-controlled verification scripts and model-visible
   output;
5. one owner-approved, one-cent-maximum public-fixture Sandbox/OIDC drill plus live deny-all network,
   fixed safe environment, destruction, cancellation, expiry, refund, monitoring, and rollback proof;
6. repeatable provider runs with holdouts, measured mean/p95 latency, actual mean/p95 unit cost, and
   an approved sustainable credit envelope;
7. an owner-controlled signed-attestation verifier, explicit activation decision, and separate
   reviewed change that opens both independent release controls.

Until those gates pass, the truthful state is: local checks pass, source activation is held, and
public activation is not ready.
