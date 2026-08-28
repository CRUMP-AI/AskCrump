# Changelog

## 5.9.55 — 2026-08-28

### Clear, accessible authentication handoffs

- Sign-in, registration, password recovery, and password-reset views now move focus to their first
  actionable field after every direct link and in-page transition. Keyboard and assistive-input users
  no longer remain on a control that was just hidden.
- Browser validation that stops a sign-in before the network request now renders a persistent,
  announced message for the exact missing or malformed field instead of relying on a transient native
  bubble. Safe funnel events distinguish validation, submission, completion, and request failure
  without recording credentials or account identifiers.
- Advanced the application to 5.9.55, native build 50955, and service-worker cache revision 89.

## 5.9.54 — 2026-08-28

### Private upstream observability boundary

- Full dependency-level HTTP request records are now dropped before configured handlers can emit
  them. Supabase filter URLs containing opaque session hashes and internal account, Project, chat,
  or file IDs no longer belong in application runtime logs.
- The boundary is reasserted at the start of every request because serverless/ASGI hosts can apply
  their logging configuration after importing the app. It covers root handlers, transport-specific
  handlers, and current `httpx`/`httpcore` child loggers.
- Database failures now retain categorical status and detail type while excluding raw upstream
  response details from application logs.
- Advanced the application to 5.9.54, native build 50954, and service-worker cache revision 88.

## 5.9.53 — 2026-08-28

### Recoverable Project return-to-work reads

- The Projects list, saved-conversation list, and private Project-note reads now have a bounded
  15-second response window, including response-body parsing. None of the three surfaces can remain
  on an indefinite loading state after a dropped or stalled connection.
- Each failed Project read now renders a focused retry action in its own surface. A Project-note
  failure does not block a successfully loaded saved conversation, and a saved-conversation failure
  does not discard the active Project.
- The shared optional request boundary now propagates an abort raised while parsing a response body
  instead of treating the aborted body as an empty successful response.

### Verification and release

- A credential-free real-runtime browser fixture reproduced the prior saved-conversation loading
  deadlock. The corrected Project-list, saved-conversation, and Project-note reads each aborted at
  the bounded test interval, rendered their own retry action, and remained reusable with zero
  browser errors. The successful fixture restored the intended conversation and closed the studio.
- Advanced the application to 5.9.53, native build 50953, and service-worker cache revision 87 so
  web, installed PWA, and generated native clients receive the complete Project read boundary.

## 5.9.52 — 2026-08-28

### Recoverable private Project handoff

- The primary `Keep in a Project` action now bounds its Project create or attach request through
  response-body parsing. A stalled connection releases the disabled action with truthful retry
  guidance instead of leaving the durable-work path frozen forever.
- A successful save no longer waits for a secondary Project-list refresh before confirming the
  result. The list still refreshes in the background while the saved Project becomes immediately
  available to the conversation.
- Retrying after an uncertain response reuses the newest active owned Project already containing
  that conversation, including when the user has since reached the plan's Project limit. The
  ownership check, private mapping, and content-free durable-value event remain server-authoritative.

### Verification and release

- A credential-free browser fixture reproduced the prior indefinite disabled state with the real
  result and Project code. The corrected path aborted the stalled response, restored the action,
  and accepted a second retry; service and route tests prove the retry does not create a duplicate.
- Advanced the application to 5.9.52, native build 50952, and service-worker cache revision 86 so
  web, installed PWA, and generated native clients receive the recovery boundary.

## 5.9.51 — 2026-08-28

### Single-owner startup and reconnect synchronization

- Opening a clean starter conversation no longer schedules an independent blind push while the
  authenticated pull/merge/push sequence is still establishing server-authoritative state.
- Reconnection synchronization now has one owner. The presence layer continues to announce and
  render connection recovery, while the synchronization layer alone performs the data transfer.
- Normal conversation creation remains immediately durable, and offline work still synchronizes
  through the existing account-scoped queue when connectivity returns.

### Verification and release

- Real-browser restored-session and fresh-login checks each produced one ordered synchronization
  sequence: pull, push, confirmation pull. A stalled initial pull produced no competing push, and
  offline startup produced no sync traffic until reconnection, followed by exactly one sequence.
- Advanced the application to 5.9.51, native build 50951, and service-worker cache revision 85 so
  web, installed PWA, and generated native clients receive the corrected synchronization ownership.

## 5.9.50 — 2026-08-28

### Authenticated workspace startup boundary

- Projects/Video, Crump Code, Library, and the credits badge now construct their interface without
  requesting protected account data until the server-confirmed user reaches the workspace.
- The auth controller announces one explicit `crump:authenticated-ready` boundary after account
  storage and authenticated application initialization. Each protected surface hydrates from that
  boundary and also handles a user who was already confirmed before its script finished loading.
- A signed-out visit now makes only the intended session check instead of five additional requests
  that must fail with 401. Successful sign-in still hydrates every protected surface immediately.

### Verification and release

- A full local application-shell browser run proved the signed-out state made one session request,
  zero protected requests, and produced zero script errors. The matched authenticated run opened the
  workspace and loaded sync, presence, analytics, Projects, feature status, Library, Code
  availability, and credits after confirmation.
- Added source contracts for the authentication event ordering and all four protected startup gates.
- Advanced the application to 5.9.50, native build 50950, and service-worker cache revision 84 so
  web, installed PWA, and generated native clients receive the authenticated startup boundary.

## 5.9.49 — 2026-08-28

### Durable mobile sign-in and PWA wake-up

