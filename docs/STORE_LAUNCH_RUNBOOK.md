# Ask Crump Store Launch Runbook

This is the permanent release path for `com.clevercrump.askcrump`. A source commit is not a store release: every release must pass the database, native build, device-test, commerce, privacy, and store-console gates below.

## 1. Choose the publisher identity first

Use an **organization** account if CleverCrump is a registered legal entity and the storefront should identify the company. Apple and Google require the legal entity and a D-U-N-S number for organization enrollment. A trade name by itself is not a legal entity.

An individual enrollment is faster, but Apple displays the individual's legal name as the seller. A newly created Google Play personal account must also complete Google's closed-test requirement before production access.

Never create duplicate developer accounts while identity verification is pending.

Official references:

- Apple enrollment: <https://developer.apple.com/programs/enroll/>
- Apple organization/D-U-N-S requirements: <https://developer.apple.com/help/account/membership/D-U-N-S/>
- Google Play account setup: <https://support.google.com/googleplay/android-developer/answer/6112435>
- Google organization verification: <https://support.google.com/googleplay/android-developer/answer/13634885>
- Google personal-account testing: <https://support.google.com/googleplay/android-developer/answer/14151465>

## 2. Release order

1. Merge a reviewed, fully verified release commit to `main`.
2. Inventory the remote migration ledger and apply only the reviewed migrations required by
   this release, in their documented compatibility order. Never apply every pending migration
   solely because it is present in the checkout.
3. Run Supabase security and performance advisors and resolve new findings.
4. Deploy the matching backend/frontend commit to Vercel only after its required database
   changes and rollback/compatibility checks are complete.
5. Prepare the native project for one platform.
6. Build and sign the release using owner-controlled credentials.
7. Test the exact signed build on physical devices and in store sandboxes.
8. Upload to TestFlight or Play internal testing.
9. Complete privacy, content-rating, app-access, and commerce declarations.
10. Submit for review, then use a staged production rollout.

Do not test a new API route against production before its matching migration is applied. For the in-app AI report flow, `migrations/014_ai_content_reports.sql` must exist in production first. For multi-engine video and native continuation, `migrations/015_video_engine_continuations.sql` must exist before the new video routes are deployed.

### Video-provider release gates

- Keep the existing Veo Lite route as the Quick engine; use Veo 3.1 Fast for the Extendable engine and native continuation.
- Keep `RUNWAYML_API_SECRET` server-side only. The Runway engine must remain unavailable until that secret is deliberately configured in the production host.
- Preserve `X-Runway-Version=2024-11-06` through `RUNWAY_API_VERSION` and review Runway's current API version before future releases.
- Runway outputs must be copied into private Supabase Storage; never persist an expiring Runway delivery URL as the user's durable asset.
- Show the required **Powered by Runway** attribution wherever a Runway engine/result is surfaced.
- Verify `VIDEO_DAILY_PROVIDER_BUDGET_CENTS`, `VIDEO_USER_DAILY_PROVIDER_BUDGET_CENTS`, and `RUNWAY_MONTHLY_PROVIDER_BUDGET_CENTS` before production rollout. Founder/internal access may bypass app-credit metering, but not the global provider-cost circuit breakers.
- Verify the `crump-files` bucket and `MAX_GENERATED_VIDEO_BYTES` remain compatible. Native Veo continuation is intentionally disabled when the next combined file is projected to exceed the configured storage guard.

### Outsourced release-specialist boundary

Outsourcing the final console, signing, beta-distribution, and review-response work is allowed only
after one exact release commit and its unsigned CI evidence are approved. The specialist is a
temporary release operator, not the publisher, account owner, product architect, or custodian of
Ask Crump's infrastructure.

- The company creates and owns both developer accounts, app records, bundle/package identifiers,
  signing identities, upload keys, listings, and every submitted artifact. A contractor must never
  create or retain any of them under the contractor's identity.
- Invite the specialist with their own account. On Apple, use app-limited Developer access first
  and elevate to app-limited App Manager only for a task that requires it. On Google Play, use a
  time-limited User with only the Ask Crump app and only the release/store-listing permissions
  required by the agreed milestone. Never grant Account Holder, global Admin, user-management,
  Finance, payments-profile, tax, banking, or unrestricted API-key access.
- Never share the founder's password, two-factor or recovery material, Apple Account, Google
  Account, password-manager access, Supabase/Vercel/Stripe credentials, production database
  access, RevenueCat secret keys, Play service-account keys, or an unencrypted signing secret.
