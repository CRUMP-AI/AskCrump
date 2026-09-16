# Pending registration inbox-gated setup candidate — 2026-09-16

## Decision and lineage

This branch is the only candidate in this line that may receive further review. Commits `7b30421`,
`88b1cc7`, and `cde1893` were independently rejected and must not ship or be cherry-picked alone.
The branch remains `candidate/pending-registration-inbox-setup-20260916`, based on exact production
source `7833d89e2e5ee419fd27757f82c4fff92beed295`.

This superseding change moves the credential/session race boundary into PostgreSQL. It does not apply
that migration anywhere, contact a Supabase project, deploy, push, or write production data.

## Atomic database boundary

The migration `20260916214309_atomic_auth_generation.sql` was generated locally with
`supabase migration new atomic_auth_generation` using Supabase CLI 2.117.0. Its timestamp is after
the required `20260916160711` floor. The generated file was moved into this repository's established
root `migrations/` ledger. It is deliberately **unapplied**. Before any later application, an owner
must perform a fresh remote-ledger check after the production-isolation window and review the exact
release tip.

The migration adds a nonnegative `auth_generation` to both `public.users` and `public.sessions`.
Existing rows backfill to generation zero through the non-null default.

Two private functions provide the shared user-row serialization boundary:

- `public.persist_auth_session(...)` locks the non-deleted user row only when its current generation
  equals the generation whose password was verified. It then persists or device-rotates the session,
  records that generation, and applies the existing 20-session bound inside the same transaction.
- `public.consume_password_reset(...)` conditionally consumes the presented unexpired token, changes
  the password, advances the generation, clears both token families, and revokes every active session
  inside one transaction. If the account was unverified, the same update clears the pre-inbox
  `full_name` and terms fields; verified-account recovery preserves owner-authorized metadata.

Both functions are `SECURITY INVOKER`, use an empty fixed `search_path`, and fully qualify table
objects. Execution is explicitly revoked from `PUBLIC`, `anon`, and `authenticated` (and reset before
granting), then granted only to `service_role`. Existing RLS, table grants, and policies are unchanged.

All production session creation callers—password login and verification-link handoff—now use the
generation-checking RPC. If reset wins before a stale login persists, login returns the existing
generic invalid-credentials 401 and creates no session or cookie. If login persistence wins first,
reset waits on the same user row, then advances the generation and revokes that session. Session
authentication also rejects and revokes any row whose stored generation differs from its user.

The verification route retains its token-ownership recheck and exact-session cleanup. The intentional
15-minute mail-scanner replay window remains, but password reset clears that token and advances the
generation atomically with session revocation.

## Pending registration and delivery behavior

Every syntactically valid registration computes exactly one submitted-password hash before the
existence branch. New and existing-pending requests return the same HTTP 200 generic finish-setup
shape for email success, false return, `EmailDeliveryError`, and unexpected email exceptions. This is
a response-shape and one-password-hash CPU-work guarantee, not a constant-time or identical-outbox
claim: new registration and pending recovery still execute different database/email paths.

If two first registrations race after both read no row, the normalized-email unique-key loser now
re-reads the winner and returns the same bounded generic success. The ordinary pre-existing verified
account 409 remains unchanged.

Repeat registration never changes the pending password, profile, consent, attribution, or
verification token. It may issue only an inbox-delivered reset/setup token. If delivery is false or
throws, cleanup conditionally clears that exact undelivered token; it never restores a predecessor
token that another overlapping request may have consumed or superseded. A newer token, verification,
or completed reset wins the compare-and-set cleanup.

## Acceptance evidence

Deterministic route and contract tests cover:

- reset-before-login: the old password was already verified in Python, but the stale generation RPC
  loses, returning generic 401 with no persisted session or cookie;
- login-before-reset: the session is persisted at generation zero, then reset advances to one and
  leaves no active old-generation session;
- simultaneous same-token reset replay: only one password update and revocation wins;
- a superseded reset token cannot update the password or revoke sessions;
- unverified recovery clears unproven profile/terms metadata, while verified recovery preserves it;
- verification/reset interleavings and scanner replay retain no stale active session;
- same-installation session rotation still converges through the atomic RPC;
- simultaneous first-registration unique conflict returns generic success with one submitted-password
  hash unit;
- new-versus-pending response parity for all four email outcomes;
- failed setup delivery never resurrects a predecessor token and cannot clobber a newer token; and
- the migration inventory, user-row lock, generation predicates, atomic reset/revocation order,
  invoker/search-path posture, and service-role-only grants.

Validation on this exact worktree:

- full Python suite: **1,160/1,160 passed** using the repository-pinned Argon2 25.1.0 / bindings 26.1.0
  in an isolated temporary dependency directory;
- focused authentication, concurrency, registration, verification, recovery, and migration-contract
  tests passed;
- full Ruff check passed;
- the migration parsed as 16 PostgreSQL statements with `pglast` 7.10;
- production preflight passed, including **54 JavaScript files** and **21/21** store-submission
  self-tests;
- the real production-script browser matrix passed **48/48** verifiers in installed Microsoft Edge;
- native web-bundle creation, client credential-boundary scanning, source privacy verification, and
  store metadata source checks passed.

The direct signed store-submission gate remains expectedly unavailable in this source-only worktree:
platform projects, signed artifacts, screenshots, evidence, reviewer access, and release keys are not
present. No artifact or credential was fabricated to bypass it.

All tests used local synthetic fixtures. No production account, email, credential, session, database
row, event, payment, migration, deployment, or remote ledger was created or changed.

## Residual risks and release gate

- The migration received PostgreSQL grammar parsing and source-contract coverage but was not executed
  against a local or remote PostgreSQL instance in the original isolated pass. The loopback-checked,
  ownership-attested `scripts/verify_atomic_auth_generation_postgres.py` gate and the
  `atomic-auth-postgres` CI job now provide a disposable PostgreSQL 15 migration apply, privilege
  inspection, and real multi-connection concurrency probe. The CI job owns a host-networked
  container bound only to runner loopback; the harness also rejects directly addressed non-loopback
  endpoints. Because an address check cannot detect a loopback proxy or tunnel, local operators must
  explicitly attest that they own the disposable cluster. A passing run is still required before
  production approval; the source-review host had no Docker, PostgreSQL, Supabase CLI, or installed
  WSL distribution.
- Deployment order is mandatory: apply the reviewed migration first, verify its function privileges
  and columns, then release the backend that calls the RPCs. Rolling backend first would fail login
  and password reset because the functions would not exist.
- An authentication request already in progress when reset commits may finish its current authorized
  operation; subsequent requests fail through revocation/generation checks. The database boundary
  specifically prevents a stale password verifier from creating a surviving post-reset session.
- Failed pending-email delivery intentionally invalidates the reset token it just wrote and does not
  restore an older token. In overlapping delivery attempts this can make an ambiguously accepted
  older email link unusable. It fails closed; the preserved verification link, original password, or
  a fresh forgot-password request remains the recovery path.
- A caller can still cause bounded transactional-email nuisance and token rotation within existing
  per-identity and per-IP rate limits.
- The scanner-tolerant verification replay window remains intentional; inbox-link possession can
  create another session during that short window unless password reset clears it first.

Release only the reviewed branch tip containing the migration and backend changes, after the fresh
ledger/staging gate above. Do not release any rejected predecessor commit by itself.
