# Browser control matrix guard release — 2026-09-09

## Outcome

Ask Crump's complete credential-free browser control sweep is now one fail-closed command instead
of a manually assembled release step. The repository already had 34 focused browser verifiers, but
their different local roots and ports made it possible for a future release to run only a familiar
subset without noticing that a verifier had been added or omitted.

`npm run test:browser-controls` now:

- locks the exact reviewed inventory of **34** browser verifier programs;
- fails if a verifier is added, removed, or renamed without an explicit matrix review;
- starts and owns the five required repository/public static origins on ports 4173, 8765, 8766,
  8767, and 8770;
- normalizes the three historical browser-executable variable names used by existing verifiers;
- bounds every verifier to a two-minute execution window;
- runs the paid-plan timing repeat at one case per plan and viewport while preserving its separate
  full timing-grid verifier; and
- always stops the local server processes after success or failure.

The matrix covers primary navigation, Chats, Create handoffs, Projects, generated-output save/open,
Files and viewers, image stability and precision editing, Video/reference images, Library,
Settings, plans/credits, account entry and recovery, lifecycle/referral recovery, campaign
attribution, guide starts, and close/back/retry states.

## Verification

- Browser control matrix: **34/34** verifier programs passed in one command.
- Button integrity: **21/21** focused checks passed.
- Complete Python suite: **928 collected**, **926 passed**, two environment-dependent skips.
- JavaScript integration contract: **49 files** and **6/6** attribution cases passed.
- Ruff, Python compilation, production preflight, native web build, and diff integrity passed.
- Feature commit: **4bc068c2314aee987f1205cef5f8183829064d91**.
- Main CI **34373041386**, Android Store Bundle Verification **34373041395**, and iOS Store Source
  Verification **34373041371** passed.

## Safety and production boundary

The sweep uses fictional local fixture state and contains no credentials. Destructive, account,
checkout, download, and provider-backed generation actions remain isolated behind confirmation or
recovery fixtures. The marketing preload verifier reads the public analytics runtime but intercepts
its event delivery locally; no production account, analytics event, content, Project, file,
generation, setting, credit, checkout, payment, or customer record was created or changed.

Automatic production deployment **dpl_6z7YiJqk6CH6rZTG3sbBkAZi3TTm** is READY on all six aliases
with no alias error and contains only the new release guard, package command, and tests;
customer-facing application bytes are unchanged. All four Ask Crump/Clever Crump custom-domain
health endpoints returned HTTP 200. The initial runtime-error aggregate was empty and the exact
deployment returned only successful runtime traffic during inspection. Signed physical
iPhone/Android interaction, real provider responses, real permissions, and legitimate customer
data states remain their separate acceptance boundaries.
