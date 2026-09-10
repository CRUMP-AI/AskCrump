# Browser API route-integrity release — 2026-09-10

## Outcome

Ask Crump's shipped browser controls can no longer point at a literal first-party API
destination that is missing from the actual FastAPI application without failing CI.
This extends the existing button-owner and real-browser interaction matrix through the
next boundary: the browser-to-backend route handoff.

## Fail-closed contract

`tests/test_public_api_route_integrity.py` reads every public JavaScript and HTML file,
discovers quoted and template-literal `/api/` destinations, normalizes query strings and
dynamic identifier segments, and compares them with the routes registered by the real
application factory.

The current reviewed inventory contains:

- **97** distinct raw browser API references;
- **84** normalized request-path shapes;
- **27** public source files containing those references; and
- one dynamic manuscript-run action family constrained to exactly Pause, Resume, and
  Cancel backend routes.

The raw-reference and source-file totals are pinned. An addition, removal, file move,
unmatched parameter shape, widened dynamic action, or missing backend route requires an
explicit test review instead of silently passing.

The service worker's bare `/api/` namespace classification is the only non-request
exception. A separately constructed `/api/files/` prefix passes only because it resolves
to a one-segment parameter route; broad prefix matching is not accepted.

## Production non-success classification

A read-only last-day log review found one HTTP 404 for `/api/version` and one HTTP 401
for `/api/features`. No public Ask Crump source references `/api/version`, and no product
route depends on it, so the single 404 is an unrelated probe rather than a dead control.
The feature route exists and requires authentication, so its lone 401 is the intended
protected-route boundary. No endpoint was added merely to turn either diagnostic into a
success response.

## Verification

- The new focused contract passed **2/2**.
- The complete Python suite passed **1001/1001**.
- JavaScript validation passed **53/53** files.
- The complete real-browser control matrix passed **44/44** using the supported local
  Edge executable after the bundled Chromium launcher returned a Windows `spawn UNKNOWN`
  environment error before running the first case.
- GitHub CI run **34533414320** covers the committed test on the repository runner.
- Commit **d47e1ce** deployed automatically as
  **dpl_HJfjonWvDKAAJCeH2mzcSaCBaGeD**, which is Ready. The change is a regression gate;
  no public application byte or database object changed.

## Boundary

Route existence does not claim successful provider generation, payment, permissions,
destructive confirmation, authentication, request payload correctness, or physical-device
behavior. Those remain covered by their dedicated tests and action-time gates. No account,
conversation, customer content, payment, provider, credential, environment variable, or
database state was read or changed by this release.
