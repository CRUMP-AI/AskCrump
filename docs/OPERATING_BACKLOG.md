# Ask Crump operating backlog

Last updated: 2026-08-27

## Operating standard

Ask Crump's north-star outcome is a user completing valuable work, keeping it, and returning
to continue it. Revenue and user growth should follow verified activation, durable value,
retention, and referral behavior. No acquisition spend should scale on impressions alone.

Every item below needs four things before it is called shipped: an accountable product
outcome, privacy and safety constraints, automated coverage, and production evidence.

## Verified releases

| Outcome | Evidence | State |
| --- | --- | --- |
| Conversational document delivery | Commit `c4ef9ee`; explicit follow-up delivery requests cannot be downgraded to clarification; targeted regressions pass; the fix is present in every current production build; no `/api/chat` runtime error cluster was reported in the seven-day production scan on 2026-08-27. | Verified |
| Professional presentation exports | Commit `b98d82a`; dark/light editorial rhythm, executive layouts, improved tables, native editable charts, and strict OOXML chart compatibility; full backend suite, JavaScript validation, production preflight, native build, and a ten-slide render review passed; production health returned HTTP 200 after deployment. | Verified |
| Private artifact journey telemetry | Commit `f497ab0`; entitled request, successful packaging, packaging failure, and first-download events are server-authoritative and content-free; Supabase migration `artifact_journey` is recorded; anonymous and authenticated roles cannot execute the aggregate report while `service_role` can; 265 backend tests, JavaScript validation, production preflight, production health, and post-deploy runtime checks passed. | Verified |
| Crump Code private foundation | Owner-scoped task, event, and approval tables are live with client roles denied; the server-role privilege repair leaves audit events append-only and approvals non-deletable; the runner uses an ephemeral 2-vCPU/4-GB, deny-all, no-secret sandbox and returns patches without pushing source. Public feature flag remains off pending a real sandbox smoke test, UI, and benchmark. | Staged, disabled |
| Crump Voice private foundation | Explicit signed-in playback route, Professional entitlement, rate/character/audio limits, provider-failure refund, server-held ElevenLabs key, non-cacheable ephemeral MP3 response, and device-speech fallback are implemented. Public feature flag remains off pending approved disclosure, credentials/voice rights, and smoke tests. | Staged, disabled |
| Private conversation-to-Project continuity | Commit `e99fc1f`; production 5.9.22 puts `Keep in a Project` directly on the latest result, reducing durable-work preservation from two commitments to one. The existing server route synchronizes and ownership-checks the chat, attaches idempotently to the selected/new Project, and records only a content-free Project milestone. All 285 tests, backend lint/compile checks, 40 JavaScript validations, production preflight, and native web-bundle build passed. Live health and version checks returned HTTP 200, the deployed client contained the direct action, and the deployment-scoped error/fatal scan was empty. | Verified |
| Comparable growth-cohort boundary | Supabase migration `product_growth_measurement_boundary`; live first-event evidence fixes the lower bound at `2026-08-23 09:10:55.602863+00`; the 30-day report now returns 18 metrics and zero comparable external accounts instead of misclassifying three historical accounts. The function remains security invoker, `anon`/`authenticated` execution is denied, `service_role` execution succeeds, and post-change advisors reported no errors or warnings. | Verified |
| Truthful organic discovery | Commit `150ced2`; deployment `dpl_HUbcyLdLFdh7SVpqF3S99XL3caMo`; production 5.9.23 adds unique, crawlable presentation and document workflow pages, homepage/cross-page links, canonical metadata, valid JSON-LD, and a four-URL sitemap. Known search referrers collapse to `organic` without retaining the referrer URL or query, and internal CTA placements cannot overwrite acquisition. All 290 backend tests, 40 JavaScript validations, production/native bundle checks, CI run `33116981568`, Android run `33116981449`, iOS run `33116981462`, clean-URL HTTP checks, desktop/mobile browser checks, and the deployment-scoped error/fatal scan passed. | Verified |
| Truthful referral delivery | Commit `a7f3482`; deployment `dpl_2zxpBU85E3uJkygbmmjquhq4fVQJ`; production 5.9.24 keeps the post-useful-result invitation content-free and carries only aggregate `referral` acquisition plus `response-share` placement into registration. The registration server preserves `referral` on `AccountCreated`. Denied clipboard access can no longer display a false success or record `ResponseShared`; an executable browser-script contract proves failed copy records zero events while a verified fallback records exactly one. All 291 backend tests, 40 JavaScript validations, production/native/store checks, CI run `33119777886`, Android run `33119777893`, iOS run `33119777888`, live route/version checks, and the deployment-scoped error/fatal scan passed. A legitimate referred account and activated outcome have not yet been observed. | Verified delivery; outcome pending |
| Measurable social previews | Commit `6d2c24f`; deployment `dpl_CZih5NeHk8JjDp1tukrLZPCXhioD`; production 5.9.25 gives the home, presentation, and document pages distinct 1,200-by-630 social cards composed from the canonical mark, with large-card metadata and truthful page-specific copy. The generator is deterministic on the verified release machine; automated tests validate PNG format, dimensions, color mode, and per-page references. All 292 backend tests, 40 JavaScript validations, production/native/store checks, CI run `33123220073`, Android run `33123220055`, iOS run `33123220046`, six live route/asset checks, and the deployment-scoped warning/error/fatal/5xx scan passed. Socially attributed signup outcome remains unproven. | Verified delivery; outcome pending |

