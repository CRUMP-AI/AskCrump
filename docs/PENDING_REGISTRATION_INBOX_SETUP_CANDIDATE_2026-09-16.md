# Pending registration inbox-gated setup candidate — 2026-09-16

## Decision

Hold the earlier repeat-registration password replacement design. This isolated candidate instead
keeps the original pending account under the original inbox owner's control.

Candidate branch: `candidate/pending-registration-inbox-setup-20260916`

Exact clean base: `7833d89e2e5ee419fd27757f82c4fff92beed295`

## Security outcome

When registration is submitted for an existing unverified email, the server now discards the
submitted password, name, consent, plan, destination, and acquisition values. It preserves the
existing password hash and verification token, then conditionally writes only a one-hour password
reset/setup token while the account is still unverified. The existing reset endpoint and UI make the
password change only after the person opens the inbox-delivered link.

The registration response uses the same generic finish-setup copy for a newly created account and an
existing pending account. The pending UI no longer promises that the password supplied to the latest
registration attempt can be used.

The conditional write closes the verification race: if verification wins before the setup-token
write, no setup email is sent. A false delivery result, a typed delivery exception, or an unexpected
delivery exception triggers a compare-and-set rollback that restores the prior reset state only while
the account is still unverified and still contains this request's token. A newer recovery request,
completed reset, or verification therefore cannot be overwritten by the rollback.

## Acceptance evidence

Focused authentication coverage proves:

- a second actor cannot replace the original pending password, profile, consent, attribution, or
  verification token by registering the inbox owner's email;
- the original inbox owner can still use the preserved verification link and original password;
- the inbox setup link accepts only the password chosen after inbox proof, verifies the account,
  clears both token families, revokes sessions, and cannot be replayed;
- an expired setup link cannot change the password;
- delivery `false`, `EmailDeliveryError`, and an unexpected exception restore the exact original
  pending record;
- a verification-wins race emits no reset email; and
- a failed-delivery rollback cannot clobber a newer reset token.

Validation completed on this exact worktree:

- 49 focused Python tests passed across pending setup, authentication recovery, registration consent,
  attribution, destination handoff, release hardening, and frontend authentication policy.
- The complete Python suite passed all 1,143 tests with the repository dependency environment.
- Ruff passed for every changed Python file.
- All 54 JavaScript validation files passed, including the service-worker cache contract at `r249`.
- The complete production-script browser control matrix passed 48/48 verifiers against installed
  Microsoft Edge.
- Production preflight, native web-bundle creation, client credential-boundary checks, store metadata
  source checks, and native privacy-source verification passed.
- Store-submission self-tests passed 21/21. No release artifact submission was attempted.

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

Ship only if review confirms that the repeated-registration branch changes no account-owned fields
other than the conditional reset-token tuple and timestamp, the complete gates remain green, and a
human owner verifies the inbox setup and preserved-verification paths on the exact release candidate.
