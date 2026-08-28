# Ask Crump 5.9.61 Project-target disclosure release

Date: 2026-08-28
Production version: 5.9.61
Feature commit: `dd7848adaeaa32a6f9aabb8c35f522d9d59a5edc`
Production deployment: `dpl_Fh7ZLzDbBNLHPVneLsmX1YQvZmWh`

## Outcome

The latest-response continuity action previously said `Keep in a Project` without identifying
where the conversation would go. If Project hydration or selection changed near the click, the
interface also did not give the user a stable, named destination to evaluate.

Production 5.9.61 now says `Start a Project` when no destination is selected and
`Keep in “Project name”` when an active destination exists. The click captures that exact Project
identifier. Background loading or a subsequent Project selection cannot silently reroute the
in-flight save. Long visible names are shortened only on screen; the complete name remains in the
accessible label.

## Scope and safety

- Project ownership, conversation ownership, synchronization, storage, schema, RLS, authentication,
  pricing, entitlements, payments, providers, and analytics semantics did not change.
- Existing callers that do not specify a target retain the previous active-Project fallback.
- The browser fixture uses placeholder identifiers, a synthetic Project name, local mocked requests,
  and no credential, customer content, account, production write, generation, payment, or event.
- Authenticated production verification inspected the rendered destination label but did not click
  it, attach a conversation, create a Project, or generate a synthetic retention event.

## Verification

### Local contracts

- All 391 Python tests passed.
- Ruff passed across the application, backend, and tests; backend compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight, native web bundle, and store metadata source validation passed.
- The local all-platform check retained the expected Windows iOS-project gap and existing
  RevenueCat/Firebase submission warnings; the hosted Android and iOS gates passed.

### Browser fixture

- A selected synthetic Project rendered `Keep in “Q3 Finance Forecast”` with the complete named
  accessible destination and sent the save to that exact Project.
- No selected Project rendered `Start a Project` and created `Website launch checklist`, even when
  delayed Project hydration completed around the action.
- Delayed hydration updated an unclicked action from the truthful new-Project state to the named
  selected destination.
- Both paths reported zero browser errors and made zero unexpected fixture requests.

### Hosted gates

- CI: [run 33201063440](https://github.com/CRUMP-AI/AskCrump/actions/runs/33201063440) — passed.
- Android store bundle: [run 33201063452](https://github.com/CRUMP-AI/AskCrump/actions/runs/33201063452) — passed.
- iOS store source: [run 33201063450](https://github.com/CRUMP-AI/AskCrump/actions/runs/33201063450) — passed.

### Production

- Git deployment `dpl_Fh7ZLzDbBNLHPVneLsmX1YQvZmWh` reached READY on production and serves
  commit `dd7848a`.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.61.
- The live app returned HTTP 200 with the 5.9.61 marker and 5.9.61 UI asset.
- The live service worker returned HTTP 200 with cache `ask-crump-new-body-v1-r95` and 5.9.61
  assets.
- In the authenticated production shell, a conversation with a latest assistant response rendered
  one Project action naming the active destination in both visible and accessible text.
- A full production refresh retained the permanent expanded desktop Chats control and visible
  conversation library.
- No runtime error cluster was reported in the inspected 15-minute release window.

## Outcome still to prove

Delivery and routing truthfulness are verified. The next legitimate post-release cohort must show
whether users choose this clearer action, create or reuse Projects, and return to continue useful
work. No retention or Project-adoption lift is claimed from fixture or owner-session verification.
