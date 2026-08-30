# Artifact journey cohort boundary — 2026-08-30

## Decision

The production artifact reliability snapshot now measures real production accounts by default.
Owner, demo, preview, development, and deleted accounts cannot silently enter the production
totals used to decide whether artifact creation and download are healthy enough to promote.

## Server-authoritative boundary

Migration `20260830192948_artifact_journey_cohort_boundary.sql` replaces the three-argument
aggregate with a backward-compatible four-argument version. Existing three-argument calls keep
working through the default value of `p_include_internal => false`.

For every counted event, the report requires:

- the allowlisted event environment to equal the requested environment;
- the owning account's server-derived registration environment to equal that same environment;
- the owning account not to be deleted; and
- no internal entitlement unless a service-role operator explicitly asks to include internal
  accounts for diagnostics.

The response remains aggregate and content-free. It returns only allowlisted artifact categories,
counts, and conversion rates. Execution remains revoked from public, anonymous, and authenticated
roles and granted only to the service role.

## Product implication

The demo account is intentionally registered as `preview` and marked internal. Recording a demo
against the live product can no longer create a false production artifact success. A zero-row
external report is therefore an honest absence of customer evidence, not a mixture of customer and
team behavior.

## Acceptance evidence

- Static regression coverage verifies the exact registration-environment, deletion, and internal
  account predicates plus the service-role-only, content-free return contract.
- The migration was applied after the API repository's `20260830192411 add_public_data_cache`
  migration and is recorded remotely as `20260830192948 artifact_journey_cohort_boundary`.
- The live database exposes only the four-argument/defaulted signature, uses invoker security with
  an empty search path, denies execution to anonymous and authenticated roles, and grants it to
  the service role.
- The post-migration external production snapshot returned no rows, preserving the honest current
  baseline without creating a synthetic customer or product event.
- Supabase advisors reported only informational findings: 54 security and 57 performance, with no
  warning or error caused by this change.
