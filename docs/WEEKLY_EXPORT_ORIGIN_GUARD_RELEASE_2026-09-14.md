# Weekly export origin guard release — 2026-09-14

## Outcome

Ask Crump's standalone weekly growth exporter now validates the exact HTTPS Supabase project
origin before it constructs a request carrying the privileged server credential. The combined
operating snapshot already enforced this boundary; the standalone path did not.

The shared validator accepts only:

`https://xncftwjfpjskgtwgbgci.supabase.co`

with an optional trailing slash. It rejects HTTP, a different or look-alike hostname, embedded
credentials, an explicit port, a path, a query, and a fragment before any network function is
called. Both reporting entry points now import this one validator, preventing the two secret-bearing
paths from drifting independently.

A follow-up parity review found that the combined operator also validated the reporting window
before its first request, while the standalone command waited until response processing. Both paths
now share one pre-network window validator. Reversed or equal windows, timestamps without a UTC
offset, and environments outside production/preview/development fail before request construction;
valid timestamps are normalized once and reused in the exact RPC payload.

This follows Supabase's current rule that elevated secret/service-role credentials belong only in
developer-controlled backend jobs and must never reach a browser, shipped client, or unintended
destination. No key value was read, printed, rotated, or changed.

## Verification

- exact-origin, adversarial-origin, and pre-network boundary suite: **53/53**;
- complete Python suite: **1,132/1,132**;
- JavaScript validation: **54/54** files;
- Ruff: passed;
- whitespace integrity: passed;
- GitHub CI: `34907390546` and `34908700820`; Python and JavaScript jobs passed.

The executable fixtures prove that every rejected origin causes zero network calls. The valid
fixture proves the exact RPC URL, POST body boundary, 30-second timeout, and privileged headers are
constructed only after origin validation. Separate fixtures prove invalid time windows and an
invalid environment also cause zero network calls.

## Release proof

- Commits: `02d0666bec0fd52986245359335f2413e4303b24` and
  `3ba4de6d1697418ee979dbaf4ebb48b3837d6741`.
- Final production deployment: `dpl_2vGtdumQVKBX8yZUykeyY5KPEjP5`; Ready in production with
  `www.askcrump.com` and both Vercel production aliases assigned.
- The origin-guard deployment's first scoped log window contained four scheduled manuscript
  requests, all HTTP
  200, with zero warning, error, or fatal console entries.

## Boundary and next decision

This is operator-security infrastructure. It changes no application screen, Supabase table,
function, policy, migration, credential, customer record, or metric definition. It adds no network
request and reads no customer content or identity.

The next decision-grade product evidence remains the first comparable D1 read after
`2026-09-15T00:00:00Z`. The protected operator must continue to fail closed if its aggregate or
origin boundary is invalid; do not replace missing retention evidence with an inferred rate.
