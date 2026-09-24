# App Store and Google Play submission packet gate

Date: 2026-09-10
Updated: 2026-09-21

## Outcome

Ask Crump now has one fail-closed structural packet linter for the owner-controlled step after an
iOS or Android candidate has completed device and store-console validation. The gate does not sign,
upload, submit, authenticate external receipts, or prove an artifact's embedded signer. It prevents
an obviously partial or internally inconsistent packet from advancing to independent owner review;
passing it is necessary but not sufficient for release readiness.

The verifier requires all of the following to agree:

- a clean checkout, the exact Ask Crump repository, and the full approved source commit;
- package version and an explicit platform-valid build identity;
- offline references to successful CI, platform-native, and PostgreSQL race/security runs, all bound
  to that same source commit;
- the named nonempty `.ipa` or `.aab` candidate filename and SHA-256;
- the SHA-256 fingerprint and declared role of a supplied public X.509 signing certificate;
- an operator-declared Play internal-testing or TestFlight app record, build identity, status, and
  canonical private-console reference for independent owner inspection;
- the release operator and work-order identity;
- a hashed operator-supplied access-closeout record declaring that temporary console, repository,
  and signing access was removed, rotated, or never used, with a distinct owner confirmer identity;
- a fresh evidence record no older than fourteen days;
- the complete hashed screenshot directory, with one to ten current-size 6.9-inch iPhone
  screenshots and one to ten current-size 13-inch iPad screenshots, or four to eight 9:16/16:9
  Google phone screenshots at recommendation-grade resolution;
- non-placeholder reviewer credentials, read from an untracked file and never printed;
- iOS App Review contact first name, last name, email, and international-format phone from that same ignored file;
- source-verified Apple/Google metadata plus the versioned Play listing icon and feature graphic;
- every common physical-device control: core journey, purchase/restore, session persistence,
  deletion, AI reporting, accessibility, offline/reconnect, privacy forms, reviewer path, and
  store-console screenshot acceptance; and
- every platform-specific signing, product/RevenueCat, push/notification, privacy/pre-launch,
  and console-declaration control.

The version-three evidence schema rejects version-two packets, unknown fields, and unknown checks.
CI receipts are exact offline references; the gate validates their structure and source binding but
does not query GitHub. The certificate fingerprint binds the packet to the supplied public
certificate; it does not independently extract or prove the signer of the binary. Artifact and
screenshot hashes and dimensions are calculated from the files at verification time. Screenshots
must be checksum-valid, decompressible 24-bit RGB PNG files with complete pixel data and no alpha
or transparency. Unverified JPEG input is rejected. Android screenshot count,
aspect ratio, dimensions, and file size are enforced. Because the compiled iOS candidate explicitly
targets both device families, iOS input must contain exact `iphone/` and `ipad/` directories, and
each image must match a current accepted 6.9-inch iPhone or 13-inch iPad size. This is a completeness
and identity gate; the operator must still perform the actual signed-device and console work
represented by each fixed boolean.

The packet is not a trustless substitute for owner review. CI URLs, private console status, access
closure, and boolean checks are operator-supplied evidence, not authenticated live API responses.
Before approval, the owner must independently open the referenced runs and store records from the
owner account, install the exact hashed artifacts through the named test channels, compare signing
identity with platform tooling, and personally confirm that temporary access is absent or revoked.
Contractor screenshots or command output alone are not acceptance evidence.

## Usage after owner-controlled validation

Copy the platform template to the ignored `store/submission-evidence.json`, replace each placeholder,
and keep all booleans false until that exact signed build has passed the named check. Version-two
packets have no compatibility path and must be recreated from a current template. Store reviewer
credentials only in ignored `store/reviewer-access.json`. Store access-removal evidence in an
ignored `store/access-closeout-evidence.*` file. Supply only the public signing certificate to the
verifier; never place a private key or signing password in the repository.

```powershell
npm run store:verify:submission -- --platform android --artifact C:\secure\ask-crump.aab --screenshots C:\secure\screenshots\android --evidence store\submission-evidence.json --reviewer-access store\reviewer-access.json --signing-certificate C:\secure\play-upload-public.pem --access-evidence store\access-closeout-evidence.pdf --build-number 50977
```

For iOS, run the same command on the macOS release host with `--platform ios`, the signed `.ipa`,
an Apple-compatible one-to-three-part `--build-number` such as `5.9.76`, and a screenshot root
containing the required `iphone/` and `ipad/` subdirectories. Android build numbers are integers
from 1 through 2,100,000,000. The iOS evidence template separately requires the physical iPad
layout/core journey to be verified.

Build constraints follow Apple's
[`CFBundleVersion` specification](https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundleversion)
and Android's official
[`versionCode` guidance](https://developer.android.com/studio/publish/versioning).

Templates:

- `store/submission-evidence.android.example.json`
- `store/submission-evidence.ios.example.json`

## Verification boundary

The pure fail-closed structural matrix covers valid owner, specialist, and dual-device iOS evidence plus wrong
platform/build/hash, retired schema, source and CI drift, failed or duplicate receipts, signing and
console mismatch, incomplete access closure, stale evidence, missing screenshots, wrong
dimensions/device labels, alpha/transparency, incomplete Apple device sets, incomplete/unknown
checks, placeholder credentials, and a short reviewer secret.
Repository tests additionally require the complete common and platform-specific control list,
non-publishing implementation, workflow change coverage, and deliberately false templates.

No developer account, signing credential, reviewer password, app record, store product, screenshot,
signed artifact, upload, submission, purchase, customer data, or spend was created or changed by
this release.
