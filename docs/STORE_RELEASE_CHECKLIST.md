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
- multi-engine video disclosure: Veo/Google and Runway prompts/media routed only through the Ask Crump backend, with private durable storage and provider attribution
- deterministic per-platform native preparation and version/build validation
- Android compile/target SDK 36 enforcement
- base iOS privacy manifest copied into the app Resources build phase
- machine-validated en-US store metadata and signed-build screenshot capture plan
- permanent package/bundle identifier verification for both native platforms
- Android cleartext traffic and local backup disabled for account-linked session data

## 2026-08-27 audit snapshot

- [x] Production 5.9.22 and the one-click continuing-work path verified
- [x] Android source regenerated and verified as 5.9.22/build 50922, API 36
- [x] Store metadata fits current Apple and Google field limits
- [x] Current Google API-level, AI-reporting, deletion, Data Safety, and app-access rules reviewed
- [x] Current Apple privacy, reviewer-access, and screenshot requirements reviewed
- [x] Reviewed npm lockfile committed; clean Node 22 `npm ci`, dependency tree, npm audit, and
      deterministic Android preparation pass (2026-08-27)
- [ ] Owner publisher identity and developer-account state confirmed
- [ ] Android Firebase, RevenueCat public key, upload keystore, and compatible JDK 21 supplied (the
      installed Android Studio Java 25 runtime cannot run this Gradle toolchain)
- [ ] iOS source generated, signed, and archived on macOS
- [ ] Exact signed builds pass the physical-device, billing, privacy, and console gates

See `docs/STORE_READINESS_AUDIT_2026-08-27.md` for evidence, blockers, and official references.

## Apple

- [ ] App record, agreements, tax/banking, bundle ID, signing, and provisioning complete
- [ ] Push Notifications capability and APNs key configured
- [ ] Push permission explanation appears only when the user enables notifications
- [ ] Foreground/background/terminated push and deep-link behavior tested on physical devices
- [ ] App Privacy answers include conversations, delivery metadata, optional check-in data, push tokens, device/session, usage, diagnostics, and purchases
- [ ] Privacy manifest/required-reason APIs validated from the final Xcode archive
- [ ] Dynamic Type, VoiceOver, Reduce Motion, haptics-off, keyboard, and safe areas tested
- [ ] Native purchases, restore, cancellation disclosure, sync, persistent login, and deletion tested
- [ ] Real final screenshots and reviewer account/steps supplied

## Google Play

- [ ] App record, app signing, upload-key backup, package ID, and payments profile complete
- [ ] Firebase app and `google-services.json` configured
- [ ] Runtime notification permission and notification channel tested on current Android versions
- [ ] Target/compile SDK and current Play submission requirements rechecked on submission day
- [ ] Data Safety matches `docs/DATA_SAFETY.md` and actual provider behavior
- [ ] In-app AI response reporting reaches the production moderation queue and failed-network retry is tested
- [ ] Account deletion URL, in-app deletion, content rating, app access, and no-ads declaration completed
- [ ] Purchases, restore, push, sync, persistent login, offline/reconnect, and pre-launch report tested

## RevenueCat and server schedule

- [x] `migrations/014_ai_content_reports.sql` applied to production (2026-08-16)
- [x] Supabase access grants and security/performance advisors reviewed after the migration
- [ ] Store products and entitlements exactly match production environment IDs
- [ ] Purchase, restore, renewal, cancellation, expiration, billing issue, and transfer tested
- [ ] RevenueCat webhook authentication configured
- [ ] Vercel `CRON_SECRET` configured and protected hourly check-in invocation verified
- [ ] Internal accounts confirm no check-in during quiet hours, no repeated unanswered check-in, and correct notification routing

## Reviewer notes

Explain that Ask Crump delivers completed answers in a messaging-style bubble, that `Seen` means the server accepted the request, and that proactive check-ins are optional and disabled by default. Provide steps to test cross-device sync, notification opt-in, native billing/restore purchases, in-app AI reporting, session management, and deletion.

Store approval is never guaranteed; rerun current Apple/Google requirements before submission.
