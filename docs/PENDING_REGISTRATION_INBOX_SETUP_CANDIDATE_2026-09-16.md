# Pending registration inbox-gated setup candidate — 2026-09-16

## Decision

Hold the earlier repeat-registration password replacement design. This isolated candidate instead
keeps the original pending account under the original inbox owner's control.

The first candidate commit, `7b30421d591a9e219a8d122c9ee3f60692ef83fa`, was independently
rejected for non-atomic reset-token consumption, trust of metadata collected before inbox proof, and
observable new-versus-pending registration failure behavior. It must not ship by itself. The
follow-up commit `88b1cc72c0662b4e88b064066ad833855af5bd84` closed those findings but was
then rejected for a verification/session interleaving: a stale verification read could resume after
password reset cleared both token families and revoked sessions, then create a new surviving session.
Neither earlier commit may ship alone. The latest follow-up containing this evidence supersedes both.

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

Email verification now captures the presented token hash and comparison time once. Its first-use
update condition includes user ID, still-unverified state, the presented token hash, and an expiry
later than that captured time. A returned row is required; if a concurrent mail-scanner click won,
the route accepts only a freshly read, verified row that still owns the same unexpired token. This
preserves the intentional 15-minute scanner/replay window without accepting a password-reset-cleared
token.

The verification session is persisted before a second token-ownership read. If password reset wins
before or during session creation, that read fails and the route revokes the exact new session by its
session ID, user ID, and raw-token hash before returning a failure redirect with no cookie. If reset
wins after the read, the session already exists and reset's user-scoped revocation necessarily sees
it. A concurrent login that rotates the same installation is protected by the exact token filter.

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
- password reset winning after verification's initial token read prevents session creation and emits
  no cookie;
- password reset winning after verification session persistence but before the ownership recheck
  leaves no active session, revokes the exact created token, and emits no cookie;
- simultaneous mail-scanner verification reads have one conditional verification-update winner while
  both retain the intentional short replay handoff and receive valid sessions;
- ordinary first-click verification and sequential scanner replay still issue the expected workspace
  session while retaining the shortened verification token;
- an expired setup link cannot change the password;
- new and existing-pending registration perform one submitted-password Argon2 hash and return the
  same status and copy under success, false-return, typed exception, and unexpected-exception email
  outcomes;
- delivery `false`, `EmailDeliveryError`, and an unexpected exception restore the exact original
  pending record;
- a verification-wins race emits no reset email; and
- a failed-delivery rollback cannot clobber a newer reset token.

Validation completed on this exact worktree:

- 64 focused Python tests passed across pending setup, verification/session races, authentication
  recovery, registration consent, attribution, destination handoff, release hardening, and frontend
  authentication policy.
- The complete Python suite passed all 1,155 collected tests with the repository dependency
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
- User-token updates, session persistence, the verification ownership recheck, and session revocation
  are ordered database calls rather than one transaction. A recheck or exact-revocation failure emits
  no new cookie, so the undisclosed session token is unusable. The remaining transactional boundary is
  a password reset that starts after a successful verification recheck and then suffers an
  infrastructure failure while revoking sessions: the already returned verification session could
  survive. Closing that requires a reviewed database RPC/migration that atomically consumes the reset
  token and revokes sessions; no remote migration was applied in this candidate.
- The 15-minute verification-token replay window remains intentional for mail-scanner tolerance. A
  holder of that inbox link can create another session during the window unless password reset clears
  the token first.
- Verified-email registration retains its pre-existing conflict response. Changing that broader
  account-enumeration contract is outside this candidate.

## Release gate

Do not ship or cherry-pick rejected commits `7b30421` or `88b1cc7` alone. Ship only the reviewed branch
tip that includes the latest superseding follow-up, after review confirms both reset and verification
conditional-update filters, the post-session verification ownership check and exact-session cleanup,
unverified metadata clearing, and the generic registration contract. The complete gates must remain
green, followed by a human owner verifying the inbox setup, scanner replay, password reset, and
preserved-verification paths on the exact release candidate.
