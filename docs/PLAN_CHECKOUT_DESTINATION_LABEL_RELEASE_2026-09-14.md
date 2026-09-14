# Plan checkout destination label release — 2026-09-14

## Outcome

Ask Crump's web plan actions now name their actual next destination before activation:
**Review Professional in Stripe** and **Review Enterprise in Stripe**. Native builds use the
parallel **in app store** wording. The change removes the ambiguity in the previous **Choose**
labels without changing a plan, price, entitlement, payment route, or confirmation boundary.

The existing current-plan, billing-recovery, provider-management, unavailable-product, and busy
states remain unchanged. Stripe Checkout remains the web review and confirmation surface; native
purchases remain owned by the applicable device store.

## Button and recovery proof

The credential-free checkout-recovery browser fixture now requires the exact web labels, proves
that deliberate activation sends one plan choice to the existing subscription endpoint, preserves
the same selection across authentication recovery without automatically reopening Checkout, and
rejects deceptive or non-Stripe destinations. Both legacy and final plan-center owners carry the
same platform-aware wording so a timing or loading-order difference cannot restore the vague label.

The complete browser-control matrix passed **48/48** verifiers, covering navigation, Projects,
Files, creation studios, Video, Library, image editing, mobile drawers, subscription recovery, and
the rest of the automated control inventory. The complete Python suite passed **1,108/1,108** and
JavaScript validation passed **54/54** files. Production build, native web-bundle, client-credential,
whitespace, Android, iOS, and CI gates are green.

## Live production proof

- Feature commit: `0d1639fc08c24044cf216739f8090c73a0ff40bf`.
- GitHub CI: `34903550942`; Android: `34903550893`; iOS: `34903550917`; all succeeded.
- Production deployment: `dpl_9vNPMZ1jw4d1CjyRqHNsoTW1554U`; Ready on all six aliases with no
  alias error.
- Installed-PWA cache generation: `ask-crump-new-body-v1-r247`.
- A signed-in live replay applied the ready app update, opened Plan & credits, and found both exact
  new labels with neither retired **Choose** label present. The release replay did not activate a
  checkout control.
- The deployment's initial production sample contained 32 HTTP 200 responses, no HTTP 5xx response,
  no warning/error/fatal log, and no grouped runtime error.

During the preceding product audit, one internal Checkout review was opened and immediately exited
without payment information, confirmation, charge, entitlement, or purchase. It is diagnostic
traffic only and must not be counted as a payer or recognized revenue.

## Boundary

This release proves owned safe controls and the plan-button destination contract. It does not claim
that destructive actions, real payment completion, provider media generation, uploads/downloads on
every physical device, or native permissions were executed. Those outcomes retain their separate
approval, fixture, legitimate-user, or physical-device gates. No Stripe product, price, customer,
subscription, tax, or provider configuration changed.