- Web sign-in now gives mobile browsers a bounded 2.65-second confirmation window for a newly
  issued HttpOnly session instead of declaring failure after roughly 275 milliseconds. The server
  still must confirm the session; authentication policy and credential handling are unchanged.
- An installed Ask Crump app now checks for a service-worker update when it loads, returns from the
  background, regains connectivity, or is restored from the page cache. A safe signed-out screen
  adopts the corrected runtime automatically; signed-in work or entered authentication fields get
  a restrained “Reload now” notice rather than a destructive refresh.
- Authentication logs now record only categorical outcomes and an allowlisted web/native client
  class. They never record an email address, password, token, user ID, or device name.
- Routine upstream HTTP request logs are suppressed so Supabase filter URLs cannot place opaque
  session hashes or internal row IDs into the production log stream.

### Verification and release

- Added a credential-free loopback fixture using the real authentication transport, device auth,
  and controller. It reproduces the former three-check failure, then proves one login opens the
  workspace exactly once when the same session becomes visible on the fourth check.
- Advanced the application to 5.9.49, native build 50949, and service-worker cache revision 83 so
  web, installed PWA, and generated native clients receive the hardened sign-in runtime.

## 5.9.48 — 2026-08-28

### Durable password-reset handoff

- A successful password reset no longer flashes its confirmation inside a form that disappears
  after 1.8 seconds. The user now reaches sign-in immediately with a persistent “Password updated”
  status and keyboard focus on the email field.
- The reset token is removed from the address bar as soon as the client captures it and is deleted
  from the form state after success or an explicit return to sign-in.
- Password rules, token validation and lifetime, session revocation, authentication policy, rate
  limits, schema/RLS, pricing, entitlements, analytics, and payments remain unchanged.

### Verification and release

- Added a loopback fixture using the real authentication resilience and controller assets. It proves
  the prior blank sign-in handoff and the corrected persistent status, focused next step, single
  local reset request, and cleaned URL without a production token, account, or credential.
- Advanced the application to 5.9.48, native build 50948, and service-worker cache revision 82 so
  web, PWA, and generated native clients receive the corrected recovery handoff.

## 5.9.47 — 2026-08-28

### Recoverable verification-link return

- A failed or already-used verification link no longer leaves a new user with only an
  “invalid or expired” dead end. The sign-in screen now explains every truthful possibility,
  focuses the email field, and exposes the existing resend-verification action immediately.
- The resend result remains generic to prevent account enumeration, and a user whose account was
  already verified can sign in normally.
- Verification-token lifetime, single-use behavior, server authentication, account state, password
  policy, rate limits, cookies, schema/RLS, pricing, entitlements, and payments remain unchanged.

### Verification and release

- Added a loopback fixture using the real authentication controller. It proves the released dead-end
  state, the corrected recovery instructions, keyboard-ready email focus, and successful local resend
  feedback without creating an account or contacting production.
- Advanced the application to 5.9.47, native build 50947, and service-worker cache revision 81 so
  web, PWA, and generated native clients receive the verified-return recovery surface.

## 5.9.46 — 2026-08-28

### Complete signup milestone delivery

- A valid registration submission now records `SignupCredentialsReady` before
  `SignupSubmitted` even when a password manager restored both fields without normal focus or
  input events.
- The shared milestone helpers preserve one-time, ordered delivery for typed and autofilled paths;
  they do not collect an email address, password, or any other credential value.
- Registration behavior, validation, account creation, verification, auth policy, pricing,
  entitlements, server-side analytics, Supabase schema/RLS, and payments remain unchanged.

### Verification and release

- Added a credential-free loopback fixture using the real auth controller. Before the correction,
  its valid autofill submission skipped `SignupCredentialsReady`; after the correction, both
  autofilled and typed paths recorded the ordered four-milestone sequence exactly once.
- Advanced the application to 5.9.46, native build 50946, and service-worker cache revision 80 so
  web, PWA, and generated native clients receive the corrected measurement contract.

## 5.9.45 — 2026-08-28

### Recoverable authentication requests

- Added one shared, bounded authentication transport for registration, verification email,
  password recovery, terms/profile saves, sign-in, session confirmation, and sign-out. Each
  boundary covers response-body parsing as well as the initial connection.
- A stalled registration submission now restores the primary action and explains that the account
  may already exist, so the user can check their inbox before retrying instead of remaining on
  `Creating account…` forever.
- A web sign-in whose HttpOnly session cookie was issued before its response stalled now reconciles
  the bounded session endpoint before reporting failure or rotating another session.
- Authentication policy, credentials, cookies, session lifetime, rate limits, registration data,
  verification rules, Supabase schema/RLS, pricing, entitlements, and analytics semantics remain
  unchanged.

### Verification and release

- Advanced the application to 5.9.45, native build 50945, and service-worker cache revision 79.
  The shared auth transport and both auth consumers are release-versioned and network-first so web
  and installed clients receive the same recovery contract.

## 5.9.44 — 2026-08-28

### Recoverable first reply

- Bounded message acknowledgement and the first AI reply request so a lost or never-settling
  connection can no longer leave the primary workspace permanently ignoring Send.
- Added an authenticated, owner-scoped, non-cacheable reply-status route. The client reconciles the
  existing idempotent server job and reuses its persisted answer instead of blindly generating or
  charging again.
- Preserved the server assistant-message identity, artifact and creation handoffs, visible retry
  state, and safe stale-job takeover contract across the primary and fallback runtimes.
