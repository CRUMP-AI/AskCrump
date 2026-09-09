# Button control matrix isolation release — 2026-09-09

## Outcome

Ask Crump's complete button audit now fails closed when a stale local fixture server is already
using one of the five ports required by the browser matrix. This prevents an older build from
silently supplying assets and creating a false pass or false failure during release verification.

The production application itself required no customer-facing source change for this finding.
The defect was in the isolation of the release proof: an existing listener on port `8765` served
an older `auth-controller.js`, while the newly spawned fixture server exited because its address
was already in use. The matrix previously continued against that stale listener.

## Prevention added

- `scripts/verify-browser-control-matrix.mjs` checks ports `4173`, `8765`, `8766`, `8767`, and
  `8770` before starting any fixture server.
- Any occupied required port stops the matrix with an exact, actionable error instead of using
  the unknown listener.
- Matrix-owned servers are terminated and awaited in the `finally` path, including a failed
  verifier run.
- `tests/test_button_integrity.py` locks the port-isolation and cleanup contract so a future
  runner change cannot silently remove it.

The guard was first proved against the actual stale listener on `8765`; it rejected the run.
After that listener was stopped, the clean matrix passed and all five ports were released.

## Complete control evidence

- **181 rendered + 94 programmatic = 275** reviewed button construction sites retain an explicit
  owner and behavior contract.
- Button integrity passed **21/21**.
- The fail-closed browser control matrix passed **36/36** on clean, matrix-owned fixture servers.
- The complete Python suite collected **942 tests**: **940 passed** and two environment-dependent
  tests skipped.
- **49 JavaScript files** validated, including **6/6** attribution cases.
- Python compilation, production preflight, native web bundle construction, and diff integrity
  passed.

A separate signed-in production walkthrough exercised the safe interaction boundary on desktop
and at a `390 × 844` iPhone-sized viewport. The verified controls included:

- primary Ask, Projects, Create, Video, Library, You, and Chats navigation;
- Projects and Files entry/return, file filters, progressive disclosure, foreground image viewer,
  and foreground editable-PowerPoint viewer;
- Document Studio, Presentation mode, Image Studio, Manuscripts, and Video Studio entry/return;
- Library grid/book/list views, Recently Deleted, book details, manuscript reader, and close/back;
- Settings profile, behavior, plan/credits, account, about, signed-in devices, and the complete
  six-step workspace guide;
- Intelligence mode, review behavior, saved-memory, explicit-learning, live-information, and
  remembered-information controls, with changed preferences restored to their starting values;
- conversation options, rename/delete/clear confirmations through their non-destructive Cancel
  boundary; and
- **Think with Crump**, **Research something**, and **Analyze a file** handoffs without sending a
  message or uploading a file.

The mobile Chats drawer remained open while the conversation options and Rename action were
used. Creating a new conversation with no message did not create a blank server conversation: the
visible conversation count was unchanged after closing and reopening Chats.

## Deliberate live-action boundary

This release does not claim that irreversible or externally consequential outcomes were executed
against production. The walkthrough did not complete a purchase, delete or clear customer data,
sign out another device, upload a file, download a file, send a message, start image/video/provider
generation, or consume credits. Those controls were exercised through their available entry,
confirmation, cancel, and recovery states and retain their focused fixture/contract coverage.

The browser recorded no page or console error during the final sweep. Two duplicate, transient
warnings at the same earlier timestamp reflected a service-worker update fetch and a sync fetch
during the requested runtime reload. The interface recovered to **Synced** and remained usable;
this is not represented as an error-free network history.

## Release evidence

- Commit: `b613ae03a00e629f3c922fd69f0eebc823f8b253`
- GitHub Actions CI: run **34396097315**, completed successfully
- Production deployment: **dpl_EeruqACiiDr5PLaK3LPRxccmwwLV**, READY with no alias error
- Production health: HTTP 200, Ask Crump version `5.9.76`
- Initial 30-minute runtime-error query: no grouped runtime error
- Initial deployment-scoped one-hour 5xx query: no matching log

This release strengthens release evidence. It does not claim user-growth, activation, retention,
or revenue lift.
