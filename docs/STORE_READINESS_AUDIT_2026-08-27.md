# Ask Crump store-readiness audit — 2026-08-27

## Outcome

Ask Crump has a verified store-release source foundation, but it is not yet ready for upload or
submission. Android source was regenerated for 5.9.30/build 50930 and its unsigned Release App
Bundle compiled on a hosted Java 21 runner. The iOS project was generated and its unsigned Release
configuration compiled on a hosted macOS runner. Signing, push, native billing products, reviewer
access, physical-device testing, screenshots, console declarations, and publisher-account setup
remain owner-controlled gates.

No store upload, public listing, developer-account enrollment, purchase, or pricing change was made
during this audit.

## Verified source state

| Area | Evidence | State |
| --- | --- | --- |
| Production release | Production health returned 5.9.30; the deployed client contains the repaired web-session handoff and the five-destination Ask, Projects, Create, Library, and You navigation on desktop/mobile while preserving the direct `Keep in a Project` action, crawlable workflow pages, verified referral-copy handling, canonical native API defaults, and the backward-compatible credits webhook secret-key alias. Authenticated-browser, direct Stripe replay, and current-deployment runtime checks passed with no observed error cluster. | Verified |
| Permanent identifier | Capacitor app ID and Android namespace/application ID are `com.clevercrump.askcrump`; native verification now fails if either platform drifts. | Verified |
| Android platform level | Regenerated source uses min SDK 24 and compile/target SDK 36. Google requires new apps and updates to target API 36 beginning August 31, 2026. | Verified |
| Android release identity | Regenerated source uses version 5.9.30 and build/version code 50930. | Verified |
| Android local security | Generated releases explicitly disable cleartext traffic and local app backup; durable work is restored through Ask Crump's authenticated server sync. | Verified in source |
| Android assets | Launcher and splash assets exist and the native release verifier accepts the generated set. | Verified in source |
| AI safety reporting | Every rendered assistant response exposes an in-app Report action backed by the private, rate-limited moderation queue, satisfying Google's in-app AI-content reporting requirement in source. | Verified in source and automated tests |
| Account deletion | In-app permanent deletion and `https://askcrump.com/delete-account.html` exist; the final signed-build deletion journey still needs a physical-device test. | Source ready; device test pending |
| Store copy | `store/listing.en-US.json` is machine-checked against Apple/Google field limits and the reviewed Markdown draft. | Verified in source |
| Reproducible dependencies | The tracked npm v3 lockfile was generated with Node 22.22.0/npm 11.6.0 in an isolated worktree. Clean `npm ci`, `npm ls --all`, a zero-vulnerability `npm audit`, production build, and deterministic Android preparation passed. | Verified |
| Privacy inventory | `docs/DATA_SAFETY.md`, the public privacy notice, and the iOS base privacy manifest enumerate account, content, device, usage, purchase, reporting, push, and provider flows. | Source ready; final SDK/archive reconciliation pending |
| iOS generation | The deterministic scripts set the bundle ID/version, push callbacks, Photos explanations, and bundled privacy manifest. GitHub run [33129397539](https://github.com/CRUMP-AI/AskCrump/actions/runs/33129397539) regenerated 5.9.30 and compiled its Release configuration on hosted macOS. | Verified unsigned Release compile |
| iOS cloud boundary | `.github/workflows/ios-store-verify.yml` uses a standard GitHub macOS runner with signing disabled and no upload credentials. The first run exposed a workspace/project assumption; the corrected workflow accepts the generated Xcode project and the second run passed. | Verified no-secret/no-upload boundary |
| Android cloud boundary | `.github/workflows/android-store-verify.yml` prepares source with Node 22, selects Temurin Java 21, compiles a Release App Bundle, and requires the `.aab` to be non-empty. The refreshed 5.9.30/build 50930 [run 33129397531](https://github.com/CRUMP-AI/AskCrump/actions/runs/33129397531) passed every source, signing-control, Gradle, and bundle-output step. | Verified unsigned `.aab` compile |
| Signing controls | Mobile signing verification found no tracked keys, certificates, provisioning profiles, service-account files, or passwords. | Verified |

## Current blockers

### Owner accounts and legal identity

- Choose individual versus organization enrollment. An organization storefront requires the exact
  registered legal entity and matching D-U-N-S information; enrollment fees, agreements, tax, and
  banking are owner approvals.
- Create or confirm Apple Developer/App Store Connect and Google Play Console access under
  company-controlled credentials with recovery access and at least two trusted administrators.
- Confirm whether the Google developer account is a new personal account; if so, plan the required
  closed test and production-access application rather than promising a launch date prematurely.

### Reproducible dependency install — resolved 2026-08-27

- `package-lock.json` is committed at lockfile version 3 with the root Node requirement fixed at
  `22.x`. It was generated with Node 22.22.0/npm 11.6.0 in an isolated worktree.
- Clean `npm ci` installed 130 packages; `npm ls --all` resolved without invalid or missing nodes;
  `npm audit` reported zero vulnerabilities; the production bundle and deterministic Android
  preparation passed. CI now uses `npm ci` and validates the production bundle plus store metadata.
- The store preparation script continues to fail closed if the lockfile is removed. Regenerate and
  review the lockfile in a clean Node 22 environment whenever dependencies change.

### Android

- Add the owner-controlled `android/app/google-services.json` after registering
  `com.clevercrump.askcrump` in Firebase.
- Configure `REVENUECAT_ANDROID_PUBLIC_SDK_KEY`, create the exact Play subscription/credit products,
  and map them in RevenueCat.
- Create and securely back up the Play upload keystore outside Git, then load all four
  `ASKCRUMP_ANDROID_*` signing variables only in the release shell.
- Android Studio and the Android SDK are installed, but its bundled Java 25 runtime is incompatible
  with the current Gradle toolchain (`Unsupported class file major version 69`). This is no longer a
  release-build blocker: the no-secret cloud verifier selects Java 21 explicitly and has produced a
  verified unsigned `.aab`. Local Android Studio builds still require selecting a compatible JDK.
- Produce a signed bundle, upload only to Play internal testing, and complete device/pre-launch,
  billing, restoration, push, deletion, accessibility, and offline/reconnect tests.

### iOS

- The generated iOS project and unsigned Release compile passed on a GitHub-hosted macOS runner,
  preserving a Windows-led release process without outsourcing the submission. Keep the verified
  no-secret workflow separate from any future credentialed archive/upload workflow.
- Select the Apple team, enable Push Notifications and Background Modes, and supply APNs credentials.
- Configure `REVENUECAT_IOS_PUBLIC_SDK_KEY`, create the exact App Store products, and map them in
  RevenueCat.
- Validate the final archive's privacy report and required-reason API declarations, then test the
  signed build through TestFlight on physical iPhone and iPad hardware before review.

### Both stores

- Create a dedicated, non-expiring reviewer account using the ignored
  `store/reviewer-access.json` file; never commit credentials or use a real customer's account.
- Confirm the public support page has every owner-approved contact detail required for the chosen
  seller identity and regions. It currently publishes support email channels but no legal address or
  telephone number; do not invent or expose personal contact data in source.
- Capture screenshots from the exact signed build using `store/screenshots/README.md`; no mockup is
  evidence that the release works.
- Reconcile the final binary/SDK inventory to Apple App Privacy, Google Data Safety, the public
  privacy notice, and `docs/DATA_SAFETY.md`.
- Complete content/age rating, generative-AI, app-access, ads, encryption/export, deletion, support,
  regional trader, and purchase declarations in each console.
- Test purchase, restore, renewal, cancellation, expiration, billing issue, refund, and cross-device
  entitlement sync before any public rollout.

## Current official requirements checked

- Google API 36 deadline: <https://support.google.com/googleplay/android-developer/answer/11926878>
- Google AI-generated content reporting: <https://support.google.com/googleplay/android-developer/answer/13985936>
- Google account deletion: <https://support.google.com/googleplay/android-developer/answer/13327111>
- Google Data Safety: <https://support.google.com/googleplay/android-developer/answer/10787469>
- Google listing assets: <https://support.google.com/googleplay/android-developer/answer/9866151>
- Google reviewer access: <https://support.google.com/googleplay/android-developer/answer/10788890>
- Apple App Review Guidelines: <https://developer.apple.com/app-store/review/guidelines/>
- Apple privacy responses: <https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy/>
- Apple privacy manifests: <https://developer.apple.com/documentation/bundleresources/privacy-manifest-files>
- Apple version metadata and reviewer access: <https://developer.apple.com/help/app-store-connect/reference/app-information/platform-version-information/>
- Apple screenshots: <https://developer.apple.com/help/app-store-connect/manage-app-information/upload-app-previews-and-screenshots/>
- Apple build uploads: <https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds>
- GitHub-hosted macOS runners: <https://docs.github.com/en/actions/how-tos/manage-runners/github-hosted-runners/use-github-hosted-runners>

Recheck these sources on the actual submission day. Store approval is never guaranteed.

## Submission gate

Do not click a final store submission button until Greg has reviewed the signed-build evidence,
screenshots, privacy/data-safety answers, pricing/product mappings, reviewer instructions, rollout
plan, and unresolved warnings, then explicitly approves submission for that platform.
