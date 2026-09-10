# Ask Crump daily operating review — 2026-09-10

Review time: 21:19 UTC

Scope: production reliability, account/activation evidence, durable work, and
revenue-boundary reconciliation

Privacy boundary: aggregate counts only; no prompt, response, filename, email,
referrer URL, or customer content was read

## Executive decision

The product is healthy, but the verified business bottleneck remains qualified
acquisition into a complete continuing-work journey. Do not redesign the stable
entry surface, add redundant controls, alter pricing, or scale paid traffic in
response to an empty comparable cohort.

The next product change should be triggered by one of two authoritative signals:

1. a legitimate post-September account reaches or drops from the measured
   account → activation → Project/file → return journey; or
2. a reproducible customer/tester defect identifies a broken boundary in that
   journey.

Until one of those signals exists, preserve the current release and keep the
product team focused on reliability and evidence rather than feature volume.

The safe delivery improvement completed after this review preserves every
Projects, Files, Manuscripts, Video, Library, and continuity action while moving
the full Product Studio off a clean authenticated startup. A clean workspace now
avoids 170,040 raw source bytes and one stylesheet until that capability is
needed. The cache-safe production release passed 1,003 product tests, 54
JavaScript validations, and all 45 browser-control verifiers; the signed-in live
replay opened Projects on first use and Video on reuse. This is deterministic
delivery evidence, not a field-speed or customer-outcome claim.

## Production health

The latest 24-hour Vercel production aggregation reported:

| Status | Requests | Interpretation |
| --- | ---: | --- |
| HTTP 200 | 2,241 | Successful application/API responses |
| HTTP 302 | 20 | Normal redirects; no error classification |
| HTTP 401 | 1 | One `/api/features` request without an authenticated session |
| HTTP 404 | 1 | One `/api/version` request; no application route depends on it |
| HTTP 429 | 0 | No observed capacity/rate-limit response |
| HTTP 5xx | 0 | No observed server/provider failure response |

The same window contained no grouped runtime error, HTTP 429, or HTTP 5xx signal.
This proves a clean observed window, not provider quality or future uptime.

The complete seven-day production Web Analytics view reported 20 visitors, 109
page views, and 30% bounce. Its full event list contained three `MarketingCTA`
visitors, two `CreationIntentContinued`, two `MarketingExplore`, two
`MarketingLanding`, and one `PlanIntentReached`. No signup event appeared in the
complete list. These anonymous counts can include internal or automated traffic;
they diagnose discovery and intent only and are not an account conversion rate.

A fresh release-window log sample contained 50 visible requests, all HTTP 200,
with zero warning, error, or fatal entries. This narrower read validates the latest
control release; it does not replace the 24-hour aggregation above.

## Product and journey evidence

The current database reconciliation reports:

| Measure | Verified count |
| --- | ---: |
| External accounts | 3 |
| Verified external accounts | 2 |
| Comparable September production accounts | 0 |
| External active paid accounts | 0 |
| Comparable activation accounts | 0 |
| Comparable durable-value accounts | 0 |
| Comparable return accounts | 0 |
| Comparable artifact journeys | 0 |
| Comparable lifecycle rows | 0 |

The 21:19 UTC service-role refresh returned all 18 comparable growth stages at
zero and empty weekly-attribution, artifact-journey, and Project-continuity exports.
The three legacy external accounts still include two verified accounts, zero
September logins, and zero active provider-backed payers. The fixed sanitized demo
identity does not exist. A corrected live lookup confirmed that
`demo_recording_proof_snapshot()` is installed, stable, security-invoker, empty
search-path, denied to public/anonymous/authenticated roles, and executable by
service role. Its seven fixed proof booleans are all false because no completed
sanitized demo journey exists. Account provisioning and the real recorded journey
remain explicit operator gates rather than customer metrics.

Internal production testing since September 1 recorded one activation, one aha
signal, two artifact downloads, six recent-work resumes across two internal
accounts, eight workspace opens, and five outcome-feedback submissions. Those
events show that the instrumented controls can fire; they are not customer,
conversion, retention, or product-market-fit evidence.

## Revenue boundary

The product database reports zero active external paid accounts. Direct live
Stripe reconciliation could not be refreshed because the connected Stripe
session requires reauthentication. The last verified Stripe baseline remains
`$0`, but this review does not present that older value as a current live balance
or recognized-revenue confirmation.

