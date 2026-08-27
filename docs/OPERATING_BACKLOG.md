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
| Private conversation-to-Project continuity | Commit `edfd7d2`; useful-result UI prioritizes keeping work before referral; the server synchronizes and ownership-checks the chat, attaches idempotently to the selected/new Project, and records only a content-free Project milestone. All 284 tests, backend checks, 40 JavaScript validations, production preflight, and native web-bundle build passed. Production 5.9.20 health returned HTTP 200, both client assets were live, the new route returned 401 without authentication, and the initial runtime-error scan was clean. | Verified |

## Ranked execution backlog

### P0 — Convert useful answers into continuing Project work

**Evidence:** two external accounts completed 14 successful AI jobs with no recorded failures, but
the external aggregate contains zero Projects and zero files, and no external activity occurred
after 2026-08-23. The useful-result UI previously promoted referral sharing before preserving the
user's own work.

**Outcome:** after a user confirms that an answer moved work forward, make private Project continuity
the primary next action. Synchronize and ownership-check the conversation, attach it to the selected
Project or create one, and record only a content-free durable-value milestone. Keep referral sharing
secondary.

**Release gate:** automated ownership, mapping, ordering, analytics, full release verification, and
production health passed in 5.9.20. The remaining outcome gate is at least one legitimate external
conversation-to-Project transition and a later return. Do not infer a retention rate from a single
user.

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

**Evidence:** the Search Console domain property and DNS verification record were created, but
verification and sitemap submission still depend on DNS propagation.

**Outcome:** verified domain ownership, one canonical sitemap submitted, valid canonical URLs,
and indexed landing pages tied to privacy-safe account-creation attribution.

**Release gate:** Search Console verification succeeds, `https://www.askcrump.com/sitemap.xml`
is accepted, canonical inspection is clean, and indexed-page coverage is reviewed after Google
has had time to crawl.

### P1 — Observe the new activation and referral funnel before scaling spend

**Evidence:** starter intent, activation, durable value, useful-result feedback, recent-work
continuation, response sharing, checkout, and paid status are now measurable, but the comparable
production cohort is new.

**Outcome:** a weekly operating review of account creation → workspace open → starter intent →
activation → durable value → useful outcome → return/share → checkout → paid.

**Release gate:** at least one fully elapsed D7 cohort, explicit denominators, internal accounts
excluded, and a written decision for the largest observed drop-off. Treat small samples as
directional rather than statistically conclusive.

### P2 — Prove the advertising creative system

**Evidence:** Deevid has produced promising video candidates, but the two newest candidate files
have not yet received a completed frame-by-frame review because screen control was paused.

**Outcome:** a restrained campaign library organized by hook, audience, duration, CTA, and funnel
stage, with branding added in post to prevent generated-logo distortion.

**Release gate:** creative QA, licensed audio/visual provenance, mobile-safe text, platform-native
aspect ratios, one measurable CTA, and controlled tests against activation—not view count alone.

## Next operating decision

Ship and verify conversation-to-Project continuity, then obtain the first consented
post-instrumentation durable-value, return, and artifact-journey observations. Keep both new provider
foundations off. Do not enable Crump Code until the real sandbox/OIDC test, review UI, monitoring,
and benchmark gates pass. Do not enable Crump Voice until its disclosure, key, voice rights, and
playback tests are approved.
