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
| Crump Code private foundation | Commit `018b46c`; deployment `dpl_GjeFNqmhK32QeyQyXKLrDoePxViu`; production 5.9.35 adds a Project-attached review workspace for repository/revision/mode/objective/cost confirmation, task status, explicit approvals, verification, history, cancellation, and patch download. Preparation does not run or charge; the client and server both require explicit run confirmation, and cancellation is checked before each next model/tool step. The Create entry remains hidden unless the server reports configured plus entitled. All 313 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33134659887`, Android run `33134659984`, and iOS run `33134659934` passed. Production health returned 5.9.35; assets returned 200; the inspected deployment had no runtime error cluster, 5xx, severe log, or `/api/code` request. The feature flag remains off pending the live sandbox/OIDC test, expiry exercise, and benchmark. | Staged, disabled |
| Clear signup password readiness | Commit `40bbc28`; deployment `dpl_5kDcdWj7KpWHbq9kXrjDJacQjESV`; production 5.9.36 replaces a late static password hint with three live, visible rule states plus a polite screen-reader status and post-review invalid state. The unchanged policy remains ten to 256 characters with a letter and number; auth, verification, pricing, and analytics semantics did not change. All 314 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33135663864`, Android run `33135663895`, and iOS run `33135663885` passed. Production health returned 5.9.36; the app and changed assets returned 200; the inspected release had no runtime error cluster, severe log, or 5xx. Local desktop/short-phone states had no overflow and no production event or account creation. Signup lift remains unproven. | Verified delivery; outcome pending |
| Durable registration verification handoff | Commit `ebd1454`; deployment `dpl_EVrjwoQRXALKP1UvqvSnpZYsFsnj`; production 5.9.37 replaces a 1.8-second success message and generic-login redirect with a persistent, focused inbox-confirmation state, prefilled email, explicit verified/sign-in action, resend action, and durable success/failure feedback. The account-created/email-delivery-failure branch uses the same recovery surface, and content-free account creation now records only sent/failed verification delivery. Password, registration, verification, authentication, pricing, and entitlement policy remain unchanged. All 315 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33136496183`, Android run `33136496185`, and iOS run `33136496204` passed. Production health returned 5.9.37; the app and changed assets returned 200; the inspected release had no runtime error cluster, severe log, 5xx, or registration request. No account or synthetic funnel event was created. | Verified delivery; outcome pending |
| Optional profile activation entry | Commit `81b39be`; deployment `dpl_G7oecbc71CPp6913TWvDoacTxsSv`; production 5.9.38 removes the mandatory display-name commitment between verified, terms-accepted users and the first workspace. Terms remain required and server-saved; name setup is a dismissible, account-scoped launchpad prompt, and `OnboardingCompleted` remains server-authoritative. Settings no longer reports a rejected profile update as saved. All 320 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33137238298`, Android run `33137238297`, and iOS run `33137238319` passed. Production health returned 5.9.38; the app and changed assets returned 200; the inspected deployment had no runtime error cluster, severe log, 5xx, signup, profile, terms, account, or activation request. No synthetic account or event was created. | Verified delivery; outcome pending |
| Reliable first workspace choice | Commit `e8fb9f0`; deployment `dpl_HE8v2SbtqeuayEJajMYiTrLt3Q1p`; production 5.9.39 replaces the launchpad's fixed 120-millisecond Projects/Video readiness guess with the runtime completion event. A delayed-load browser reproduction recorded starter intent but opened nothing under the old path; the corrected path waits visibly, opens the queued workspace exactly once, restores the card, reports a real asset failure, and lets the latest choice win. All 324 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33137897554`, Android run `33137897556`, and iOS run `33137897614` passed. Production health returned 5.9.39; the live readiness/cache assets returned 200; the release had no runtime error cluster, non-informational log, or 5xx. No production click, account, or synthetic event was created. | Verified delivery; outcome pending |
| Truthful first-prompt handoff | Commit `3ab5acb`; deployment `dpl_CT2aQtDDAwNLAEc2MzDwoWkvCaeW`; production 5.9.40 corrects a browser-reproduced composer handoff where Research/Image erased an existing draft and programmatic text did not update the active composer state. Research, Image, and Code now prefix the draft once, emit the real input event, preserve focus/caret, and stop an exact bare scaffold before usage checks or chat mutation. File and starter-intent contracts remain unchanged. All 329 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33138434467`, Android run `33138434500`, and iOS run `33138434478` passed. Production health returned 5.9.40; live composer/cache assets returned 200; the release had no runtime error cluster, non-informational log, or 5xx. No production prompt, account, usage check, or synthetic event was created. | Verified delivery; outcome pending |
| Reliable authenticated entry | Commit `ee3862d`; deployment `dpl_7sBD8Y3e8oyW696ec7HpHBLNLMVU`; production 5.9.41 removes the secondary full-state sync from the authenticated-entry critical path. A credential-free browser fixture proved that a never-settling sync left a completed login on a permanently disabled `Signing in…` button and a restored session on a blank screen. Both corrected paths open the account-scoped shell immediately while the existing server-authoritative synchronizer continues in the background. Credentials, verification, session rotation, cookies, ownership, pricing, entitlements, analytics, Supabase schema, and RLS remain unchanged. All 332 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33139229180`, Android run `33139229175`, and iOS run `33139229205` passed. Production health returned 5.9.41; the live shell/controller/cache assets returned 200; the release had no runtime error cluster, warning/error/fatal log, or 5xx. The fixture made no production write; owner credential-entry recheck remains pending. | Verified delivery; human proof pending |
| Crump Voice private foundation | Explicit signed-in playback route, Professional entitlement, rate/character/audio limits, provider-failure refund, server-held ElevenLabs key, non-cacheable ephemeral MP3 response, and device-speech fallback are implemented. Public feature flag remains off pending approved disclosure, credentials/voice rights, and smoke tests. | Staged, disabled |
| Private conversation-to-Project continuity | Commit `e99fc1f`; production 5.9.22 puts `Keep in a Project` directly on the latest result, reducing durable-work preservation from two commitments to one. The existing server route synchronizes and ownership-checks the chat, attaches idempotently to the selected/new Project, and records only a content-free Project milestone. All 285 tests, backend lint/compile checks, 40 JavaScript validations, production preflight, and native web-bundle build passed. Live health and version checks returned HTTP 200, the deployed client contained the direct action, and the deployment-scoped error/fatal scan was empty. | Verified |
| Comparable growth-cohort boundary | Supabase migration `product_growth_measurement_boundary`; live first-event evidence fixes the lower bound at `2026-08-23 09:10:55.602863+00`; the 30-day report now returns 18 metrics and zero comparable external accounts instead of misclassifying three historical accounts. The function remains security invoker, `anon`/`authenticated` execution is denied, `service_role` execution succeeds, and post-change advisors reported no errors or warnings. | Verified |
| Truthful organic discovery | Commit `150ced2`; deployment `dpl_HUbcyLdLFdh7SVpqF3S99XL3caMo`; production 5.9.23 adds unique, crawlable presentation and document workflow pages, homepage/cross-page links, canonical metadata, valid JSON-LD, and a four-URL sitemap. Known search referrers collapse to `organic` without retaining the referrer URL or query, and internal CTA placements cannot overwrite acquisition. All 290 backend tests, 40 JavaScript validations, production/native bundle checks, CI run `33116981568`, Android run `33116981449`, iOS run `33116981462`, clean-URL HTTP checks, desktop/mobile browser checks, and the deployment-scoped error/fatal scan passed. | Verified |
| Truthful referral delivery | Commit `a7f3482`; deployment `dpl_2zxpBU85E3uJkygbmmjquhq4fVQJ`; production 5.9.24 keeps the post-useful-result invitation content-free and carries only aggregate `referral` acquisition plus `response-share` placement into registration. The registration server preserves `referral` on `AccountCreated`. Denied clipboard access can no longer display a false success or record `ResponseShared`; an executable browser-script contract proves failed copy records zero events while a verified fallback records exactly one. All 291 backend tests, 40 JavaScript validations, production/native/store checks, CI run `33119777886`, Android run `33119777893`, iOS run `33119777888`, live route/version checks, and the deployment-scoped error/fatal scan passed. A legitimate referred account and activated outcome have not yet been observed. | Verified delivery; outcome pending |
| Measurable social previews | Commit `6d2c24f`; deployment `dpl_CZih5NeHk8JjDp1tukrLZPCXhioD`; production 5.9.25 gives the home, presentation, and document pages distinct 1,200-by-630 social cards composed from the canonical mark, with large-card metadata and truthful page-specific copy. The generator is deterministic on the verified release machine; automated tests validate PNG format, dimensions, color mode, and per-page references. All 292 backend tests, 40 JavaScript validations, production/native/store checks, CI run `33123220073`, Android run `33123220055`, iOS run `33123220046`, six live route/asset checks, and the deployment-scoped warning/error/fatal/5xx scan passed. Socially attributed signup outcome remains unproven. | Verified delivery; outcome pending |
| Direct canonical native/payment host | Source correction shipped in 5.9.26. With owner approval, both live Stripe destinations were then changed to their direct `https://www.askcrump.com/...` handlers without rotating secrets or widening their permanent event allowlists. A signed subscription replay returned 200. The first signed credits replay exposed a deployed plural environment-key alias; commit `4dfed9b` added a backward-compatible, precedence-tested alias without exposing or rotating the secret. Deployment `dpl_H5Dn15BVY5rzh5G6azq36eKiTXb3` is `READY` on production 5.9.27, a final signed credits replay returned 200, and the temporary harmless test event was removed. All 295 backend tests, 40 JavaScript validations, production/native/store checks, CI run `33126121600`, Android run `33126121646`, and iOS run `33126121595` passed. Production health returned 5.9.27, the payment routes had no runtime error cluster, and the deployment log breakdown contained only 200/302 responses. | Verified end to end |
| Named recent-work continuation | Commit `6161778`; deployment `dpl_EJmVH3eLTbfQdPzLCpyLZ6H22RUj`; production 5.9.28 replaces the generic return card with the actual local conversation name and a clear continuation cue. Names are whitespace-normalized, length-bounded, rendered with `textContent`, visually ellipsized, and used only in the signed-in interface; `RecentWorkResumed` remains free of chat IDs, titles, and content. All 295 backend tests, lint, 40 JavaScript validations, production/native/store checks, CI run `33126950108`, Android run `33126950133`, and iOS run `33126950091` passed. Production health returned 5.9.28, desktop/mobile browser checks passed, the card opened the intended conversation, and the deployment had no runtime error cluster or warning/error/fatal/5xx response. The comparable external cohort remains zero, so no retention lift is claimed. | Verified delivery; outcome pending |
| Reliable web-session handoff | Commit `38f7d11`; deployment `dpl_4H1xjuSyrC9dBxg5WWZ95jkfrox8`; production 5.9.29 repairs a user-observed false login failure. Runtime evidence showed successful login/session writes followed by immediate unauthenticated confirmation probes. The server now checks a bounded set of same-name cookie candidates while preserving bearer precedence, canonical login retires the legacy parent-domain cookie, logout clears both scopes, and the client rotates once before bounded confirmation probes. The auth asset is release-versioned and network-first. All 298 tests, lint, 40 JavaScript validations, production/native/store checks, CI run `33128276341`, Android run `33128276312`, and iOS run `33128276343` passed. Production health returned 5.9.29, an authenticated browser opened the workspace, and the deployment had only 200 responses with no runtime error cluster or warning/error/fatal logs in the inspected window. | Verified repair; owner credential-entry recheck pending |
| Five-destination workspace navigation | Commit `86dfb2c`; deployment `dpl_8q5SK1mLXcqcExhLBvH9wgHPeTbT`; production 5.9.30 organizes the signed-in product around Ask, Projects, Create, Library, and You. It reuses every existing owner-scoped data/API/entitlement surface, adds a non-generating Create chooser, keeps Research inside Ask, and provides a device-local legacy rollback switch. All 303 tests, lint/compile, 41 JavaScript validations, production/native/store checks, CI run `33129397532`, Android run `33129397531`, and iOS run `33129397539` passed. Production health and six release assets returned 200; authenticated desktop/mobile checks passed; the inspected deployment had 23 successful 200 responses with no 5xx, warning/error/fatal log, or runtime error cluster. | Verified first slice; usability outcome pending |
| Resumable Project conversations | Commit `e67ff3b`; deployment `dpl_3FzSEnwGFXSTxh73AcdcXUD28U3t`; production 5.9.31 closes the gap between keeping work and finding it again. Owned Projects now show content-free conversation metadata and a Continue action that syncs a missing cross-device conversation before opening it. The authenticated endpoint requires both Project and conversation ownership, excludes deleted chats, and never returns messages or files. All 306 tests, lint, 41 JavaScript validations, production/native/store checks, CI run `33130217575`, Android run `33130217571`, and iOS run `33130217560` passed. Production health and release assets returned 200; the unauthenticated route returned the expected 401; an authenticated desktop/mobile audit rendered two real linked conversations without generating a synthetic resume event; the inspected deployment had no runtime error cluster or non-informational log level. | Verified delivery; retention outcome pending |
| Expanded high-intent organic discovery | Commit `afd5473`; deployment `dpl_3VQGjdTVUeDNNzRHqRa1UprHHZ2e`; production 5.9.32 adds focused, crawlable AI résumé-builder and AI video-generator pages around capabilities already verified in production. Résumé claims are fact-grounded and reject invented experience; video copy exposes credit use, compatibility, and variable output. The homepage and existing use-case pages now form a four-capability internal-link graph, the sitemap contains six canonical URLs, and both new pages have unique JSON-LD and deterministic 1,200-by-630 social cards. All 306 tests, lint, 41 JavaScript validations, production/native/store checks, CI run `33131314907`, Android run `33131314974`, and iOS run `33131314943` passed. Production health returned 5.9.32; both clean URLs, both cards, and the sitemap returned 200; desktop/phone layout checks found no horizontal overflow; the inspected deployment reported no runtime error cluster and only 200 responses. | Verified delivery; acquisition outcome pending |
| Accessible public first visit | Commit `8d03ce7`; deployment `dpl_9sMBVqXWhqSS3QgRkXYKr1G3b62o`; production 5.9.33 raises muted marketing text to WCAG AA contrast while preserving the black/charcoal/gold system. Mobile Lighthouse moved the homepage and résumé page from accessibility 95 with 13 and four contrast failures respectively to accessibility 100 with zero failures; both production runs also scored 100 for performance, best practices, and SEO. A deterministic relative-luminance test covers ten selector/background pairs. All 307 tests, lint, 41 JavaScript validations, production/native/store checks, CI run `33132384656`, Android run `33132384622`, and iOS run `33132384717` passed. Production health returned 5.9.33; mobile browser checks found no overflow or console warning/error; the inspected deployment reported no runtime error cluster and only 200 responses. | Verified delivery; acquisition outcome pending |
| Accessible workspace zoom | Commit `7f6013b`; deployment `dpl_4SgvrggyDSKbr5jJuEzipjhdo4yF`; production 5.9.34 removes the app-wide maximum-scale, user-scaling, Safari gesture, and two-finger touch blockers. The shell retains no-drift constraints and 16-pixel mobile editor safeguards while explicitly allowing vertical pan and pinch zoom. Registration moved from a local Lighthouse accessibility score of 93 with a failed meta-viewport audit to 100; local signed-out and production registration states also scored 100 with zero contrast failures. All 307 tests, lint, 41 JavaScript validations, production/native/store checks, CI run `33133179838`, Android run `33133179924`, and iOS run `33133179768` passed. Production health returned 5.9.34; the short-phone primary action stayed visible with no overflow or console issue; the inspected deployment reported no runtime error cluster, warning/error/fatal log, or 5xx response. | Verified web/PWA delivery; signed-device zoom check pending |

