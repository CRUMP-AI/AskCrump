# Durable growth measurement release

Released: 2026-09-08

Product commit: `4690062`

Supabase migration: `20260908134343`

Production deployment: `dpl_As2odzPQZibmBRfT24PzBeju9Mbd`

## Outcome

Ask Crump's two service-role growth reports now recognize durable product work when
a best-effort analytics event is absent. The correction is evidence-led: a
content-free production audit found three externally eligible accounts, two with a
completed chat response, and zero `ActivationReached` events. The old reports would
therefore label both completed-response accounts as unactivated.

Both `product_growth_funnel_snapshot` and
`product_weekly_attribution_export` now use the earliest of the existing activation
event and a completed chat job as the activation anchor. Project continuity and
ready, nonempty generated files can similarly establish durable value when the Aha
event is missing. D1 and D7 denominators remain limited to accounts with an actual
activation anchor; signup time is never substituted for activation.

## Boundaries

- The cohort remains bounded by account creation time, deletion state, registration
  environment, and the existing internal-account exclusion.
- Legacy null registration environments are included only in production, matching
  the lifecycle eligibility contract.
- A bare Project shell does not establish durable value. The report requires a chat
  or file attached to an active Project, or a ready nonempty generated artifact.
- The return schemas are unchanged and contain aggregate counts only. They expose no
  account identifier, email, prompt, response, conversation, Project, file name,
  URL, referrer, or metadata.
- Attribution remains the immutable, allowlisted `AccountCreated` tuple. Prices,
  checkout, entitlements, finance fields, lifecycle copy, holdouts, email, and push
  behavior did not change.
- No synthetic account, event, job, Project, file, payment, or customer-content row
  was created for verification.

## Database evidence

The remote migration ledger was rechecked after API-owner coordination and ended at
`20260908131539 lifecycle_prompt_delivery_kill_switch`. The transactional,
function-only migration then applied as
`20260908134343 durable_growth_measurement`.

Post-release definition inspection proved both functions have:

- completed-job activation fallback;
- Project-continuity and nonempty generated-file durable-value fallbacks;
- exact registration-environment and internal-account cohort boundaries;
- activation-only retention denominators;
- `prosecdef=false`, `search_path=""`, and ACLs containing only the database owner
  and `service_role`.

The current comparable production cohort remains empty because no eligible external
account was created after the established 2026-08-23 product-event boundary. The
weekly attribution export therefore returns zero rows. This is an honest empty
denominator, not evidence of conversion or retention performance.

Post-DDL advisors reported only the existing informational RLS-with-no-policy and
unused-index lists; no new error-level advisory appeared. References:

- <https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy>
- <https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index>

## Validation

- Focused durable-growth/lifecycle/attribution suite: 29 passed.
- Full Python suite: 866 passed, 2 environment-dependent skips (868 collected).
- JavaScript contract: 49 files plus all 6 attribution runtime cases passed.
- Python compilation, production preflight, and diff integrity passed.
- Main CI run `34234011007` passed.
- The automatic production deployment `dpl_As2odzPQZibmBRfT24PzBeju9Mbd` reached
  READY. The release changes database reporting, tests, and documentation only; no
  browser or native runtime asset changed.
- The seven-day production review contained no runtime error cluster, 5xx request
  path, or warning/error/fatal log.

## Decision gate

The reports can now be trusted not to lose completed first value solely because an
analytics write failed. Paid acquisition and performance claims remain held until a
legitimate comparable cohort supplies activation, decision-grade value, payer, and
elapsed D1/D7 denominators. Finance fields remain unavailable until an authoritative
finance export is implemented.
