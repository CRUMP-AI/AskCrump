# Event-driven credit-balance refresh

Date: 2026-08-29  
Behavior commit: `413a136`  
Production deployment: `dpl_Bnfx2Ekf22ZBdPJnTBdA6MrppGph`

## Accountable outcome

Ask Crump no longer calls the credit-status endpoint once per minute merely because an
authenticated tab is visible. The sidebar balance now updates from exact balances already returned
by usage checks, successful AI responses, and purchase events. A returning tab performs one
coalesced status refresh only when its last known balance is at least five minutes old. Opening the
Plan & credits center still loads current billing, allowance, catalog, ledger, and subscription
state directly.

This removes an avoidable idle database and function request without weakening server-authoritative
credit accounting, checkout verification, usage enforcement, cross-device correction, or native
purchase restoration.

## Production evidence that selected the work

The trailing 24-hour Vercel aggregate contained 8,664 HTTP 200 responses. The largest application
paths included 3,054 sync pulls, 1,468 sync pushes, 1,440 scheduled manuscript checks, and 520
credit-status requests. The narrower preceding hour contained 57 credit-status requests, closely
matching the prior one-per-minute visible-tab timer. The previously corrected sync volume spans
many deployments and active release checks, while the billing source contained an explicit
60-second loop. That made the billing loop the deterministic, independently removable defect.

These are aggregate operational counts. They do not establish unique users, conversions, revenue,
or customer behavior.

## Corrected contract

- One balance request may run at a time.
- Startup and repeated authenticated-readiness signals coalesce.
- Usage preflight, successful chat completion, and recovered chat completion dispatch the exact
  server-returned balance without another request.
- Credit-purchase events update the badge immediately.
- Focus or visibility return refreshes only after a five-minute staleness boundary.
- There is no recurring billing-status interval.
- Plan Center continues to hydrate current billing state when opened.
- Invalid event data fails closed to one forced authoritative refresh.

No account, payment, checkout, credit transaction, prompt, message, artifact, Project, or synthetic
analytics event was created for this release.

## Verification

- All 483 Python tests passed.
- All 45 JavaScript files passed the repository validation contract.
- Production preflight passed.
- The native web bundle regenerated successfully.
- Store metadata source checks passed.
- A real browser fixture proved:
  - one startup status request and a 12-credit badge;
  - duplicate authenticated-ready and visible-return signals produced no additional request;
  - a server-derived balance event changed the badge to 41 credits without a request;
  - a return inside five minutes produced no request;
  - a return after the staleness boundary produced exactly one request and the new 22-credit
    server balance;
  - no browser warning or JavaScript error.
- Canonical health, the versioned billing asset, the chat transport, the runtime loader, and service
  worker returned HTTP 200 with the exact release markers.
- Deployment `dpl_Bnfx2Ekf22ZBdPJnTBdA6MrppGph` reached `READY`.
- Its initial inspected runtime window contained two HTTP 200 responses, no runtime error group, and
  no warning/error/fatal log.

## Observation boundary

Reconcile `/api/billing/credits/status` after a complete 24-hour window. Compare requests per
authenticated active period rather than raw traffic alone because this release window included
many deployments and owner-operated verification sessions. Treat the release as delivered now;
claim a realized request reduction only after that elapsed aggregate is available.
