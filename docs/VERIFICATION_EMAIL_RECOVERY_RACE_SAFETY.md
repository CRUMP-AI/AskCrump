# Verification email recovery race safety

Status: implemented behind two hard-off gates. `VERIFICATION_EMAIL_RECOVERY_RELEASED`
remains `False`, and `CRUMP_ENABLE_VERIFICATION_EMAIL_RECOVERY` defaults to
`false`. This change does not enable a provider, database migration, cron, or
production path.

## State and token invariants

- The original verification token remains authoritative during claim and
  preparation. Preparation stores only a one-way SHA-256 digest of the fresh,
  high-entropy recovery token in the forced-RLS private ledger.
- An exact preparation replay with the same environment, claim, digest, and
  expiry is success-equivalent. A committed response loss therefore cannot
  consume a second attempt or suppress the provider send.
- `authorize_verification_email_recovery_dispatch` is the database
  linearization point immediately before provider I/O. A delivered, permanent,
  failed, suppressed, complaint, or verified-account commit before
  authorization wins and prevents the send while preserving the original
  token.
- Once authorization commits, the provider request wins. Post-authorization
  callbacks advance only the monotonic outcome and cannot revoke the in-flight
  send. The external HTTP request cannot be atomic with Postgres; the durable
  authorized digest bridges that boundary. It can verify the account even if
  the provider accepted the request but the worker lost the completion
  response.
- Provider failure, worker crash, or lease cleanup never rotates the original
  token. The attempt count is permanently bounded to one.
- Recovery consumption never replaces the original token digest. Whichever
  delivered link is opened first marks the account verified and bounds both
  links to the same remaining, at-most-15-minute handoff window. Either link
  and its scanner-safe replay can then issue a session during that window;
  expiry, environment mismatch, or a token bound to another user fails closed.

## Environment and webhook boundary

- Every claim, preparation, authorization, completion, failure, consumption,
  and cleanup transition takes an allowlisted environment and filters the
  private row by it.
- Outgoing transactional messages carry `delivery_environment` and
  `message_kind` as allowlisted provider tags. The webhook reads environment
  only from the signature-verified payload, never from the receiver
  deployment's settings.
- The wrapper resolves an idempotent signed event by provider-event hash or
  payload fingerprint. Identical payload replays under another event ID ACK;
  any semantic mismatch fails closed.
- Outcome precedence is monotonic. Complaint, suppression, permanent failure,
  and failure cannot be downgraded by late delivery or transient callbacks.
- Registration and the signed-event wrapper take the same transaction advisory
  lock keyed by allowlisted environment plus provider-message digest. This
  closes the interleaving where each transaction could otherwise miss the
  other. Registration also reconciles an already-committed callback, and the
  environment-scoped claim path performs an eventual reconciliation pass for
  any historical `sent` row left beside a signed event.

## Activation prerequisites

Startup rejects enabled recovery unless the Resend API key, a verifier-valid
Resend webhook secret, the cron secret, and an allowlisted environment are all
present. The shared cron gives account deletion first priority, then Code and
manuscript work; verification recovery uses only otherwise-idle capacity.
Activation still requires the reviewed PostgreSQL 17 gate, provider webhook
configuration, and an explicit source-lock change in a separate release.