### Current production reliability checkpoint

A project-wide production runtime scan covering the trailing 24 hours on 2026-08-27 found no
runtime error clusters, no error/fatal/warning log entries, and no 5xx responses. The status
breakdown contained 1,841 successful 200 responses and five expected 401 responses from explicit
unauthenticated release probes against the disabled Crump Code, disabled Crump Voice, and private
Project attachment routes. A later user report exposed a client-visible login failure despite four
successful login responses and persisted sessions. Immediate confirmation probes were
unauthenticated before reaching the session table, which justified the 5.9.29 cookie/handoff
repair. The repaired deployment returned only 200 responses and no runtime error cluster or
warning/error/fatal logs in its inspected release window.

The 5.9.31 Project-resume release then rendered real owner-linked conversation metadata on desktop
and mobile without exposing message content or generating a synthetic retention event. Its inspected
deployment window showed no runtime error cluster, informational logs only, 41 successful 200
responses, and one expected 401 from the explicit unauthenticated ownership probe among the
reported status groups.

The 5.9.32 acquisition release then added two evidence-backed public entry pages without changing
authentication, billing, or private data. Production served both clean URLs, both page-specific
social cards, and the six-URL sitemap with 200 responses. The inspected deployment window reported
no runtime error cluster and only successful 200 responses. The comparable external cohort was zero
before release, so delivery is verified while acquisition lift remains unproven.

