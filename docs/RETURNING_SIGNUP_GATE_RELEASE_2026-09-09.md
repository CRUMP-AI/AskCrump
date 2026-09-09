# Returning-device signup gate release — 2026-09-09

## Outcome

A signed-in user who followed a public **Start free** link to `/app?signup=1` could briefly see
the registration form before the existing session restored the workspace. The form was usable and
the session recovery succeeded, but the intermediate paint looked like an authentication glitch
and contradicted the user's actual state.

Ask Crump now uses the existing, content-free device cache only as a presentation hint while the
server remains authoritative:

- a new device with no cached identity still sees registration immediately;
- a returning device waits behind the existing workspace opening gate instead of painting a form
  that may disappear;
- an authenticated server response opens the workspace normally;
- a definitive signed-out response clears the stale cache and opens registration for the requested
  signup route; and
- a transient session-check failure preserves the saved sign-in and shows the existing recovery
  message instead of pretending the user was logged out.

No cookie, cached profile value, or customer content is exposed to analytics or rendered by this
decision. The cache hint cannot authenticate a user; only `/api/auth/check-session` can do that.
The versioned controller is `5.9.76-returning-signup-gate-1`, carried by service-worker cache
revision `r226` into web, installed PWA, Android, and iOS source bundles.

## Verification

- A 390×844 production reproduction before the change showed **Create your workspace** during
  session hydration and the signed-in workspace afterward.
- The local real-controller fixture passed three timed cases without credentials or network writes:
  1. newcomer + signup: registration visible while the delayed session check remained unsettled;
  2. cached + authenticated: stable workspace gate first, workspace afterward, registration never
     visible; and
  3. cached + definitively signed out: stable gate first, registration afterward with email focus.
- Complete Python suite: **913 collected**, **911 passed**, two environment-dependent skips.
- JavaScript integration contract: **49 files** and **6/6** attribution runtime cases passed.
- Ruff, Python compilation, production preflight, native web build, and diff integrity passed.
- Main CI: **34357295789** — success.
- Android store-source workflow: **34357295886** — success.
- iOS store-source workflow: **34357295853** — success, including unsigned Release compilation and
  compiled privacy-manifest inventory verification.

## Production evidence

- Feature commit: `34ed3134617435b3c16bfcc76adad4498ddcdcbe`.
- Automatic production deployment: `dpl_7qe7ETQPLdDg5WXPEFA6MLnkmAAK` — READY on all six aliases
  with no alias error.
- `www.askcrump.com`, `askcrump.com`, `www.clevercrump.com`, and `clevercrump.com` returned HTTP 200;
  `www.askcrump.com/api/health` returned HTTP 200.
- Live app, service-worker, and controller responses expose exact cache `r226`, controller version,
  returning-device hint, conditional gate, and definitive signed-out registration fallback.
- Replaying the exact signed-in 390×844 production route showed the workspace gate at the early
  check and the ready workspace afterward; registration remained hidden at both checks and the
  browser error log was empty.
- The initial 30-minute runtime-error aggregate and deployment-scoped 5xx query were empty.

The production proof did not submit credentials, create an account, send a prompt, open customer
content, generate media, start checkout, or mutate product data. Physical signed iPhone and Android
launch transitions remain final distribution evidence rather than a web-release blocker.
