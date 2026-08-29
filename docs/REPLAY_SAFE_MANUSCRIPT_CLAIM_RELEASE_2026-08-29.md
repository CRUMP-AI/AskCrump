# Replay-safe manuscript claim release — 2026-08-29

## Outcome

Ask Crump's scheduled manuscript worker can now recover from a transient Data API
response without claiming a second job or leaving a successfully claimed job hidden
until its lease expires. The application retries only this explicitly replay-safe
lease operation; ordinary writes and RPC calls remain single-attempt.

Production release:

- behavior commit: `d9e318990e179a581710dcae71a26ab8289ece96`
- Vercel deployment: `dpl_86QGTpLX4duvhqngCqTeoKuWCUYY`
- deployment state: `READY`
- production version: `5.9.76`
- Supabase migration version: `20260829184012`

## Evidence before the correction

The production runtime review found three HTTP 503 responses from
`GET /api/cron/manuscripts` at 18:15:05, 18:16:05, and 18:25:05 UTC. All three
belonged to deployment `dpl_G53uYtpnAR7sgJTkr8uRBvzyKnJe` and reported a database
503. User-facing authentication, chat, Projects, synchronization, and billing routes
were not part of that cluster.

The corresponding Postgres window contained normal checkpoints and no error, fatal,
panic, or connection-exhaustion record. Current Supabase API calls had recovered to
200. Current Supabase documentation maps PostgREST `PGRST001` to an HTTP 503 database
or schema-cache connection failure, so the evidence supported a transient Data API
boundary rather than a database-engine fault.

The prior worker used a POST RPC that generated the lease token inside the database.
It correctly was not retried, because an uncertain write response can hide a committed
side effect. That left a narrow failure mode: a committed lease whose response was
lost could remain unavailable until its seven-minute expiry.

## Correction

- The worker generates one UUID claim token before the request and sends that exact
  token with every bounded retry attempt.
- A private two-argument `claim_manuscript_run` overload first returns the same
  still-live lease for that token, then uses the existing atomic `FOR UPDATE SKIP
  LOCKED` claim path when no replay exists.
- The one-argument function remains during deployment overlap. Both overloads are
  security invoker; anonymous and authenticated execution are denied, and only the
  service role may execute them.
- The database transport keeps retries disabled for writes and RPCs by default.
  Only the manuscript lease passes the explicit replay-safe flag.
- Database failure logs now include only a validated categorical provider code,
  retry state, and attempt count. Provider messages, SQL, prompts, content, account
  data, and identifiers remain excluded.

No manuscript content, Project, file, account, authentication, entitlement, credit,
payment, provider-selection, or user-facing workspace behavior changed.

## Verification

- The migration was applied before the application deployment. Live inspection
  confirmed both overloads use security invoker, deny anonymous/authenticated
  execution, and allow the service role.
- Supabase security and performance advisors returned zero errors and zero warnings;
  their remaining results were informational.
- 472 Python regression tests passed, including identical-payload retry, ordinary
  write non-retry, replay-order, function-privacy, and log-redaction coverage.
- 45 JavaScript files passed syntax and integration validation.
- Explicit Python compilation, production preflight, native web-bundle creation, and
  Apple/Google store-metadata source checks passed.
- The native release verifier reported only the existing owner-controlled store
  blockers: missing iOS project on this Windows host, missing RevenueCat public keys,
  and missing Android FCM configuration.
- Canonical production health returned HTTP 200 on version `5.9.76`.
- After deployment, two natural scheduled calls returned HTTP 200 at 18:47:05 and
  18:48:05 UTC. Supabase independently recorded both corresponding
  `/rest/v1/rpc/claim_manuscript_run` calls as HTTP 200.
- The exact deployment's initial observed window contained three HTTP 200 responses,
  no warning/error/fatal log, and no manuscript runtime-error cluster.
- Verification did not manually invoke the claim function and created no account,
  conversation, message, manuscript, Project, file, artifact, checkout, payment, or
  synthetic product event.

## Outcome boundary

The deterministic uncertain-response behavior is corrected. Continue watching the
scheduled route for 24 hours and compare any recurrence by deployment, categorical
provider code, attempt count, and final HTTP status. A future 503 that exhausts the
bounded retries remains a real availability event and must not be hidden or converted
to a false success.

