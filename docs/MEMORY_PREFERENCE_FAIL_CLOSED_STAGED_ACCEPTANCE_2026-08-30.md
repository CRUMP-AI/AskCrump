# Memory preference fail-closed staged acceptance

Date: 2026-08-30  
Status: accepted locally; not committed, deployed, or migrated

## Outcome

Turning off **Use saved memory** or **Learn explicit details** now reduces memory
permission immediately on the next chat request, even when the durable preference
service is temporarily unavailable. Ask Crump no longer reports a preference write
as successful when Supabase did not accept it.

## Defect closed

The prior preference service swallowed database write failures and returned the
desired value as though it were durable. The browser kept only an ordinary local
copy and had no pending retry record. It also sent `memoryEnabled` on chat requests
but omitted `autoLearn`. A temporary outage could therefore leave the UI showing
learning off while a later request still followed an older server-side
`auto_learn=true` preference.

A failed preference read also used defaults. If the write recovered immediately
afterward, unchanged adjacent settings could have been overwritten with those
defaults.

## Staged behavior

- Preference booleans accept only literal `true` or `false`; string and
  conflicting camel/snake values return a 400.
- Preference updates require an authoritative current read before writing the
  complete row.
- Read or write failure returns
  `INTELLIGENCE_PREFERENCES_UNAVAILABLE` with HTTP 503 and `shouldRetry: true`.
- The signed-in browser retains only the five fixed preference fields in an
  account-scoped pending record and retries it during the next preference
  hydration.
- A pending record is cleared only after the matching snapshot succeeds; a stale
  response cannot clear or overwrite a newer choice.
- Every chat request includes literal `memoryEnabled` and `autoLearn` values.
- Request-level values may reduce durable memory permission but cannot expand a
  server-disabled `autoLearn` preference. Nonboolean chat values fail closed.
- No prompt, response, memory content, filename, raw URL, customer identifier, or
  provider detail is added to the pending record.

## API coordination boundary

AskCrump-API commit `04901a8` documents the private v0.25+
`suggest_memory` proposal contract and an unpublished Node SDK. Broad app
integration is deliberately deferred. The API path remains private/internal alpha
until the app owns a server-side feature flag, exact Save/Dismiss confirmation,
duplicate-submit reconciliation for memory creation, edit/delete controls,
content-free rollback telemetry, and a coherent release. Nothing in this staged
repair calls the API memory tool or changes the current authoritative app memory
system.

## Verification

- Full Python suite: 681 passed.
- Focused intelligence, route, and launch-packet suite: 26 passed.
- JavaScript contract validation: 48 files passed.
- Diff integrity: passed; the existing `public/landing.js` CRLF normalization
  warning is unrelated.
- The Search Console packet test now normalizes whitespace and passes without
  changing packet meaning.
- An isolated content-free replay fixture covers the outage, chat override, retry,
  and clear sequence. The connected desktop browser runtime could not start
  because its sandbox helper failed before browser selection, so this record makes
  no rendered-browser claim.

## Release boundary

No production database, Supabase migration, account, memory, conversation, model
request, event, payment, price, plan, social profile, publication, or Search
Console property was changed. Commit and deployment remain a separate
action-time decision.
