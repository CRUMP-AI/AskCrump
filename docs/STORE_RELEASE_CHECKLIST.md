# App Store and Google Play Release Checklist

## Implemented in source

- Capacitor iOS/Android structure and native build scripts
- persistent secure native sessions
- messaging-style delivery, seen, queued, failure, and retry states
- inline task-aware activity indicator
- optional haptics and network/reconnect feedback
- opt-in Crump Check-ins with quiet hours and anti-annoyance rules
- APNs/FCM server delivery support and notification deep links
- RevenueCat native billing; Stripe blocked in native clients
- restore purchases, account deletion, privacy/terms, and deletion URL
- reduced-motion and live-region accessibility support
- accessible in-app AI response reporting with a private, rate-limited moderation queue
- separate versioned AI-provider data-sharing permission that blocks provider-bound foreground and background work before content leaves Ask Crump, with in-app withdrawal
- multi-engine video disclosure: Veo/Google and Runway prompts/media routed only through the Ask Crump backend, with private durable storage and provider attribution
- deterministic per-platform native preparation and version/build validation
- Android compile/target SDK 36 enforcement
- base iOS privacy manifest copied into the app Resources build phase
- machine-validated en-US store metadata and signed-build screenshot capture plan
- permanent package/bundle identifier verification for both native platforms
- Android cleartext traffic and local backup disabled for account-linked session data

## 2026-09-13 audit snapshot

- [x] Production 5.9.76, truthful representative document and résumé output, immediate race-safe account entry, recoverable failed/reused verification-link return, complete ordered signup milestone delivery, bounded and recoverable authentication entry/recovery, recoverable primary first-message and reply delivery, bounded queue-preserving sync, non-blocking authenticated entry, truthful first-prompt handoff, reliable first workspace choice, optional first-workspace personalization, durable registration-verification handoff, accessible password readiness and web/PWA pinch zoom, WCAG AA public first visit, reliable web-session handoff, six-destination Ask, Projects, Create, Video, Library, and You desktop/mobile workspace, resumable Project conversations, named recent-work continuation, one-click Project continuity, disabled-by-default Crump Code review workspace, 12 canonical crawlable public pages, truthful referral-copy handling, canonical native API host, direct signed Stripe delivery, transient database-read recovery, value-aware cold signup entry, exact native billing identity, and user-controlled chat scrolling verified
- [x] Android source regenerated and verified as 5.9.76/build 50976, API 36
- [x] Store metadata fits current Apple and Google field limits
- [x] Current Google API-level, AI-reporting, deletion, Data Safety, and app-access rules reviewed
- [x] Current Apple privacy, reviewer-access, and screenshot requirements reviewed
- [x] Reviewed npm lockfile committed; clean Node 22 `npm ci`, dependency tree, npm audit, and
      deterministic Android preparation pass (2026-08-27)
- [ ] Owner publisher identity and developer-account state confirmed
- [ ] Android Firebase, RevenueCat public key, and upload keystore supplied; the hosted Java 21
      release-build path is verified, while local Android Studio still needs a compatible JDK
- [ ] iOS source generated, signed, and archived on macOS
- [ ] No-upload GitHub macOS 26/Xcode 26+ source and Release compile verification must pass for
      version 5.9.76 with a valid Apple build such as `5.9.76` before signing. Earlier runs used the
      invalid single-component build `50976`; they retain compile/privacy value but are not current
      App Store identity evidence. The run must include the explicit iPhone+iPad family and
      screenshot-packet gate.