- Kept usage limits, credit prices, provider routing, authentication, Supabase schema/RLS, pricing,
  entitlements, analytics semantics, and payment behavior unchanged.

### Verification and release

- Advanced the application to 5.9.44, native build 50944, and service-worker cache revision 78.
  The shared chat transport and primary workspace runtime are release-versioned and network-first
  so web and installed clients receive the recovery contract together.

## 5.9.43 — 2026-08-28

### Recoverable first-message preflight

- Bounded the message-availability preflight through response-body parsing so a stalled request can
  no longer make repeated Send actions silently stop responding before the first message exists.
- Preserved and refocused the user's draft when the preflight times out or the connection fails,
  with a visible explanation and an immediately retryable Send path.
- Kept usage limits, credit accounting, authentication, chat delivery, provider routing, and
  activation measurement unchanged.

### Verification and release

- Advanced the application to 5.9.43, native build 50943, and service-worker cache revision 77 so
  web and installed clients receive the first-message recovery boundary together.

## 5.9.42 — 2026-08-27

### Recoverable continuing-work sync

- Bounded cross-device sync requests through response-body parsing so a stalled network request can
  no longer leave message delivery or `Keep in a Project` waiting forever.
- Preserved the account-scoped pending queue on timeout or network failure and returned an explicit
  retryable result; a later automatic or user-initiated sync can safely replay the same work.
- Kept Project ownership, chat merge/revision rules, authentication, pricing, entitlements, and
  analytics semantics unchanged.

### Verification and release

- Advanced the application to 5.9.42, native build 50942, and service-worker cache revision 76.
  The changed sync manager is now release-versioned and network-first so web and installed clients
  receive the recovery boundary together.

## 5.9.41 — 2026-08-27

### Reliable authenticated entry

- Removed the full cross-device sync from the authentication critical path. A successful login or
  restored session now opens the account-scoped workspace immediately instead of waiting forever
  when a secondary sync request stalls.
- Kept server-authoritative synchronization in the existing authenticated background lifecycle,
  which renders the account-scoped cache first and then merges current server state.
- Kept credentials, password verification, email verification, opaque session rotation, cookies,
  account ownership, pricing, entitlement, and analytics semantics unchanged.

### Verification and release

- Advanced the application to 5.9.41, native build 50941, and service-worker cache revision 75 so
  web and installed clients receive the authenticated-entry correction together.

## 5.9.40 — 2026-08-27

### Truthful first prompt

- Preserved an existing composer draft when the user chooses Research, Image, or Code. The selected
  mode now prefixes the draft once instead of replacing the user's work.
- Dispatched the real composer input event after programmatic mode changes so send-state styling,
  body state, and textarea sizing agree with the visible prompt.
- Stopped bare mode scaffolds before usage checks or chat mutation and returned focused, specific
  guidance instead of allowing an incomplete request to consume product resources.
- Kept file selection, starter-intent measurement, authentication, pricing, entitlement, and
  backend routing unchanged.

### Verification and release

- Advanced the application to 5.9.40, native build 50940, and service-worker cache revision 74 so
  web and installed clients receive the composer handoff correction together.

## 5.9.39 — 2026-08-27

### Reliable first action

- Replaced the launchpad's fixed 120-millisecond Projects/Video readiness guess with the existing
  runtime-ready contract. A choice made while the product workspace is still loading is now held
  and opened as soon as that runtime is actually ready, including on slower connections.
- Added restrained visible and assistive progress to the selected launch card while it waits, plus
  an explicit retry message if the runtime finishes without the requested workspace.
- Kept the content-free, idempotent starter-intent event at the user's click. Authentication,
  verification, terms, pricing, entitlement, and product-workspace behavior are unchanged.

### Verification and release

- Advanced the application to 5.9.39, native build 50939, and service-worker cache revision 73 so
  web and installed clients receive the readiness correction together.

## 5.9.38 — 2026-08-27

### Faster first value

- Removed the mandatory name modal between terms acceptance and the first workspace visit. The
  legally required, server-saved terms gate remains unchanged; the task-oriented launchpad now
  opens immediately afterward even when the account has no display name.
- Reintroduced name setup as a compact, optional launchpad prompt with Add name and Not now
  controls. Dismissal is account-scoped on the device, and the existing Profile settings remain
  available across signed-in devices.
- Made the optional name dialog dismissible by button or Escape, keyboard-focused when opened, and
  explicit about save errors. The save action now exposes a busy state and cannot double-submit.
- Corrected Profile settings so a rejected server name update is no longer reported as saved.
  Successful profile updates close the optional prompt immediately.
- Kept registration, verification, terms, authentication, pricing, and entitlement behavior
  unchanged. `OnboardingCompleted` remains server-authoritative and fires only when the account
  actually adds its first name.

### Verification and release

- Advanced the application to 5.9.38, native build 50938, and service-worker cache revision 72 so
  installed clients receive the optional activation path and its styles together.

## 5.9.37 — 2026-08-27

### Durable registration handoff

- Replaced the 1.8-second post-registration message with a persistent, keyboard-focused “Check
  your inbox” state that confirms the destination email and explains the exact next step.
- Added explicit “I’ve verified — sign in” and “Resend verification email” actions. The sign-in
  email is prefilled, and resend success, delivery failure, and network failure remain visible.
- Reused the same recovery state when an account is created but initial verification delivery
  fails, instead of dropping the user onto a generic sign-in form.
- Kept password, registration, verification, authentication, pricing, and entitlement policy
  unchanged. The existing content-free `AccountCreated` event now records a privacy-safe
  verification-delivery status on both account-created branches.

