# Presentation attribution fixture receipt

**Prepared:** 2026-09-01  
**Product fixture commit:** `de60728a7c5843d68b9a475079f1ebc21dcc6861`  
**Execution state:** clean tracked worktree immediately after the fixture commit  
**Classification:** isolated technical proof only; not a legitimate user, acquisition, activation, payer, revenue event, or campaign result

## Result

The exact presentation first touch survived the browser landing-to-registration handoff, remained
immutable when a second valid campaign was presented in the same tab, crossed the real application
registration function, and reached the product-analytics writer exactly once. The isolated cohort
contained one account and one authoritative event after registration, remained one after a direct
idempotency replay and a pending-account registration retry, and returned to zero after the normal
`delete_user_account` RPC/cascade boundary.

| Field | Verified categorical value |
| --- | --- |
| acquisition | `instagram` |
| placement | `profile-link` |
| campaign | `presentation-proof-current` |
| creative | `ig-feed` |
| intent | `presentation` |
| milestone | `AccountCreated` |

## Content-free before/replay/cleanup receipt

| Boundary | Fixture aggregate rows | Accounts created | Account event recorded | `AccountCreated` event count |
| --- | ---: | ---: | ---: | ---: |
| Before registration | 0 | 0 | 0 | 0 |
| After first registration | 1 | 1 | 1 | 1 |
| After idempotency replay and pending-account retry | 1 | 1 | 1 | 1 |
| After account cleanup | 0 | 0 | 0 | 0 |

The isolated production-control account/event counts and the finance sentinels for credit ledger,
media jobs, and recognized revenue were identical before and after the run.

## Exact verification commands

From the repository root:

```powershell
& 'C:\Users\gcrum\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tests/test_presentation_attribution_fixture.py tests/test_attribution_measurement.py -q
```

Result: **13 passed, 0 failed**.

With a local static server bound only to `127.0.0.1:8765`:

```powershell
$env:ASKCRUMP_PLAYWRIGHT_MODULE='C:\Users\gcrum\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright'
$env:ASKCRUMP_BROWSER_EXECUTABLE='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
& 'C:\Users\gcrum\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts/verify-presentation-attribution-browser.cjs
```

Result: **1 browser fixture passed, 0 failed**. The receipt contained the exact categorical tuple,
one local intercepted registration request, same-tab overwrite rejection, and explicit
`networkAccountCreated=false` and `analyticsSent=false` results.

Full release validation:

- **726 Python tests passed, 0 failed**.
- **47 JavaScript files validated**.
- Python compilation passed.
- Production preflight passed.
- Native web-bundle generation passed.
- Apple and Google store-metadata source checks passed.
- Mobile signing-source controls passed with no tracked secret.
- Git diff integrity passed.
- The native release verifier correctly retained the existing non-product gates: generated Android
  and iOS projects are absent and RevenueCat public SDK keys are not configured in this shell. No
  signed native-candidate claim is made.

## Registry and storage contract versions

- `20260830171056_weekly_growth_attribution_export.sql`: exact campaign registry, bounded
  server-authoritative `AccountCreated` RPC, uniqueness conflict, and service-role export boundary.
- `20260901012708_decision_grade_growth_snapshot.sql`: current environment-isolated,
  privacy-safe cohort/export contract.
- Runtime registry parity remains executable across `public/landing.js`,
  `public/auth-controller.js`, `backend/product_analytics.py`, and SQL.

## Isolation and privacy controls

- The browser loaded only the loopback fixture origin; its registration request was intercepted
  locally before any network account could be created.
- Browser analytics were replaced by an in-memory categorical event-name collector; no Vercel
  analytics request was sent.
- The server fixture used the real registration function and real analytics normalizer/writer, but
  replaced database and verification delivery with isolated in-memory implementations.
- The fixture environment was `development`, derived from a non-public fixture host. Production
  cohort controls were seeded separately and proved unchanged.
- No production endpoint, campaign URL, customer table, live mailbox, payment provider, finance
  writer, customer content, prompt, response, filename, Project, artifact URL, token, secret, or
  legitimate-user ledger was touched.
- The evidence above contains no fixture identifier, email address, credential, or private log.

## Limitation and remaining evidence gate

This workstation has no local Supabase CLI, container runtime, or disposable Postgres stack. The
database portion therefore uses an application-level in-memory RPC/cascade fixture plus the existing
executable Python/JavaScript/SQL parity and migration-contract tests; it does not execute the two SQL
migrations inside Postgres. It does exercise the real browser attribution code, real registration
function, real server environment derivation, and real analytics normalization/writer before the
database call.

This receipt proves transport, idempotency, cohort isolation, and cleanup. It does not prove a
legitimate external registration, activation, useful outcome, retention, payer, or revenue result,
and it does not authorize publication, profile changes, outreach, lifecycle delivery, ads, spend,
pricing, checkout, migration, backfill, or production mutation.
