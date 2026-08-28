# Ask Crump 5.9.67 navigation-responsibility release

Date: 2026-08-28
Production version: 5.9.67
Feature commit: `127ed27ccdf6b9651ed62b0a92bb6f39dfc8baf8`
Production deployment: `dpl_97Rmrz5JdkUZMaPhtWzuzGPcRcQV`

## Outcome

The five-destination shell was live, but the open Chats panel still repeated Projects, Settings,
Plan & credits, Legal & Privacy, and account-sync status beneath conversation history. Those rows
made Chats behave like a second application menu and preserved the exact navigation redundancy the
reorganization was intended to remove.

Production 5.9.67 gives each destination one responsibility:

- Chats contains new-conversation controls and synchronized conversation history only.
- Projects remains a first-class destination in the desktop rail and phone navigation.
- You now contains Profile, Behavior, Plan & credits, Account, and About.
- Plan & credits shows the live credit balance and opens the existing billing center from You.
- Legal & Privacy remains available in You → About.
- The redundant account-sync footer is removed because the Chats heading already exposes the
  synchronized state.

The Settings save action now appears only on Profile and Behavior, the two editable settings
sections. It is absent from Plan & credits, Account, and About.

## Scope and safety

- The existing billing center, price display, credit balance, purchase history, checkout handlers,
  subscription management, and provider integrations were reused unchanged.
- Opening Plan & credits does not start a checkout. A purchase still requires a separate explicit
  choice and provider confirmation.
- The legacy navigation rollback retains its previous sidebar destinations. The final 5.9.67 layer
  hides the compatibility footer only after the new You/Plan surface is available.
- Authentication, sessions, ownership, RLS, storage, customer content, pricing, credits, payments,
  entitlements, providers, and analytics semantics did not change.
- Production verification inspected the owner's existing balance and billing surface without
  starting a checkout, creating content, changing settings, or recording a synthetic event.

## Verification

### Local contracts and build

- All 405 Python tests passed.
- Ruff and backend/API compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight and the native web-bundle build passed.
- Android regenerated for API 36 as 5.9.67/build 50967.
- Store metadata and mobile signing-source checks passed.
- The production-layer fixture proved that the Chats accessibility tree contained conversation
  history but none of the Projects, Settings, billing, legal, or account-sync footer controls.
- The fixture opened You → Plan & credits, mirrored a 649-credit balance, opened the billing dialog
  exactly once, and did not expose the Save changes action on the non-editable Plan section.
- A 390-pixel framed review proved the Chats-only drawer and the complete five-tab You sheet without
  horizontal page drift.

### Hosted gates

- CI: [run 33215392537](https://github.com/CRUMP-AI/AskCrump/actions/runs/33215392537) — passed.
- Android store bundle: [run 33215392543](https://github.com/CRUMP-AI/AskCrump/actions/runs/33215392543) — passed.
- iOS store source: [run 33215392555](https://github.com/CRUMP-AI/AskCrump/actions/runs/33215392555) — passed.

### Production

- Deployment `dpl_97Rmrz5JdkUZMaPhtWzuzGPcRcQV` reached READY and serves commit `127ed27`.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.67.
- The live app references 5.9.67 assets and the service worker serves cache revision 101.
- The authenticated Chats snapshot contained only its brand/header, New conversation, Clear all,
  Conversations, and Synced controls before the workspace.
- The authenticated You snapshot exposed Profile, Behavior, Plan & credits, Account, and About.
- The live Plan panel mirrored the owner's 649-credit balance and opened the existing billing
  center. No purchase option was selected, no checkout was started, and both dialogs were closed.
- The exact deployment reported no warning, error, or fatal runtime log in the inspected one-hour
  release window.

## Store gates unchanged

RevenueCat Android/iOS public configuration, `google-services.json`, final Android signing
credentials, physical-device review, store screenshots/forms, reviewer access, and console
submission remain human/store gates. The hosted Android and iOS runs verify unsigned release
source/build readiness only.

## Outcome still to prove

Delivery and destination clarity are verified. Reduced navigation hesitation, faster return to a
conversation, Plan discovery, checkout entry, and mobile task completion still require legitimate
post-release behavior. No activation, retention, or monetization lift is claimed from the interface
change alone.
