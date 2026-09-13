# App Store and Google Play submission packet gate

Date: 2026-09-10
Updated: 2026-09-13

## Outcome

Ask Crump now has one fail-closed final-packet verifier for the owner-controlled step after a
signed iOS or Android candidate has completed real device and store-console validation. The gate
does not sign, upload, or submit an app. It prevents a partial packet from being described as ready.

The verifier requires all of the following to agree:

- package version and deterministic build number;
- the exact nonempty signed `.ipa` or `.aab` filename and SHA-256;
- a fresh evidence record no older than fourteen days;
- the complete hashed screenshot directory, with one to ten current-size 6.9-inch iPhone
  screenshots and one to ten current-size 13-inch iPad screenshots, or four to eight 9:16/16:9
  Google phone screenshots at recommendation-grade resolution;
- non-placeholder reviewer credentials, read from an untracked file and never printed;
- every common physical-device control: core journey, purchase/restore, session persistence,
  deletion, AI reporting, accessibility, offline/reconnect, privacy forms, reviewer path, and
  store-console screenshot acceptance; and
- every platform-specific signing, product/RevenueCat, push/notification, privacy/pre-launch,
  and console-declaration control.

The version-two evidence schema rejects unknown fields and unknown checks. Artifact and screenshot
hashes and dimensions are calculated from the files at verification time. JPEG structure is
inspected; PNG files must be 24-bit RGB with no alpha or transparency. Android screenshot count,
aspect ratio, dimensions, and file size are enforced. Because the compiled iOS candidate explicitly
targets both device families, iOS input must contain exact `iphone/` and `ipad/` directories, and
each image must match a current accepted 6.9-inch iPhone or 13-inch iPad size. This is a completeness
and identity gate; the operator must still perform the actual
signed-device and console work represented by each fixed boolean.

## Usage after owner-controlled validation

Copy the platform template to the ignored `store/submission-evidence.json`, replace each placeholder,
and keep all booleans false until that exact signed build has passed the named check. Store reviewer
credentials only in ignored `store/reviewer-access.json`.

```powershell
npm run store:verify:submission -- --platform android --artifact C:\secure\ask-crump.aab --screenshots C:\secure\screenshots\android --evidence store\submission-evidence.json --reviewer-access store\reviewer-access.json
```

For iOS, run the same command on the macOS release host with `--platform ios`, the signed `.ipa`,
and a screenshot root containing the required `iphone/` and `ipad/` subdirectories. The iOS evidence
template separately requires the physical iPad layout/core journey to be verified.

Templates:

- `store/submission-evidence.android.example.json`
- `store/submission-evidence.ios.example.json`

## Verification boundary

The pure fail-closed matrix covers valid evidence plus wrong platform/build/hash, stale evidence,
missing screenshots, wrong dimensions/device labels, alpha/transparency, incomplete Apple device
sets, schema drift, incomplete/unknown checks, placeholder credentials, and a short reviewer secret.
Repository tests additionally require the complete common and platform-specific control list,
non-publishing implementation, workflow change coverage, and deliberately false templates.

No developer account, signing credential, reviewer password, app record, store product, screenshot,
signed artifact, upload, submission, purchase, customer data, or spend was created or changed by
this release.
