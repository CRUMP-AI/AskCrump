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
Google is processing the property's first search and indexing data. The canonical sitemap is entered
and ready for final owner-confirmed submission.

**Outcome:** verified domain ownership, one canonical sitemap submitted, valid canonical URLs,
and indexed landing pages tied to privacy-safe account-creation attribution.

**Release gate:** Search Console verification passed. Remaining gates are acceptance of
`https://www.askcrump.com/sitemap.xml`, clean canonical inspection, and indexed-page coverage review
after Google has had time to crawl.

### P1 — Observe the new activation and referral funnel before scaling spend

**Evidence:** starter intent, activation, durable value, useful-result feedback, recent-work
continuation, response sharing, checkout, and paid status are now measurable, but the comparable
production cohort is new.

**Outcome:** a weekly operating review of account creation → workspace open → starter intent →
activation → durable value → useful outcome → return/share → checkout → paid.

**Release gate:** at least one fully elapsed D7 cohort, explicit denominators, internal accounts
excluded, and a written decision for the largest observed drop-off. Treat small samples as
directional rather than statistically conclusive.

### P1 — Prepare native store distribution without premature submission

**Evidence:** production 5.9.22 is healthy; the Android release source regenerates as build 50922
with API 36, the permanent package ID, generated assets, cleartext/backup protections, and a passing
native source verifier. Structured en-US metadata passes current field limits. A reviewed Node 22
lockfile now supports clean `npm ci`, a zero-vulnerability npm audit, and deterministic Android
preparation from an isolated worktree. GitHub run `33111605249` generated the iOS project and
compiled its unsigned Release configuration under Xcode 16.4 with no signing or upload credentials.
The matching Java 21 Android App Bundle cloud verifier is prepared for its first run. Firebase,
RevenueCat public keys/products, signing credentials,
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

Submit the staged canonical sitemap after owner confirmation, then obtain the first consented
post-instrumentation durable-value, return, and artifact-journey observations. Keep both new provider
foundations off. Do not enable Crump Code until the real sandbox/OIDC test, review UI, monitoring,
and benchmark gates pass. Do not enable Crump Voice until its disclosure, key, voice rights, and
playback tests are approved.