### Current production reliability checkpoint

A project-wide production runtime scan covering the trailing 24 hours on 2026-08-27 found no
runtime error clusters, no error/fatal/warning log entries, and no 5xx responses. The status
breakdown contained 1,841 successful 200 responses and five expected 401 responses from explicit
unauthenticated release probes against the disabled Crump Code, disabled Crump Voice, and private
Project attachment routes. The evidence does not justify a reliability code change; acquisition
and comparable user observation remain the next operating constraint.

## Ranked execution backlog

### P0 — Convert useful answers into continuing Project work

**Evidence:** two external accounts completed 14 successful AI jobs with no recorded failures, but
the external aggregate contains zero Projects and zero files, and no external activity occurred
after 2026-08-23. Release 5.9.20 made Project continuity primary after positive feedback, but still
required a feedback click before the durable-work action appeared.

**Outcome:** expose private Project continuity directly on the latest result as a one-click next
action. Synchronize and ownership-check the conversation, attach it to the selected Project or
create one, and record only a content-free durable-value milestone. Keep feedback optional and
referral sharing secondary.

**Release gate:** automated ownership, mapping, direct-action ordering, analytics, full release
verification, and production health passed for 5.9.22. The remaining outcome gate is at least one
legitimate external conversation-to-Project transition and a later return. Do not infer a retention
rate from a single user.

### P0 — Review the first complete artifact journey cohort

**Evidence:** artifact-journey instrumentation reached production on 2026-08-27. Its first
service-role production snapshot returned no rows, which is the correct pre-traffic baseline;
Ask Crump will not insert synthetic production events to make the report look populated.

**Outcome:** use real traffic to identify the largest request-to-package or package-to-download
drop by artifact category. Keep reporting limited to aggregate stage counts and rates—never
prompts, responses, filenames, URLs, customer data, or arbitrary error text.

**Release gate:** at least one real production request and a written reconciliation of requested,
packaged, packaging-failed, and downloaded counts. Treat a small first sample as operational
evidence, not a statistically reliable conversion benchmark.

### P0 — Complete the Crump Code activation gates

**Evidence:** The server and private schema now provide public-repository task creation, bounded
tool use, isolated execution, patch generation, verification, state transitions, cancellation,
and approval records. The code is disabled, has no customer UI, and has not completed a real
production sandbox run.