### Verification and release

- Advanced the application to 5.9.37, native build 50937, and service-worker cache revision 71 so
  installed clients receive the revised authentication shell and controller together.

## 5.9.36 — 2026-08-27

### Clearer account creation

- Added a live, visible password checklist for the three unchanged account requirements: ten or
  more characters, one letter, and one number. Each rule confirms independently as it is met.
- Added a polite screen-reader status that announces only when a requirement state changes, plus
  an invalid-field state after the password field has been reviewed or a submission is attempted.
- Kept account creation, password policy, verification, pricing, analytics, and authentication
  semantics unchanged. The improvement is pre-submit guidance, not a looser security rule.

### Verification and release

- Advanced the application to 5.9.36, native build 50936, and service-worker cache revision 70.
  The authentication controller is now release-versioned and network-first so installed clients do
  not serve an older signup interaction during a new release.

## 5.9.35 — 2026-08-27

### Crump Code review workspace

- Added a restrained, Project-attached private workspace for preparing public-repository tasks,
  reviewing the selected repository, revision, mode, objective, time boundary, and cost boundary,
  and following the task through result, verification, activity history, and patch download.
- Kept the Create entry invisible unless the existing server-controlled Crump Code feature is both
  configured and entitled. The public production feature flag remains off; this release does not
  advertise coding-agent availability or make a parity claim.
- Separated task preparation from execution. Preparing a task performs no model run or credit
  charge; execution stays disabled until the user checks an explicit review confirmation, and the
  server independently rejects an unconfirmed run.
- Added human-visible pending-approval decisions and cancellation. A concurrent cancellation is
  now checked before every next model or tool step so the bounded sandbox shuts down without
  publishing or pushing changes.
- Preserved the existing isolation contract: public GitHub roots only, ephemeral microVM, no
  environment variables, deny-all network after checkout, bounded tools and duration, patch-only
  output, and no source-repository writeback.

### Verification and release

- Exercised both disabled and mocked-enabled states in a local browser without a production
  account, event, sandbox, provider call, or credit charge. The disabled entry stayed hidden; the
  enabled review surface rendered its safety boundaries, result, verification, history, and patch;
  the run control stayed disabled until review confirmation.
- Advanced the application to 5.9.35, native build 50935, and service-worker cache revision 69 so
  web, PWA, and generated native clients receive the guarded workspace layer together.

## 5.9.23 — 2026-08-27

### Truthful organic discovery

- Added dedicated, crawlable AI presentation-maker and AI document-generator pages for people
  already searching for editable PowerPoint, Word, and PDF workflows.
- Gave both pages unique titles, descriptions, canonical URLs, social metadata, valid structured
  data, useful workflow guidance, and explicit human-review requirements without parity, perfection,
  or publication-readiness claims.
- Linked the new pages from the homepage and from each other, and added their clean canonical URLs
  to the sitemap with accurate change dates.
- Reduced known search-engine referrers to the privacy-safe acquisition label `organic`; no search
  query, referrer URL, page content, or user identifier is stored. On-site CTA labels remain
  placement data and cannot overwrite first-touch acquisition.

### Measurement and release

- Refreshed the protected production growth and artifact-journey reports before choosing the work.
  Both returned the valid zero-traffic baseline for the comparable external cohort, making
  acquisition—not a speculative activation redesign—the current evidence-backed bottleneck.
- Advanced the application to 5.9.23 and the service-worker cache to revision 57 so installed and
  web clients receive the changed marketing attribution contract together.

## 5.9.22 — 2026-08-27

### One-click continuing work

- Put `Keep in a Project` directly on the latest successful result instead of hiding it behind a
  separate positive-feedback click, reducing the durable-work path from two commitments to one.
- Kept outcome feedback optional and preserved the privacy-safe referral prompt after positive
  feedback without making either action a prerequisite for saving the conversation.
- Reused the existing synchronized, ownership-checked, idempotent conversation-to-Project route and
  its content-free durable-value milestone; no prompts, response content, filenames, or titles were
  added to product analytics.

### Release

- Advanced the application to 5.9.22 and the service-worker cache to revision 56 so installed and
  web clients receive the lower-friction Project action together.

### Store readiness

- Added a structured, machine-validated en-US listing packet, a signed-build screenshot plan, and a
  reviewer-access template that keeps credentials out of source control.
- Strengthened native verification around the permanent bundle/package ID and configured generated
  Android releases to disable cleartext traffic and local backup of account-linked session data.
- Reconciled the current Apple and Google requirements into an evidence-backed readiness audit
  without enrolling, signing, uploading, changing pricing, or submitting either app.
- Committed the reviewed npm lockfile produced with Node 22.22.0/npm 11.6.0; a clean `npm ci`, full
  resolved dependency tree, zero-vulnerability npm audit, and deterministic Android preparation all
  pass from an isolated worktree.
- Switched JavaScript CI to the reproducible `npm ci` path and added production-bundle plus store
  metadata validation on every main-branch change.
- Moved the official checkout, Node, and Python setup actions to their Node 24-backed releases so
  the verified pipeline no longer depends on deprecated action runtimes.
- Added a no-secret, no-signing, no-upload macOS workflow that deterministically generates the iOS
  source and compiles its Release configuration before Apple credentials enter the process.
- Used the first hosted-macOS run to detect and correct an Xcode project/workspace assumption; the
  corrected run generated Ask Crump and compiled its unsigned Release configuration under Xcode
  16.4 without certificates, provisioning profiles, store credentials, upload, or submission.