The 5.9.33 accessibility release then corrected 17 observed mobile contrast failures across the
homepage and résumé page. Both production pages now score 100 for accessibility with zero contrast
failures while retaining 100 performance, best-practices, and SEO scores in the verification runs.
Phone-size browser checks found no overflow or console issue, production health returned 5.9.33,
and the inspected deployment window reported no runtime error cluster and only 200 responses.

The 5.9.34 workspace accessibility release then removed the app-wide user-zoom lock and gesture
blockers while preserving horizontal-drift and mobile-input safeguards. The local registration
state moved from accessibility 93 to 100, and the local signed-out and production registration
states also scored 100 with zero contrast failures. Production health returned 5.9.34; the inspected
deployment reported no runtime error cluster, warning/error/fatal log, or 5xx response. Exact signed
device zoom and zoomed-layout usability remain store gates.

The 5.9.35 Crump Code review release then added the missing human control surface without enabling
the provider. Production health and six release assets returned 200, the Create entry remained
hidden behind configured-plus-entitled server state, and the inspected deployment had no runtime
error cluster, 5xx response, warning/error/fatal log, or `/api/code` request. Local browser evidence
proved the disabled state and the review-confirmation gate without creating a production task or
charge.

The 5.9.36 signup-guidance release then corrected a reproducible pre-submit clarity defect without
changing authentication. A short-phone browser check proved independent length/letter/number states,
polite status text, post-review invalid state, no horizontal or vertical overflow, and an above-fold
primary action. Production health and the app/release assets returned 200; the inspected deployment
had no runtime error cluster, warning/error/fatal log, or 5xx response. No production signup event
was generated, so delivery is verified while conversion impact remains unproven.

