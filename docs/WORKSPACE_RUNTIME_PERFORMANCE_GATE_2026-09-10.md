# Ask Crump workspace runtime performance gate

Date: 2026-09-10  
Release commit: `0632523`  
Production deployment: `dpl_Ck9S1t588p5KXtqpNvavrfjn4SBQ`

## Trigger

A read-only Vercel Speed Insights review found a changed seven-day production observation. The
desktop `/app` route reported a Real Experience Score of **79** across **156** events for September
3–9, after the prior September 1–8 checkpoint had reported **91** across **400** events. Mobile still
reported no events. The current plan does not expose individual Core Web Vital values, so this is a
smaller, differently composed field window—not proof that the loader code regressed.

Vercel also displayed an optional Rolling Releases recommendation. Ask Crump already has 12-hour
Skew Protection, but the current legitimate traffic volume is too small for a fractional rollout to
produce a useful comparison and an active rollout would prevent a second promotion until the first
is resolved. The project configuration was therefore left unchanged. No paid Speed Insights or
other add-on was enabled.

## Outcome

The previously static workspace fetch-plan fixture is now an executable, fail-closed browser gate
inside the required CI matrix. It proves the structure responsible for the earlier performance
improvement instead of inferring that structure from source strings alone.

Under one fixed 120 ms latency model, the browser must prove:

- all **21** workspace styles are requested and reach **21-way concurrency**;
- all **33** scripts are preloaded before ordered execution starts;
- exactly **33** scripts execute;
- the first script remains the onboarding runtime and the final script remains the lifecycle
  runtime;
- the workspace reaches `ready` in less than one second, which distinguishes the parallel plan
  from a serialized multi-second regression; and
- the fixture and browser console remain error-free.

The first clean run reached ready in **321 ms**. The favicon fetch initially produced a deterministic
fixture-only 404; the fixture was corrected and the zero-error requirement remained intact.

## Verification

- Browser control/performance matrix: 39/39 passed.
- Full Python suite: 996/996 passed.
- JavaScript validation: 49 files, 22/22 rough-to-useful cases, 10/10 Word/PDF cases, 10/10 résumé
  cases, and the 14/14 store-packet self-test passed.
- Client credential boundary passed for public and generated native-web artifacts.
- GitHub CI run `34517258692` passed.
- Production deployment `dpl_Ck9S1t588p5KXtqpNvavrfjn4SBQ` is READY.
- `https://www.askcrump.com/`, `/app`, and `/api/health` returned HTTP 200 after release.

## Decision boundary

This gate proves loader concurrency, preload completeness, execution order, readiness, and error
handling under a deterministic model. It does not convert synthetic time into a field metric or
explain the changed 79 score. Keep the loader stable, retain Speed Insights, and recheck after the
field window has at least the prior 300-event denominator or exposes a specific failing vital. Do
not claim mobile performance until mobile events or exact signed-device measurements exist.
