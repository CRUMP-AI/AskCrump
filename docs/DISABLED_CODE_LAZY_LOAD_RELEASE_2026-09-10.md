# Disabled Crump Code lazy-load release — 2026-09-10

## Decision

Keep Crump Code behind its existing server-authoritative configuration and entitlement gate,
but stop making every authenticated user download, parse, and initialize the unavailable private
preview during ordinary workspace startup.

This is a delivery change, not a Crump Code launch. The feature remains disabled and no parity,
quality, provider, cost, Sandbox, or public-readiness claim is created by this release.

## Previous contradiction

The Code destination was correctly hidden unless the backend reported a configured provider, but
the authenticated runtime still treated the full preview as boot-critical:

- `crump-code-5.9.35.js`: 33,121 raw bytes in the release candidate;
- `crump-code-5.9.35.css`: 13,177 raw bytes; and
- a static Code workspace shell was constructed even when the server gate remained closed.

The disabled path therefore paid for 46,298 raw bytes of unreachable UI. The service worker also
pre-cached those same assets for every installed workspace.

## Released behavior

Commit `03ca7f0` replaces those two boot-critical assets with the 4,573-byte
`crump-code-loader.js` gate:

1. the signed-in runtime asks the existing `/api/features` authority whether Code and its provider
   are configured;
2. an unconfigured response keeps both desktop and mobile destinations hidden and requests neither
   full Code asset;
3. a configured response loads the stylesheet and script exactly once, then applies the returned
   entitlement state only after both are ready;
4. a configured but unentitled account sees the existing Professional-plan boundary;
5. an entitled account sees the existing destination; and
6. the full workspace still rechecks authority before an explicit open or metered action.

The ordinary authenticated plan now loads 20 styles instead of 21. It still loads 33 scripts
because the small gate replaces the full Code script, but it avoids 41,725 raw source bytes,
eliminates one initial stylesheet request, and does not construct the hidden Code workspace.
The native runtime uses the same plan. The PWA pre-cache includes the gate and no longer installs
the unavailable workspace assets.

Load failure is fail-closed: the destination stays hidden, partially inserted lazy assets are
removed, and a later bounded retry can start cleanly.

## Automated proof

The new real-browser verifier exercises three credential-free local server responses:

| Server state | Full Code JS | Full Code CSS | Destination result |
| --- | ---: | ---: | --- |
| Disabled | 0 requests | 0 requests | hidden on desktop and mobile |
| Configured, not entitled | 1 request | 1 request | visible and plan-locked |
| Configured and entitled | 1 request | 1 request | visible and unlocked |

Every state made exactly one initial feature-authority request, retained no bootstrap status on the
page, and produced zero console or page errors. The verifier is the required 41st member of the
fail-closed browser matrix.

Release validation:

- complete Python suite: 998/998 passed with the repository-pinned FastAPI 0.116.1 contract;
- JavaScript inventory and integration contract: 50 files passed;
- real-browser control/performance matrix: 41/41 passed;
- Python compilation and Ruff: passed;
- production preflight, native web build, and client-credential boundary: passed;
- GitHub CI `34522511218`: passed;
- Android source/bundle verification `34522511160`: passed; and
- iOS source verification `34522511224`: passed.

No store submission or store-account readiness claim is made.

## Production acceptance

Production deployment `dpl_CzFUbzsH8Rx5kG2KBYumwGb7DjuT` reached `READY` on all six expected
aliases. Direct production reads returned exact SHA-256 parity for the committed app shell,
workspace runtime, Code gate loader, navigation runtime, and service worker. `/api/health` returned
HTTP 200 with version 5.9.76.

A signed-in canonical workspace reload then showed:

- both Code destinations hidden and unlocked-state styling absent;
- the small `crump-code-loader.js` script present;
- no `crump-code-5.9.35.js` script;
- no `crump-code-5.9.35.css` stylesheet; and
- no constructed Code workspace shell.

The first 30-minute production scan contained no grouped runtime error and the exact deployment had
no warning, error, or fatal log.

## Remaining boundary

This release improves deterministic startup work. It does not prove a field Speed Insights lift,
activation lift, retention lift, or revenue lift. Keep the feature disabled until its existing live
Sandbox/OIDC/model/cost/cancellation/rollback/approval gates pass, and remeasure workspace field
performance only after a comparable denominator exists.
