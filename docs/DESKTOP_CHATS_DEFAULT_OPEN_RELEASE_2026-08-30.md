# Desktop Chats default-open release

Date: 2026-08-30

## Outcome

The desktop Chats rail now remains visible after a reload, including for browsers that retained the
legacy `crump_v1_library_collapsed` preference. A user may still hide or show the rail during the
current desktop session. Every new desktop page load starts with Chats expanded. The mobile drawer
keeps its existing open, select, and close behavior.

## Cause and correction

The initial shell rendered the rail correctly, but `restoreDesktopPreference()` later reapplied a
persisted collapsed value. That delayed restore caused the rail to appear briefly and then shrink to
one pixel with zero opacity. Desktop startup now clears the stale persistence keys and establishes
the expanded state as the session default. The in-session toggle remains local to the loaded page.

## Verification

- Product commit: `8212576b6b8e49d9725869de373ea7b3b2506fa3`
  (`Keep desktop Chats visible after reload`).
- Production deployment: `dpl_Aw8dZYrWbGGfgtuxEV9UrYhZhqoP`, `READY` on all six Ask Crump and
  Clever Crump aliases.
- All 579 Python tests passed.
- The official integration validator passed all 45 JavaScript files.
- Lint for the changed tests, production preflight, native web-bundle creation, and diff-integrity
  checks passed.
- A local desktop fixture seeded the stale collapsed preference and proved: expanded boot, working
  in-session Hide/Show, and expanded state again after reload.
- A local mobile fixture proved: closed default drawer, correct open state, selected-conversation
  navigation, and automatic close after selection.
- An authenticated production desktop reload was sampled 24 times over roughly 2.4 seconds. Every
  sample retained a 292-pixel rail, full opacity, `aria-hidden=false`, and no inert state.
- Production served cache revision `r162` and the exact
  `5.9.76-desktop-chats-default-1` runtime loaders.
- The browser console was clean, and the inspected Vercel release window contained no runtime error
  cluster.

## Safety boundary

This release changed navigation presentation only. It did not create or modify production messages,
Projects, files, accounts, subscriptions, payments, model calls, entitlements, or customer data.

## Follow-through

The implementation and production behavior are verified. Continue observing normal owner and
customer desktop use; do not infer retention or activation improvement from release verification.
