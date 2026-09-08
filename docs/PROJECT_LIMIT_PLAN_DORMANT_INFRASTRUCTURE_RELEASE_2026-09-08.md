# Dormant Project-limit value-to-plan infrastructure release — 2026-09-08

## Decision

**SHIP_INFRASTRUCTURE_DORMANT / HOLD_EXPOSURE_AND_COMMERCE**

Ask Crump now has server-authoritative infrastructure for a future two-arm experiment at the
existing Free Project limit. The release does not expose either experiment arm. The Vercel
application flag is absent and therefore defaults false; the database control exists and is
explicitly false. A missing, disabled, invalid, or failed decision preserves the exact prior
Project-limit recovery experience.

No price, allowance, plan card, checkout confirmation, subscription, entitlement, campaign, or
public claim changed. The treatment remains unavailable until a later release decision proves the
commerce, finance, tax, support, privacy, and legitimate-cohort gates in the frozen experiment
contract.

## What was released

- Eligibility is evaluated only after the server confirms `PROJECT_LIMIT_REACHED`.
- Only a verified, undeleted, external production Free/inactive account with exactly two active
  Projects and attached durable work can qualify.
- Internal, preview, unverified, deleted, commerce-identified, active-work, lifecycle/referral,
  recent Plan-center, and recent checkout states fail closed.
- Assignment is a durable account-level random split limited to `control` or `value-specific`.
- A two-phase claim/record protocol rechecks eligibility and records the fixed exposure before
  treatment copy can render.
- Frequency is limited to one recorded exposure per account in a rolling 30-day window.
- The treatment changes one fixed detail sentence only. It cannot open Checkout automatically.
- The service-role aggregate keeps content and identifiers out of the report and returns
  `unavailable` for finance and reversal inputs that are not authoritative.

## Current-main integration

The independently accepted source candidate was based six commits behind production. It was
integrated onto current main without altering the frozen SQL bytes. The newer explicit-button and
active-work update protections were preserved. Changed runtime assets use the new
`5.9.76-project-limit-plan-dormant-1` identity and service-worker cache `r221`; no old candidate or
current-production URL was reused.

## Database proof

- Remote migration: `20260908163226 add_project_limit_plan_experiment_dormant`.
- Repository source:
  `migrations/20260908163226_add_project_limit_plan_experiment_dormant.sql`.
- Exact SQL SHA-256:
  `584F294FA9C9D9F1449CA9E08954526991AD7FE337A854885A65ACFFA944A807`.
- That hash matches the independently accepted PostgreSQL 17.11 migration.
- The database control is `false`; assignment rows are `0`; exposure rows are `0`.
- All three tables have RLS enabled.
- `anon` and `authenticated` have zero table grants and zero function grants on the new objects.
- All three functions are security-invoker with an empty search path.
- Post-DDL advisors returned only the expected informational
  [`rls_enabled_no_policy`](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)
  finding for the new deny-by-default server tables and
  [`unused_index`](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index)
  findings for their still-empty indexes. No client policy or index deletion is appropriate while
  the feature remains dormant.

## Application and browser verification

- The full suite collected **893 tests**: **891 passed** and two environment-dependent tests were
  skipped.
- The 20 focused experiment tests and 32 related billing/button/recovery tests passed.
- All **49 JavaScript files** and all six attribution runtime cases passed.
- Ruff, Python compilation, production preflight, native web-bundle generation, and diff integrity
  passed.
- The disabled browser fixture proved both billing runtimes preserve the exact control copy, close
  correctly, and issue zero checkout requests.
- The delivery-order fixture proved the shown event precedes treatment visibility, with zero
  checkout requests and zero browser errors.
- The live Vercel environment-variable search returned no
  `CRUMP_ENABLE_PROJECT_LIMIT_PLAN_EXPERIMENT` variable; no value was revealed or changed.
- `/api/health` and `/app?release_probe=project-limit-plan-dormant-1` returned 200. The new shown
  route rejected an unauthenticated request with 401.
- The exact live `crump-product-5.3.js`, `crump-billing-5.1.js`, `crump-5.2.js`, and `sw.js` bytes
  matched the committed files.
- The production deployment reached READY on all six aliases with no alias error. Its initial
  30-minute runtime-error query was empty and its build completed without a failing log event.

## Release identity

- Integrated feature commit: `d6e200e854e1946b40cb1d7a99f3b0589dc61608`
- Frozen source candidate: `220ff1308194275b135461eb82a8a1dcfc618ba5`
- Frozen proof head: `2df11af532490185e79b2b5cabbcc36893e3b7e1`
- Production deployment: `dpl_HQhsTHSoHnBdRgnhWWvqTC8JMSNk`
- Main CI: `34251906993` — success
- Android verification: `34251906924` — success
- iOS verification: `34251906899` — success
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project/main aliases

## Live hashes

- `crump-product-5.3.js`:
  `409E1144F421C6DA651BDCB860EC8947B01BD4F2E0C0D8E7E1DF388CDAC71BF5`
- `crump-billing-5.1.js`:
  `95DCB5C23FE3C7BEC37065E79071EC7D19B4470C244B66EE3EE4E83F33C3E0AD`
- `crump-5.2.js`:
  `E9B192380CB6F4FCC478A36DB44C36BECA446AC805D6786749FE8FB66896F51E`
- `sw.js`:
  `6448B046440C9C700612592AAF263C0CE760B54976E1083EE33A3D3D5AEC0C3D`

## Boundary and next decision

No account, Project, prompt, response, file, assignment, exposure, product event, checkout,
subscription, entitlement, price, payment, customer record, campaign, message, or spend was
created or changed during the live canary. The migration added only dormant server-owned schema.

Do not enable either gate until the live Professional catalog/allowance, webhook reconciliation,
cancellation/refund recovery, monitored billing support, reviewed tax posture, finance-authoritative
recognized-revenue reporting, and a legitimate non-internal eligible cohort are all proven. The
first integrity read remains 20 eligible exposures per arm; the first decision read remains 50 per
arm plus seven elapsed days. Synthetic production exposure is prohibited.
