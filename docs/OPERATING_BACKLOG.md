# Ask Crump operating backlog

Last updated: 2026-08-28

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
| Restrained presentation visual rhythm | Commit `8610584`; deployment `dpl_5gfTeD8G3StkKRvvNhpdEufe3gtQ`; production 5.9.58 replaces repetitive equal-column output with editable statement, alternating split, asymmetric three-point, evidence, data, and purposeful dark layouts. A single table lead now stays with its native chart instead of creating a sparse duplicate slide. A nine-slide mixed deck and four-slide rhythm deck passed native PowerPoint render review with zero measured text overflow; all 384 tests, 44 JavaScript validations, production/native/store checks, CI `33192168201`, Android `33192168206`, and iOS `33192168205` passed. Production returned 5.9.58/cache revision 92 with no release-window runtime error. | Verified delivery; real-user quality outcome pending |
| Discoverable desktop conversations | Commit `cd87e3f`; deployment `dpl_HnFmTa3DKW1Vk6Knz2nRgLHuLCbE`; production 5.9.59 responds to a direct owner discovery failure by naming New, Chats, and Projects in the compact desktop rail. Chats now exposes and visually tracks its open state, preserves the remembered preference, and makes the collapsed list hidden plus inert. A credential-free browser proved both accessible states without a network write. All 387 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI `33195911931`, Android `33195912823`, and iOS `33195912147` passed. Production returned 5.9.59/cache revision 93 with no release-window runtime error cluster. | Verified delivery; returning-user outcome pending |
| Reliable desktop and mobile navigation | Commit `61ea00a`; deployment `dpl_AxX8py6sdMRREjqR5YXCSqtf4Puq`; production 5.9.60 corrects two owner-reproduced failures. The final desktop shell now retains a permanent Chats control and clears the stranded collapse preference once; mobile conversation options use a hydration-safe delegated handler, while Projects, Settings, and Plan & credits open before the drawer closes. A production-layer fixture and authenticated live checks proved exact conversation options, all three mobile destinations, and desktop collapse/reopen state. All 391 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI `33199837780`, Android `33199837741`, and iOS `33199837726` passed. Production serves 5.9.60/cache revision 94 with no release-window runtime error cluster. | Verified repair; repeated real-device use pending |
| Truthful Project continuity destination | Commit `dd7848a`; deployment `dpl_Fh7ZLzDbBNLHPVneLsmX1YQvZmWh`; production 5.9.61 replaces `Keep in a Project` with `Start a Project` or the exact named destination, then freezes that target at click time so delayed hydration cannot silently reroute the save. A local production-layer fixture proved selected, new, and delayed-loading paths with exact requests and zero browser errors; authenticated production inspection confirmed the named action without writing Project data. All 391 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI `33201063440`, Android `33201063452`, and iOS `33201063450` passed. Production serves 5.9.61/cache revision 95 with no release-window runtime error cluster. | Verified delivery; Project-adoption and return outcome pending |
| Truthful presentation output proof | Commit `84eddec`; deployment `dpl_J49gDvXouaQXjiWpobM4kSowkby7`; production 5.9.62 adds three 1,600-by-900 synthetic slide renders from the current PowerPoint exporter to the presentation page. The gallery is explicitly representative, makes no universal-quality claim, and contains no customer content or testimonial. Desktop and 390-pixel mobile checks proved the three-image layout, full source dimensions, zero horizontal overflow, and zero browser errors. All 393 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI `33202997095`, Android `33202997026`, and iOS `33202997094` passed. Production serves 5.9.62/cache revision 96 with no 30-minute runtime error cluster. | Verified delivery; acquisition-to-artifact outcome pending |
| Dedicated private Library | Commit `4fc7b40`; deployment `dpl_H8AmzuGM8t6AvR1gVrZNNmPTYSeD`; production 5.9.63 consolidates the manuscript bookshelf and saved documents/images/videos/exports/uploads into one top-level Library, removes the redundant Saved/Library workspace tab, preserves Chats as conversation history, and restores Files to attachment. Desktop and 390-pixel fixture checks proved one visible Library panel, both owner-scoped content groups, correct active state, intact Projects/Create paths, and zero browser errors; authenticated production proved the same dedicated structure without recording private content. All 394 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI `33204557657`, Android `33204557680`, and iOS `33204557672` passed. Production serves 5.9.63/cache revision 97 with no 30-minute runtime error cluster. | Verified delivery; reuse and return outcome pending |
| Isolated primary destinations | Commit `bdef095`; deployment `dpl_5F2JeFyYrGwGvHaLuFqw66cwWyPm`; production 5.9.64 removes the remaining Projects/Manuscripts/Video tab bar, gives Projects, Manuscripts, Video Studio, and Library distinct titles and active primary destinations, and adds an explicit Projects recovery when Manuscripts has no active Project. Files remains attachment and Chats remains history. Desktop and 390-pixel fixture checks plus authenticated production proved exactly one visible panel, zero internal tabs, correct active state, and contained mobile width without writing customer data. All 395 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI `33207125922`, Android `33207125976`, and iOS `33207125988` passed. Production serves 5.9.64/cache revision 98 with no 30-minute runtime error cluster or warning/error/fatal deployment log. | Verified delivery; discovery, reuse, and return outcomes pending |
| Clean cross-device conversation startup | Commit `1d7e908`; deployment `dpl_DU1j6CsCCnHFGBcjtH4quoYjAych`; production 5.9.65 keeps an untouched fresh canvas ephemeral and materializes a conversation only when a real send begins. Local cache, server merge, and outbound sync suppress legacy default-titled empty rows without deleting server/customer data. A production-layer fixture proved a clean device pulling one real chat plus two legacy blanks retained exactly one durable row and pushed zero blanks, then created exactly one conversation on first send. The same release removes programmatic-focus inflation from `SignupStarted`. All 399 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI `33210710079`, Android `33210710087`, and iOS `33210710074` passed. Production serves 5.9.65/cache revision 99 with no one-hour runtime error cluster or warning/error/fatal deployment log. | Verified repair; repeated real-device history cleanliness pending |
| Distinct company identity and contained desktop canvas | Feature commit `05418a5`; routing stabilization `8b960d1`; final deployment `dpl_Em4W8i3M1jjFPexcv33hkXBcNo3c`; production 5.9.66 gives Clever Crump a dedicated parent-company landing at both clean root domains while preserving the Ask Crump product root. It also cancels a legacy 292-pixel offset that was double-counting the open Chats library and pushing the signed-in workspace beyond a 1,280-pixel viewport. Desktop and 375-pixel fixtures, production screenshots, and semantic snapshots proved distinct brand surfaces, a centered contained app canvas, and zero measured horizontal overflow. All 402 tests, lint/compile, 44 JavaScript validations, production/native/store checks, feature CI `33213150773`, Android `33213150645`, iOS `33213150810`, and routing CI `33213752591` passed. Production health serves 5.9.66 and the one-hour warning/error/fatal scan was empty. | Verified delivery; brand handoff and first-use outcomes pending |
| Private artifact journey telemetry | Commit `f497ab0`; entitled request, successful packaging, packaging failure, and first-download events are server-authoritative and content-free; Supabase migration `artifact_journey` is recorded; anonymous and authenticated roles cannot execute the aggregate report while `service_role` can; 265 backend tests, JavaScript validation, production preflight, production health, and post-deploy runtime checks passed. | Verified |
| Crump Code private foundation | Commit `018b46c`; deployment `dpl_GjeFNqmhK32QeyQyXKLrDoePxViu`; production 5.9.35 adds a Project-attached review workspace for repository/revision/mode/objective/cost confirmation, task status, explicit approvals, verification, history, cancellation, and patch download. Preparation does not run or charge; the client and server both require explicit run confirmation, and cancellation is checked before each next model/tool step. The Create entry remains hidden unless the server reports configured plus entitled. All 313 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33134659887`, Android run `33134659984`, and iOS run `33134659934` passed. Production health returned 5.9.35; assets returned 200; the inspected deployment had no runtime error cluster, 5xx, severe log, or `/api/code` request. The feature flag remains off pending the live sandbox/OIDC test, expiry exercise, and benchmark. | Staged, disabled |
| Clear signup password readiness | Commit `40bbc28`; deployment `dpl_5kDcdWj7KpWHbq9kXrjDJacQjESV`; production 5.9.36 replaces a late static password hint with three live, visible rule states plus a polite screen-reader status and post-review invalid state. The unchanged policy remains ten to 256 characters with a letter and number; auth, verification, pricing, and analytics semantics did not change. All 314 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33135663864`, Android run `33135663895`, and iOS run `33135663885` passed. Production health returned 5.9.36; the app and changed assets returned 200; the inspected release had no runtime error cluster, severe log, or 5xx. Local desktop/short-phone states had no overflow and no production event or account creation. Signup lift remains unproven. | Verified delivery; outcome pending |
| Durable registration verification handoff | Commit `ebd1454`; deployment `dpl_EVrjwoQRXALKP1UvqvSnpZYsFsnj`; production 5.9.37 replaces a 1.8-second success message and generic-login redirect with a persistent, focused inbox-confirmation state, prefilled email, explicit verified/sign-in action, resend action, and durable success/failure feedback. The account-created/email-delivery-failure branch uses the same recovery surface, and content-free account creation now records only sent/failed verification delivery. Password, registration, verification, authentication, pricing, and entitlement policy remain unchanged. All 315 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33136496183`, Android run `33136496185`, and iOS run `33136496204` passed. Production health returned 5.9.37; the app and changed assets returned 200; the inspected release had no runtime error cluster, severe log, 5xx, or registration request. No account or synthetic funnel event was created. | Verified delivery; outcome pending |
| Optional profile activation entry | Commit `81b39be`; deployment `dpl_G7oecbc71CPp6913TWvDoacTxsSv`; production 5.9.38 removes the mandatory display-name commitment between verified, terms-accepted users and the first workspace. Terms remain required and server-saved; name setup is a dismissible, account-scoped launchpad prompt, and `OnboardingCompleted` remains server-authoritative. Settings no longer reports a rejected profile update as saved. All 320 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33137238298`, Android run `33137238297`, and iOS run `33137238319` passed. Production health returned 5.9.38; the app and changed assets returned 200; the inspected deployment had no runtime error cluster, severe log, 5xx, signup, profile, terms, account, or activation request. No synthetic account or event was created. | Verified delivery; outcome pending |
| Reliable first workspace choice | Commit `e8fb9f0`; deployment `dpl_HE8v2SbtqeuayEJajMYiTrLt3Q1p`; production 5.9.39 replaces the launchpad's fixed 120-millisecond Projects/Video readiness guess with the runtime completion event. A delayed-load browser reproduction recorded starter intent but opened nothing under the old path; the corrected path waits visibly, opens the queued workspace exactly once, restores the card, reports a real asset failure, and lets the latest choice win. All 324 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33137897554`, Android run `33137897556`, and iOS run `33137897614` passed. Production health returned 5.9.39; the live readiness/cache assets returned 200; the release had no runtime error cluster, non-informational log, or 5xx. No production click, account, or synthetic event was created. | Verified delivery; outcome pending |
| Truthful first-prompt handoff | Commit `3ab5acb`; deployment `dpl_CT2aQtDDAwNLAEc2MzDwoWkvCaeW`; production 5.9.40 corrects a browser-reproduced composer handoff where Research/Image erased an existing draft and programmatic text did not update the active composer state. Research, Image, and Code now prefix the draft once, emit the real input event, preserve focus/caret, and stop an exact bare scaffold before usage checks or chat mutation. File and starter-intent contracts remain unchanged. All 329 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33138434467`, Android run `33138434500`, and iOS run `33138434478` passed. Production health returned 5.9.40; live composer/cache assets returned 200; the release had no runtime error cluster, non-informational log, or 5xx. No production prompt, account, usage check, or synthetic event was created. | Verified delivery; outcome pending |
| Reliable authenticated entry | Commit `ee3862d`; deployment `dpl_7sBD8Y3e8oyW696ec7HpHBLNLMVU`; production 5.9.41 removes the secondary full-state sync from the authenticated-entry critical path. A credential-free browser fixture proved that a never-settling sync left a completed login on a permanently disabled `Signing in…` button and a restored session on a blank screen. Both corrected paths open the account-scoped shell immediately while the existing server-authoritative synchronizer continues in the background. Credentials, verification, session rotation, cookies, ownership, pricing, entitlements, analytics, Supabase schema, and RLS remain unchanged. All 332 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33139229180`, Android run `33139229175`, and iOS run `33139229205` passed. Production health returned 5.9.41; the live shell/controller/cache assets returned 200; the release had no runtime error cluster, warning/error/fatal log, or 5xx. The fixture made no production write; owner credential-entry recheck remains pending. | Verified delivery; human proof pending |
| Recoverable continuing-work sync | Commit `76455e5`; deployment `dpl_G77wN9y7d7T1ftgWch1kw8AU63zQ`; production 5.9.42 bounds sync requests through body parsing and preserves the account-scoped pending queue on timeout/network failure. A credential-free browser fixture proved the old latest-result Project action remained disabled forever; the corrected path stopped the stalled request, enabled retry, and retained exactly one queued save. Project ownership, merge/revision rules, auth, pricing, entitlements, analytics, Supabase, and payments remain unchanged. All 336 tests, lint, 42 JavaScript validations, production/native/store checks, CI run `33140100110`, Android run `33140100029`, and iOS run `33140100058` passed. Production health returned 5.9.42; the live versioned/network-first sync asset and cache revision returned 200; the release had no runtime error cluster or warning/error/fatal log. No production login, chat, Project, account, payment, or synthetic event was created. | Verified delivery; retention outcome pending |
| Fallback first-message preflight | Commit `6111540`; deployment `dpl_52eNo3CQUC3JFcooDeBsbpgx7Z4q`; production 5.9.43 bounded the early `app.js` usage preflight and preserved the draft on failure. A subsequent steady-state audit found that post-load `crump-5.0.js` replaced Send with an unbounded primary path, so the original fixture proved fallback behavior only. Its 340 tests and hosted gates remain valid for that scope; release 5.9.44 supersedes the incomplete runtime boundary. | Partial delivery; superseded |
| Recoverable first reply | Commit `4804fc4`; deployment `dpl_HgAo8qwFh1gzroqUE47SrDFqxTnf`; production 5.9.44 applies one bounded transport to both fallback and primary runtimes, covering usage, acknowledgement, reply, and response parsing. A real-primary-runtime fixture proved the old reply stalled forever and ignored a second Send; the corrected path aborted locally, reconciled the existing owner-scoped idempotent job, rendered its persisted answer, and accepted a second message. A separate acknowledgement stall exposed visible retry and completed safely. The authenticated no-store status route filters user plus message ID; schema/RLS, usage, credits, providers, pricing, entitlements, analytics, and payments remain unchanged. All 347 tests, lint, 43 JavaScript validations, production/native/store checks, CI run `33141840340`, Android run `33141840370`, and iOS run `33141840430` passed. Production health returned 5.9.44; live changed assets/cache returned 200; the one-hour scan had no runtime error cluster or warning/error/fatal log. No production login, message, generation, Project, account, payment, or synthetic event was created. | Verified delivery; activation outcome pending |
| Recoverable authentication requests | Commit `0012a30`; deployment `dpl_3QsniFHTrMSACqNWPf7DzNqMckJ2`; production 5.9.45 applies one bounded transport through response parsing to registration, verification-email resend, password recovery/reset, terms acceptance, profile save, session checks, login, logout, and native push-registration cleanup. A registration-stall fixture proved the old permanently disabled `Creating account…` state; the corrected path restores the action with truthful uncertain-outcome guidance. A login-response-stall fixture proved the web client can reconcile a session issued before the response connection stalls. Auth policy, cookies, schema/RLS, pricing, entitlements, analytics, and payments remain unchanged. All 352 tests, lint, 44 JavaScript validations, production/native/store checks, CI run `33142697258`, Android run `33142697156`, and iOS run `33142697157` passed. Production health returned 5.9.45; live assets/cache returned 200; the one-hour scan had no runtime error cluster or warning/error/fatal log. No production login, account, event, message, Project, or payment was created. | Verified delivery; human proof pending |
| Complete signup milestone delivery | Commit `6c3e546`; deployment `dpl_9Mn5E1AtiiNL1FKN345Ag6gF5LkL`; production 5.9.46 closes a deterministic measurement gap in which valid password-manager/autofill values could reach `SignupSubmitted` without emitting `SignupCredentialsReady`. Shared one-time helpers now guarantee the ordered `SignupStarted` → `SignupCredentialsReady` → `SignupSubmitted` sequence on valid typed and autofilled submissions. The payload remains content-free and excludes email/password values; registration, verification, auth, schema/RLS, pricing, entitlements, server analytics, and payments are unchanged. A real-controller loopback fixture proved the pre-fix omission and both corrected paths exactly once. All 353 tests, lint, 44 JavaScript validations, production/native/store checks, CI run `33143365291`, Android run `33143365303`, and iOS run `33143365301` passed. Production health returned 5.9.46; live controller/cache assets returned 200; the initial scan had no runtime error cluster or warning/error/fatal log. No production signup, account, event, login, message, Project, or payment was created. | Verified measurement; conversion outcome pending |
| Recoverable verification-link return | Commit `a3ae2de`; deployment `dpl_EBxtmgbDcy7y7yeEhijKBvNHMbU8`; production 5.9.47 turns an invalid, expired, already-used, or scanner-consumed verification-link result into an actionable recovery state. The signed-out screen focuses the email field, exposes the existing resend control, and truthfully offers sign-in when verification may already have completed; its generic resend result preserves account-state privacy. Token lifetime, single-use semantics, auth policy, schema/RLS, pricing, entitlements, analytics, and payments remain unchanged. A real-controller loopback fixture proved the old dead end and the corrected recovery path without a production account or token. All 354 tests, lint, 44 JavaScript validations, production/native/store checks, CI run `33143924537`, Android run `33143924544`, and iOS run `33143924530` passed. Production health returned 5.9.47; live app/controller/cache assets returned 200; the initial scan had no runtime error cluster or warning/error/fatal log. | Verified delivery; activation outcome pending |
| Durable password-reset handoff | Commit `7ab3b1b`; deployment `dpl_8srpxeQqjCoFEjF3tPYZRhYvrvnQ`; production 5.9.48 sends a successful password reset directly to sign-in with a persistent confirmation and focused email field instead of flashing a result for 1.8 seconds and leaving a blank form. The reset token is removed from the URL and deleted from form state. A real-controller loopback fixture proved a single request, durable result, clean URL, and keyboard-ready next step. All 355 tests, lint, 44 JavaScript validations, production/native/store checks, CI run `33153793086`, Android run `33153793090`, and iOS run `33153793073` passed. | Verified delivery; recovery outcome pending |
| Durable mobile sign-in and PWA wake-up | Commits `06c30a1` and `3b20cf4`; production 5.9.49 expands successful mobile web-session confirmation from roughly 275 milliseconds to a bounded 2.65-second window and checks for PWA updates on load, wake, page restore, and connectivity return. Idle signed-out pages adopt a new controller automatically; entered credentials and signed-in work receive a controlled reload prompt. A real-runtime fixture reproduced the three-check failure and proved one workspace start on the fourth check. Identity-free Ask Crump auth outcomes remain observable. All 359 tests, lint, 44 JavaScript validations, production/native/store checks, CI run `33155450505`, Android run `33155450518`, and iOS run `33155450469` passed. A later production-wide review found serverless host reconfiguration could restore dependency-level URL records; 5.9.54 supersedes that incomplete import-time suppression while preserving this sign-in/PWA repair. | Verified repair; owner credential recheck pending |
| Authenticated workspace startup boundary | Commit `ea74f83`; deployment `dpl_71UWy9RoEESp5WBGKVoT2XMvZAUE`; production 5.9.50 defers Projects/Video, Crump Code, Library, and credits hydration until the server-confirmed account reaches the workspace. A full-shell browser run changed signed-out startup from five expected 401s to one successful session check and zero protected calls, while the matched authenticated run loaded every protected surface without delay or script error. All 362 tests, lint, 44 JavaScript validations, production/native/store checks, CI run `33156887623`, Android run `33156887563`, and iOS run `33156887586` passed. The fresh production browser served `r84`, made one 200 session request, and produced no failed response, script error, or error/fatal deployment log. | Verified delivery; activation outcome pending |
| Single-owner startup and reconnect sync | Commit `f17b3f6`; deployment `dpl_EoWF3UipaBDMcCaqyct8dJssdMk5`; production 5.9.51 removes the starter conversation's delayed blind push and makes the synchronization layer the sole data-sync owner for browser reconnection while presence retains its status and announcement role. Restored-session and fresh-login browsers each produced one ordered pull/push/confirmation-pull sequence; a stalled pull produced no competing push; offline startup produced no sync traffic before exactly one reconnect sequence. All 364 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI run `33159045825`, Android run `33159045783`, and iOS run `33159045809` passed. Production served `r85` with one 200 signed-out session check, zero protected startup calls, no console error, no runtime error cluster, and no error/fatal deployment log. | Verified delivery; owner credential recheck pending |
| Recoverable private Project handoff | Commit `bde31da`; deployment `dpl_8mYEDxe4uVoEEUCy5qKt8UjMDBrx`; production 5.9.52 bounds the Project create/attach response behind `Keep in a Project`, restores the disabled action with truthful retry guidance, and confirms a completed save without waiting for the secondary list refresh. An uncertain create retry reuses the newest active owned Project already holding that conversation, including at the plan limit, and the successful button now exposes an accurate accessible action name. A credential-free browser proved the old indefinite disabled state, two corrected timeout/retry cycles, and the complete success response with zero browser errors. All 367 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI run `33162073713`, Android run `33162073773`, and iOS run `33162073775` passed. Production serves 5.9.52/r86 with the changed assets, no runtime error cluster, and no warning/error/fatal deployment log. | Verified delivery; retention outcome pending |
| Recoverable Project return reads | Commit `23e6f9e`; deployment `dpl_3VVnB261rupDFtaDQeENRrh3dc3K`; production 5.9.53 bounds the Project list, saved-conversation list, Project-note read, and their response-body parsing. Each failed surface exposes an accurately named Retry action without discarding the active Project or hiding another successful surface, and stale Project-note results cannot overwrite a newly selected Project. A credential-free real-runtime fixture proved all four stall modes, a reusable retry, and the successful return to the exact saved conversation with zero browser errors. All 368 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI run `33168768095`, Android run `33168768090`, and iOS run `33168768141` passed. Production serves 5.9.53/r87 with the changed runtime, no runtime error cluster, and no error/fatal deployment log. | Verified delivery; retention outcome pending |
| Private upstream observability boundary | Commit `44b0efa`; deployment `dpl_GSm6EFkPN6EpKCqrVV77WKTbQ8tt`; production 5.9.54 blocks every `httpx`/`httpcore` record at configured handlers and reapplies that boundary before each request, closing a serverless host-reset gap that left full Supabase filter URLs with session hashes and internal row IDs in runtime logs. Database failures retain categorical status/detail type without raw upstream detail. Tests proved host reconfiguration, direct transport handlers, retained Ask Crump auth outcomes, and excluded database sentinels. A non-writing fake-cookie production probe forced a real Supabase lookup: the sentinel hash and `HTTP Request:` were absent while the identity-free auth outcome remained. All 371 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI run `33172015491`, Android run `33172015490`, and iOS run `33172015531` passed. Production serves 5.9.54/r88 with no runtime error cluster or warning/error/fatal deployment log. | Verified privacy containment |
| Clear authentication entry handoffs | Commit `ed88c44`; deployment `dpl_B1jKEcq7mgoU2gacvvUicBBuUXfQ`; production 5.9.55 centralizes sign-in, registration, recovery, and reset transitions and moves focus to each view's first field instead of leaving it on a hidden link or the page body. Native validation blocked before the network now leaves a persistent announced message, and content-free events distinguish validation, submission, completion, and request failure. A real-controller fixture proved every transition, both direct-link entries, and empty-login validation with zero browser errors. The owner completed a real phone/PWA sign-out and sign-in and confirmed the update prompt. All 373 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI run `33179824223`, Android run `33179824154`, and iOS run `33179824243` passed. Production serves 5.9.55/r89; five database-backed session probes returned 200 and the exact deployment has no warning/error/fatal log. | Verified delivery and owner sign-in proof; conversion outcome pending |
| Qualified creation-intent continuation | Commit `5ceb57a`; deployment `dpl_ENikqcrY6BYhZHvzoDU5VGtgHnFc`; production 5.9.56 preserves only the allowlisted document, presentation, résumé, or video category through sign-in, registration/verification return, and an existing session, then opens the exact non-generating workspace promised by the public capability page. A real-controller browser exercised all four destinations, invalid-intent rejection, and a signed-out-to-authenticated résumé return; every path cleared once with zero browser errors. All 378 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI run `33185622078`, Android run `33185622086`, and iOS run `33185622138` passed. Production serves 5.9.56/r90; all four live phone-size pages carried intent plus acquisition with no overflow or console issue. Intermittent pre-existing background sync transport 503s preserved the local queue and were followed by 200; Supabase remained `ACTIVE_HEALTHY`. | Verified delivery; activation outcome pending |
| Résumé purpose through artifact delivery | Commit `de0440f`; deployment `dpl_6FnNfyGKHFKW4osPxEvLVwDajDDs`; production 5.9.57 preserves the exact allowlisted résumé purpose from the public handoff or in-app `RÉSUMÉ · CV` choice through send, sync, retry, server guidance, and DOCX/PDF packaging. The pre-correction fact-only brief resolved to a generic business document; corrected guidance and a real packaging test proved the ATS/fact-grounded résumé profile without requiring the user to repeat “résumé.” Arbitrary purpose values are discarded. All 382 tests, lint/compile, 44 JavaScript validations, production/native/store checks, CI run `33189736839`, Android run `33189736730`, and iOS run `33189736888` passed. Production serves 5.9.57/r91; the exact deployment returned only 200 in observed requests and had no release-window runtime error group. | Verified delivery; artifact outcome pending |
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

