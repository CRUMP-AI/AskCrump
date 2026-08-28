# Mobile login regression release evidence — 2026-08-28

## Outcome

Ask Crump 5.9.49 hardens web/PWA login against two interacting mobile boundaries:

1. A sleeping installed app could resume an older JavaScript runtime after a newer service worker
   had activated. The fixed server release could therefore appear to regress until the page was
   genuinely restarted.
2. A successful web login allowed only about 275 milliseconds across three confirmation delays for
   a newly issued HttpOnly session to become visible. A slower mobile browser could receive the
   successful login response, miss all three confirmation probes, and be returned to sign-in.

Authentication still requires a server-confirmed session. No credential, verification, session,
rate-limit, authorization, billing, entitlement, schema, or RLS policy was weakened.

## Production evidence before correction

- Production traffic contained seven `/api/auth/login` requests and 29 `/api/auth/check-session`
  requests during the reported window, without an authentication exception cluster.
- The request ratio was consistent with repeated successful-login confirmation loops followed by
  another page/bootstrap attempt. This was an inference until the client boundary was reproduced.
- The unrelated 503 responses in the same window came from manuscript cron/database work, not the
  login or session routes.
- The existing 401 responses were traced to signed-out workspace modules probing protected feature,
  project, library, and credit endpoints. They were not responses from login or session checking.

## Deterministic browser reproduction

The credential-free loopback fixture loads the real authentication transport, device-auth module,
and auth controller. Its mock login succeeds immediately while the session becomes visible on the
fourth post-login check.

Before correction:

- login requests: 1
- total session checks: 4 (one bootstrap plus three post-login checks)
- post-login checks: 3
- workspace starts: 0
- visible result: `Your session could not be established. Please try again.`

After correction:

- login requests: 1
- total session checks: 5 (one bootstrap plus four post-login checks)
- post-login checks: 4
- workspace starts: 1
- visible result: workspace ready with no login error

The fixture contains no production URL, production account, credential, or network write.

## Released correction

- Successful web login now uses bounded delays of 0, 100, 300, 750, and 1,500 milliseconds.
- Login-response timeout recovery now uses bounded delays of 0, 150, 500, 1,000, and 2,000
  milliseconds.
- The PWA checks for updates on load, `pageshow`, foreground return, and connectivity return.
- A service-worker controller change refreshes an idle signed-out screen automatically. Entered
  authentication fields, a busy form, or signed-in work receive a restrained update notice instead.
- A 15-second reload guard prevents update loops.
- The installer and its style are release-versioned, network-first boot assets.
- Authentication logs now use identity-free categorical outcomes. Routine `httpx`/`httpcore` request
  URL logging is suppressed because Supabase filters can contain opaque session hashes and internal
  row IDs.

## Verification

- 359 Python tests passed.
- Ruff passed across `backend` and `tests`.
- Backend byte-compilation passed.
- All 44 public JavaScript files passed syntax and integration-contract validation.
- The production build preflight and generated native web bundle passed.
- Android source verification passed for API 36, version 5.9.49, build 50949.
- Store metadata and mobile signing source controls passed.
- GitHub CI, Android Store Bundle Verification, and iOS Store Source Verification passed for commit
  `06c30a10c022a284c4fefe563d4a26328432b17b`.
- Privacy-log hotfix CI passed for commit `3b20cf420f3544d382791c8cae71c5fb1fa86b0f`.

Expected owner-account gates remain unchanged: Android Play Billing requires the RevenueCat public
SDK key and `google-services.json`; signed-archive, physical-device, billing, and store-console
validation remain store-submission steps.

## Production proof

- Release deployment: `dpl_FF3RBc9NHgaC7z36WMTeUhcu5nhY`
- Privacy-log hotfix deployment: `dpl_D7DKsLgZQMxXgtKnqbDVE9ozue3n`
- Production aliases were assigned without error.
- A fresh anonymous production browser received HTTP 200, the versioned 5.9.49 installer and device
  auth assets, the five-step mobile confirmation sequence, and active cache
  `ask-crump-new-body-v1-r83`.
- A fresh anonymous session check returned HTTP 200 with `authenticated: false` as expected.
- The privacy-hotfix log for that request contained only the categorical auth outcome and client
  class; no upstream request URL, opaque session hash, internal row ID, email, or token appeared.

## Owner retest

A page that was already asleep before 5.9.49 cannot retroactively install the new wake-up listener.
Fully close the installed Ask Crump PWA once, open it again, and sign in normally. From that point
forward, later service-worker changes are detected on wake and adopted safely.
