# Ask Crump 5.9.59 conversation-library discovery release

Date: 2026-08-28
Production version: 5.9.59
Feature commit: `cd87e3f40834851b57b9eae5fda1ec84cfad742c`
Production deployment: `dpl_HnFmTa3DKW1Vk6Knz2nRgLHuLCbE`

## Outcome

A direct owner question — whether the desktop app could show other chats — exposed that the
conversation library was technically available but hidden behind an unlabeled icon. The desktop
rail now names `New`, `Chats`, and `Projects` directly. Chats also shows whether the library is open
and preserves the existing remembered desktop preference.

When the library is closed, it is now marked hidden and inert so keyboard and assistive-technology
navigation cannot enter an invisible conversation list. Reopening it restores both visual and
accessible access.

## Scope and safety

- No authentication, ownership, synchronization, conversation, Project, pricing, entitlement,
  payment, schema, RLS, or analytics behavior changed.
- The new browser fixture uses local placeholder titles, makes no network write, and contains no
  credential or customer content.
- Existing Settings and Plan duplicates still leave the compact rail through the established final
  navigation layer; the visible production destinations remain New, Chats, and Projects.
- The release did not create a production account, conversation, Project, event, payment, or store
  submission.

## Verification

### Local contracts

- All 387 Python tests passed.
- Ruff passed across backend and tests; backend compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight and the native web bundle passed.
- Store metadata source validation passed.
- Android source validation passed for 5.9.59/build 50959/API 36. The local build correctly kept
  RevenueCat billing and Firebase push as submission gates because their local public configuration
  was absent.
- The all-platform local source check reported the expected Windows iOS-project gap; hosted iOS
  source verification passed.

### Browser reproduction

The credential-free fixture loaded the production rail stylesheet and controller. Full-size visual
review showed the three labels without rail or workspace overflow. Browser state inspection proved:

- collapsed: `aria-expanded=false`, conversation library `aria-hidden=true`, `inert=true`;
- reopened: `aria-expanded=true`, conversation library `aria-hidden=false`, `inert=false`.

The visible label remained Chats in both states.

### Hosted gates

- CI: [run 33195911931](https://github.com/CRUMP-AI/AskCrump/actions/runs/33195911931) — passed.
- Android store bundle: [run 33195912823](https://github.com/CRUMP-AI/AskCrump/actions/runs/33195912823) — passed.
- iOS store source: [run 33195912147](https://github.com/CRUMP-AI/AskCrump/actions/runs/33195912147) — passed.

### Production

- Git deployment `dpl_HnFmTa3DKW1Vk6Knz2nRgLHuLCbE` reached READY and received all production
  aliases in about 35 seconds.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.59.
- The live app returned HTTP 200 with the New and Chats labels, state attributes, and release-
  versioned rail stylesheet.
- The live service worker returned HTTP 200 with cache `ask-crump-new-body-v1-r93` and 5.9.59
  assets.
- No runtime error cluster was reported in the inspected 15-minute release window.

## Outcome still to prove

Delivery and interaction behavior are verified. The next legitimate returning-user observation
must show whether the plain Chats label reduces navigation confusion and helps useful answers become
continued conversations or Projects. No retention lift is claimed from the owner report or local
fixture alone.
