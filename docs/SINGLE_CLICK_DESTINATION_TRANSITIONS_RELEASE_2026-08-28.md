# Ask Crump 5.9.68 single-click destination-transition release

Date: 2026-08-28
Production version: 5.9.68
Feature commit: `3a935319537e3bf0166135965e2015ceb16200d5`
Production deployment: `dpl_AVYBR9BWompwdiMc7cGvx8e2HNeR`

## Outcome

The five primary destinations were visually persistent, but Projects, Create, Library, and You
opened inside full-viewport backdrops that still covered the visible desktop rail or mobile bottom
navigation. A click on another destination therefore hit the backdrop first. Projects, Create, or
Library closed without opening the requested destination, while You could leave the requested
navigation action entirely blocked.

Production 5.9.68 makes the destination chrome genuinely persistent:

- Projects, Create, Library, and You stop before the desktop rail rather than covering it.
- The same surfaces stop above the mobile bottom navigation and safe-area inset.
- Mobile sheets receive a matching height bound so their content remains contained above the
  persistent navigation.
- A single click now moves directly between every adjacent destination surface and back to Ask.

## Scope and safety

- The repair changes only destination-surface geometry and responsive containment.
- Navigation was not raised above authentication, onboarding, billing, confirmation, reader,
  Crump Code, or other sensitive and task-specific overlays.
- Destination controllers, authentication, sessions, ownership, RLS, storage, customer content,
  pricing, credits, payments, entitlements, providers, and analytics semantics are unchanged.
- Authenticated production verification opened existing owner-scoped surfaces with read-only GET
  hydration. It did not create content, alter settings, start checkout, or record a synthetic event.

## Verification

### Local contracts and build

- All 406 Python tests passed.
- Ruff and backend/API compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight and the native web-bundle build passed.
- Android regenerated for API 36 as 5.9.68/build 50968.
- Store metadata and mobile signing-source checks passed.
- A production-layer browser fixture proved Library → Create → Projects in one click per
  transition, with the correct active destination and exactly one visible surface.
- A second production-layer fixture proved You → Projects closes Settings on the same click.

### Hosted gates

- CI: [run 33217042720](https://github.com/CRUMP-AI/AskCrump/actions/runs/33217042720) — passed.
- Android store bundle: [run 33217042725](https://github.com/CRUMP-AI/AskCrump/actions/runs/33217042725) — passed.
- iOS store source: [run 33217042738](https://github.com/CRUMP-AI/AskCrump/actions/runs/33217042738) — passed.

### Production

- Deployment `dpl_AVYBR9BWompwdiMc7cGvx8e2HNeR` reached READY and serves commit `3a93531`.
- `https://www.askcrump.com/api/health` returned success with version 5.9.68.
- The live service worker serves cache revision 102.
- An authenticated production browser completed Projects → Create → Library → You → Ask with
  one click per transition. Each step exposed the correct active destination and surface state.
- The exact deployment reported no warning, error, or fatal runtime log in the inspected one-hour
  release window.

## Store gates unchanged

RevenueCat Android/iOS public configuration, `google-services.json`, final Android signing
credentials, physical-device review, store screenshots/forms, reviewer access, and console
submission remain human/store gates. The hosted Android and iOS runs verify unsigned release
source/build readiness only.

## Outcome still to prove

The deterministic click defect is repaired. Reduced navigation hesitation, faster task switching,
and improved mobile completion still require legitimate post-release behavior. No activation,
retention, or monetization lift is claimed from the interface change alone.