The 5.9.37 registration-handoff release then corrected the next reproducible activation defect:
successful registration no longer loses its verification instruction after 1.8 seconds. The
persistent state keeps the destination email, resend recovery, and sign-in continuation visible,
including when the account exists but initial email delivery fails. Production health and the live
shell/controller/stylesheet/service worker returned 200; the inspected deployment had no runtime
error cluster, warning/error/fatal log, 5xx response, or registration request. CI plus both hosted
unsigned native compiles passed. No synthetic account or event was created, so outcome remains
unproven.

The 5.9.38 first-workspace release then removed the nonessential display-name commitment after
verification and terms acceptance. Terms enforcement and server persistence remain unchanged; the
workspace now starts first and offers an optional, dismissible personalization prompt. Production
health and the changed release assets returned 200; the exact deployment had no runtime error
cluster, warning/error/fatal log, 5xx response, or signup/profile/terms/account/activation request.
CI plus both hosted unsigned native compiles passed. The owner's remembered-device path worked;
fresh credential-entry proof after sign-out remains pending. No synthetic account or event was
created, so activation impact remains unproven.

The 5.9.39 first-action release then corrected a deterministic slow-load race. The launchpad wired
Projects and Video before their product runtime, while a single 120-millisecond retry could expire
silently after already recording starter intent. A delayed local browser proved the old failure and
the event-driven correction, including visible busy state, explicit failure feedback, and latest-
choice behavior. Production health and the live readiness/cache assets returned 200; the exact
deployment had no runtime error cluster, non-informational log, or 5xx response. CI plus both hosted
unsigned native compiles passed. No production click, account, or synthetic event was created, so
activation impact remains unproven.