**Outcome:** complete a human-visible workspace, diff and verification experience, prove the live
runtime boundary, add durable orchestration for longer work, and measure quality against a fixed
benchmark before any parity positioning.

**Release gate:** approved sub-cent sandbox smoke test, production OIDC verification, cancellation
and expiry tests, human-visible cost/diff/approval UI, failure monitoring, rollback exercise, and
an end-to-end benchmark suite. Do not advertise Codex or Claude Code parity until measured tasks
show comparable completion quality and safety.

### P0 — Prove the first comparable continuing-work journey

**Evidence:** the 30-day external cohort contains three accounts and two verified accounts. Two
accounts completed 14 successful AI jobs, proving historical first-use activity, but external
activity ended before the first observed product-event traffic and did not resume afterward.
The external aggregate contains no Projects, files, shares, checkout, or paid events. The current
event recorder works for an internal production tester, so historical zero-event rows are a cohort
boundary—not proof that the old users never activated.

**Outcome:** observe a new, legitimate post-instrumentation cohort complete verification, start
useful work, keep it in a private Project or file, and return. Use moderated sessions to identify
telemetry gaps separately from real usability failures. Do not create synthetic backfill events.

**Release gate:** at least three consented end-to-end observations, content-free event
reconciliation, one shipped fix for the largest verified failure, and a new cohort review before
any acquisition spend scales.

### P1 — Close the organic acquisition loop

**Evidence:** the Search Console domain property is verified through the live DNS TXT record, and
Google is processing the property's first search and indexing data. Production 5.9.23 now serves
unique presentation and document workflow pages at clean canonical URLs, links them from the home
page and from each other, and includes all four public URLs in the live sitemap. The protected growth
and artifact reports still show zero comparable external activity, so acquisition is the current
evidence-backed bottleneck. A read-only Search Console inspection on 2026-08-27 showed that Google is
still processing performance and indexing data and the Submitted sitemaps table contains zero rows.
The sitemap is live and ready, but it is not entered or submitted in Search Console.

**Outcome:** verified domain ownership, one canonical sitemap submitted, valid canonical URLs,
and indexed landing pages tied to privacy-safe account-creation attribution.

**Release gate:** Search Console verification, live sitemap delivery, clean canonical HTTP/browser
inspection, unique metadata, and crawlability checks passed. Remaining gates are owner-confirmed
submission and Search Console acceptance of `https://www.askcrump.com/sitemap.xml`, followed by an
indexed-page coverage review after Google has had time to crawl.

The authoritative action-time checklist is `docs/SEARCH_CONSOLE_RELEASE_GATE_2026-08-27.md`.

### P1 — Observe the new activation and referral funnel before scaling spend

**Evidence:** starter intent, activation, durable value, useful-result feedback, recent-work
continuation, response sharing, checkout, and paid status are now measurable. Production 5.9.24
also prevents a failed clipboard operation from being counted as a share and preserves the
content-free `referral` channel through account creation, but the comparable production cohort is
new and no legitimate referred activation has been observed. A production-only Vercel Web
Analytics read on 2026-08-27 showed 78 visitors, 185 page views, and 62% bounce over the trailing
seven days; 58 visitors reached `/app`, 18 visitors produced 19 `SignupIntent` events, and one
visitor produced one client `AccountCreated` event. Those anonymous aggregates span the
pre-instrumentation boundary and may include internal or automated visits, so they are not a
conversion rate. The last 24 hours showed six production visitors, 20 page views, no signup event,
and one visitor on each new discovery page. The service-role comparable external funnel still
returned zero accounts at every stage, and the aggregate artifact journey returned no rows. A
project-wide trailing-24-hour production runtime scan found no errors, warnings, fatal logs, or 5xx
responses, so the absence of a new comparable user is not currently explained by a server failure.

**Outcome:** a weekly operating review of account creation → workspace open → starter intent →
activation → durable value → useful outcome → return/share → checkout → paid.

