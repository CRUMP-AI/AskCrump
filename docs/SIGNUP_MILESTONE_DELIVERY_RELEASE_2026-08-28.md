# Ask Crump signup milestone delivery release

**Date:** 2026-08-28

**Release:** 5.9.46 / native build 50946

**Code commit:** `6c3e546b74d25b9584db90b63dbaf6f5a74b3303`

**Production deployment:** `dpl_9Mn5E1AtiiNL1FKN345Ag6gF5LkL`

## Outcome

A valid registration submission now produces the complete ordered client milestone sequence even
when a password manager restores the email and password without normal focus or input events:

1. `SignupIntent`
2. `SignupStarted`
3. `SignupCredentialsReady`
4. `SignupSubmitted`

Typed and autofilled paths record each milestone once. The correction improves the truthfulness of
the activation funnel; it does not prove improved signup conversion.

## Decision evidence

- The trailing 24-hour production analytics view contained two `SignupStarted` visitors and no
  `SignupCredentialsReady`, `SignupSubmitted`, or `AccountCreated` event.
- Those anonymous aggregates can include internal or automated visits and are not a conversion rate.
  They justified a deterministic measurement audit, not a signup redesign.
- The protected, content-free comparable external funnel still contained zero accounts, and the
  aggregate artifact-journey report contained no rows at the last protected refresh.

## Reproduced gap

A loopback fixture loaded the real authentication transport and controller, then restored valid
synthetic values before the controller attached—matching a password-manager/autofill path that emits
neither focus nor input events. Before the correction, submitting the valid form recorded:

`SignupIntent, SignupStarted, SignupSubmitted`

The registration request reached only a local mock that deliberately returned a fixture error before
account creation. No production endpoint was called.

## Correction

- The registration controller now uses one-time `trackSignupStarted` and `trackCredentialsReady`
  helpers.
- Normal input continues to record credentials-ready as soon as both fields satisfy the existing
  validation rules.
- A valid submit also invokes the credentials-ready helper before `SignupSubmitted`, closing the
  browser-autofill gap while preserving order and de-duplication.
- The tracked payload remains limited to content-free source, acquisition, plan, and existing
  categorical outcome fields. It does not include an email address, password, or credential value.
- Release metadata advanced to 5.9.46, native build 50946, and service-worker cache revision r80.

Registration behavior, password rules, account creation, verification, authentication policy,
cookies, rate limits, pricing, entitlements, server-side analytics, database schema/RLS, and payments
are unchanged.

## Browser verification

- Before correction, untouched valid autofill skipped `SignupCredentialsReady` and made one local
  registration request.
- After correction, the same untouched autofill path recorded all four milestones in order exactly
  once and made one local registration request.
- After correction, a normal typed path also recorded all four milestones in order exactly once and
  made one local registration request.
- The fixture uses only loopback URLs and `example.test` synthetic values. It contains no production
  URL or user credential.

## Automated and hosted verification

- All 353 backend tests passed.
- Backend/test lint and Python compilation passed.
- All 44 JavaScript validations passed.
- Production preflight, native web-bundle, store-metadata, and signing-secret-control checks passed.
- Local Android source verification passed for 5.9.46/build 50946 and API 36.
- Hosted CI run `33143365291` passed.
- Hosted Android run `33143365303` generated and compiled the unsigned 5.9.46/build 50946 release
  bundle under the existing Java 21/API 36 controls.
- Hosted iOS run `33143365301` generated 5.9.46 and compiled the unsigned Release configuration on
  macOS.

The existing external store gates remain: RevenueCat public configuration, Firebase
`google-services.json`, production signing credentials, owner developer accounts, exact signed-device
testing, screenshots, declarations, and final submission approval.

## Production verification

- Deployment `dpl_9Mn5E1AtiiNL1FKN345Ag6gF5LkL` reached `READY` on production.
- `/api/health` returned HTTP 200, `Cache-Control: no-store`, and version 5.9.46.
- `/app` references the 5.9.46 authentication controller.
- The live versioned controller contains the shared credentials-ready helper and calls it before
  `SignupSubmitted`.
- The live service worker contains release 5.9.46, cache revision r80, and no-store/no-cache headers.
- The initial one-hour scan found no runtime error cluster and no warning/error/fatal application log
  for the deployment.

## Data and privacy

No production signup, account, login, event, message, Project, artifact, or payment was created by
verification. The browser fixture ran entirely on loopback with synthetic values. The earlier funnel
reads were protected aggregate/content-free or anonymous aggregate views; no identifier, content, or
credential was retained in this evidence. No Supabase schema, policy, row, or event changed.

## Rollback

The immediately preceding known-good 5.9.45 production deployment is
`dpl_4gfA9xN9fVRNsPcsAw5NQGCV4UnZ`. A rollback should restore its matching service-worker and native
version metadata.

## Remaining evidence

1. Complete one owner-run explicit sign-out followed by fresh manual credential entry on production
   5.9.46. Do not capture or share the password or verification code.
2. Observe the first legitimate post-boundary signup and compare its ordered client milestones with
   server-authoritative account creation before diagnosing or changing the next funnel boundary.