The 5.9.40 first-prompt release then corrected two browser-reproduced composer defects. Research
and Image erased an existing draft, while programmatic scaffolds did not emit the input event that
drives active/send/resize state. The corrected path preserves and prefixes the draft once, aligns
the real DOM state, and stops an exact bare scaffold before usage or chat mutation. File selection
and starter measurement remain unchanged. Production health and live composer/cache assets
returned 200; the exact deployment had no runtime error cluster, non-informational log, or 5xx.
CI plus both hosted unsigned native compiles passed. No production prompt, account, usage check, or
synthetic event was created, so activation and cost outcomes remain unproven.

The 5.9.41 authenticated-entry release then corrected a second deterministic availability
boundary after credentials or a saved session had already been accepted. The client awaited an
unbounded full-state sync before routing, so a stalled sync could strand login on a disabled button
or leave restored-session entry blank. The corrected path opens the account-scoped shell first and
uses the existing non-blocking, server-authoritative synchronizer afterward. A credential-free
browser fixture proved both old failures and both corrected paths. Production health and the live
shell/controller/cache assets returned 200; the exact deployment had no runtime error cluster,
warning/error/fatal log, or 5xx. CI plus both hosted unsigned native compiles passed. The fixture
made no production write; fresh owner credential-entry proof remains pending.