- Added the matching no-secret Android workflow to select Java 21, generate the native candidate,
  and prove Gradle can produce a Release App Bundle before a Play keystore enters the process. Its
  first run exposed Gradle-cache initialization before generated source; the corrected run passed
  native and signing-control checks, compiled `bundleRelease`, and verified a non-empty `.aab`.

## 5.9.21 — 2026-08-27

### Trustworthy growth measurement

- Established the first observed production product-event timestamp as the lower bound for
  comparable funnel cohorts, so historical accounts are no longer shown as zero-event activation
  failures merely because they used Ask Crump before the complete instrumentation sequence was
  observable.
- Preserved the service-role-only, aggregate-only report contract: the function remains security
  invoker, browser roles cannot execute it, and it returns no account identifier or customer content.
- Verified the live report returns all 18 metrics with zero comparable external accounts, while the
  separate historical aggregate continues to show three earlier accounts and 14 successful AI jobs.

### Organic acquisition

- Completed Google Search Console domain ownership verification for `askcrump.com` using the live
  DNS TXT record. Google is now processing the property's first search and indexing data.

### Release

- Advanced the application to 5.9.21 and the service-worker cache to revision 55 so release metadata
  and the corrected operating evidence stay aligned.

## 5.9.20 — 2026-08-27

### Continuing-work activation

- Reordered the useful-result follow-up so keeping the user's own work in a private Project is the
  primary next action and referral sharing remains available as a secondary action.
- Added one-click conversation continuity: the current chat is synchronized, ownership-checked,
  attached to the selected Project or used to create a new Project, and selected for future work.
- Recorded the first successful conversation-to-Project transition as a content-free durable-value
  milestone without storing prompts, titles, filenames, or response content in analytics.
- Corrected the operating baseline after aggregate production review showed 14 successful AI jobs
  across two external accounts before comparable product-event instrumentation existed. The verified
  bottleneck is durable-value conversion and return behavior, not whether Ask Crump has ever answered
  an external user.

### Release

- Advanced the application to 5.9.20 and the service-worker cache to revision 54 so web and installed
  clients receive the continuing-work path and corrected measurement baseline together.

## 5.9.19 — 2026-08-27

### Safe capability foundations

- Added the disabled-by-default Crump Code server foundation for owner-scoped public-repository
  tasks, isolated no-secret sandbox execution, bounded tools and verification, reviewable patches,
  cancellation, audit events, and future approval records.
- Added the disabled-by-default Crump Voice server path for explicit Professional playback through
  ElevenLabs, with entitlement, rate and size guards, usage refunds, ephemeral audio, and automatic
  device-speech fallback.
- Documented the new provider boundaries, privacy impact, activation gates, company operating plan,
  and evidence-backed 30/90-day priorities. Neither capability is publicly activated in this
  release.

### Release

- Advanced the application to 5.9.19 and the service-worker cache to revision 53 so installed
  clients receive the fallback-safe playback behavior and release metadata together.

## 5.9.18 — 2026-08-24

### Organic-search hygiene

- Made the public legal page explicitly indexable and gave it the production clean URL as its canonical.
- Replaced the redirecting legal URL in the sitemap and marketing-page footer with `/legal`.
- Refreshed the sitemap modification dates after the 5.9.18 acquisition and search-surface changes.

## 5.9.11 — 2026-08-24

### Acquisition attribution

- Preserved explicit `acquisition` and `utm_source` campaign attribution through signup while recovering older direct social links that encoded a known external channel in `source`.
- Restricted backward compatibility to an allowlist of known external channels so on-site CTA locations such as hero, pricing, video, closing, and footer are never mislabeled as acquisition sources.
- Advanced the service-worker cache to revision 45 so installed clients receive the corrected signup attribution path immediately.

## 5.9.10 — 2026-08-24

### Subscription checkout reliability
- Added an authenticated browser-return reconciliation path so a completed Stripe Checkout can activate the account even when the webhook is delayed.
- Reconciled entitlement from Stripe's actual subscription status and Price instead of trusting Checkout metadata, with strict user and customer ownership checks.
- Unified browser-return and webhook completion events on the Checkout Session ID for idempotent conversion measurement.
- Added one bounded browser retry for provider or activation delay, then refreshed billing state without duplicating checkout.
- Pinned subscription calls to Stripe API 2026-07-29.dahlia and added per-session integration identifiers while preserving dynamic payment methods.

### Release
- Advanced the application release to 5.9.10 and the service-worker cache to revision 44 so installed clients receive the checkout recovery path immediately.

## 5.9.9 — 2026-08-24

### Image reliability
- Made Balanced image quality the default for both conversational requests and Image Studio while preserving Highest as an explicit user choice.
- Added one bounded retry for transient provider and network failures without retrying permanent rejections or long-running timeouts.
- Extended the image-provider deadline from 180 to 240 seconds inside the existing 300-second function budget so near-complete generations are not cancelled prematurely.
- Added privacy-safe image quality and aspect telemetry, and retained the attempted image model on failed traces, without recording prompts or file contents.

### Release
- Advanced the application release to 5.9.9 and the service-worker cache to revision 43 so installed clients receive the reliability defaults immediately.

## 5.9.8 — 2026-08-24

### Activation measurement
- Added a server-authoritative `StarterIntentReached` milestone for the first task category selected from the authenticated launchpad.
- Restricted the milestone to six safe categories and a fixed idempotency key; prompts, filenames, form contents, and arbitrary metadata never enter the analytics record.
- Preserved the server-only product-event table, RLS boundary, revoked browser-role access, and service-role-only recorder path.