Do not change pricing, discounts, quotas, or plan positioning from this partial
financial view. Refresh Stripe receipts, refunds, active subscriptions, and
recognized revenue after connector access is restored or another authoritative
finance export is available.

## Current product backlog

| Priority | Item | Trigger / acceptance evidence |
| --- | --- | --- |
| P0 | Observe the first comparable account journey | Legitimate content-free AccountCreated through activation, durable value, and eligible return |
| P0 | Repair any first-user blocker | Reproducible customer/tester defect with browser/API evidence and regression coverage |
| P1 | Produce sanitized writing/refinement capture | Internal fidelity already passed 14/14 facts and 20/20 verification; public proof still requires the protected demo identity and content-free readiness receipt |
| P1 | Reconcile first payer end to end | Checkout, entitlement/credits, Stripe receipt, refund state, and variable cost agree |
| P2 | Advance Crump Code/private voice only behind existing gates | Sandbox, cancellation, monitoring, policy, cost, disclosure, and benchmark evidence |

## Actions and non-actions

- Closed the remaining vague-action gap across Projects, Files, Manuscripts,
  Video, and Library in commit `f86fad8`. The shared close control now identifies
  the visible destination or named Project, Files refresh and Video reference are
  explicit, and manuscript-run and section controls include their active title.
  The complete suite passed 1002/1002, JavaScript 53/53, browser matrix 44/44,
  CI `34535247208`, Android `34535247232`, and iOS `34535247234`. Production
  deployment `dpl_8pNsm1VvmB7ztyms1Mipcyac31k4` is Ready; four live release
  files returned HTTP 200 with their expected markers, signed-in replay proved
  Projects, Files, new Project, Video, Manuscripts, and Library without saving or
  generating, and the filtered release window contained zero warning/error/fatal
  entries. No customer content or identifier was recorded.
- Extended the whole-product control boundary through its first-party API handoff
  in commit `d47e1ce`. CI now inventories 97 raw browser API references across
  27 public source files, normalizes 84 request-path shapes, and requires every
  destination to match the real FastAPI route table. The dynamic manuscript-run
  action remains exactly Pause/Resume/Cancel. The new contract passed 2/2; the
  complete suite passed 1001/1001, JavaScript 53/53, the browser matrix 44/44,
  and CI `34533414320`. Test-only deployment
  `dpl_HJfjonWvDKAAJCeH2mzcSaCBaGeD` is Ready. No public app byte, database,
  account, provider, payment, credential, or customer-content state changed.
- Rechecked the only last-day non-success requests. `/api/version` produced one
  404 but has no first-party caller or product dependency; `/api/features` exists
  and produced one expected unauthenticated 401. Neither justifies a product route
  or authentication change.
- Received the API team's isolated v0.127.0 source-candidate handoff at commit
  `98da9c9c6230bcbb8d38388a5552c44ba6cdd1ae`. It remains experimental and
  undeployed; Ask Crump's production API pin remains v0.49.1. No candidate route,
  SDK, realtime-voice behavior, provider credential, shared table, or claim was
  integrated into the app from that handoff.
- Made conversation actions specific and keyboard-safe in product commits `5939014`
  and `6d76a2c`. Rows, three-dot triggers, menus, Rename, and Delete now identify
  the exact conversation; the trigger exposes expanded state; focus enters Rename;
  and Escape closes only the action menu, restores its trigger, and leaves Chats
  open. The fail-closed inventory remains 276 controls. The complete suite passed
  999/999, JavaScript 53/53, and the required browser matrix 44/44; CI
  `34530272347`, Android `34530272376`, and iOS `34530272346` all passed.
  Production deployment `dpl_Fa9KwgWHh75T27maHNJoWKRRgfiV` is Ready with four
  exact-byte checks, signed-in focus/state/sidebar proof, HTTP 200 release traffic,
  and zero warning/error/fatal entries. No conversation was renamed or deleted.
- Received the API team's isolated v0.126.0 candidate handoff and preserved Ask
  Crump's stable production API pin at v0.49.1. No API integration, provider,
  credential, shared-table, or production API change was made in this release.
