# Decision-grade growth evidence release — 2026-08-31

## Outcome

The service-role weekly cohort export now keeps technical activation separate
from evidence that a new account reached a useful outcome. It adds aggregate
24-hour counts for:

- independent useful feedback;
- decision-grade value: technical activation plus either independent useful
  feedback or the existing natural `AhaReached` milestone;
- active Project creation;
- a ready file attached to an active Project;
- any ready owned file; and
- provider-backed payers.

Checkout events remain diagnostics. They do not establish a payer. A payer
requires either a currently active paid subscription backed by Stripe or
RevenueCat, or a positive `credit_purchase` ledger row backed by one of those
providers. Recognized revenue, refunds, and variable cost remain unavailable
until an authorized finance source supplies aggregate period totals.

## Privacy and access boundary

`public.product_weekly_attribution_export` remains `security invoker` and is
executable by `service_role` only. The return contract contains controlled
attribution labels and aggregate counts—no account identifiers, customer
content, filenames, Project/file identifiers, payment objects, URLs, referrers,
sessions, or arbitrary metadata.

The cohort is bounded by the server-derived account registration environment,
excludes deleted and internal accounts by default, and preserves the existing
measurement start of `2026-08-23 09:10:55.602863+00`.

## Production evidence

- Supabase migration: `20260901012708 decision_grade_growth_snapshot`.
- Exact replacement window checked from `2026-08-31 20:00:00+00` through the
  release verification time: zero eligible production cohort rows and zero
  accounts, activation, value, Project/file, or payer counts.
- The full post-boundary production cohort also returned zero rows at release
  verification time. This is a valid empty result, not evidence about accounts
  outside the bounded environment-aware cohort.
- Function ACL verification: `anon=false`, `authenticated=false`,
  `service_role=true`.
- Post-DDL Supabase advisors: 55 pre-existing informational security notices and
  56 pre-existing informational performance notices; no finding relevant to
  this function or migration.

## Validation

- 684 Python tests passed.
- 47 JavaScript files passed the integration contract.
- Production build preflight passed.
- The release-boundary verifier confirmed the exact changed-file allowlist and
  all 35 aggregate return fields.
- `git diff --check` passed.

This release makes the product's weekly operating evidence more honest. It does
not claim acquisition, activation, retention, conversion, or revenue lift. The
first legitimate matched `MarketingLanding` event and its downstream account
cohort remain pending real traffic.