### Release
- Advanced the application release to 5.9.8 and the service-worker cache to revision 42 so the next tester cohort can be measured from signup through starter intent, activation, and durable value.

## 5.9.7 — 2026-08-24

### Signup conversion
- Aligned the visible password requirements with the enforced 10-character, letter-and-number policy so prospective users are no longer told that an invalid 8-character password is acceptable.
- Reduced registration to one password field with an accessible Show/Hide control, clarified that signup is free and requires no card, and added privacy-safe validation-reason telemetry without collecting form contents.
- Sent new users directly to the task-oriented workspace launchpad instead of blocking their first useful action with a six-screen passive tour; the full tour remains available on demand.

### Release
- Advanced the application release to 5.9.7 and the service-worker cache to revision 41 so web and installed-app clients receive the corrected signup experience immediately.

## 5.9.6 — 2026-08-23

### Assistant identity
- Made the saved Assistant Name a server-authoritative conversational identity so the model recognizes, answers to, and naturally uses the user-selected name without confusing it with the Ask Crump product name.
- Reflected the selected name throughout the composer and Intelligence controls, including accessible labels and memory copy.

### Intelligence
- Reintroduced Deep mode as the clearer **Think longer** experience: an additional planning pass, high-effort response guidance, and a separate final-answer review for difficult work.
- Reserved Think longer for active Professional and Enterprise subscriptions, with synchronized UI entitlements and server-side enforcement that cannot be bypassed by modifying browser requests.
- Prevented free Auto mode and expired saved preferences from silently invoking the subscriber-only multi-pass workflow.

### Navigation
- Made every conversation selection render the chosen conversation and dismiss the mobile conversation drawer, including the correct expanded-state reset.
- Changed the Legal & Privacy brand return link to reopen the authenticated Ask Crump app instead of the Clever Crump landing page.

### Release
- Advanced the application release to 5.9.6 and the service-worker cache to revision 40 so installed PWAs receive the identity, intelligence, and navigation changes immediately.

## 5.9.5 — 2026-08-23

### Fixed
- Prevented iPhone focus zoom from leaving Video Studio and other Ask Crump surfaces enlarged after editing by enforcing iOS-safe text sizing across every mobile text field, textarea, select, and editable surface.
- Locked the installed app to its intended 1:1 viewport scale and removed the remaining pinch-zoom exception, while preserving ordinary one-finger scrolling.
- Aligned the iPhone Home menu and Intelligence controls to the same safe-area centerline so the two header buttons remain visually level.
- Moved the responsive stability stylesheet to final authority so dynamically loaded Projects & Create, Library, Settings, authentication, and future tool controls inherit the same mobile behavior.

### Release
- Advanced the application release to 5.9.5 and the service-worker cache to revision 39 so installed PWAs receive the viewport correction immediately.

## 5.9.4 — 2026-08-23

### Conversation startup

- Made every cold start or reload open on a clean new-conversation surface instead of restoring the last active conversation.
- Kept every previous conversation safely available in history and preserved deliberate conversation opens from history, notifications, and other in-app navigation.
- Reused an existing pristine starter when possible so repeated reloads do not accumulate empty conversation rows.

### Quality

- Added regression coverage that prevents last-conversation restoration from returning and guards against deleting or clearing conversation history during fresh startup.
- Advanced the application release to 5.9.4 and the service-worker cache to revision 38.

## 5.9.3 — 2026-08-23

### Acquisition measurement

- Preserved a prospect's privacy-safe first-touch acquisition channel from the public homepage through account creation and initial onboarding.
- Reduced known social referrers to channel names and unknown external referrers to `referral`; full URLs, campaign content, search terms, and user identifiers are never recorded.
- Kept CTA location separate from acquisition source so the business can distinguish which channel brought a customer from which page action converted them.

### Quality

- Added regression coverage for UTM/referrer handling, CTA propagation, registration intake, and server-authoritative account-event attribution.
- Advanced the application release to 5.9.3 and the service-worker cache to revision 37.

## 5.9.2 — 2026-08-23

### Acquisition and discovery

- Restored the public Ask Crump marketing homepage instead of redirecting every first-time visitor directly into the application sign-in screen.
- Preserved source and plan attribution across every first-party signup path and added a distinct returning-user sign-in route.
- Added canonical, Open Graph, social-card, structured-application, robots, and sitemap metadata so the product has a truthful indexable surface.
- Kept the authenticated application out of search results while preserving `/app` as the installed PWA and returning-user destination.

### Quality

- Added regression coverage that prevents the public homepage redirect from returning and verifies the marketing/app indexing boundary.
- Verified the restored funnel visually at desktop and mobile breakpoints with no browser warnings or errors.
- Advanced the application release to 5.9.2 and the service-worker cache to revision 36.

## 5.9.1 — 2026-08-23

### Professional formatting

- Rebuilt Word and PDF output around format-native academic, résumé, and business conventions instead of a shared branded template.
- Enforced exact academic typography, spacing, margins, heading hierarchy, list treatment, and reference hanging indents while keeping citations source-grounded.
- Refined résumés into restrained, single-column ATS-ready documents with stronger hierarchy and no visible product chrome.
- Reworked presentations into varied editorial layouts with readable typography, content-aware tables, and neutral slide furniture.
- Simplified spreadsheets into professional working models with compact workbook indexes, restrained formatting, typed data, and selective visual analysis.
- Polished manuscript title pages and book typography across Word and PDF while preserving editable, publication-oriented structure.

