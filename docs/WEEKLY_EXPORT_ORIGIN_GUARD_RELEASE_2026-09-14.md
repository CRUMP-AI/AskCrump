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

This follows Supabase's current rule that elevated secret/service-role credentials belong only in
developer-controlled backend jobs and must never reach a browser, shipped client, or unintended
destination. No key value was read, printed, rotated, or changed.

## Verification

- exact-origin and adversarial-origin focused reporting suite: **50/50**;
- complete Python suite: **1,129/1,129**;
- JavaScript validation: **54/54** files;
- Ruff: passed;
- whitespace integrity: passed;
- GitHub CI: `34907390546`; Python and JavaScript jobs passed.

The executable fixtures prove that every rejected origin causes zero network calls. The valid
fixture proves the exact RPC URL, POST body boundary, 30-second timeout, and privileged headers are
constructed only after origin validation.

## Release proof

- Commit: `02d0666bec0fd52986245359335f2413e4303b24`.
- Production deployment: `dpl_3WTogWsAxQ1ZRqoJHG56GJcL8mLk`; Ready in production with
  `www.askcrump.com` and both Vercel production aliases assigned.
- The first deployment-scoped log window contained four scheduled manuscript requests, all HTTP
  200, with zero warning, error, or fatal console entries.

## Boundary and next decision

This is operator-security infrastructure. It changes no application screen, Supabase table,
function, policy, migration, credential, customer record, or metric definition. It adds no network
request and reads no customer content or identity.

The next decision-grade product evidence remains the first comparable D1 read after
`2026-09-15T00:00:00Z`. The protected operator must continue to fail closed if its aggregate or
origin boundary is invalid; do not replace missing retention evidence with an inferred rate.