The 5.9.42 continuing-work sync release then corrected the same unbounded-network class at the
shared persistence boundary. A stalled push could leave message delivery or `Keep in a Project`
waiting forever even though the pending work was already safe to queue. The corrected manager
bounds fetch plus body parsing, retains the account-scoped queue on timeout/network failure, and
returns a retryable result. A credential-free browser fixture proved the old disabled state and the
corrected enabled retry with exactly one queued save. Production health and the live versioned sync
asset/cache returned 200; the exact deployment had no runtime error cluster or warning/error/fatal
log. CI plus both hosted unsigned native compiles passed. No production login, chat, Project,
account, payment, or synthetic event was created, so retention impact remains unproven.

The 5.9.43 first-message fixture correctly proved the early `app.js` fallback, but a subsequent
steady-state audit found the dynamically loaded `crump-5.0.js` primary runtime replaced Send with an
unbounded path. Its evidence is retained with corrected scope rather than overstated as full delivery.

The 5.9.44 first-reply recovery release closes that gap with one shared transport across both
runtimes. Usage preflight, acknowledgement, reply, and body parsing are bounded. After a lost reply
connection, the client polls an authenticated, owner-filtered, non-cacheable job route and reuses the
persisted server answer. A primary-runtime loopback fixture proved reply recovery plus a reusable
second Send, and a separate acknowledgement stall proved visible tap-to-retry completion. Production
health and live versioned/network-first assets returned 200; CI and both hosted unsigned native
compiles passed; the one-hour production scan had no warning/error/fatal log. No production login,
message, generation, Project, account, payment, or synthetic event was created, so activation impact
remains unproven.

