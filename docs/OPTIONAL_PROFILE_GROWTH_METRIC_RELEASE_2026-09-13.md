# Optional profile growth metric correction

Date: 2026-09-13

## Decision

Do not interpret a missing display name as failed onboarding. Ask Crump intentionally lets a
verified account enter the workspace, choose work, and activate before supplying a name. The first
comparable September account exercised that valid path: it reached activation and completed three
chat jobs while the old `onboarding_completed` aggregate remained zero.

Migration `20260913192512 clarify_optional_profile_growth_metric` changes only the stage-four label
returned by `product_growth_funnel_snapshot` to `optional_profile_completed`. It preserves the
server-authoritative `OnboardingCompleted` event for compatibility, all stage ordering and counts,
the activation and retention definitions, the production/internal cohort boundary, and the
service-role-only privacy contract.

## Verification

- Product/evidence commit `6aa8d824bc0231f2d1284b29f3c1da630403f1d1` is on `main`.
- Production deployment `dpl_CLdNhFFrar8sd3AASz7eun71pJ3m` is Ready on all six aliases.
- GitHub CI run `34777787315` completed successfully for both Python and JavaScript jobs.
- Production health returned HTTP 200 on version 5.9.76, and the post-release runtime-error view was
  empty.
- A transaction-rolled-back rehearsal returned stage 4 as `optional_profile_completed` before the
  production migration was applied.
- The live production aggregate returns the corrected label with the existing 0 of 1 result.
- The other 17 metric labels and positions remain unchanged.
- The function remains security-invoker, service-role-only, and content-free; `anon` and
  `authenticated` cannot execute it.
- The focused growth-measurement suite passed 6/6 and the complete Python suite passed 1007/1007;
  lint, compilation, and diff integrity also passed.
- Post-migration database advisors reported informational findings only. No new warning or error
  was introduced by this function-label change.
- No account, event, profile, prompt, response, file, Project, payment, or customer content was
  created or changed.

## Operating implication

Keep the non-blocking profile prompt. Judge first-session onboarding through verified workspace
entry, starter intent, and activation. Report optional profile completion separately as
personalization adoption. The 24-hour durable-value and D1/D7 gates for the current one-account
cohort remain immature and must not be converted into a failure or lift claim.
