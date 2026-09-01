# Account-entry password visibility release — 2026-09-01

## Outcome

Every password a user enters in Ask Crump can now be checked before submission. Registration already
had a Show/Hide control; sign-in, new-password reset, and reset confirmation now use the same proven
interaction. This reduces avoidable login and recovery failures caused by phone keyboards, password
manager edits, or simple typing mistakes without changing the password policy, authentication API,
session behavior, or verification flow.

## Accessible interaction

Each control:

- is a non-submitting button;
- names the field it controls through `aria-controls`;
- begins with a specific accessible name such as **Show current password**;
- changes both visible text and accessible name to **Hide…** while the password is exposed;
- maintains accurate `aria-pressed` state; and
- returns focus to the password field without scrolling the form.

The two reset controls remain independently operable and have distinct accessible names. The reset
password hint lookup now uses its enclosing form group so the existing policy guidance remains intact
after the input is wrapped by the visibility control.

## Release evidence

- Code commit: `f9829c2`.
- Production deployment: `dpl_4YpgUaoshgej5vLw8NCeBTZD9Gkw`, `READY` on all six aliases.
- Production service-worker cache: `ask-crump-new-body-v1-r180`.
- Exact authentication asset: `5.9.76-auth-entry-polish-1`.
- 710 Python tests passed.
- 47 JavaScript files passed the integration contract.
- Python compilation, production preflight, native web-bundle generation, store metadata, mobile
  signing-source controls, and diff integrity passed.
- A credential-free local browser used the real authentication controller and proved masked → shown
  → masked behavior, accurate labels, field-focus preservation, independent reset controls, zero
  authentication events, and zero browser errors.
- The public production deployment proved the exact sign-in and both reset interactions. No form was
  submitted and every dummy value was cleared or discarded by navigation.
- The canonical app, service worker, and versioned authentication asset returned HTTP 200 with all
  four controls and the exact release markers.
- Production showed no runtime-error cluster for login, forgot-password, or reset-password routes and
  no warning/error/fatal log on the release deployment.

No account, email, verification, password, reset request, session, conversation, Project, artifact,
checkout, payment, subscription, entitlement, or credit state changed during verification.

## Remaining gates

Legitimate external registration, verification, sign-in, recovery-email delivery, and reset completion
still require privacy-safe funnel evidence before an activation or recovery improvement is claimed.
Native store readiness separately still requires generated platform projects, RevenueCat public SDK
keys, signed-device proof, screenshots, reviewer credentials, and console completion.
