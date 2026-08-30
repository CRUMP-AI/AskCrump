# Weekly attribution and growth export release

Date: 2026-08-30

## Outcome

Ask Crump can now connect one registered, content-free first-touch campaign tuple to a
new account and measure later product milestones in service-role-only weekly cohorts.
The release closes the prior gap where campaign and creative labels appeared in links
but were not captured by the account-creation record.

This is measurement infrastructure, not evidence that a campaign converted. The first
production export is empty because no legitimate post-release account has entered the
new cohort. No synthetic production user, event, or revenue record was created.

## First-touch contract

The browser captures one tuple for 24 hours in the current tab:

- acquisition;
- placement;
- registered campaign;
- registered creative family; and
- promised product intent.

Once captured, the tuple is immutable for that tab and time window. A later campaign,
verification return, or existing-account sign-in cannot fill or replace earlier values.
Both browser entry points, the Python boundary, and the database enforce the same exact
campaign registry. Unknown tokens and invalid campaign combinations are discarded.

Only AccountCreated may carry the campaign fields. The application never stores a
referrer URL, search term, prompt, response, filename, Project name, customer identifier,
or arbitrary metadata for attribution.

## Production cohort contract

Migration 20260830171056_weekly_growth_attribution_export.sql adds:

- a server-derived users.registration_environment boundary;
- four attribution fields on product_events with exact constraints;
- the idempotent record_account_created_event writer; and
- the aggregate product_weekly_attribution_export report.

Production cohorts include only accounts whose server-derived registration environment
is production. Preview and development accounts cannot enter production totals even if
the optional analytics write fails. Existing pre-release accounts have no registration
environment and are intentionally excluded rather than guessed or backfilled.

D1 and D7 denominators contain activated accounts only. Eligibility begins at the first
ActivationReached event and requires the full UTC observation window to have elapsed.
The report exposes explicit denominators for activation, durable value, retention, and
paid conversion. Checkout completion is payer evidence, never recognized revenue.

Refund accounts, recognized revenue, and variable cost remain null in the database
report. The operator export accepts those only as explicit aggregate inputs from an
authoritative provider and labels missing evidence not_provided rather than zero.

## Security boundary

Both new functions are SECURITY INVOKER, use an empty search path, and deny execution
to PUBLIC, anon, and authenticated. Only service_role may execute them. The weekly
report returns grouped counts and labels; it returns no account identifier or customer
content.

Post-migration database verification proved:

- the four event fields and registration-environment column are live;
- all eight allowlist and ownership constraints are live;
- anonymous and authenticated execution are denied;
- service-role execution is granted;
- the aggregate function executes successfully; and
- Supabase security and performance advisors report no warning or error introduced by
  this release.

## Operator export

Run scripts/export_weekly_growth.py only in a trusted operator environment with
SUPABASE_URL and SUPABASE_SERVICE_KEY supplied through environment variables.

    python scripts/export_weekly_growth.py
      --since 2026-08-30T00:00:00Z
      --environment production
      --output weekly-growth.json

The generated JSON is aggregate-only. Optional landing, finance, refund, cost, and spend
totals must come from authorized aggregate sources and be supplied explicitly; the script
does not read Stripe, Vercel, prompts, files, or customer records itself.

## Verification

- Full Python suite: 598 passed.
- Focused attribution/release suite: 56 passed.
- JavaScript integration contract: 45 files validated.
- Python lint: passed.
- Production preflight: passed.
- Git whitespace integrity: passed.
- Applied Supabase migration: 20260830171056 weekly_growth_attribution_export.

## Remaining evidence gates

Observe a legitimate external account traverse campaign link → account creation → first
value → durable value, then allow the applicable D1/D7 windows to elapse. Broad paid
acquisition remains held until the activated-user D7 denominator is meaningful and the
privacy-safe weekly export can be reconciled with authoritative revenue, refund, variable
cost, and spend totals. This release does not authorize publication, profile edits, email,
push, or advertising spend.