The 5.9.45 authentication request recovery release extends that bounded-response standard to account
entry and recovery. Registration restores its action with truthful guidance when the outcome cannot
be confirmed, and web login reconciles a session that was already issued before the response stalled.
Credential-free loopback fixtures proved both paths. Production health and versioned/network-first
assets returned 200; CI and both hosted unsigned native compiles passed; the one-hour production scan
had no runtime error cluster or warning/error/fatal log. No production login, account, event, message,
Project, or payment was created, so fresh owner credential entry remains the final human proof.

The 5.9.46 signup milestone release corrects the next measurement boundary without changing the
signup product. A valid autofill-only submission previously skipped `SignupCredentialsReady` while
still emitting `SignupSubmitted`; the real-controller loopback fixture now proves the full ordered
sequence once for both untouched autofill and normal typing. Production health, the live versioned
controller, and service-worker cache revision returned 200; CI and both hosted unsigned native
compiles passed; the initial production scan had no runtime error cluster or warning/error/fatal log.
No production signup, account, event, login, message, Project, or payment was created, so conversion
impact remains unproven.

The 5.9.47 verification-link recovery release then corrected a second-click/security-scanner dead
end without weakening the single-use server token policy. The failed return now focuses the email
field, exposes the existing resend control, and offers sign-in when verification may already have
completed. A real-controller loopback fixture proved the pre-fix dead end and generic recovery result.
Production health and the live app/controller/service-worker assets returned 200; CI and both hosted
unsigned native compiles passed; the initial one-hour scan had no runtime error cluster or
warning/error/fatal log. No production signup, account, verification, event, login, message, Project,
or payment was created, so activation impact remains unproven.

