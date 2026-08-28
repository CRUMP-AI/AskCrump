# Crump Code review workspace release — 2026-08-27

Release: 5.9.35 / native build 50935  
Code commit: `018b46cf8a53889549f68092300ebbb504c4189b`  
Production deployment: `dpl_GjeFNqmhK32QeyQyXKLrDoePxViu`

## Outcome

Ask Crump now has a human-visible Crump Code review workspace attached to Projects. The interface
can prepare a task against the root of a public GitHub repository, show the selected repository,
revision, mode, objective, time and cost boundaries, and render task status, pending approvals,
verification results, activity history, summary, and downloadable patch.

Preparing and running are separate commitments. Preparing stores the owner-scoped task but does
not start a model, provision a sandbox, or charge credits. The run control remains disabled until
the user checks the final review statement, and the server independently rejects a run whose JSON
body does not contain `confirmed: true`.

The Create entry ships hidden. It is revealed only when the authenticated `/api/features` response
reports that `code_workspace` and its provider are configured and the current account is entitled.
The production feature configuration was not changed during this release, so the public feature
remains off.

## Safety and trust boundary

- public `https://github.com/{owner}/{repository}` roots only; no embedded credentials, query,
  fragment, subdirectory, private repository, or alternate Git host
- ephemeral two-vCPU/four-GB sandbox, destroyed at the end of the bounded run
- empty environment, no customer or project secrets, and deny-all network after repository checkout
- bounded inspection, text edits, verification allowlist, model/tool steps, output, patch, and time
- no dependency installation, publishing, deployment, Git push, or source-repository writeback
- result summary, verification, patch, and content-free audit events presented for human review
- pending approval decisions rendered explicitly rather than silently expanding a task boundary
- concurrent cancellation checked before every next model and tool step; the task record remains
  cancelled and the usage receipt is refunded through the existing failure path

The current runner does not request a live boundary expansion, and approving a future request can
only requeue the task for another explicitly confirmed bounded run. It does not itself grant
credentials, publish, push, or change the deny-all production configuration.

## Verification

### Local and automated

- All 313 application tests passed, including canonical repository validation, private-schema and
  service-role boundaries, sandbox isolation, verification allowlists, server confirmation, and
  cancellation-before-next-step coverage.
- Ruff passed across the backend, application entry point, and tests.
- All 42 JavaScript files passed syntax and new-body integration validation.
- Production build preflight and the native web-bundle build passed.
- Android source regenerated and passed the 5.9.35/build 50935/API 36 verifier.
- Store metadata and tracked signing-secret controls passed. The known missing RevenueCat Android
  public key, `google-services.json`, signing credentials, and physical-device/store-console gates
  remain unresolved and were not bypassed.

### Browser contract

A local fixture replaced all product requests with explicit mock responses and contained no
production hostname. It created no account, product event, provider call, sandbox, or charge.

- With the feature response disabled, the Crump Code Create entry was not visible.
- With configured and entitled mock responses, the Project-attached workspace opened and rendered
  the safety boundary, completed result, passed verification, reviewable patch, and activity history.
- A queued task showed the exact cost boundary, and `Run isolated task` remained disabled until the
  review checkbox was selected.
- The dialog exposes a labeled modal, Escape close, focus containment, polite status region,
  visible focus styles, reduced-motion handling, and 16-pixel mobile form controls.

### Hosted and production

- Main CI run `33134659887` passed.
- Android Store Bundle Verification run `33134659984` passed.
- iOS Store Source Verification run `33134659934` generated, verified, and compiled the unsigned
  5.9.35 candidate without signing credentials or upload; every job step passed.
- Vercel deployment `dpl_GjeFNqmhK32QeyQyXKLrDoePxViu` reached `READY` and owns the four canonical
  production aliases.
- Production health returned HTTP 200 and version 5.9.35 with `no-store`.
- The app, runtime loader, Crump Code JavaScript/CSS, navigation, and service worker returned 200.
  The runtime and cache contain the new assets, the navigation source contains the hidden slot, and
  the workspace source contains the configured/entitled gate plus confirmed-run request.
- The inspected deployment window contained no runtime error cluster, no 5xx response, no
  warning/error/fatal log, and no `/api/code` runtime request.

## Remaining activation gates

This release proves delivery of the human review surface, not production coding-agent quality.
Crump Code remains disabled until all of the following are complete:

1. owner-approved sub-cent live sandbox smoke test using a harmless public repository;
2. production Vercel OIDC identity proof and explicit rollback exercise;
3. live cancellation and expiry behavior observed without an orphaned sandbox or charge;
4. a real pending-approval scenario verified against the intended boundary semantics;
5. failure monitoring and a fixed end-to-end benchmark covering planning, implementation,
   verification quality, patch usefulness, safety, cost, and latency;
6. a written activation decision with no Codex or Claude Code parity claim unless measurements
   support it.

## Rollback

The first rollback control is the existing server-side `CODE_WORKSPACE_ENABLED` flag, which remains
off. If the dormant client layer itself causes a regression, restore production deployment
`dpl_9se9uqzQ3mn4HYAYXRzzNec8ijG9` or revert commit `018b46c`. Neither rollback requires deleting a
customer task or changing a payment, account, schema, or provider credential.