### Current monetization checkpoint

A live Stripe reconciliation on 2026-08-27 found five active catalog products and no transactions,
active subscriptions, paid customers, gross volume, or balance. The single customer record is the
internal owner account with $0 spend. The Professional live price ID matches the production
fallback. With owner approval, both webhook destinations now use direct `www` URLs, preserve their
descriptions, API version, signing secrets, and original narrow event scopes, and have returned 200
to signed harmless replays. No price, product, customer, tax setting, payment, or secret was changed.

## Ranked execution backlog

### Completed P0 — Repair live Stripe webhook delivery before the first payment

**Evidence:** Stripe now sends subscription events directly to
`https://www.askcrump.com/api/stripe/webhook` and credit-purchase completion directly to
`https://www.askcrump.com/api/billing/credits/stripe-webhook`. Signed harmless event replays returned
200 from both destinations. The credits replay also proved the 5.9.27 environment-key compatibility
fix against production without rotating or displaying the signing secret.

**Outcome:** both direct canonical destinations are active with their original narrow allowlists:
three subscription events and one credit-completion event. The replayed event was an expired Checkout
Session, so neither handler performed a subscription or credit mutation. Exactly-once credit-grant
behavior remains covered by the automated handler suite and should be observed on the first real
credit purchase.

**Release gate:** passed with owner approval, before/after destination evidence, signed 200 responses,
restored allowlists, production 5.9.27 health, no route error cluster, and successful CI/Android/iOS
verification. Rollback is to restore the prior apex URLs, although Stripe would again classify their
307 redirects as failed delivery.

### P0 — Convert useful answers into continuing Project work

