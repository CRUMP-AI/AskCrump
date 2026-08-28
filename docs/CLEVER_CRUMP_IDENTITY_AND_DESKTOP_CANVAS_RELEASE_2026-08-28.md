# Ask Crump 5.9.66 company identity and desktop-canvas release

Date: 2026-08-28
Production version: 5.9.66
Feature commit: `05418a59433a6b4387fc84ef880172d669f7ae2f`
Root-routing stabilization: `8b960d1b31edfceb1274dceafc4364d231fd57b3`
Final production deployment: `dpl_Em4W8i3M1jjFPexcv33hkXBcNo3c`

## Outcome

Clever Crump and Ask Crump now have distinct jobs and distinct public identities. The parent-company
domain presents Clever Crump as an independent Savannah AI product company, with Ask Crump clearly
positioned as its first product. The Ask Crump domain retains the focused product landing and the
signed-in workspace. Both brands share the restrained black, charcoal, ivory, and gold system without
presenting the same page under two names.

The same release corrects a desktop layout collision in the signed-in product. The final three-column
navigation grid was still inheriting a legacy 292-pixel sidebar offset, so opening Chats applied the
library width twice and pushed the workspace beyond the viewport. The final navigation layer now owns
the desktop positioning completely. Chats remains open, the launchpad is centered in the remaining
canvas, and the composer stays inside the viewport.

## Scope and safety

- The parent-company root changes only on `clevercrump.com` and `www.clevercrump.com`.
- `askcrump.com` and `www.askcrump.com` continue to serve the Ask Crump product landing at `/`.
- App, API, legal, use-case, asset, and clean URLs remain unchanged.
- The root routing uses static files and reversible Vercel routing; it adds no new runtime dependency.
- Authentication, sessions, ownership, RLS, storage, private content, pricing, credits, providers,
  payments, entitlements, analytics semantics, and customer data did not change.
- Browser verification inspected the owner's existing signed-in shell structure without creating or
  modifying a conversation, Project, message, artifact, account, event, or payment.

## Verification

### Local contracts and build

- All 402 Python tests passed.
- Ruff and backend/API compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight passed.
- Native web-bundle, Android configuration, store metadata, and mobile signing-source checks passed
  for 5.9.66. Hosted Android and iOS source workflows also passed.
- The desktop grid fixture measured a 1,280-pixel shell, workspace x-position 386, workspace width
  894, workspace right edge 1,280, contained launchpad, and zero document overflow.
- The 375-pixel parent-company fixture measured matching client and scroll widths after the mobile
  overflow guard, with no horizontal drift.

### Hosted gates

- Feature CI: [run 33213150773](https://github.com/CRUMP-AI/AskCrump/actions/runs/33213150773) — passed.
- Android store bundle: [run 33213150645](https://github.com/CRUMP-AI/AskCrump/actions/runs/33213150645) — passed.
- iOS store source: [run 33213150810](https://github.com/CRUMP-AI/AskCrump/actions/runs/33213150810) — passed.
- Root-routing CI: [run 33213752591](https://github.com/CRUMP-AI/AskCrump/actions/runs/33213752591) — passed.

### Production

- Final deployment `dpl_Em4W8i3M1jjFPexcv33hkXBcNo3c` reached READY and serves routing commit
  `8b960d1`.
- `https://www.clevercrump.com/` and `https://clevercrump.com/` returned HTTP 200 with the title
  `Clever Crump | Independent AI product company` and the hero `We build the part after the prompt.`
- `https://www.askcrump.com/` returned HTTP 200 with the title
  `Ask Crump | An AI workspace for work that continues` and the Ask Crump product hero.
- `https://www.askcrump.com/api/health` returned HTTP 200 and production version 5.9.66.
- An authenticated 1,280-pixel production screenshot showed Chats open, the full centered launchpad,
  all six starting actions, the tool selector, and the composer inside the available canvas.
- The parent-company production screenshot and semantic snapshot showed the correct Clever Crump
  identity, company navigation, Ask Crump product handoff, and Savannah positioning.
- Vercel reported no warning, error, or fatal runtime log in the inspected one-hour production window.

## Store gates unchanged

RevenueCat Android/iOS public configuration, `google-services.json`, final Android signing credentials,
physical-device review, store screenshots/forms, and App Store/Google Play console submission remain
human/store gates. This visual release does not represent those gates as complete.

## Outcome still to prove

Delivery is verified. Parent-brand clarity, traffic handed from Clever Crump to Ask Crump, first-use
completion, and returning-work behavior still require legitimate post-release content-free evidence.
No acquisition or retention lift is claimed from implementation alone.
