# Facebook cell early technical observation — 2026-09-16 18:59 UTC

State: **TECHNICALLY HEALTHY / CONVERSION AND DISTRIBUTION UNDECIDED**

## Boundary

The live Ask Crump Facebook Feed cell began at 2026-09-16 17:28 UTC. This checkpoint is an early,
read-only reliability and exact-attribution observation through 2026-09-16 18:59:24 UTC. The
governing 24-hour isolation window remains open until 2026-09-17 13:28 EDT.

No post, profile, campaign, product, deployment, database, customer record, account, event, payment,
credit, provider job, or public content was created or changed for this observation.

## Vercel production reliability

The connected Vercel observability API returned:

- no grouped runtime-error cluster;
- no warning, error, or fatal application log;
- at least 100 HTTP 200 responses in the grouped status view;
- empty explicit 3xx, 4xx, and 5xx request-path groups; and
- a 100-request visible path breakdown of 92 manuscript cron requests, four sync pulls, and one each
  for lifecycle decision, presence preferences, check-in cron, and billing credit status.

The grouped status endpoint reported two distinct status values while displaying only the leading
200 group. Because explicit 3xx/4xx/5xx queries were empty, this record does not invent the hidden
second value or claim that every request was 200.

This rules out an observed server/runtime failure in the early campaign window. It does not measure
static page exposure, browser rendering, post reach, or conversion.

## Server-authoritative attribution

A read-only aggregate query called only
`public.product_weekly_attribution_export(2026-09-16 17:28:00+00, now(), 'production', false)` and
filtered to the exact registered tuple:

`facebook / organic-social / rough-to-useful-v2 / rough-to-useful-current-feed / projects`

The function returned no row. The query requested only bounded aggregate counts and returned no
account identifier, email, prompt, response, filename, Project name, URL, customer content, or raw
event row.

## Decision

Preserve the live cell and production unchanged. No exact-tuple account exists yet, but the exposure
denominator is unavailable and the 24-hour window is incomplete. At the boundary, pair legitimate
Facebook reach/view evidence with the same exact-tuple aggregate. If exposure is under 25 viewers
and the aggregate remains empty, classify the cell as under-distributed rather than as a product
conversion failure.
