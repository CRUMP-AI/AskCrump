# Visible workspace return measurement release — 2026-09-15

## Decision boundary

Ask Crump's D1 and D7 workspace-return measures use the content-free `WorkspaceOpened` product
event. A return should mean that an authenticated person had the workspace visible; a restored,
preloaded, or background browser tab is not sufficient evidence of a return.

## Reproduced defect

A credential-free authenticated-entry fixture forced `document.visibilityState` to `hidden` before
session restoration. The previous controller still emitted one daily `WorkspaceOpened` event:

```json
{"visibility":"hidden","events":[{"name":"WorkspaceOpened","detail":{"eventKey":"workspace-open:2026-09-15"}}]}
```

That behavior could inflate a later D1 or D7 numerator without a visible workspace visit.

## Shipped behavior

Authenticated startup now:

- records the daily event immediately only when the document is not hidden;
- otherwise waits for the first `visibilitychange` that makes the workspace visible;
- removes the temporary listener after that transition; and
- suppresses repeat client emissions for the same account and UTC day.

The server-owned event key remains `workspace-open:YYYY-MM-DD`, the payload remains content-free,
and no prompt, response, filename, Project, conversation, email, or customer identifier is added.
Authentication, session restoration, analytics ingestion, database schema, RLS, report definitions,
pricing, entitlements, and payments are unchanged.

## Verification

- The corrected hidden fixture emitted zero workspace-return events before visibility.
- Its first hidden-to-visible transition emitted exactly one correctly shaped daily event.
- A repeated visible transition emitted no duplicate.
- The complete browser-control matrix passed **48/48**, including the new regression case.
- The complete Python suite passed **1,133/1,133**.
- The JavaScript integration suite passed **54/54**; store packet self-test passed **21/21**; diff
  integrity passed.

Production commit, CI, deployment, asset, health, and runtime-log evidence will be sealed here after
the exact release is Ready.

## Interpretation

This closes a deterministic measurement-integrity gap; it does not create retention. The first
recorded one-account D1 observation remains historical, directional evidence and should not be
treated as a stable rate. Future return observations after this release have the stronger visible
workspace boundary. D7, durable value, Project continuity, payer, and recognized-revenue gates stay
separate and unchanged.
