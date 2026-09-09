# Checkout session recovery release — 2026-09-09

## Outcome

An expired Ask Crump session no longer turns a selected credit pack or subscription into a
dead-end error. When checkout returns `AUTH_REQUIRED`, the app closes the purchase modal,
explains that nothing was charged, and opens the existing sign-in path. After successful
authentication it reopens **Plan & credits** and focuses the exact selection the user made.

The app does **not** create a second checkout request, submit a purchase, or charge the user
automatically. The user must deliberately select the purchase action again after signing in.

## Evidence that selected the work

A bounded production review found no runtime-error cluster and no HTTP 5xx response. It did
contain four checkout-route HTTP 401 responses among seven total 401 responses and two 404
responses. A 401 is not proof of a lost purchase or provider failure, but it exposed a
deterministic interface gap: the previous client restored the purchase button and showed a toast
without carrying the user through reauthentication or preserving the selected product.

The privacy-safe production growth reports contained no comparable external account cohort for
this period. Conversion or revenue lift therefore remains unproven.

## Delivered behavior

- `billing-manager.js` stores one allowlisted recovery record in session storage: purchase kind,
  allowed selection, and capture time. It expires after 15 minutes and rejects future timestamps.
- Only `credits_50`, `credits_150`, `credits_400`, `professional`, and `enterprise` can be retained.
- `auth-controller.js` clears stale local session state before attempting sign-in and presents a
  checkout-specific, no-charge explanation.
- Credit and subscription checkout handlers preserve the server error code and hand
  `AUTH_REQUIRED` to the common reauthentication path.
- After `crump:authenticated-ready`, the exact allowed selection is reopened and focused with
  `preventScroll`; the recovery record is then consumed.
- No account identifier, card data, price, payment token, prompt, response, filename, or raw URL
  is stored by this mechanism.

## Executable verification

The 390×844 browser fixture covers `credits_150` and **Professional**. Each first checkout is
forced to return `401 AUTH_REQUIRED`; a deliberately delayed local-session clear proves login
cannot race stale-state removal. Each selection survives sign-in, reopens and receives focus.
Across both cases there are exactly two initial checkout requests and zero automatic retry
requests. The consumed recovery record is absent at the end, and the browser reports no console
or page error.

- Focused checkout recovery verifier: passed.
- Fail-closed browser matrix: **36/36** passed.
- Complete Python suite: **937 collected**, **935 passed**, two environment-dependent skips.
- JavaScript validation: **49 files** passed.
- Attribution registry/runtime validation: **6/6** passed.
- Ruff, compilation, production preflight, native web build, store metadata, native privacy
  source, and diff integrity: passed.
- Main CI: [34389267609](https://github.com/CRUMP-AI/AskCrump/actions/runs/34389267609), passed.
- Android bundle verification:
  [34389267684](https://github.com/CRUMP-AI/AskCrump/actions/runs/34389267684), passed.
- iOS source verification:
  [34389267605](https://github.com/CRUMP-AI/AskCrump/actions/runs/34389267605), passed.

## Production verification

- Feature commit: `45c5d4bca81b1e34da0e7cd096af7ed2ca978f54`.
- Vercel deployment: `dpl_H3hWMjkxGdxiVfVZHGmioJVkVawA`, READY on all six aliases with
  no alias error.
- All four custom-domain `/api/health` checks returned HTTP 200.
- The release probe returned HTTP 200 and served
  `5.9.76-checkout-session-recovery-1` with service-worker cache
  `ask-crump-new-body-v1-r227`.
- Exact production bytes matched the deployed local assets for the authentication, billing,
  credit checkout, subscription checkout, runtime loader, and service-worker files.
- A fresh 390×844 Edge session loaded the production app with a visible body and workspace,
  the exact release marker, and zero console or page errors.
- The post-deployment runtime-error query and deployment-scoped HTTP 5xx query were empty.

## Decision boundary

The deterministic recovery defect is fixed and production delivery is verified. This release
does not prove increased conversion, a completed provider checkout, or revenue. Keep the path
stable and observe a legitimate expired-session recovery followed by an explicit user checkout
and provider-confirmed completion before making a conversion claim.
