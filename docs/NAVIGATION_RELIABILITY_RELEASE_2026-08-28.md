# Ask Crump 5.9.60 navigation-reliability release

Date: 2026-08-28
Production version: 5.9.60
Feature commit: `61ea00a3b3140adbc528de47641e68ea5e7e3a74`
Production deployment: `dpl_AxX8py6sdMRREjqR5YXCSqtf4Puq`

## Outcome

Two direct owner observations exposed different navigation failures that shared the same final shell:

- on desktop, the conversation panel appeared only briefly during refresh because the reorganized
  rail replaced the temporary Chats control and then honored a collapse preference with no durable
  way to reopen the panel;
- on iPhone/mobile, Projects, Settings, Plan & credits, and conversation options could lose the
  intended touch while the drawer closed.

Production 5.9.60 keeps a permanent desktop `Chats` control in the final navigation layer, clears
the stranded collapse preference once for existing accounts, and then preserves deliberate user
choices. Mobile footer destinations now get the requested surface open before the drawer closes.
Conversation options use one delegated handler that survives chat-list hydration and stops the
clickable parent row from consuming the same tap.

## Scope and safety

- No authentication, session, ownership, synchronization, conversation data, Project data, pricing,
  entitlement, payment, schema, RLS, provider, generation, or analytics behavior changed.
- The desktop preference migration removes only the device-local obsolete collapsed flag once. Every
  later collapse or reopen remains device-local and remembered.
- The release verification opened existing private navigation surfaces but created no conversation,
  Project, file, event, purchase, account, payment, or store submission.
- The credential-free browser fixture uses a local placeholder conversation and mocked local
  destination surfaces. It makes no network write and contains no credential or customer content.

## Verification

### Local contracts

- All 391 Python tests passed.
- Ruff passed across backend and tests; backend compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight and the native web bundle passed.
- Store metadata source validation passed.
- The local all-platform source check retained the expected Windows iOS-project gap and the existing
  RevenueCat/Firebase submission warnings; hosted Android and iOS source verification passed.

### Browser reproduction

The fixture loads the four production navigation layers. Its compact branch proved:

- opening the drawer changed it to `aria-hidden=false`, removed `inert`, and set the menu to
  `aria-expanded=true`;
- the exact conversation-options control opened one menu, left the drawer open, and did not select
  the parent conversation;
- Settings, Plan & credits, and Projects each opened once, then closed the drawer and reset its menu
  state;
- a stale desktop collapse preference was cleared once, leaving Chats visible after final-shell
  hydration; the permanent Chats control then collapsed and reopened the panel with matching
  `aria-expanded`, `aria-hidden`, and `inert` state.

### Hosted gates

- CI: [run 33199837780](https://github.com/CRUMP-AI/AskCrump/actions/runs/33199837780) — passed.
- Android store bundle: [run 33199837741](https://github.com/CRUMP-AI/AskCrump/actions/runs/33199837741) — passed.
- iOS store source: [run 33199837726](https://github.com/CRUMP-AI/AskCrump/actions/runs/33199837726) — passed.

### Production

- Git deployment `dpl_AxX8py6sdMRREjqR5YXCSqtf4Puq` reached READY, received every production
  alias, and serves commit `61ea00a`.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.60.
- The live app returned HTTP 200 with the 5.9.60 marker and one permanent desktop Chats control.
- The live service worker returned HTTP 200 with cache `ask-crump-new-body-v1-r94` and 5.9.60
  assets.
- In the authenticated production shell at the compact breakpoint, conversation options remained
  open without closing the drawer; Settings, Plan & credits, and Projects each opened their intended
  surface and reset the drawer state.
- In a clean desktop production tab, Chats was visible and expanded after final navigation loaded;
  one click collapsed it to hidden/inert and a second click restored it.
- No runtime error cluster was reported in the inspected 15-minute release window.

## Outcome still to prove

The owner-reported failures are reproduced and the corrected paths are verified in production.
The next legitimate returning-user observation must show whether desktop conversation history now
stays discoverable and mobile navigation remains dependable across repeated real-device use. No
retention lift is claimed from owner validation or browser verification alone.
