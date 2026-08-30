# Registration value clarity release - 2026-08-30

## Outcome

The signed-out account-creation surface now makes Ask Crump's actual Free value and product
structure clear before a visitor commits. It names the same five destinations as the public and
authenticated product, states the enforced Free allowance of 25 messages each day and two private
Projects, and distinguishes free account creation from the separate confirmation required to buy
Professional or Enterprise.

This release improves a deterministic acquisition boundary. It does not claim a registration,
activation, retention, or revenue lift before comparable legitimate traffic produces that evidence.

## Product contract

- The desktop value panel now teaches **Ask, Projects, Create, Library, and You** instead of the
  stale Research, Documents, Images, and Memory labels.
- Generic Free and qualified creation-intent registration state the exact backend-enforced Free
  allowance: **25 messages each day and 2 private Projects**.
- Professional and Enterprise handoffs state that creating the account does not start billing and
  that checkout remains a separate confirmation.
- Existing registration, password, consent, verification, acquisition, plan-intent, and
  creation-intent behavior remains unchanged.
- The versioned authentication controller and service-worker cache advanced together so existing
  PWA installations receive the same contract.

## Verification

- All 560 Python tests passed on the final source state.
- All 45 JavaScript integration validations passed.
- Ruff, Python compilation, production preflight, and diff integrity passed.
- Focused policy coverage ties the visible Free allowance to the current backend defaults and
  rejects the stale signed-out capability labels.
- A real-controller local fixture proved generic Free, Projects, and Professional handoffs with no
  production request, account, analytics event, checkout, or payment.
- The native verifier continued to report only the known release-time prerequisites: RevenueCat
  public keys are absent from the current build, Android Firebase configuration is missing, and
  the iOS project must be generated on macOS.

## Production evidence

- Feature commit: **19485fb** (`Clarify registration value and product map`).
- Deployment: **dpl_FBTQeu7azo7zjwUs47niG1ZpVLpe**.
- State: READY on all six configured project domains with no alias error.
- Canonical health returned HTTP 200, version 5.9.76, and `cache-control: no-store`.
- The deployed app, versioned authentication controller, and cache revision `r156` returned HTTP
  200 with the exact release contract.
- A write-blocked production browser audit covered:
  - generic Free registration at 320 by 667;
  - Projects-intent registration at 390 by 844; and
  - Professional registration at 1,440 by 900.
- Every path focused the email field, kept the primary action above the fold, had no horizontal
  overflow, and produced no page error, console error, or unexpected failed request.
- The release window had no runtime-error cluster and no error or fatal deployment log.
- Analytics transport and all non-GET/HEAD requests were blocked during browser verification. No
  production user, registration, event, message, artifact, Project, checkout, payment, or
  subscription was created.

## Next evidence boundary

Observe legitimate external visitors through first visit, registration, first useful work, and a
durable keep-or-return action before changing the acquisition boundary again or claiming improved
conversion. Segment only by the existing allowlisted, content-free acquisition and intent fields.

Rollback remains the prior production deployment
**dpl_3npXSzqpVozQqPVxQDipujeVJKmJ**.