Production 5.9.48 made the successful password-reset return durable, and 5.9.49 then closed the
reproduced slow-mobile confirmation plus sleeping-PWA update gap. A real-runtime fixture proved the
old three-check session failure and the corrected fourth-check workspace entry. The release also
replaced identifier-bearing upstream request logs with identity-free categorical outcomes. Hosted
CI and both native verifiers passed; fresh owner credential proof remains pending after the required
one-time restart of a PWA page that was already asleep before the new listener existed.

Production 5.9.50 then removed five expected protected 401s from every signed-out startup. The full
shell made only one successful session check while signed out, then hydrated every protected surface
after a mocked server-confirmed account. The fresh production browser repeated the one-request,
zero-failure result with `r84`; its deployment had no error/fatal log. This verifies a cleaner,
cheaper, and more observable activation boundary, not improved conversion.

Production 5.9.51 then removed two redundant synchronization owners found in the authenticated and
offline browser traces. Restored-session and fresh-login entry now run one ordered convergence
sequence; a stalled initial pull cannot be bypassed by a delayed starter push; offline startup makes
no sync request until one reconnect sequence. The production release served `r85` with one successful
signed-out session request, no protected call or browser error, and no runtime error cluster or
error/fatal deployment log. Owner credential-entry proof remains the final real-device auth gate.

