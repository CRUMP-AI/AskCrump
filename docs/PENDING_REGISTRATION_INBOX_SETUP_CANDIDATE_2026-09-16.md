# Pending registration inbox-gated setup candidate — 2026-09-16

## Decision

Hold the earlier repeat-registration password replacement design. This isolated candidate instead
keeps the original pending account under the original inbox owner's control.

The first candidate commit, `7b30421d591a9e219a8d122c9ee3f60692ef83fa`, was independently
rejected for non-atomic reset-token consumption, trust of metadata collected before inbox proof, and
observable new-versus-pending registration failure behavior. It must not ship by itself. The
follow-up commit containing this evidence supersedes it and closes those findings.

Candidate branch: `candidate/pending-registration-inbox-setup-20260916`

Exact clean base: `7833d89e2e5ee419fd27757f82c4fff92beed295`

## Security outcome

When registration is submitted for an existing unverified email, the server now discards the
submitted password, name, consent, plan, destination, and acquisition values. It preserves the
existing password hash and verification token, then conditionally writes only a one-hour password
reset/setup token while the account is still unverified. The existing reset endpoint and UI make the
password change only after the person opens the inbox-delivered link.

Every valid registration performs one Argon2 password hash before distinguishing a new address from
an existing pending account; only a new insert retains that hash. New and pending registrations use
the same HTTP 200 generic finish-setup response for successful delivery, a false delivery result,
`EmailDeliveryError`, and an unexpected delivery exception. The pending UI no longer promises that
the password supplied to the latest registration attempt can be used. The pre-existing verified-email
HTTP 409 contract is unchanged.

The conditional write closes the verification race: if verification wins before the setup-token
write, no setup email is sent. A false delivery result, a typed delivery exception, or an unexpected
delivery exception triggers a compare-and-set rollback that restores the prior reset state only while
the account is still unverified and still contains this request's token. A newer recovery request,
completed reset, or verification therefore cannot be overwritten by the rollback.

Password reset now captures the current time once, selects the presented unexpired token, hashes the
new password, and then conditionally updates the user by ID, the same presented token hash, and an
expiry still later than that captured time. A non-returning update is an invalid/expired reset result;
sessions are revoked only after a row is returned. A stale selected token therefore cannot overwrite
a newer token, and simultaneous reuse of one token has exactly one winner.

When that successful conditional update completes an originally unverified account, it also clears
`full_name`, `terms_accepted_at`, and `terms_version`. Those values may have been supplied by a
pre-inbox actor, so the existing terms gate and optional profile setup must collect them from the
verified inbox owner. Ordinary recovery for an already verified account preserves those fields.

## Acceptance evidence

Focused authentication coverage proves:

- a second actor cannot replace the original pending password, profile, consent, attribution, or
  verification token by registering the inbox owner's email;
- the original inbox owner can still use the preserved verification link and original password;
- the inbox setup link accepts only the password chosen after inbox proof, verifies the account,
  clears both token families and unproven profile/terms metadata, revokes sessions, and cannot be
  replayed;
- ordinary verified-account recovery preserves owner-authorized profile and terms metadata;
- a token selected before a newer token is committed cannot change the password or revoke sessions;
- two simultaneous resets that both select the same token produce one password winner, one rejected
  replay, and exactly one session revocation;
- an expired setup link cannot change the password;
- new and existing-pending registration perform one submitted-password Argon2 hash and return the
  same status and copy under success, false-return, typed exception, and unexpected-exception email
  outcomes;
- delivery `false`, `EmailDeliveryError`, and an unexpected exception restore the exact original
  pending record;
- a verification-wins race emits no reset email; and
- a failed-delivery rollback cannot clobber a newer reset token.

Validation completed on this exact worktree:

- 57 focused Python tests passed across pending setup, authentication recovery, registration consent,
  attribution, destination handoff, release hardening, and frontend authentication policy.
- The complete Python suite passed all 1,152 collected tests with the repository dependency
  environment.
- Ruff passed for every changed Python file.
- All 54 JavaScript validation files passed, including the service-worker cache contract at `r249`.
- The complete production-script browser control matrix passed 48/48 verifiers against installed
  Microsoft Edge.
- Production preflight, native web-bundle creation, client credential-boundary checks, store metadata
  source checks, and native privacy-source verification passed.
- Store-submission self-tests passed 21/21. No release artifact submission was attempted.
- The standalone signed-native release verifier remains correctly blocked in this source-only
  worktree because Android/iOS projects and RevenueCat release keys are absent. No project, key, or
  release artifact was fabricated to bypass that external gate.

All tests used synthetic local fixtures. No production account, email, credential, session, database
row, event, payment, or deployment was created or changed.

## Scope and residual risk

No schema, migration, landing page, campaign, pricing, package, entitlement, or API shape outside the
registration success copy changed. No production write, push, or deployment is part of this
candidate.

- A successful repeated request intentionally sends a transactional recovery email. Existing
  per-identity and per-IP authentication rate limits bound this, but a determined caller can still
  cause inbox nuisance and rotate the current reset token.
- Email acceptance and the database write are not one transaction. If a provider accepts the email
  but reports an ambiguous failure, the compare-and-set rollback can make that delivered setup link
  invalid. This fails closed: the original password and verification link remain valid, and the inbox
  owner can request another reset.
- If the rollback database operation itself fails, an undelivered reset token may remain current. It
  still grants no access without the random inbox token and does not alter the original password or
  verification proof.
- Verified-email registration retains its pre-existing conflict response. Changing that broader
  account-enumeration contract is outside this candidate.

## Release gate

Do not ship or cherry-pick rejected commit `7b30421` alone. Ship only the reviewed branch tip that
includes the superseding follow-up, after review confirms the reset update requires the user ID,
presented token, and unexpired timestamp; requires a returned row before session revocation; clears
pre-inbox profile/terms metadata only for originally unverified accounts; and preserves the generic
registration contract. The complete gates must remain green, followed by a human owner verifying the
inbox setup and preserved-verification paths on the exact release candidate.
