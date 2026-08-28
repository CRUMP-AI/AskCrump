# Signup password-guidance release evidence

Date: 2026-08-27  
Release: 5.9.36 / native build 50936  
Code commit: `40bbc28da6f559036890425ca56276767594626c`  
Production deployment: `dpl_5kDcdWj7KpWHbq9kXrjDJacQjESV`

## Outcome

Account creation now explains each unchanged password requirement before submission: ten or more
characters, one letter, and one number. Each item confirms independently while the user types. A
polite screen-reader status reports only changed requirement state, and the password field receives
an invalid state only after it has been reviewed or a submission is attempted.

This is a clarity improvement, not a password-policy, authentication, verification, pricing, or
analytics change. The Create account action remains available so the interface does not strand a
user behind an unexplained disabled control.

## Evidence that justified the change

The protected operating snapshot showed two anonymous signup starts without a credentials-ready
event. That sample is context, not proof of a password-specific conversion problem. The release was
instead justified by a reproducible UI defect in the local production shell:

- a ten-character, letters-only password appeared native-valid even though it did not satisfy the
  unchanged Ask Crump password contract;
- the account action remained enabled;
- the page showed only one static sentence, with no visible or accessible indication of the unmet
  number rule before submission.

No production form was submitted and no synthetic production event was created during diagnosis or
verification.

## Safety and privacy boundary

- Existing server and client password validation remains ten to 256 characters with at least one
  letter and one number.
- No credential, session, cookie, verification, database, billing, provider, or entitlement logic
  changed.
- The rule state is calculated only in the current page and is not logged or transmitted.
- Browser verification used a reserved `.invalid` email address and test-only passwords on a local
  static server. No account was created and no password was sent to Ask Crump.
- The owner-run manual sign-out and credential-entry proof remains separate and pending.

## Automated and local verification

- All 314 application tests passed.
- Ruff passed for `backend` and `tests`.
- All 42 JavaScript files passed syntax and integration validation.
- Production preflight and the native web bundle passed.
- Android source regenerated as 5.9.36/build 50936 with API 36 and passed the native, metadata, and
  signing-source controls.
- The known owner gates remain unchanged: the Android RevenueCat public key and
  `google-services.json` are not present, and signed/physical-device/store-console review remains
  pending.

## Browser verification

The local release shell was reviewed at 1,440 by 900 and 390 by 667 without touching production
analytics or authentication.

- A letters-only ten-character password showed length and letter as met, number as unmet, and the
  screen-reader status `Password still needs one number.`
- After the field was reviewed, `aria-invalid` became `true`.
- Adding a number changed all three rules to met, set `aria-invalid` to `false`, and changed the
  status to `Password meets all requirements.`
- The 390-pixel layout had no horizontal overflow, the page needed no vertical scroll, and the
  account action ended at approximately 471 pixels inside the 667-pixel viewport.
- Desktop and short-phone screenshots retained the restrained black/charcoal/gold hierarchy.
- No browser warning or error was recorded.

## Hosted and production verification

- CI run `33135663864` passed.
- Android Store Bundle Verification run `33135663895` passed with no signing or upload credentials.
- iOS Store Source Verification run `33135663885` passed its unsigned Release compile with no
  signing or upload credentials.
- Vercel deployment `dpl_5kDcdWj7KpWHbq9kXrjDJacQjESV` reached `READY`, was assigned the four
  canonical Ask Crump/Clever Crump aliases, and points to the exact code commit above.
- `https://askcrump.com/api/health` returned HTTP 200, `no-store`, and version 5.9.36.
- The production app shell and the versioned authentication controller, body stylesheet, legacy
  compatibility script, and service worker returned HTTP 200. The app shell contained the release
  label and three-rule checklist.
- The inspected release window contained no runtime error cluster, warning/error/fatal log, or 5xx
  response.

## Outcome boundary and rollback

Delivery and production reliability are verified. Improved signup completion is not yet proven;
evaluate only legitimate post-release traffic and do not calculate a rate until the comparable
cohort has a credible denominator.

Rollback is to redeploy `dpl_DMDgRTkaFYcDiDenuW7cmxobrSXi` or revert commit `40bbc28`. Neither path
requires deleting account or product data.
