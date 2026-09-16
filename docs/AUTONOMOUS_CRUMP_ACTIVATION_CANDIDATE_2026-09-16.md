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
- The workspace, plan label, API error copy, model persona, default result copy, billing disclosure,
  and downloaded patch filename use the new customer brand.
- A five-stage, Project-backed progress view distinguishes Prepared, Accepted, Working, Verifying,
  and Ready to review without inventing a percentage.
- The active view states that the private worker continues if the user closes the window or explores
  elsewhere. A failed status refresh now shows a truthful reconnecting state, uses bounded backoff,
  and immediately reconciles on browser visibility or online recovery.
- Completed implementations expose a file-scoped diff console, changed-file count, addition and
  deletion totals, per-file navigation, added/removed/hunk highlighting, and the existing complete
  `.patch` download.
- Verification rows expose the exact recorded command, pass/fail result, and bounded recorded output
  in expandable controls. No verification claim is manufactured by the client.
- The button inventory now explicitly owns the new diff-file control, raising the locked programmatic
  inventory from 94 to 95 and the total reviewed button inventory from 276 to 277.

## Activation decision gate

`scripts/verify_autonomous_crump_activation.py` is an offline, fail-closed decision tool. Its normal
run executes the existing Sandbox dry contract and the fixed orchestration benchmark, validates the
two-stop source boundary, validates the lazy-load and review-console proofs, and emits a bounded JSON
receipt. It reports separate fields for `sourceCandidateReady` and `publicActivationReady`.
It also requires a resolved full Git revision and a clean tracked/untracked source tree, so live
evidence cannot accidentally authorize a dirty checkout that differs from its recorded revision.

The verified local receipt reported:

- `sourceCandidateReady=true`;
- `publicActivationReady=false`;
- zero verifier network requests, model calls, database writes, or provider spend;
- Sandbox dry receipt: pinned `octocat-hello-world` revision, deny-all networking, empty injected
  environment, non-persistent workspace, destruction enabled, no customer data, and no live-run
  authorization;
- fixed offline benchmark: 4/4 cases passed, mean score 100 against threshold 90.

`--require-public-activation` fails closed unless a fresh, exact-revision, content-free live evidence
object satisfies every OIDC, isolation, destruction, cancellation, expiry, refund, monitoring,
rollback, approval-boundary, repeatability, holdout, cost-envelope, and operator-decision field. The
evidence parser rejects credential-, token-, key-, password-, and secret-named fields.

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
- the new review console passed at 1280×760 and 390×844 with two-file selection, exact `+3/−1`
  totals, expandable passing verification output, no horizontal shell overflow, and no browser error;
- a forced status-read interruption showed **Reconnecting**, retained the last durable activity,
  recovered through the online event, progressed through Verifying, and rendered the completed diff.

## Validation

- Complete Python suite: **1,142/1,142 passed** (two dependency deprecation warnings only).
- Focused Autonomous Crump / internal Code suite: **78/78 passed**.
- JavaScript integration contract: **54 files passed**.
- Fail-closed browser-control inventory: **49/49 passed**.
- Public accessibility matrix: **33/33 passed**.
- Offline orchestration benchmark: **4/4**, mean **100/100**.
- Sandbox smoke harness: dry-run only, exact safety receipt passed.
- Ruff and Python compilation passed.
- Production build preflight, native web-bundle construction, and client credential scan passed.
- Git diff whitespace integrity passed.

## Naming boundary

Customer-facing runtime strings in the workspace, loader, navigation, plan policy, API errors,
runner persona, and billing disclosure no longer contain **Crump Code**. An executable inventory
guard enforces that boundary. The intentional legacy references are internal identifiers and file
paths (`crump_code`, `code_workspace`, `/api/code`, `crump-code-*`, database and environment names),
historical dated evidence, and the current runbook's one migration note:
**Autonomous Crump (formerly Crump Code; internal identifier `crump_code`)**.

Landing pages, sitemap, store listing, onboarding, and marketing were not changed and do not teach
the still-disabled destination.

## Remaining live-only gates

Public activation is still held until all of the following are recorded against the exact reviewed
source revision:

1. one owner-approved, one-cent-maximum, public-no-secret Sandbox/OIDC drill;
2. live deny-all networking, empty environment, automatic destruction, cancellation, expiry,
   refund reconciliation, monitoring visibility, and rollback timing;
3. one real pending-approval boundary scenario;
4. repeatable provider runs with separately injected holdouts, measured quality and latency, actual
   unit cost, and an approved sustainable credit envelope;
5. an explicit activation decision that deliberately opens the source release lock and operator
   environment switch in a reviewed release.

Until those gates pass, the truthful state is: source candidate ready, public activation not ready.