- [x] No-upload GitHub Java 21 Android App Bundle verification passed before signing credentials
      were added for 5.9.76/build 50976, including the screenshot-packet gate
      ([run 34790149297](https://github.com/CRUMP-AI/AskCrump/actions/runs/34790149297), 2026-09-13)
- [x] Apple/Google listing copy, reviewer path, and screenshot sequence match the released Ask,
      Projects, Create, Video, Library, and You information architecture; Research remains inside Ask
- [ ] Exact signed builds pass the physical-device, billing, privacy, and console gates
- [ ] Native billing remains OFF until the server-authoritative owner/fence marker and
      practical before/after SDK setup or identity-alignment checks, plus
      pre-operation purchase, restore, and customer-refresh checks, pass on
      signed builds. These checks reduce stale-client windows; they do not
      guarantee that a paused client cannot recreate a provider customer.
- [ ] Signed two-device deletion tests pause one device after an owner check while the
      other deletes the account, then resume SDK setup/identity alignment and inspect
      provider records after cleanup. Include a concurrent account switch and an
      in-flight purchase/restore case; resolve any remaining provider-recreation or
      charge risk before turning native billing ON or submitting either store build.
- [ ] Exact signed builds prove the AI-sharing first-use prompt appears before the provider request; “Not now” sends nothing; allow resumes once; withdrawal blocks chat, media, voice, manuscript, Autonomous Crump, and scheduled-provider work
- [x] Final packet has a fail-closed local completeness gate for exact signed artifact hash, fresh
      device/console evidence, current iPhone + iPad and Android screenshot dimensions/format,
      and untracked reviewer access; it performs no signing, upload, or submission
      (`docs/STORE_SUBMISSION_PACKET_GATE_2026-09-10.md`)

See `docs/STORE_READINESS_AUDIT_2026-08-27.md` for evidence, blockers, and official references.

## 2026-09-20 release-candidate delta (not a store submission)

- [x] An isolated source candidate integrates account/checkout/video owner-isolation fixes and
      PWA cache versioning. Its focused local test and browser matrices passed. This is not a
      merged, deployed, signed, or store-reviewed build.
- [ ] Prove the staged video/account-deletion database fence against two concurrent database
      connections, confirm worker compatibility and cost/retention policy, then review and apply
      the exact migration before any dependent code deploy. The SQL remains staged, not applied.
- [ ] Verify an actual owned signed PDF opens inside the production app under the proposed
      exact-origin preview policy. Source/CSP parity alone is insufficient.
- [ ] Re-run unsigned iOS compilation with an explicitly selected Apple-accepted Xcode/iOS SDK,
      and verify Android AAB 16 KB native-page compatibility for the exact release candidate.
- [ ] Confirm the publisher account, agreements, app records, signing materials, Firebase,
      RevenueCat/store products, and whether Google's new-personal-account closed test applies.
- [ ] If a release specialist is used, invite a time-limited, app-scoped user only after the exact
      release commit is approved; record the permitted milestones, retain company ownership of all
      accounts/signing material, and remove the specialist's access after the final handoff.
- [ ] Produce and test exact signed IPA/AAB artifacts; capture physical iPhone, iPad, and Android
      journeys, purchase/restore, push, deletion, privacy declarations, screenshots, and reviewer
      access; pass the existing submission-packet gate before either store submission.

Until these gates pass, prior unsigned CI builds and source tests are progress evidence only.

## Apple

- [ ] App record, agreements, tax/banking, bundle ID, signing, and provisioning complete
- [ ] Push Notifications capability and APNs key configured
- [ ] Push permission explanation appears only when the user enables notifications
- [ ] Foreground/background/terminated push and deep-link behavior tested on physical devices
- [ ] App Privacy answers include conversations, delivery metadata, optional check-in data, push tokens, device/session, usage, diagnostics, and purchases
- [ ] App Review notes describe the separate AI-provider permission, current recipients/data categories, first-use test path, and Settings withdrawal path
- [ ] Privacy manifest/required-reason APIs validated from the final Xcode archive
- [ ] Dynamic Type, VoiceOver, Reduce Motion, haptics-off, keyboard, and safe areas tested
- [ ] Native purchases, restore, cancellation disclosure, sync, persistent login, and deletion tested
- [ ] Real final 6.9-inch iPhone and 13-inch iPad screenshot sets and reviewer account/steps supplied

## Google Play

- [x] Versioned 512 × 512 RGBA listing icon and 1024 × 500 RGB feature graphic pass the source gate
- [ ] Upload the exact gated icon and feature graphic to the Play Console listing

- [ ] App record, app signing, upload-key backup, package ID, and payments profile complete
- [ ] Firebase app and `google-services.json` configured
- [ ] Runtime notification permission and notification channel tested on current Android versions
- [ ] Target/compile SDK and current Play submission requirements rechecked on submission day
- [ ] Data Safety matches `docs/DATA_SAFETY.md` and actual provider behavior
- [ ] Data Safety and reviewer instructions match the versioned AI-sharing prompt and server-authoritative withdrawal behavior
- [ ] In-app AI response reporting reaches the production moderation queue and failed-network retry is tested
- [ ] Account deletion URL, in-app deletion, content rating, app access, and no-ads declaration completed
- [ ] Purchases, restore, push, sync, persistent login, offline/reconnect, and pre-launch report tested

## RevenueCat and server schedule

- [x] Native build and server reconciliation share one exact-match, non-secret RevenueCat catalog;
      duplicate/malformed product IDs and stale native runtime IDs fail release verification
- [x] `migrations/014_ai_content_reports.sql` applied to production (2026-08-16)
- [x] Supabase access grants and security/performance advisors reviewed after the migration
- [ ] Store products and entitlements exactly match production environment IDs
- [ ] Purchase, restore, renewal, cancellation, expiration, billing issue, and transfer tested
- [ ] RevenueCat webhook authentication configured
- [x] Vercel `CRON_SECRET` and protected hourly check-in route verified in production: exactly 24
      scheduled calls completed in the trailing 24-hour window with no route-level 4xx/5xx or
      runtime error (`docs/CHECK_IN_CRON_PRODUCTION_READINESS_2026-09-10.md`)
- [ ] Internal accounts confirm no check-in during quiet hours, no repeated unanswered check-in, and correct notification routing

## Reviewer notes

Explain that Ask Crump delivers completed answers in a messaging-style bubble, that `Seen` means the server accepted the request, and that proactive check-ins are optional and disabled by default. Provide steps to test the separate AI-provider permission and withdrawal, cross-device sync, notification opt-in, native billing/restore purchases, in-app AI reporting, session management, and deletion.

Store approval is never guaranteed; rerun current Apple/Google requirements before submission.