Production 5.9.52 then closed the remaining network-stall boundary in the primary durable-value
action. The Project create/attach response is bounded, a completed save no longer waits for a
secondary list refresh, and an uncertain retry returns the existing owner-scoped Project instead
of creating a duplicate. The real browser fixture recovered twice from stalled responses and
completed the success path with an accurate accessible action and zero browser errors. Production
serves `r86`; hosted CI and both unsigned native source builds passed, and the inspected deployment
has no severe log or runtime error cluster. Legitimate Project conversion and later return remain
unobserved.

Production 5.9.53 then closed the corresponding return-to-work read boundary. Project discovery,
saved conversations, private notes, and response-body parsing are bounded independently; each
surface exposes its own reusable Retry action, and stale note results cannot cross a Project switch.
The real browser fixture proved Project-list, conversation, note, and body-stream stalls plus the
complete successful continuation with zero browser errors. Production serves `r87`; hosted CI and
both unsigned native source builds passed, and the exact deployment has no error/fatal log or
runtime error cluster. Legitimate Project return and retention lift remain unobserved.

Production 5.9.54 then corrected a privacy defect found by widening the runtime review beyond
application-owned auth messages. Serverless host logging could restore `httpx` INFO records after
app import, exposing full Supabase filter URLs with opaque session hashes and internal row IDs. The
new handler filter is reapplied before every request, raw database details are no longer logged, and
Ask Crump's categorical outcomes remain visible. A fake-cookie production probe forced a real
Supabase lookup: neither the fake hash nor `HTTP Request:` appeared, while the identity-free auth
outcome did. Production serves `r88`; hosted CI and both unsigned native builds passed, and the
exact deployment has no warning/error/fatal log or runtime error cluster.

