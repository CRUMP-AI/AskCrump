# Dormant paid rough-to-useful attribution release — 2026-09-09

## Outcome

Ask Crump can now preserve one exact, server-authoritative first-touch tuple for a future
Facebook paid-learning route:

| Acquisition | Placement | Campaign | Creative | Intent |
| --- | --- | --- | --- | --- |
| `paid-social` | `facebook-paid` | `rough-to-useful-v2` | `rough-to-useful-current-feed` | `projects` |

The existing organic route remains unchanged:

| Acquisition | Placement | Campaign | Creative | Intent |
| --- | --- | --- | --- | --- |
| `facebook` | `organic-social` | `rough-to-useful-v2` | `rough-to-useful-current-feed` | `projects` |

Both routes are represented as explicit touchpoints across the landing client, authentication
client, Python normalization, SQL constraints, the service-role writer, executable browser
fixtures, and parity tests. Their fields cannot be cross-combined.

This is a dormant measurement release. No tagged production page was opened, no campaign or
Meta setting changed, no traffic or spend was activated, and no production event was
manufactured.

## Review correction

The first rollback-only production exercise exposed a PostgreSQL three-valued-logic edge case:
after unknown source and placement values normalized to `NULL`, `IF NOT (NULL)` did not execute
and a campaign label could survive. The transaction aborted and rolled back before leaving any
fixture row.

Migration `20260909220929 reject_null_paid_attribution_cross_products` closes that gap in both
places that matter:

- the complete campaign constraint is explicitly required to evaluate `TRUE`, so a `NULL`
  expression cannot pass a PostgreSQL `CHECK`; and
- both writer validation stages use `IS NOT TRUE`, so unknown or incomplete tuples normalize
  campaign and creative to `NULL` instead of retaining a partial label.

A regression contract now rejects the old null-sensitive form. The correction applies to the
whole registered campaign writer, not only the new paid route.

## Database and privacy boundary

- Migration `20260909220127 paid_rough_to_useful_attribution` adds the two allowlisted labels,
  the exact paid touchpoint, and the unchanged organic touchpoint.
- Migration `20260909220929 reject_null_paid_attribution_cross_products` installs the null-safe
  campaign constraint and writer validation.
- `record_account_created_event` remains `SECURITY INVOKER` with an empty search path.
- Execute remains denied to PUBLIC, `anon`, and `authenticated`; only `service_role` can call it.
- No referrer URL, prompt, response, search term, filename, email, account label, or arbitrary
  metadata is stored or exported.
- Before and after the rollback proof, production contained zero rows with campaign
  `rough-to-useful-v2`, source `paid-social`, or placement `facebook-paid`.

The successful production transaction proved:

1. the exact paid tuple writes once;
2. an identical retry is idempotent;
3. twelve source, placement, campaign, creative, intent, blank, missing, and unknown variants
   normalize campaign and creative fail-closed;
4. a direct paid/organic cross-product violates the database constraint; and
5. the exact tuple appears in the privacy-safe weekly attribution aggregate.

The transaction rolled back. A separate residue query confirmed zero fixture users and zero
fixture events. The live constraint is validated and the writer ACL remained service-role-only.
Post-DDL advisors reported only the project's pre-existing informational RLS-with-no-policy and
unused-index notices; no new warning or error was introduced.

## Validation and delivery

- Product commit: `7199f79d6bb131e733525f0eeeb2a948c695b5fc`.
- Complete Python suite: 961 collected, 959 passed, two environment-dependent skips.
- JavaScript contract: 49 files and all 21 rough-to-useful attribution runtime cases passed.
- Browser control matrix: 36/36 verifiers passed.
- Focused attribution browser proof: five valid tuples and nineteen rejected variants, with no
  credentials entered, account created, or analytics event sent.
- Ruff, Python compilation, production preflight, native web bundle, and diff integrity passed.
- GitHub Actions:
  - CI `34411176750` — success;
  - Android Store Bundle Verification `34411176742` — success; and
  - iOS Store Source Verification `34411176744` — success.
- Production deployment `dpl_AM3njKxRukCAX948ExCCVYAFSTkS` is READY on all six aliases with no
  alias error.
- All four custom-domain `/api/health` checks returned HTTP 200 on Ask Crump 5.9.76. The app and
  untagged rough-idea guide returned HTTP 200.
- Live `landing.js` SHA-256
  `81b62cbfe4abdc84d18f9f022ae75c6246dea172d5b260f02f09803be005cb83` matches the committed
  asset exactly.
- Live `auth-controller.js` SHA-256
  `c09ac6c2c794ccd2b52a87256d9a8b76a90afe20ee39e6a9616452350fbaa967f` matches the committed
  asset exactly.
- The first 30-minute runtime scan found no grouped error, no HTTP 5xx, and no
  warning/error/fatal log.

## Decision boundary

The measurement destination is ready only for the two exact rough-to-useful touchpoints above.
The future canonical URL remains unvisited and the paid route remains dormant. This release is
not authorization to publish, activate traffic, change Meta, spend, claim performance, alter the
offer, or start a pilot. Marketing must retain its separate action-time approval and evidence
gates before any such action.
