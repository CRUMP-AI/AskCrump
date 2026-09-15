# Ask Crump first valid D1 retention observation — 2026-09-15

Observation time: 2026-09-15 00:00:17–00:00:22 UTC

Window: `[2026-09-01 00:00:00 UTC, observation time)`; production only; internal accounts excluded

Privacy boundary: service-role aggregate counts and fixed categorical attribution only. No account
identifier, email, prompt, response, filename, Project name, URL, payment detail, or customer
content was read or retained.

## Result

The first eligible comparable external account returned on D1. Both independent protected reports
agree on the same numerator and denominator:

| Report | D1 eligible | D1 returned | Rate |
| --- | ---: | ---: | ---: |
| `product_growth_funnel_snapshot` | 1 | 1 | 100.0% |
| `product_weekly_attribution_export` | 1 | 1 | 100.0% |

The first post-boundary funnel read completed at `2026-09-15 00:00:17.797009 UTC`; the attribution
read completed at `2026-09-15 00:00:22.427800 UTC`. The corresponding pre-boundary read at
`2026-09-14 23:43:01.922709 UTC` correctly reported D1 eligible/returned as `0/0`. This proves the
completed-calendar-day eligibility boundary opened as designed rather than being inferred from an
intra-day visit.

## Cohort context

The cohort remains one account with immutable acquisition `clevercrump` and no placement,
campaign, creative, or intent label. It reached account creation, event coverage, current
verification, workspace entry, starter intent, and technical activation. Its complete 24-hour value
window still contains:

- zero useful-feedback or needs-work outcome;
- zero durable value, Project creation, Project-file attachment, or ready file;
- zero artifact journey or Project-save/resume milestone;
- zero plan intent, Checkout, payer, or active-paid state; and
- unavailable finance-recognized revenue, refund, and variable-cost totals.

D7 remains ineligible (`0/0`). The observed D1 rate is therefore encouraging one-account
directional evidence, not a stable retention percentage, decision-grade value, product-market fit,
or permission to scale paid acquisition.

## Access and production integrity

Immediately before the boundary, all ten operating-report functions denied execution to `anon` and
`authenticated`, allowed `service_role`, used invoker rights, and pinned an empty search path. The
three-hour production runtime window contained 353 HTTP 200 responses, four expected HTTP 302
private-file handoffs, no 4xx or 5xx route, no warning/error/fatal log, no grouped runtime error, and
no unresolved Vercel feedback.

Supabase advisors returned only the known informational states: 61 RLS-enabled server-only tables
with no client policy and 58 low-traffic unused indexes. These are not permission or removal
instructions; no database object or policy changed during this observation.

## Operating decision

Preserve the current activation and return experience. Do not redesign the interface or scale paid
acquisition from a single returning account. The highest-value evidence gap is now the absence of
decision-grade and durable work: observe the released result-to-Project offer on legitimate traffic,
then distinguish offer visibility, save intent, completion, and later Project resume. Continue
recruiting the remaining consented end-to-end observations and keep D7, payer, and finance gates
separate.

## Recorded evidence verification

- Evidence commit: `e8d58377841ebcedf07b8d209817eded2da823b1` on `main`.
- Complete Python suite: **1,132/1,132** passed; diff integrity passed.
- GitHub CI: run `34911600608` completed successfully.
- Vercel production deployment: `dpl_4BDsnP7ghPHw1PMWTiCBFUA4DTrU` reached Ready for the exact
  evidence commit.
- Canonical homepage, workspace, and health routes returned HTTP 200.
- The exact deployment's initial log window contained three HTTP 200 responses, no 4xx or 5xx
  route, and no warning/error/fatal entry.

No product, database, account, campaign, billing, provider, or customer state changed during this
read-only observation.
