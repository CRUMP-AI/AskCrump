# Public destination integrity release — 2026-09-14

## Decision

Ship one bounded destination correction and make live first-party destination verification
repeatable. The **Clever Crump** action in the signed-in You surface now opens the direct canonical
`https://www.clevercrump.com/` destination instead of taking an avoidable apex-domain redirect.
No other button handler, account flow, purchase behavior, provider action, or customer data path
changed.

The existing `/legal.html` and `/delete-account.html` links remain in the application shell because
the same source is packaged into native WebViews, where the physical files are required. The live
verifier allows only those two exact compatibility redirects to their reviewed canonical pages. Any
other redirect, missing Location header, second redirect, non-200 response, missing sitemap
canonical, or missing robots-to-sitemap declaration fails the proof.

## Permanent proof

`scripts/verify-live-public-destinations.mjs` discovers literal first-party links from shipped HTML
and JavaScript, normalizes HTML query separators, excludes dynamic user-specific templates, and
checks the deployment without authentication, cookies, privileged headers, customer data, or API
mutation. It is available as `npm run test:live-public-destinations` and accepts an explicit
`ASKCRUMP_PUBLIC_ORIGIN` for a reviewed alternate deployment.

Commit `ab2940a` adds `.github/workflows/public-destination-health.yml`. It runs this proof daily at
11:17 UTC and on manual dispatch, with read-only repository permission, Node 22, a ten-minute job
limit, no secrets, and no push or pull-request trigger. Safe credential-free GETs receive at most
three attempts for network failures or HTTP 408/429/500/502/503/504; redirects and all other
responses retain the exact fail-closed rules above.

The 2026-09-14 production execution passed:

- **67** unique first-party anchor destinations;
- **12** canonical sitemap pages;
- **69** HTTP 200 destination checks; and
- exactly **2** reviewed native-compatibility redirects.

The served `/app` shell contains `https://www.clevercrump.com/` and no longer contains the redirecting
bare-domain href. The served worker exposes cache `ask-crump-new-body-v1-r243`, ensuring an installed
PWA receives the new shell.

## Verification

Commit `e479faa` passed:

- backend **1,066/1,066**;
- JavaScript contracts **54/54**;
- interactive browser verifiers **48/48**;
- public accessibility scenarios **33/33**;
- production build preflight and native web bundling;
- public client-secret boundary; and
- diff integrity.

GitHub CI `34874380847`, Android bundle verification `34874380896`, and iOS source verification
`34874380954` completed successfully. Vercel reported the commit deployment complete at deployment
target `6M422PAt3876egMhAvZmiona1vJH`; the live app and service worker checks passed after that state.
The first manually dispatched hosted health run, GitHub Actions `34875692579`, completed successfully
against commit `ab2940a` in 13 seconds.

## Operating boundary

This release proves control ownership and destination availability; it does not prove a purchase,
provider-backed generation, native permission, account deletion, or later customer return. Preserve
the current activation and continuity funnel until the first valid D1 cohort reading at or after
2026-09-15 00:00 UTC.
