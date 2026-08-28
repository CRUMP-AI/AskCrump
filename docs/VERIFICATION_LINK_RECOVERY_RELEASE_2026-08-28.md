# Ask Crump verification-link recovery release

**Date:** 2026-08-28

**Release:** 5.9.47 / native build 50947

**Code commit:** `a3ae2def5c9f1cdce2c6230e68af6395c0d35a2d`

**Production deployment:** `dpl_EBxtmgbDcy7y7yeEhijKBvNHMbU8`

## Outcome

A person who returns through an invalid, expired, already-used, or security-scanner-consumed email
verification link no longer reaches a dead-end error. The signed-out screen now keeps a visible
recovery region, focuses the email field, offers the existing resend action, and truthfully explains
that the person can sign in if verification already completed.

This correction improves the recoverability of the activation journey. It does not prove improved
signup or verification conversion.

## Decision evidence

- The protected, content-free comparable external funnel still contained zero accounts, and the
  aggregate artifact-journey report contained no rows at the last protected refresh.
- The verification route intentionally clears the token hash and expiry after a successful use.
  Therefore a second click—or an email security scanner opening the link first—can return through the
  generic failed state even when the account is already verified.
- The previous failed state displayed only an invalid-or-expired alert. It did not expose the existing
  resend control or direct the user toward sign-in.

The evidence justified a client recovery correction, not a change to token lifetime, single-use
semantics, authentication policy, or server verification rules.

## Reproduced gap

A loopback fixture loaded the real authentication resilience and controller scripts with
`?verification=failed`. Before correction, the browser exposed the login form and the alert “That
verification link is invalid or expired,” but no recovery region or resend action.

The fixture contains only loopback URLs, uses a local mocked resend endpoint, and supplies the
synthetic address `recover@example.test`. No production account, verification token, or email was
used.

## Correction

- The failed-link message now covers invalid, expired, and already-used links without claiming which
  condition occurred.
- The existing verification-recovery region becomes visible for that result and explains both safe
  next actions: resend or sign in if verification already completed.
- Focus moves to the login email field so keyboard and assistive-technology users can recover without
  searching the page.
- The recovery region now has an accessible title and region relationship.
- The existing resend response remains generic: “If verification is needed, a new email has been
  sent.” This avoids exposing account or verification state.
- Release metadata advanced to 5.9.47, native build 50947, and service-worker cache revision r81.

Token issuance, token lifetime, single-use semantics, password rules, registration, authentication,
cookies, rate limits, pricing, entitlements, analytics, database schema/RLS, and payments are
unchanged.

## Browser verification

- Before correction, the failed-link query produced an alert without a visible recovery action.
- After correction, the email field was active and the page exposed the recovery title, instructions,
  and resend button.
- Submitting the synthetic address to the local mock produced the generic success message without
  revealing whether the account exists or is already verified.
- The fixture uses no production URL, user credential, token, or account write.

## Automated and hosted verification

- All 354 backend tests passed.
- Backend/test lint and Python compilation passed.
- All 44 JavaScript validations passed.
- Production preflight, native web-bundle, store-metadata, and signing-secret-control checks passed.
- Local Android source verification passed for 5.9.47/build 50947 and API 36.
- Hosted CI run `33143924537` passed.
- Hosted Android run `33143924544` generated and compiled the unsigned 5.9.47/build 50947 release
  bundle under the existing Java 21/API 36 controls.
- Hosted iOS run `33143924530` generated 5.9.47 and compiled the unsigned Release configuration on
  macOS.

The existing external store gates remain: RevenueCat public configuration, Firebase
`google-services.json`, production signing credentials, owner developer accounts, exact signed-device
testing, screenshots, declarations, and final submission approval.

## Production verification

- Deployment `dpl_EBxtmgbDcy7y7yeEhijKBvNHMbU8` reached `READY` on production.
- `/api/health` returned HTTP 200, `Cache-Control: no-store`, and version 5.9.47.
- `/app` returned HTTP 200, references the 5.9.47 controller, and contains the accessible recovery
  title and instruction.
- The live versioned controller contains the truthful failed-link copy, exposes the recovery region,
  and focuses the email field.
- The live service worker contains release 5.9.47, cache revision r81, and
  `no-store, must-revalidate, no-cache` headers.
- The initial one-hour scan found no runtime error cluster and no warning/error/fatal application log
  for the deployment.

## Data and privacy

No production signup, account, verification, login, event, message, Project, artifact, or payment was
created by verification. The browser fixture ran entirely on loopback with a synthetic
`example.test` address. No token, credential, identifier, email content, or account state was
retained in this evidence. No Supabase schema, policy, row, or event changed.

## Rollback

The immediately preceding known-good 5.9.46 production deployment is
`dpl_EAGrNS76BCCDAR1uBJQVaDJxeEGa`. A rollback should restore its matching service-worker and native
version metadata.

## Remaining evidence

1. Complete one owner-run explicit sign-out followed by fresh manual credential entry on production
   5.9.47. Do not capture or share the password or verification code.
2. Observe the first legitimate post-boundary signup and verification journey before diagnosing or
   changing the next funnel boundary.
3. Keep the existing single-use server verification policy unchanged unless a separate security and
   privacy review justifies a policy change with explicit owner approval.
