# Project click reliability release

Date: 2026-08-29

## Outcome

Selecting a saved Project now produces an unmistakable list-to-workspace transition on desktop
and mobile. The named workspace contains its description, instructions, private files, saved
conversations, durable notes, scoped new-chat action, and a visible Back to Projects path.

## Root cause

The Project row already changed internal state, but desktop kept the Project index alongside an
editor surface. That made the result look static and did not communicate that a specific Project
had opened. Row listeners were also attached to each rendered button, leaving the interaction more
fragile than necessary while asynchronous Project refreshes replace list markup.

The production table contained eight active Projects, with no missing IDs or names. This ruled out
malformed persisted Project identity as the cause.

## Correction

- Project activation is delegated from the stable Project-list container, so re-rendered rows keep
  one durable click path.
- Project IDs are normalized at the browser boundary instead of relying on implicit type equality.
- A stale or unresolvable row now produces a visible retry message rather than silently returning.
- The detail state is applied immediately, before secondary context and conversation reads.
- The selected Project occupies a dedicated workspace at every viewport; the Project index returns
  only through the explicit Back action.
- Project JavaScript and CSS advanced to the independent
  `5.9.76-project-workspaces-3` identity for browser, PWA, and native delivery.

## Verification

- Commit: `52f5e81` (`Open projects as dedicated workspaces`)
- Final production deployment: `dpl_w7qv72UP7SWXwbY99HJrq1jYMsEX`
- A credential-free real-runtime browser fixture opened `Launch Operations`, hid the Project index,
  exposed the named workspace, returned to the index, reopened the Project with a real click, and
  reported zero browser errors.
- The same opened workspace passed at 390 by 700 with no horizontal overflow.
- Supabase aggregate check: eight active Projects, one owner, zero missing IDs, and zero missing
  names; no private Project names or contents were retrieved.
- 32 focused Project/runtime tests passed, followed by all 479 Python tests.
- Python lint and explicit compilation passed.
- All 45 JavaScript files, production preflight, and native web-bundle build passed.
- Canonical production health, runtime loader, exact Project JavaScript, and exact Project CSS
  returned HTTP 200. The live JavaScript contains the delegated click, normalized-ID lookup,
  immediate detail transition, and visible stale-row error; the live CSS contains the dedicated
  opened-workspace layout.
- The deployment is `READY` on all six production aliases. Its first inspected runtime window
  contained two HTTP 200 responses and no warning, error, or fatal log.

## Outcome boundary

This release verifies the interaction and delivery contract. The next evidence is a legitimate
owner return through a saved Project on desktop and phone/PWA, followed by the existing
content-free `RecentWorkResumed` measurement. No retention lift is claimed from the fixture.
