# Native store privacy evidence release — 2026-09-07

## Outcome

Ask Crump's native store source and compiled candidates now fail closed when their privacy evidence
drifts. The release corrects the Apple purchase-history declaration to include both app
functionality and analytics, records every runtime native package in the engineering Data Safety
inventory, verifies the app-level disclosure semantically, and inspects the actual compiled iOS
privacy manifests and merged Android permissions.

This is submission evidence, not a claim that either app is ready for review. Signing, store
products, reviewer access, console declarations, screenshots, and physical-device commerce tests
remain required.

## Correction

`resources/PrivacyInfo.xcprivacy` already declared account-linked purchase history for app
functionality. RevenueCat's current App Privacy guidance also requires the analytics purpose for
its customer history, charts, and experiments. The purchase-history declaration now includes both
purposes, remains linked to the Ask Crump account, and remains explicitly not used for tracking.
The product continues to ship no advertising SDK or ad-attribution collection.

The engineering inventory in `docs/DATA_SAFETY.md` now names every runtime native package and the
capability/disclosure boundary it owns. Adding or removing a Capacitor, RevenueCat, Aparajita, or
Capacitor Community runtime package without reconciling that inventory makes the store privacy
verifier fail.

## Compiled evidence

The exact unsigned 5.9.76/build 50976 iOS candidate compiled on Xcode 16.4 and contained five valid
privacy manifests:

- `PrivacyInfo.xcprivacy` at the app root;
- `Frameworks/Capacitor.framework/PrivacyInfo.xcprivacy`;
- `Frameworks/Cordova.framework/PrivacyInfo.xcprivacy`;
- `RevenueCat_RevenueCat.bundle/PrivacyInfo.xcprivacy`; and
- `SDWebImage_SDWebImage.bundle/PrivacyInfo.xcprivacy`.

The exact unsigned Android App Bundle compiled with Java 21 and its final merged manifest contained
only these eight permissions:

- `android.permission.ACCESS_NETWORK_STATE`;
- `android.permission.INTERNET`;
- `android.permission.POST_NOTIFICATIONS`;
- `android.permission.VIBRATE`;
- `android.permission.WAKE_LOCK`;
- `com.android.vending.BILLING`;
- `com.clevercrump.askcrump.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`; and
- `com.google.android.c2dm.permission.RECEIVE`.

The verifier rejects an unexpected advertising ID, coarse/fine/background location, contacts,
account-list, call-log, or SMS permission. It also rejects a compiled iOS app missing the root,
Capacitor, Cordova, RevenueCat, or SDWebImage privacy manifest. Every bundled privacy manifest is
validated with Apple's `plutil` before the compiled inventory check.

## Validation and release evidence

- Commits: `f77953f`, `df06c75`, and `e882471`.
- Main CI: [34159190232](https://github.com/CRUMP-AI/AskCrump/actions/runs/34159190232).
- Android Store Bundle Verification: [34159190266](https://github.com/CRUMP-AI/AskCrump/actions/runs/34159190266).
- iOS Store Source Verification: [34159190241](https://github.com/CRUMP-AI/AskCrump/actions/runs/34159190241).
- Production deployment: `dpl_E38RmBQM4E59QhjeChJntsWFkVy4`, READY on all six aliases with no
  alias error.
- All 839 Python tests, all 49 JavaScript validations, Ruff, production preflight, native web
  build, structured store metadata, source privacy verification, YAML parsing, and diff integrity
  passed.
- Production health remained 5.9.76, `/app` returned HTTP 200, and the inspected release window had
  no runtime-error cluster or warning/error/fatal log.

No account, customer content, Project, file, event, credit, entitlement, purchase, provider job,
payment object, store listing, signing identity, or console state was created or changed for this
proof.

## Remaining submission gates

1. Configure the owner-controlled Apple and Google RevenueCat public keys and exact store products.
2. Create signed internal/TestFlight candidates and complete purchase, restore, renewal,
   cancellation, expiration, billing-issue, refund, and cross-device identity tests.
3. Re-run the compiled manifest/permission inventory against those exact signed candidates and
   generate Apple's archive privacy report.
4. Capture privacy-safe screenshots from the signed builds, create the dedicated reviewer account,
   reconcile the console privacy/data-safety forms, and obtain founder approval before submission.

## Current primary requirements

- [Apple privacy manifest files](https://developer.apple.com/documentation/bundleresources/privacy-manifest-files)
- [Apple third-party SDK requirements](https://developer.apple.com/support/third-party-SDK-requirements/)
- [Google Play Data Safety](https://support.google.com/googleplay/android-developer/answer/10787469)
- [RevenueCat Apple App Privacy guidance](https://www.revenuecat.com/docs/platform-resources/apple-platform-resources/apple-app-privacy)

Recheck these external requirements against the exact signed submission candidate on submission
day.