Production 5.9.55 then separated an overnight transient database 503 from the current PWA login
path. One older-deployment login and nearby background jobs recorded the same upstream connection
failure; the current release returned successful database-backed session checks, and the owner
completed a real phone/PWA sign-out and sign-in. A separate real-controller audit found every auth
view transition left focus on a hidden link or the page body. Centralized transitions now focus the
first actionable field, and pre-network browser validation leaves a persistent announced message
plus content-free outcome telemetry. Production serves `r89`; hosted CI and both unsigned native
builds passed, five post-release database-backed probes returned 200, and the exact deployment has
no warning/error/fatal log.

Production 5.9.56 then closed the deterministic gap between high-intent organic entry and the
first creation workspace. Capability-page CTAs previously retained acquisition/location/plan but
discarded whether the visitor chose a document, presentation, résumé, or video. The allowlisted
category now survives authentication for 24 hours, opens the exact existing non-generating
surface, records one content-free continuation event, and clears only after acknowledgment. All
four immediate paths plus a signed-out-to-authenticated return passed in the real controller with
zero browser errors, and all four production pages passed phone-size CTA/overflow/console checks.
Production serves `r90`; hosted CI and both unsigned native builds passed. The exact deployment
also exposed intermittent background sync transport 503s already present before the release. The
account-scoped client queue remained intact, the next observed sync returned 200, and Supabase
reported `ACTIVE_HEALTHY` with matching database requests returning 200. The transport pattern
remains a reliability signal; no creation-intent conversion lift is claimed yet.

