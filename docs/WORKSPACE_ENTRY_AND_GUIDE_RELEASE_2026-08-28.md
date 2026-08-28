# Ask Crump 5.9.69 workspace-entry and guide release

Date: 2026-08-28
Production version: 5.9.69
Feature commit: `ee5428c09a62913eddaa4d6b349ab6dea9ab76e7`
Production deployment: `dpl_8kuUjepL31DL8s3ecVQdxB2HY7jK`

## Outcome

The reorganized product had two connected first-use defects. An authenticated workspace could
briefly expose the obsolete two-button rail and redundant Chats footer before the final runtime
replaced them, and the replayable tutorial still taught the previous feature-category structure.

Production 5.9.69 makes the entry and guide agree with the released product:

- The first visible authenticated workspace frame is now a restrained Ask Crump handoff while the
  final body and navigation runtimes settle.
- The handoff releases to one stable navigation containing Ask, Chats, Projects, Create, Library,
  and You; the obsolete rail no longer flashes first.
- The tutorial now teaches exactly five destinations: Ask with Chats as synchronized history,
  Projects, Create, Library, and You.
- Every tutorial step displays the same five-destination map and marks the current destination.
- The guide remains replayable from You → About as `Replay workspace guide`.

## Scope and safety

- The workspace gate is visual and interaction-bounded. It removes `inert` as soon as the final
  runtime reports ready and includes a five-second fallback so an asset failure cannot strand the
  user behind the handoff.
- Authenticated account initialization and the existing secondary synchronization continue beneath
  the handoff; credentials, sessions, ownership, RLS, customer content, pricing, credits, payments,
  entitlements, providers, and analytics semantics are unchanged.
- The automatic guide still yields to the first-use launchpad when that launchpad is present, so a
  new user is not forced through two stacked onboarding experiences before the first prompt.
- Production verification replayed the owner-scoped guide without creating a conversation,
  Project, artifact, checkout, account, or synthetic analytics event.

## Verification

### Local contracts and build

- All 408 Python tests passed.
- Ruff and backend/API compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight and the native web-bundle build passed.
- Android regenerated for API 36 as 5.9.69/build 50969.
- Store metadata and mobile signing-source checks passed.
- A production-code tutorial fixture traversed all five steps and proved the exact current
  destination, progress, copy, and controls at every step.
- Static contracts prove the bounded workspace gate, the five-destination guide, and the updated
  You → About replay copy.

### Hosted gates

- CI: [run 33218241231](https://github.com/CRUMP-AI/AskCrump/actions/runs/33218241231) — passed.
- Android store bundle: [run 33218241102](https://github.com/CRUMP-AI/AskCrump/actions/runs/33218241102) — passed.
- iOS store source: [run 33218241194](https://github.com/CRUMP-AI/AskCrump/actions/runs/33218241194) — passed.

### Production

- Deployment `dpl_8kuUjepL31DL8s3ecVQdxB2HY7jK` reached READY and serves commit `ee5428c`.
- `https://www.askcrump.com/api/health` returned success with version 5.9.69.
- The live service worker serves cache revision 103.
- At the exact first frame where the authenticated app became visible, the branded workspace gate
  was present and both final runtimes were still settling. After release, the gate was hidden and
  the stable navigation exposed only Ask, Chats, Projects, Create, Library, and You.
- The live You → About replay traversed Ask, Projects, Create, Library, and You as steps 1–5, with
  the matching destination selected on every step, then closed normally through `Enter workspace`.
- The exact deployment reported no warning, error, or fatal runtime log in the inspected one-hour
  release window.

## Store gates unchanged

RevenueCat Android/iOS public configuration, `google-services.json`, final Android signing
credentials, physical-device review, store screenshots/forms, reviewer access, and console
submission remain human/store gates. The hosted Android and iOS runs verify unsigned release
source/build readiness only.

## Outcome still to prove

The deterministic entry flash and obsolete guide are repaired. Improved first-session confidence,
tutorial completion, destination discovery, and return behavior still require legitimate
post-release usage. No activation or retention lift is claimed from the interface change alone.