**Evidence:** two external accounts completed 14 successful AI jobs with no recorded failures, but
the external aggregate contains zero Projects and zero files, and no external activity occurred
after 2026-08-23. Release 5.9.22 exposed the durable-work action directly. Release 5.9.28 now names
the exact conversation on the most prominent return card instead of asking mobile users to resume
unknown work.

**Outcome:** expose private Project continuity directly on the latest result as a one-click next
action. Synchronize and ownership-check the conversation, attach it to the selected Project or
create one, and record only a content-free durable-value milestone. Keep feedback optional and
referral sharing secondary.

**Release gate:** automated ownership, mapping, direct-action ordering, content-free analytics, full
release verification, production health, desktop/mobile UI checks, and the named resume action passed
through 5.9.28. The remaining outcome gate is at least one legitimate external
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

**Evidence:** the server and private schema provide public-repository task creation, bounded tool
use, isolated execution, patch generation, verification, state transitions, cancellation, and
approval records. Production 5.9.35 adds the Project-attached human review surface, server-enforced
run confirmation, cost disclosure, patch download, and cancellation checks before every next
expensive step. The Create entry and provider remain disabled, and no real production sandbox run
has occurred.

**Outcome:** complete a human-visible workspace, diff and verification experience, prove the live
runtime boundary, add durable orchestration for longer work, and measure quality against a fixed
benchmark before any parity positioning.

**Release gate:** the human-visible cost/patch/approval UI, server confirmation, and local
cancellation-before-next-step contract passed in 5.9.35. Remaining gates are an approved sub-cent
sandbox smoke test, production OIDC verification, live cancellation and expiry tests, failure
monitoring, rollback exercise, a real approval-boundary scenario, and an end-to-end benchmark suite.
Do not advertise Codex or Claude Code parity until measured tasks show comparable completion
quality and safety.

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
Google is processing the property's first performance and indexing reports. Production 5.9.34 now
serves four high-intent capability pages at clean canonical URLs, links them from the homepage and
from each other, and includes all six public URLs in the live sitemap. The protected growth and
artifact reports still show zero comparable external activity, so acquisition is the current
evidence-backed bottleneck. A read-only Search Console inspection on 2026-08-27 showed that the
homepage is indexed, while the presentation, document, résumé, and video pages are all unknown to
Google with no referring sitemap or page detected. The Submitted sitemaps table contains zero rows.
A live URL test reports that the video page is available to Google and can be indexed, proving that
technical crawlability is not the current block. The sitemap is live and ready, but it is not
entered or submitted in Search Console.

**Outcome:** verified domain ownership, one canonical sitemap submitted, valid canonical URLs,
and indexed landing pages tied to privacy-safe account-creation attribution.

**Release gate:** Search Console verification, live sitemap delivery, clean canonical HTTP/browser
inspection, unique metadata, and a Google live crawlability test passed. Remaining gates are
owner-confirmed submission and Search Console acceptance of
`https://www.askcrump.com/sitemap.xml`, followed by an indexed-page coverage review after Google has
had time to crawl.

The authoritative action-time checklist is `docs/SEARCH_CONSOLE_RELEASE_GATE_2026-08-27.md`.

### P1 — Observe the new activation and referral funnel before scaling spend

**Evidence:** starter intent, activation, durable value, useful-result feedback, recent-work
continuation, response sharing, checkout, and paid status are now measurable. Production 5.9.24
also prevents a failed clipboard operation from being counted as a share and preserves the
content-free `referral` channel through account creation, but the comparable production cohort is
new and no legitimate referred activation has been observed. A production-only Vercel Web
Analytics read on 2026-08-27 showed 88 visitors, 238 page views, and 61% bounce over the trailing
seven days; 60 visitors reached `/app`, 20 visitors produced 24 `SignupIntent` events, and one
visitor produced one client `AccountCreated` event. Those anonymous aggregates span the
pre-instrumentation boundary and may include internal or automated visits, so they are not a
conversion rate. The last 24 hours showed 16 production visitors, 72 page views, three
`MarketingCTA` visitors, and two visitors each at `SignupIntent` and `SignupStarted`, with no
`SignupCredentialsReady`, `SignupSubmitted`, or `AccountCreated` event. Before 5.9.29,
`MarketingCTA` mixed account-creation and sign-in clicks; the release now records existing-account
traffic separately as `MarketingSignin`. The service-role comparable external funnel still
returned zero accounts at every stage in the latest refresh, and the aggregate artifact journey
returned no rows. A user-reported login handoff defect was repaired in 5.9.29, but no comparable external
account has yet been observed after the repair. The full content-free evidence boundary and
decision are recorded in `docs/OPERATING_SNAPSHOT_2026-08-27_2140.md`.

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