Production 5.9.57 then closed the next deterministic résumé-delivery gap. The public résumé
handoff and in-app `RÉSUMÉ · CV` outcome selected DOCX but discarded the résumé purpose before the
request. A fact-only experience/skills brief therefore resolved to a generic business document
unless the user repeated “résumé.” The exact allowlisted purpose now survives send, sync, retry,
model guidance, and DOCX/PDF packaging; arbitrary values are dropped. A real package verified the
résumé profile and layout, and the controller fixture verified `{format: docx, purpose: resume}`
with zero browser errors. Production serves `r91`; hosted CI and both unsigned native builds
passed, the exact deployment's observed requests returned 200, and no release-window runtime error
group appeared. No artifact conversion or résumé quality lift is claimed yet.

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
release verification, production health, desktop/mobile UI checks, named resume, bounded
queue-preserving persistence, and recoverable primary first-message/reply delivery passed through 5.9.44. The
remaining outcome gate is at least one legitimate external conversation-to-Project transition and
a later return. Do not infer a retention rate from a single user.

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
entered or submitted in Search Console. A second read-only review on 2026-08-28 found the Page
indexing report still processing and the Submitted sitemaps table still at zero rows. Direct live
checks confirmed HTTP 200 delivery for `robots.txt`, `sitemap.xml`, the homepage, and every use-case
page, with no response-level robots block. The public pages still expose unique canonicals,
metadata, structured data, and crawlable internal links. No additional code defect was found; the
remaining acquisition gate is the owner-confirmed Search Console submission.

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
Analytics read on 2026-08-28 showed 89 visitors, 269 page views, and 62% bounce over the trailing
seven days; 61 visitors reached `/app`, 21 visitors produced 34 `SignupIntent` events, and one
visitor produced one client `AccountCreated` event. Those anonymous aggregates span the
pre-instrumentation boundary and may include internal or automated visits, so they are not a
conversion rate. The last 24 hours showed 14 production visitors, 93 page views, three
`MarketingCTA` visitors with eight events, two `SignupIntent` visitors with 14 events, and two
`SignupStarted` visitors, with no
`SignupCredentialsReady`, `SignupSubmitted`, or `AccountCreated` event. Before 5.9.29,
`MarketingCTA` mixed account-creation and sign-in clicks; the release now records existing-account
traffic separately as `MarketingSignin`. The service-role comparable external funnel still
returned zero accounts at every stage in the latest refresh, and the aggregate artifact journey
returned no rows. The deterministic audit found unbounded account-entry and recovery requests;
production 5.9.45 now bounds those requests through parsing and safely reconciles a web session
issued before a login response stalls. No comparable external account has yet been observed after
the repair. A follow-on autofill fixture then proved that a valid submit could omit
`SignupCredentialsReady`; production 5.9.46 now guarantees the complete one-time ordered milestone
sequence without changing signup behavior. The release evidence is recorded in
`docs/SIGNUP_MILESTONE_DELIVERY_RELEASE_2026-08-28.md`. A failed or reused verification return could
still strand a legitimate user after an email scanner or second click; production 5.9.47 now exposes
the existing privacy-preserving resend path and sign-in guidance without changing token or auth
policy. Its evidence is recorded in `docs/VERIFICATION_LINK_RECOVERY_RELEASE_2026-08-28.md`.
The next 24-hour read showed 19 visitors, 109 page views, 42% bounce, and two direct desktop-Mac
`SignupStarted` visitors with no credential-ready or submitted event. That sample remains too small
and automation-prone for a signup decision. The deterministic capability-page audit instead found
that qualified creation intent disappeared at `/app`; production 5.9.56 now carries only the
allowlisted document/presentation/résumé/video category through auth, opens the exact existing
non-generating surface, and emits `CreationIntentContinued`. The release evidence is recorded in
`docs/CREATION_INTENT_HANDOFF_RELEASE_2026-08-28.md`.
The subsequent creation audit found that a selected résumé lost its purpose after choosing DOCX;
production 5.9.57 now preserves only the allowlisted résumé purpose through sync/retry, guidance,
and final packaging. The release evidence is recorded in
`docs/RESUME_PURPOSE_DELIVERY_RELEASE_2026-08-28.md`.

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