**Release gate:** at least one fully elapsed D7 cohort, explicit denominators, internal accounts
excluded, at least one legitimate referral delivery-to-account-to-activation observation, and a
written decision for the largest observed drop-off. Treat small samples as directional rather
than statistically conclusive.

### P1 — Measure richer social share previews

**Evidence:** Facebook was the largest observed external referral family in the trailing seven-day
Web Analytics view (`m.facebook.com` 10 visitors and `facebook.com` eight), while every public page
still exposed the square app icon as its share image. That traffic is small and may include internal
visits, so it establishes a channel worth instrumenting—not a reliable conversion benchmark.

**Experiment:** production 5.9.25 gives the home, presentation, and document pages distinct
1,200-by-630 social cards composed from the canonical Ask Crump mark and restrained product copy.
The intervention changes only link previews; landing copy, signup behavior, pricing, and attribution
remain unchanged. Existing acquisition and signup events provide a privacy-safe onsite outcome.

**Decision rule:** observe for at least 14 days and at least 50 combined Facebook/social referral
visitors before comparing socially attributed `SignupIntent` reach with the pre-release directional
baseline. Keep the cards if qualified onsite intent improves without a material rise in bounce;
revise or revert if the preview attracts less-qualified traffic. Do not infer social click-through
rate without platform impression data.

### P1 — Prepare native store distribution without premature submission

**Evidence:** production 5.9.24 is healthy; the Android release source regenerates as build 50924
with API 36, the permanent package ID, generated assets, cleartext/backup protections, and a passing
native source verifier. Structured en-US metadata passes current field limits. A reviewed Node 22
lockfile now supports clean `npm ci`, a zero-vulnerability npm audit, and deterministic Android
preparation from an isolated worktree. GitHub run `33119777888` generated the 5.9.24 iOS project and
compiled its unsigned Release configuration on hosted macOS with no signing or upload credentials.
GitHub run `33119777893` generated the 5.9.24/build 50924 Android project under Java 21, passed the
native and signing-control verifiers, compiled `bundleRelease`, and confirmed a non-empty unsigned
`.aab`, also with no signing or upload credentials. Firebase, RevenueCat public keys/products,
signing credentials,
publisher-account state, reviewer access, signed builds, physical-device results, screenshots, and
console declarations are not yet verified.

**Outcome:** produce exact signed Android and iOS candidates with truthful listings, reviewer access,
privacy/data-safety reconciliation, native purchase restoration, AI reporting, deletion, push,
accessibility, and reliable core workflows proven in internal testing.

**Release gate:** resolve every platform blocker in
`docs/STORE_READINESS_AUDIT_2026-08-27.md`, review the final signed-build packet with the owner, and
obtain explicit per-platform approval before submission. Never claim store availability from source
readiness alone.

### P2 — Prove the advertising creative system

**Evidence:** Deevid has produced promising video candidates, but the two newest candidate files
have not yet received a completed frame-by-frame review because screen control was paused.

**Outcome:** a restrained campaign library organized by hook, audience, duration, CTA, and funnel
stage, with branding added in post to prevent generated-logo distortion.

**Release gate:** creative QA, licensed audio/visual provenance, mobile-safe text, platform-native
aspect ratios, one measurable CTA, and controlled tests against activation—not view count alone.

## Next operating decision

Submit the live canonical sitemap after owner confirmation, allow the social-preview experiment to
reach its minimum observation window, then obtain the first consented
post-instrumentation account, durable-value, return, referral, and artifact-journey observations.
Do not rewrite the signup flow from anonymous seven-day aggregates that cross the measurement
boundary; diagnose the next real post-boundary attempt instead. Keep both new provider foundations
off. Do not enable Crump Code until the real sandbox/OIDC test, review UI, monitoring, and benchmark
gates pass. Do not enable Crump Voice until its disclosure, key, voice rights, and playback tests
are approved.