### Quality

- Removed visible Ask Crump branding from default user deliverables while retaining internal provenance metadata.
- Added regression checks for exact Word font slots, reference indentation, neutral page furniture, and professional-format conventions.
- Advanced the application release to 5.9.1 and the service-worker cache to revision 35.

## 5.9.0 — 2026-08-23

### Added

- Added outcome-first Document Studio paths for essays and reports, résumés and CVs, presentations, spreadsheets, and manuscripts.
- Added format-aware, editable Word, PDF, PowerPoint, and Excel finishing with academic, résumé, presentation, spreadsheet, and business profiles.
- Added source-aware research routing and automatic final verification for downloadable artifact requests.
- Added a checksum-locked app-identity pipeline that derives versioned web-install icons, the native icon source, and the native splash source from the permanent Ask Crump C-and-magnifying-glass mark.
- Added representative artifact fixtures and structural tests covering page setup, metadata, editability, spreadsheet types and formulas, presentation dimensions, and extractable PDF text.

### Quality and safety

- Prevented the document system from inventing citations, quotations, credentials, employment history, dates, metrics, research results, or financial inputs.
- Added spreadsheet formula-injection guards, explicit print areas, stable pagination, inferred business number formats, filters, frozen headings, and editable native tables.
- Replaced a fragile manuscript scene-break glyph with a cross-platform typographic break for consistent Word, PDF, and EPUB output.

### Changed

- Advanced the application release to 5.9.0 and the service-worker cache to revision 34 so installed customers receive the document-quality and identity updates.

## 5.8.5 — 2026-08-23

### Added

- Added a privacy-safe `ActivationReached` milestone when an account receives its first successful Ask Crump response.
- Added an account-scoped local guard so the activation event is attempted once, while the server remains the idempotent source of truth.

### Privacy

- Kept activation measurement limited to a fixed milestone key; prompts, responses, filenames, and arbitrary metadata are never sent to product analytics.

### Changed

- Advanced the service-worker cache to revision 33 so activation measurement reaches installed customers.

## 5.8.4 — 2026-08-23

### Added

- Added a deliberate Share action to every Ask Crump response, using the native share sheet on supported devices and a branded clipboard fallback elsewhere.
- Added a privacy-safe `ResponseShared` milestone so the response-sharing loop can be measured without storing prompts, response text, filenames, or personal data.

### Changed

- Limited shared responses to a practical excerpt and attached the canonical AskCrump.com destination for a clear recipient experience.
- Advanced the service-worker cache to revision 32 so the sharing feature reaches installed customers.

## 5.8.3 — 2026-08-22

### Fixed

- Rendered Markdown tables as accessible, responsive tables instead of raw pipe-delimited text.
- Rendered quoted copy and numbered steps with designed blockquote and ordered-list presentation.
- Preserved the safe renderer's HTML escaping and URL protections while expanding its presentation support.
- Advanced the service-worker cache to revision 31 so the conversation polish reaches installed customers.

## 5.8.2 — 2026-08-22

### Added

- Added a private, account-level milestone ledger for activation, durable-artifact value, retention, paid-plan intent, and the verified Stripe subscription lifecycle.
- Added server-authoritative activation, durable-artifact, Checkout, billing-portal, and webhook events plus one authenticated workspace-open event per UTC day.
- Added an operating analytics contract that excludes prompts, responses, filenames, emails, payment details, prices, and arbitrary metadata.

### Security

- Locked the product-event table and idempotent recording function to the server service role, enabled row-level security, and separated preview events from production reporting.
- Made analytics writes fail open so an instrumentation outage cannot interrupt account, chat, artifact, or billing flows.

### Changed

- Advanced the application release to 5.8.2 and the service-worker cache to revision 30.

## 5.8.1 — 2026-08-22

### Added

- Preserved a prospect's Professional or Enterprise selection through registration, verification, onboarding, and sign-in, then opened the matching in-app plan for review without starting checkout automatically.
- Added a privacy-conscious `PlanIntentReached` funnel event containing only the selected plan and sanitized acquisition source.

### Fixed

- Made Saved Library cover URLs expire with their private storage signatures instead of remaining cached indefinitely.
- Added one automatic signed-URL refresh when a cover image fails, then restored the designed placeholder if the retry cannot load.
- Advanced the service-worker cache to revision 29 so the reliability and conversion fixes reach installed customers.

## 5.8.0 — 2026-08-22

### Added

- Added a transparent Free, Professional, Enterprise, and Crump Credits pricing section to the Clever Crump acquisition site.
- Added direct signup links from every primary marketing call to action so new prospects land on account creation instead of a returning-user sign-in screen.
- Added privacy-conscious Vercel Web Analytics page views and non-PII funnel events for marketing CTA intent, signup intent, signup submission, and successful account creation.

### Changed

- Reframed the public product copy around a currently available paid product instead of an unfinished product customers may eventually pay for.
- Updated the public release presentation, in-app About signature, package metadata, and backend version to 5.8.0.
- Advanced the service-worker cache to revision 28 so the signup and analytics runtime reaches installed customers promptly.

## 5.7.2 — 2026-08-22

### Fixed

- Restored dependable sidebar access to Settings, Plan & credits, and Projects when late UI hydration replaces destination elements or drops their original listeners.
- Kept each product module's normal click handler as the primary path, with a guarded fallback that opens a destination only when it is still closed.
- Made the navigation bundle boot-critical and network-first so customers receive the repair promptly instead of remaining on a stale service-worker copy.
- Replaced an undefined Library muted-text token with the canonical application theme tokens.
- Added regression coverage for the revenue, account, and Projects navigation paths and advanced the service-worker cache to revision 27.

