# Login-failure measurement release — 2026-09-08

## Outcome

Ask Crump now distinguishes the recoverable reason for a failed sign-in without recording the
person, email, password, response text, or account identifier. Invalid credentials,
verification-required, rate limiting, session-establishment failure, timeout, offline state, and an
unknown request failure each produce a stable, content-free analytics category.

The server now returns `INVALID_CREDENTIALS` and `EMAIL_VERIFICATION_REQUIRED` codes for its two
expected login rejections. The browser reduces only fixed server/client codes and connectivity state
to an allowlisted reason. User-visible messages, login acceptance, rate limits, session creation,
cookies/native tokens, and verification behavior remain unchanged.

## Decision evidence

Before the diagnostic production visit, the seven-day Vercel Analytics view reported 24 visitors,
218 page views, and 29% bounce rate. It recorded two `SignupIntent` visitors—one direct and one from
Clever Crump—but no `SignupStarted`, `SignupSubmitted`, or account creation. It also recorded one
`LoginFailed` visitor under the old generic `request_failed` reason, one `LoginCompleted` visitor,
and two login submissions. Both signup-intent visitors were desktop/Windows in this very small
sample.

The service-role 30-day product reports independently returned zero comparable production account
creations, activation records, lifecycle rows, payer evidence, or attribution cohorts. All seven
existing product accounts remain legacy/internal-test-era profiles. These observations prove that
Ask Crump does not yet have a decision-grade acquisition cohort; they do not prove a conversion
rate, broad login defect, or customer behavior. The live product inspection added one signed-in app
visit and therefore is excluded from the pre-inspection traffic statement above.

## Verification

- All **872 Python tests** were collected: **870 passed** and two environment-dependent tests were
  skipped.
- All **49 JavaScript files** and all six attribution runtime cases passed.
- Focused authentication coverage passed 35 checks.
- A real-browser, real-controller fixture passed seven failure cases: credentials, verification,
  rate limit, session establishment, timeout, offline, and unknown fallback. Every case retained a
  visible user-facing error and produced no browser error.
- Executable backend coverage proves the expected 401 and 403 responses carry stable codes while
  preserving the existing public messages.
- Ruff, Python compilation, production preflight, native web-bundle generation, and diff integrity
  passed.
- The exact production deployment is `READY` on all six aliases.
- The live app and versioned controller asset returned HTTP 200 and exposed the exact new classifier.
- Main CI, Android unsigned-store-bundle verification, and iOS unsigned-Release source/privacy
  verification passed.
- The initial production window contained no runtime-error cluster and no warning/error/fatal log.
- Verification created no account, login session, email, customer event, Project, file, provider
  request, credit charge, subscription, payment, or database write. Synthetic credentials were used
  only inside the local browser fixture.

## Release identity

- Feature commit: `734f6473e793e19b3140e36345ea5deab2ac210f`
- Production deployment: `dpl_7fVb6KtDrRMvf77Vnztyjr1U2f5t`
- Status: `READY`
- Main CI: `34238088527`
- Android verification: `34238088610`
- iOS verification: `34238088590`
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project/main aliases

## Remaining acceptance work

1. Observe the next legitimate `LoginFailed` category and use repeated evidence before changing
   login UX or backend behavior.
2. Keep the prior 24-visitor/two-signup-intent sample out of conversion claims; it is too small and
   may contain founder/test activity.
3. Marketing should increase measured, privacy-safe account-entry traffic while product preserves
   current signup-intent attribution and reports the first real registration cohort.
4. Keep lifecycle email off and paid acquisition held until legitimate cohorts produce activation,
   decision-grade value, payer, and elapsed D1/D7 denominators.