**Evidence:** production 5.9.41 is healthy; the Android release source regenerates as build 50941
with API 36, the permanent package ID, generated assets, cleartext/backup protections, and a passing
native source verifier. Structured en-US metadata passes current field limits. A reviewed Node 22
lockfile now supports clean `npm ci`, a zero-vulnerability npm audit, and deterministic Android
preparation from an isolated worktree. GitHub run `33139229205` generated the 5.9.41 iOS project and
compiled its unsigned Release configuration on hosted macOS with no signing or upload credentials.
GitHub run `33139229175` generated the 5.9.41/build 50941 Android project under Java 21, passed the
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

### P1 — Reorganize the product experience before store screenshots

**Evidence:** Ask Crump's current interface accumulated navigation, product, polish, library, and
legacy compatibility layers as capabilities expanded. The product now needs a calmer hierarchy
before native screenshots and acquisition campaigns lock in the existing structure. This is a
product-direction decision, not evidence that the working experience should be discarded.

Release 5.9.30 completes the first staged slice: one labeled five-destination model on desktop and
mobile plus a non-generating Create chooser. The migration map and rollback are recorded in
`docs/PRODUCT_REORGANIZATION_MAP_2026-08-27.md`. Production and hosted native verification passed;
real-user task-flow evidence remains open before final screenshots.

**Outcome:** organize the workspace around five user destinations: Ask, Projects, Create, Library,
and You. Keep Research as an intelligent mode within Ask; group documents, presentations, images,
and video under Create; preserve every account, conversation, Project, file, entitlement, and stable
deep link. Use restrained black/charcoal/gold styling, clear empty states, accessible motion, and
consistent mobile and desktop navigation.

**Release gate:** owner-approved information architecture and wireflow; a route/capability migration
map; staged implementation behind a rollback path; automated regression coverage; keyboard,
screen-reader, reduced-motion, and responsive checks; real-task usability review; production
reliability verification; and final store screenshots only from the exact signed candidate. Do not
begin a ground-up rewrite or major architecture change from visual preference alone.

### P2 — Prove the advertising creative system

**Evidence:** Deevid has produced promising video candidates, but the two newest candidate files
have not yet received a completed frame-by-frame review because screen control was paused.

**Outcome:** a restrained campaign library organized by hook, audience, duration, CTA, and funnel
stage, with branding added in post to prevent generated-logo distortion.

**Release gate:** creative QA, licensed audio/visual provenance, mobile-safe text, platform-native
aspect ratios, one measurable CTA, and controlled tests against activation—not view count alone.

## Next operating decision

Complete the owner-run sign-out and manual credential-entry proof. Submit the live canonical
sitemap after owner confirmation, allow the social-preview experiment to reach its minimum
observation window, then obtain the first consented post-instrumentation account, durable-value,
return, referral, and artifact-journey observations. Observe the first real checkout and reconcile
Stripe with Ask Crump entitlement/credit state. Do not rewrite the signup flow from anonymous
seven-day aggregates that cross the measurement boundary; diagnose the next real post-boundary
attempt instead. Keep both new provider foundations off. Do not enable Crump Code until the real
sandbox/OIDC test, review UI, monitoring, and benchmark gates pass. Do not enable Crump Voice
until its disclosure, key, voice rights, and playback tests are approved.