## 5.6.1 — 2026-08-17

### Fixed

- Allowed authenticated inline video playback from Ask Crump's private Supabase Storage domains through the web Content Security Policy. Saved Library previews remain private and still use short-lived signed URLs.
- Added a release regression guard so future CSP changes cannot silently block private video previews again.

## 5.6.0 — 2026-08-17

### Added

- Added a final store-debut polish layer that normalizes buttons, links, focus states, touch targets, studio hierarchy, billing surfaces, and responsive behavior without replacing the proven 5.x product architecture.
- Added Projects and Video as first-class launchpad actions so important creation workflows are easier to discover from the empty workspace.
- Added a current six-step product tour covering Projects, creation tools, Video Studio, scene continuation, and the Saved Library.
- Added an updated Clever Crump parent-company page that reflects Ask Crump's current Projects, long-form, Saved Library, and multi-engine video capabilities.

### Changed

- Renamed the creation workspace to “Projects & Create” and simplified video status, Founder Lab, Library, and action copy.
- Standardized video result actions so links and buttons share one visual system and the Download video action no longer renders as a raw underlined link.
- Moved the legacy 4.3 runtime dependency into the deterministic runtime loader instead of loading it as an onboarding side effect.
- Improved Studio tab keyboard semantics, settings access to the product tour, mobile spacing, text sizing, and responsive touch targets.
- Updated PWA product metadata and store-facing copy to reflect Projects, manuscripts, saved creations, Runway Cinematic video, and native scene continuation.
- Advanced the service-worker cache to revision 12.

## 5.5.0 — 2026-08-17

### Added

- Added a provider-agnostic Crump Video Engine with Quick, Extendable, and Cinematic generation paths.
- Added native Veo 3.1 Fast scene continuation with durable job lineage, provider-reference expiry, and private-storage size safeguards.
- Added an optional server-only Runway Gen-4.5 provider with plan-aware 5/10 second generation, attribution, and provider-cost circuit breakers.
- Added continuation controls to completed compatible videos and Saved Library items.

### Changed

- Preserved Veo 3.1 Lite as the existing Quick video path and made expensive video compute explicitly credit-metered behind Professional/Enterprise access.
- Made video failure accounting provider-aware so billable moderation rejections are not automatically treated like infrastructure failures.
- Reduced the default generated-video safety ceiling to 45 MB for compatibility with the current storage tier; it can be raised deliberately when storage capacity is upgraded.
- Fixed Windows JavaScript syntax validation by converting file URLs to native filesystem paths before invoking Node.
- Advanced the application to 5.5.0 and service-worker cache revision 11.

## 5.4.1 — 2026-08-15

### Added

- Added leased, resumable full-manuscript jobs with pause, resume, cancellation, progress, automatic export, and a protected minute worker.
- Added founder/staff lab access that bypasses Ask Crump message, feature, credit, and Project limits without changing customer billing records.
- Added actionable, sanitized OpenAI image and Gemini video provider diagnostics and exposed the configured non-secret model names.

### Changed

- Made book-scale chat requests persist their workspace before any model call, eliminating the 90-second request-timeout failure mode.
- Enabled video generation by default when a Gemini key is configured while preserving the explicit emergency-disable flag.
- Advanced the service-worker cache to revision 8.

## 5.4.0 — 2026-08-15

### Added

- Introduced a durable long-form workflow that turns book-scale chat requests into persistent Project and Manuscript workspaces instead of truncating them into a single response.
- Added AI manuscript blueprints, chapter-purpose continuity, target-word progress, one-click next-chapter drafting, and chat-to-workspace handoff cards.
- Added visible Document and Manuscript composer modes and natural-language detection for Word, PDF, presentation, spreadsheet, Markdown, and text deliverables.
- Added a server-managed internal entitlement for founder, staff, and QA access that remains separate from customer billing records.

### Changed

- Opened manuscript creation and KDP-aware DOCX, PDF, and EPUB export to every tier; Free accounts can use Crump Credits for AI planning and drafting.
- Made the system capability contract explicit so the assistant no longer falsely claims that Ask Crump cannot create or export files.
- Restored Projects, Manuscripts, navigation, stability, and subscription layers to native builds for web/mobile feature parity.
- Advanced the application and service-worker release to 5.4.0 / cache revision 7.

## 4.2.0 — 2026-08-01

### Changed

- Decomposed the API entry point into domain routers and a dedicated application factory.
- Reworked repository documentation around product architecture, operational boundaries, and reviewable engineering decisions.
- Updated the default OpenAI image model to `gpt-image-2`.
- Removed promotional and implementation-history language from user-facing and repository-facing copy.
- Standardized client logging, attachment previews, legal copy, and version metadata.
- Corrected password-recovery layering, account-dialog focus handling, notification rendering, and destructive-action confirmation.
- Hardened the database migration to remove legacy raw session credentials and fail on incomplete data conversion.
- Consolidated conversation, attachment, account, and native-shell styling into defined design tokens.

### Added

- GitHub Actions quality checks for Python and JavaScript.
- Security policy, contribution guide, pull-request template, editor configuration, and project metadata.
- Architecture decision records for synchronization, message presence, and proactive check-ins.

## 4.1.0 — 2026-07-30

- Introduced the FastAPI backend, persistent opaque sessions, synchronized conversations, message delivery states, proactive check-ins, native push support, and web/native billing separation.
