# Submit-button ownership gate — 2026-09-16

## Outcome

Ask Crump's fail-closed button audit no longer assumes that a rendered `type="submit"` control is
functional merely because it is a submit button. The audit now identifies the exact enclosing form
and requires a bounded executable `submit` owner for that form. A future orphaned submit button, a
submit button outside a form, or a handler attached only to a different form fails CI.

## Reviewed controls

The strengthened gate covers the nine rendered submit actions currently shipped across the public
workspace sources:

- sign in;
- create account;
- request a password-reset link;
- reset a password;
- import a manuscript;
- save a book;
- prepare a Crump Code task;
- save a Project; and
- create a video.

This complements the existing inventory of 182 rendered and 94 programmatically created buttons.
Programmatic controls continue to require an explicit type and direct or explicitly reviewed
delegated owner.

## Verification

- focused button-integrity contract: **27/27**;
- complete backend suite: **1,134/1,134**;
- JavaScript contract: **54/54**; and
- real-browser control matrix: **48/48**.

No application behavior, customer data, account, event, provider call, file, payment, entitlement,
database object, or production configuration changed. This is a release guard: it prevents a class
of future dead controls that the previous audit would have incorrectly accepted.

## Boundary

The gate proves source ownership and the existing browser journeys prove representative execution,
recovery, focus, responsive layout, and destination behavior. It does not manufacture a destructive
action, payment, provider generation, native permission, or signed-device outcome. Those actions
retain their separate safe fixtures and legitimate-user release gates.
