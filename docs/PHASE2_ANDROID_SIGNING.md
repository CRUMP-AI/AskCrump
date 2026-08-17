# Ask Crump Phase 2 — Android Upload Signing

Permanent Android package ID:

`com.clevercrump.askcrump`

Ask Crump uses the Google Play App Signing model:

1. Clever Crump protects the upload key locally.
2. Ask Crump's `.aab` is signed with that upload key.
3. Google Play verifies the upload certificate.
4. Google Play protects the separate app-signing key used for user-delivered APKs.

## Secret boundary

Private upload keystores and passwords never belong in GitHub.

Default private key location:

`%USERPROFILE%\.askcrump\signing\android\askcrump-upload.jks`

The exported PEM beside it is the PUBLIC upload certificate.

## Environment variables for a signed build

Set only in the release process:

- `ASKCRUMP_ANDROID_KEYSTORE_FILE`
- `ASKCRUMP_ANDROID_KEY_ALIAS`
- `ASKCRUMP_ANDROID_KEYSTORE_PASSWORD`
- `ASKCRUMP_ANDROID_KEY_PASSWORD`

The generated Gradle project reads those variables. No password is written into
Gradle source, package.json, .env, or Git.

## Current service gates

A cryptographic signing proof is not automatically a submission-ready bundle.

Before the final Google Play internal-testing bundle, also configure:

- RevenueCat Android PUBLIC SDK key
- Play subscription / Crump Credit product mappings
- Firebase Android app and local `google-services.json` if Ask Crump push notifications ship in the Android release
- Google Play developer/app record
- Play App Signing
- internal testing

The final AAB must be rebuilt after all required production service configuration
is present.