- Completed the whole-product control gate and removed unused Library startup work
  in product commit `73c3829`. The fail-closed inventory covers 182 rendered plus
  94 programmatic controls, and the complete real-browser matrix passed 43/43.
  The authenticated plan now loads a 6,376-byte media-save module and 4,312-byte
  Library loader instead of the prior 65,362-byte Library script plus 37,386-byte
  stylesheet, avoiding 92,060 raw bytes and one startup style until Library is
  chosen. All 998 Python tests, 53 JavaScript files, production/native/credential
  gates, and all three GitHub workflows passed. Production deployment
  `dpl_GumgE795YnTj7saXj31JwewG7DUy` is Ready; six exact-byte checks passed,
  signed-in first Library entry loaded the bookshelf once and restored its controls,
  Grid/Book/List and all six main destinations responded, and the inspected release
  log contained only HTTP 200 responses with zero warning/error/fatal entries.
  Paid, destructive, provider, permission, upload, download, external-message, and
  physical-device outcomes retain their separate action-time gates.
- Revalidated the complete shipped control boundary and removed unused Precision
  Edit startup work in product commit `1345449`. The authenticated plan now loads
  a 3,379-byte on-demand gate instead of the 78,537-byte editor script plus
  17,650-byte stylesheet, avoiding 92,808 raw source bytes and one startup style.
  The complete suite passed 998/998, JavaScript 51/51, the expanded browser matrix
  42/42, and all three GitHub workflows. Production deployment
  `dpl_5EG2rm1YxGXR9tfNXHLf5ioTq9XA` is READY on six aliases with five exact-byte
  checks, stable signed-in activation of cache `r230`, safe live movement through
  all six main destinations, only the small Precision loader present before use,
  and no release-window runtime error, 5xx, or severe log. Paid, destructive,
  provider, download, permission, external-message, and physical-device outcomes
  retain their separate action-time gates.
- Removed deterministic startup work from the disabled Crump Code preview in
  product commit `03ca7f0`. The signed-in runtime now loads a 4,573-byte gate
  instead of the full 33,121-byte script plus 13,177-byte stylesheet. A real
  browser proved zero full-asset requests while disabled and exact one-time
  loading for configured locked and entitled states. The complete suite passed
  998/998, JavaScript 50/50, the browser matrix 41/41, and all three GitHub
  workflows. Production deployment `dpl_CzFUbzsH8Rx5kG2KBYumwGb7DjuT` is READY
  with five exact-byte checks, live signed-in disabled-state proof, healthy API,
  and no release-window runtime error or severe log. Crump Code remains disabled;
  this is a startup-delivery improvement, not a feature-readiness claim.
- Corrected a deterministic returning-load performance defect in product commit
  `753cc65`. Production response headers require revalidation for representative
  workspace JS/CSS, but the previous service worker also routed all 43
  boot-critical path classes through network-first after pre-caching them. Cache
  revision `r228` now keeps the shell and main app controller fresh while serving
  the remaining installed boot files cache-first. A new real-browser gate proves
  zero second-load origin requests for representative runtime JS and CSS while
  the shell still revalidates exactly once. The complete suite passed 997/997,
  the browser matrix 40/40, all three GitHub workflows passed, and production
  deployment `dpl_81jjQfD1J4zfZaXHavLrqamRW2eX` is READY with exact-byte service
  worker parity and no release-window runtime error or severe log. This is a
  delivery fix, not yet a claimed field-score improvement.
- Added a fail-closed public-reference guard in product commit `225cecd`.
  It inventories 447 static first-party link/asset references across 15 public
  HTML surfaces, verifies their local route/file/fragment targets, and requires
  explicit review when the inventory changes. A separate read-only production
  sweep resolved all 67 unique first-party destinations with HTTP 200 and no
  failed destination. The complete suite passed 986/986; CI run `34502052022`
  passed; deployment `dpl_BvuzsiqAgeLWNTDV65hK7ZEB3ydN` is READY on all six
  expected aliases. No public product byte changed because the release adds a
  regression guard only.
- Reconciled the protected recording identity without reading or returning any
  customer content. `demo@askcrump.com` does not currently exist, so it neither
  contaminates customer metrics nor satisfies the sanitized public-proof gate.
  The existing founder-account writing result remains valid internal evidence
  only; it cannot be used as public creative.
- Confirmed that the protected September production funnel and artifact snapshot
  still contain zero external accounts and zero external artifact rows. This
  keeps qualified acquisition—not another speculative interface change—as the
  binding company constraint.
- Preserved the current landing and product hierarchy.
- Kept paid acquisition at `$0` from the product decision boundary.
- Made no account, checkout, price, quota, billing, provider, campaign,
  Search Console, or customer-data change.
- Left the full company mission active; the verified gap remains materially open.