- Keep the Android upload keystore and Apple signing/provisioning material company-controlled.
  When temporary signing access is unavoidable, use a revocable, least-privilege path and rotate or
  revoke it immediately after acceptance. Disable individual App Store Connect API-key generation
  for the specialist unless the reviewed workflow explicitly requires it.
- Pay against evidence-based milestones: exact commit recorded; signed AAB installed through Play
  internal testing; signed iOS build installed through TestFlight; listings and declarations
  completed without placeholders; rejection findings resolved; and a final handoff containing
  artifact hashes, build/version numbers, console status, reviewer correspondence, and removal of
  contractor access.
- Product, privacy, billing, entitlement, or backend changes discovered during submission return to
  the repository review process. The specialist may not patch production or substitute a different
  source snapshot to make a review pass.

Apple documents app-scoped access and role capabilities in its
[accounts and roles](https://developer.apple.com/help/app-store-connect/manage-your-team/overview-of-accounts-and-roles),
[role permissions](https://developer.apple.com/help/app-store-connect/reference/account-management/role-permissions),
and [app access](https://developer.apple.com/help/app-store-connect/create-an-app-record/edit-access-to-an-app)
references. Google documents app-level access, permission expiry, and granular permissions in
[Play Console user management](https://support.google.com/googleplay/android-developer/answer/9844686).

## 3. One-time account setup

### Apple

- Join the Apple Developer Program and finish App Store Connect agreements, tax, and banking.
- Register bundle ID `com.clevercrump.askcrump`.
- Create the app record and enable App Store Connect API access if release automation will be used.
- Enable Push Notifications and Background Modes for the App target.
- Create an APNs authentication key and configure the production server/FCM integration.
- Create subscriptions and consumable credit products, then map their exact identifiers in RevenueCat.
- Add a Sandbox Apple Account and a reviewer/demo account.

### Google

- Finish Play Console identity verification and payments profile setup.
- Create the app with package ID `com.clevercrump.askcrump`; this ID is permanent after first upload.
- Enable Play App Signing and back up the upload keystore securely.
- Register the Android app in Firebase and place `google-services.json` in `android/app/` after native generation.
- Create subscriptions and consumable credit products, then map their exact identifiers in RevenueCat.
- Configure license testers and internal-test users.

### RevenueCat

- Keep Apple, Google, RevenueCat, and backend product identifiers exactly aligned.
- Use the public RevenueCat SDK keys only in the client; keep webhook authorization and store credentials server-side.
- Test purchase, restore, renewal, cancellation, expiration, billing issue, refund, and cross-device entitlement sync.

## 4. Prepare Android on Windows

Install Node 22, Android Studio, JDK 21, and the Android 16/API 36 SDK. From the repository root:

Use the tracked, reviewed `package-lock.json` with Node 22. Regenerate and review it in a clean Node
22/npm environment whenever dependencies change. The preparation script intentionally stops if the
lockfile is missing; do not replace the reproducibility gate with a mixed-package-manager install.

```powershell
npm ci
npm run store:prepare:android
```

The preparation command builds the local web bundle, creates Android if absent, syncs Capacitor, generates store assets, locks the package version/build number, configures notification metadata, and validates the result.

For a later upload build, choose an unused integer above the highest build number in both
store consoles. Do not reuse the historical example value from an older release:

```powershell
$env:STORE_BUILD_NUMBER = "<next-unused-store-build-number>"
npm run store:prepare:android
```

Create the signed Android App Bundle from Android Studio or with the generated project's Gradle release task after the upload keystore is configured. Upload the `.aab` to Play internal testing first. Never commit the keystore, keystore password, Play service-account key, or production Firebase credentials.

## 5. Prepare iOS on macOS

Xcode and CocoaPods require macOS. Apple currently requires iOS submissions to be built with Xcode 26
or later and the iOS 26 SDK or later. A Mac is not required for day-to-day source work, but a signed iOS
archive must be produced with that toolchain on a Mac or a trusted macOS CI runner. Ask Crump's preferred Windows-led
path is a manually dispatched GitHub-hosted macOS runner, followed by an owner-approved App Store
Connect upload. Do not outsource merely to obtain a Mac unless the controlled CI path fails.

`.github/workflows/ios-store-verify.yml` is the no-credential first stage. It pins the GitHub macOS 26
image, fails closed below Xcode 26 or the iOS 26 SDK, generates the iOS project, runs the native
verifier, and compiles Release with code signing disabled. It cannot upload
or submit. Add a separate, owner-reviewed signing/upload stage only after the Apple team, app record,
certificates/profiles or managed-signing path, and App Store Connect authentication are approved.
The unsigned compile must explicitly select an Xcode version and iOS SDK accepted by Apple on the
submission date; a hosted runner's default Xcode version is not evidence of compliance.

```bash
npm ci
npm run store:prepare:ios
npm run cap:open:ios
```

In Xcode:

1. Select the correct Apple team and automatic signing.
2. Confirm bundle ID `com.clevercrump.askcrump`.
3. Enable Push Notifications and Background Modes → Remote notifications.
4. Validate the privacy report and required-reason API declarations from the final archive.
5. Archive the **App** scheme using **Any iOS Device (arm64)**.
6. Validate and upload to App Store Connect, then test through TestFlight.

The generated `ios/` and `android/` folders are intentionally not the source of truth. `capacitor.config.ts`, `resources/`, and the native configuration/verification scripts reconstruct them.

## 6. Required signed-build tests

Run these on current physical iPhone and Android devices:

- registration, email verification, sign-in, relaunch persistence, sign-out, and revoked sessions
- Ask, Research, Image, Document, Manuscript, Video, Files, Projects, Create, and Library
- generated-file preview, playback, download, and reopening after relaunch
- Quick, Extendable, and Cinematic video engine entitlement/cost behavior; Runway must remain hidden/unavailable when its server key is absent
- Veo native continuation from a finished Extendable clip, including chained duration, 48-hour provider-reference expiry, storage-size stop, idempotent retry, and credit refund behavior
- Runway success, throttling, provider failure, billable input-safety rejection, private-storage copy, and Powered by Runway attribution
- offline/reconnect behavior, queued/failed delivery, and cross-device sync
- push opt-in, foreground/background/terminated delivery, and deep links
- subscription/credit purchase, restore, cancellation messaging, and entitlement sync
- in-app AI response reporting, including failed-network retry
- export and permanent account deletion, including the external deletion URL
- VoiceOver/TalkBack, larger text, reduced motion, contrast, keyboard, and safe areas
- no Stripe checkout inside either native application

Before trusting an Android upload candidate, verify that its exact AAB requests 16 KB page
alignment and that every packaged native library has compatible ELF load-segment alignment. The
source or unsigned-bundle check does not replace Play pre-launch and physical-device testing.

## 7. Store-console declarations

- Privacy answers must match `docs/DATA_SAFETY.md`, `public/legal.html`, the final SDK inventory, and actual provider retention settings.
- Before review, prove on both signed native builds that the first provider-backed action shows the separate AI data-sharing prompt before any network request, “Not now” sends nothing, “Allow and continue” resumes exactly once, Settings shows the current state, withdrawal blocks future foreground and background provider work, and Terms acceptance alone never grants permission. Give the reviewer the exact test path.
- Apple App Privacy and Google Data Safety are separate declarations; neither is completed automatically by the privacy policy.
- Reported AI output, optional report comments, prompt context, conversations, uploaded/generated files, purchases, identifiers, diagnostics, and push data must be classified honestly.
- Complete generative-AI/content questions, age/content ratings, app access, encryption/export compliance, ads, and account-deletion fields.
- Use `docs/STORE_LISTING_COPY.md` as reviewed draft copy, then upload screenshots captured from the exact release build.

## 8. Final packet completeness gate

After the exact signed build, physical-device matrix, store products, privacy declarations,
screenshots, and reviewer access are complete, run the non-publishing packet verifier documented in
`docs/STORE_SUBMISSION_PACKET_GATE_2026-09-10.md`. It binds the evidence to the exact artifact and
screenshot hashes and fails on stale, incomplete, placeholder, or unknown fields. Passing it does
not authorize or perform upload/submission; Greg's explicit platform-specific approval remains the
last gate.

## 9. Every future release

1. Increment `package.json` version using `major.minor.patch`.
2. Choose a new `STORE_BUILD_NUMBER` greater than every prior Apple build and Android version code.
3. Re-run tests, current store-policy checks, native preparation, and signed-device tests.
4. Update release notes and screenshots when the visible experience changes.
5. Release to internal testers, then a small production percentage, then expand while watching crashes, API errors, billing, and support reports.

Keep signing keys, recovery codes, D-U-N-S documentation, account ownership, tax/banking records, and store API credentials in a company-controlled password manager with at least two authorized administrators.
