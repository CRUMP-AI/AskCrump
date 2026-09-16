# Ask Crump native-store readiness checkpoint — 2026-09-16

State: **SOURCE READY / SIGNED DISTRIBUTION CANDIDATES NOT YET BUILDABLE**

## Current source evidence

- Product source: `7833d89e2e5ee419fd27757f82c4fff92beed295`.
- Native dependency release: `0e93620ad3bac0009661299237ba81a50cb60aa5`.
- Product version/build: `5.9.76` / `50976`.
- Capacitor core, CLI, Android, and iOS: `8.4.3`.
- Store metadata source gate: passed. Apple and Google copy remains inside every recorded limit.
- Native privacy source gate: passed.
- Mobile-signing source controls: passed; no tracked signing secret was found.
- Current hosted CI: run `35123928372`, successful.
- Current hosted Java 21 Android App Bundle verification: run `35123928343`, successful.
- Current hosted macOS iPhone+iPad Release-source verification: run `35123928415`, successful.

The hosted runs all target the native dependency release commit and prove that the current source can
regenerate and compile both native platforms without committing generated projects or credentials.
They do not prove store signing, physical-device behavior, sandbox purchases, upload, review, or
availability.

## Fail-closed local result

The current local store gates stopped for the intended reasons:

- `REVENUECAT_ANDROID_PUBLIC_SDK_KEY` and `REVENUECAT_IOS_PUBLIC_SDK_KEY` were not loaded into the
  native build;
- generated `android/` and `ios/` projects are absent from the source worktree by design;
- the final packet has no signed artifact, current screenshots, device/console evidence, or reviewer
  access record; and
- Android signing credentials are not loaded in this shell.

No verifier was bypassed. The missing generated projects are reconstructible; the remaining items
are owner-controlled distribution inputs and real-device evidence.

## Remaining release gates

1. Confirm Apple and Google publisher identities, developer-account status, agreements, tax/banking,
   and the permanent `com.clevercrump.askcrump` records.
2. Supply the exact RevenueCat public SDK keys and verify Apple/Google products plus entitlements
   against the existing fail-closed catalog.
3. Supply Firebase Android configuration, Android upload signing, and Apple team/signing/provisioning
   through company-controlled secrets. Do not commit any credential.
4. Produce the exact signed `.aab` and iOS archive, then test those bytes on physical Android,
   iPhone, and iPad devices for authentication, Files, Projects, media, push, offline recovery,
   reporting, deletion, accessibility, native purchases, restore, and entitlement reconciliation.
5. Capture the required current 6.9-inch iPhone, 13-inch iPad, and four-to-eight Android phone
   screenshots from those signed builds.
6. Complete Apple App Privacy, Google Data Safety/content/app-access declarations, reviewer access,
   artifact/screenshot hashes, and the final non-publishing packet verifier.
7. Upload only to TestFlight/Play internal testing first. Store submission and rollout remain
   separate platform-specific action-time decisions.

## Windows boundary

Windows is not a reason to outsource the iOS release. The existing GitHub-hosted macOS workflow can
generate and compile the source. Final signing/upload still needs the Apple developer identity,
certificates or managed-signing path, provisioning, App Store Connect authentication, and an
owner-approved upload stage. Google Play can be prepared from Windows once the Android/Firebase/
RevenueCat/signing inputs are present.

## Preserved boundary

This checkpoint created no developer account, certificate, profile, key, store product, signed
artifact, screenshot, reviewer credential, upload, submission, purchase, customer record, or spend.
It did not change the live Facebook acquisition cell or production 5.9.76.
