# Plan center focus containment release

Date: 2026-08-29

## Product outcome

The signed-in **Plan & credits** center now behaves as a true billing modal. Keyboard and
assistive-technology interaction moves into the pricing surface, stays there while it is open,
and returns to the exact control that opened it after Close, backdrop dismissal, or Escape.

This protects the revenue path immediately before a person reviews credits, subscriptions, and
provider checkout. It does not change prices, allowances, entitlements, payment providers, or
checkout behavior.

## Reproduced defect

A signed-in production inspection found the billing sheet declared `aria-modal="true"` while:

- focus remained on the Settings **Open plan & credits** control behind the sheet;
- 35 visible focusable controls remained outside the billing dialog;
- the background was neither `inert` nor hidden from assistive technology; and
- the billing dialog contained 11 visible focusable controls of its own.

That semantic and keyboard mismatch could strand a user before checkout. The audit did not open a
checkout, create a payment, alter an entitlement, consume credits, or change any private record.

## Correction

Both live Plan-center owners now implement the same boundary so load timing cannot select a weaker
path:

- capture the exact opening control;
- focus **Close** as soon as the dialog is mounted;
- preserve and apply `inert` plus `aria-hidden` to visible background roots while excluding the
  toast region;
- derive the focusable set dynamically from the current hydrated billing sheet;
- wrap Shift+Tab from **Close** to **Privacy** and Tab from **Privacy** to **Close**;
- close on Escape while restoring the background and opener; and
- preserve any pre-existing background `inert` or `aria-hidden` state.

The fallback billing controller, final billing controller, legacy runtime manifests, current
workspace loader, PWA cache, and native loader now reference the same versioned release. The PWA
cache advances to `r139`.

## Verification

The credential-free Plan-center browser fixture uses the production billing controllers and local
responses only. It proved:

- the background became `inert` and `aria-hidden="true"`;
- initial focus moved to **Close**;
- backward focus wrapped to **Privacy**;
- forward focus wrapped to **Close**;
- click dismissal and Escape both removed the modal, restored the background, and returned focus to
  `upgradeBtnSidebar`;
- the existing content-free `PlanCenterViewed` event remained `settings`-scoped; and
- the fixture recorded zero browser errors.

Release gates:

- 494 Python regressions passed;
- 45 JavaScript files passed the integration validator;
- the production preflight passed;
- the native web bundle rebuilt successfully;
- Apple and Google metadata source checks passed; and
- `git diff --check` passed.

## Production evidence

- Feature commit: `4c89e78`
- Deployment: `dpl_GwJbA5qARwmW58QcXc6ERUa6ny6H`
- State: `READY`
- Production aliases: all six expected Ask Crump and Clever Crump aliases
- Alias error: none
- Canonical health: HTTP 200, service `Ask Crump`
- Signed-in read-only workspace: runtime `ready`; exact versioned loader and both billing
  controllers present; no billing modal or checkout opened post-release
- Exact live cache: `r139`
- Initial runtime audit: no runtime-error cluster and no warning, error, or fatal deployment log

## Observation boundary

Delivery is verified on web/PWA and included in the regenerated native web bundle. A production
conversion claim still requires a legitimate Plan-center view followed by a real checkout and
provider-reconciled paid entitlement. Physical iPhone PWA and exact signed-candidate keyboard and
screen-reader passes remain store-readiness gates.