**Evidence:** production 5.9.55 is healthy; the Android release source regenerates as build 50955
with API 36, the permanent package ID, generated assets, cleartext/backup protections, and a passing
native source verifier. Structured en-US metadata passes current field limits. A reviewed Node 22
lockfile now supports clean `npm ci`, a zero-vulnerability npm audit, and deterministic Android
preparation from an isolated worktree. GitHub run `33179824243` generated the 5.9.55 iOS project and compiled its unsigned Release
configuration on hosted macOS with no signing or upload credentials. GitHub run `33179824154`
generated the 5.9.55/build 50955 Android project under Java 21, passed the native and signing-control
verifiers, compiled `bundleRelease`, and confirmed a non-empty unsigned
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

Observe legitimate capability CTA → auth → `CreationIntentContinued` → starter intent → artifact
delivery, with the résumé journey retaining the selected purpose through first download. Reconcile
the intermittent database-transport 503 pattern against queued recovery without changing the
shared database boundary from a small sample. Submit the live canonical sitemap after owner
confirmation, allow the
social-preview experiment to reach its minimum
observation window, then obtain the first consented post-instrumentation account, durable-value,
return, referral, and artifact-journey observations. Observe the first real checkout and reconcile
Stripe with Ask Crump entitlement/credit state. Do not rewrite the signup flow from anonymous
seven-day aggregates that cross the measurement boundary; diagnose the next real post-boundary
attempt instead. Keep both new provider foundations off. Do not enable Crump Code until the real
sandbox/OIDC test, review UI, monitoring, and benchmark gates pass. Do not enable Crump Voice
until its disclosure, key, voice rights, and playback tests are approved.
