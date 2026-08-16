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

1. Merge a reviewed release commit to `main`.
2. Apply every unapplied SQL migration to the production Supabase project.
3. Run Supabase security and performance advisors and resolve new findings.
4. Deploy the matching backend/frontend commit to Vercel.
5. Prepare the native project for one platform.
6. Build and sign the release using owner-controlled credentials.
7. Test the exact signed build on physical devices and in store sandboxes.
8. Upload to TestFlight or Play internal testing.
9. Complete privacy, content-rating, app-access, and commerce declarations.
10. Submit for review, then use a staged production rollout.

Do not test a new API route against production before its matching migration is applied. For the in-app AI report flow, `migrations/014_ai_content_reports.sql` must exist in production first.

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

```powershell
npm ci
npm run store:prepare:android
```

The preparation command builds the local web bundle, creates Android if absent, syncs Capacitor, generates store assets, locks the package version/build number, configures notification metadata, and validates the result.

For a later upload build, use a strictly increasing integer:

```powershell
$env:STORE_BUILD_NUMBER = "50402"
npm run store:prepare:android
```

Create the signed Android App Bundle from Android Studio or with the generated project's Gradle release task after the upload keystore is configured. Upload the `.aab` to Play internal testing first. Never commit the keystore, keystore password, Play service-account key, or production Firebase credentials.

## 5. Prepare iOS on macOS

Xcode and CocoaPods require macOS. A Mac is not required for day-to-day source work, but a signed iOS archive must be produced on a Mac or a trusted macOS CI runner.

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
- Ask, Research, Image, Document, Manuscript, Video, Files, and Saved Library
- generated-file preview, playback, download, and reopening after relaunch
- offline/reconnect behavior, queued/failed delivery, and cross-device sync
- push opt-in, foreground/background/terminated delivery, and deep links
- subscription/credit purchase, restore, cancellation messaging, and entitlement sync
- in-app AI response reporting, including failed-network retry
- export and permanent account deletion, including the external deletion URL
- VoiceOver/TalkBack, larger text, reduced motion, contrast, keyboard, and safe areas
- no Stripe checkout inside either native application

## 7. Store-console declarations

- Privacy answers must match `docs/DATA_SAFETY.md`, `public/legal.html`, the final SDK inventory, and actual provider retention settings.
- Apple App Privacy and Google Data Safety are separate declarations; neither is completed automatically by the privacy policy.
- Reported AI output, optional report comments, prompt context, conversations, uploaded/generated files, purchases, identifiers, diagnostics, and push data must be classified honestly.
- Complete generative-AI/content questions, age/content ratings, app access, encryption/export compliance, ads, and account-deletion fields.
- Use `docs/STORE_LISTING_COPY.md` as reviewed draft copy, then upload screenshots captured from the exact release build.

## 8. Every future release

1. Increment `package.json` version using `major.minor.patch`.
2. Choose a new `STORE_BUILD_NUMBER` greater than every prior Apple build and Android version code.
3. Re-run tests, current store-policy checks, native preparation, and signed-device tests.
4. Update release notes and screenshots when the visible experience changes.
5. Release to internal testers, then a small production percentage, then expand while watching crashes, API errors, billing, and support reports.

Keep signing keys, recovery codes, D-U-N-S documentation, account ownership, tax/banking records, and store API credentials in a company-controlled password manager with at least two authorized administrators.
