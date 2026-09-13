# Ask Crump store screenshot and device-evidence gate release

Date: 2026-09-13
Version: 5.9.76 / build 50976
Feature commit: `f176d3888e5d6266e32d53157776df97f7079c8f`

## Outcome

Ask Crump's non-publishing store packet can no longer accept screenshots based only on file count,
extension, and hash. It now inspects the image structure, format, dimensions, device family, complete
directory, and evidence record before a signed candidate can be described as submission-ready.

The generated iOS candidate already compiled for both iPhone and iPad. That device boundary is now
explicit and fail-closed in native configuration and verification. The final iOS packet requires a
current 6.9-inch iPhone set, a current 13-inch iPad set, and a separately confirmed iPad layout/core
journey. Removing the iPad evidence is not allowed unless a later signed candidate intentionally
changes and verifies the native device family first.

Android is held to four through eight recommendation-grade phone screenshots: 9:16 or 16:9, at
least 1080 pixels on the short edge, no more than 3840 pixels on the long edge, and no more than
8 MB. Both stores accept only structurally recognized JPEG or 24-bit RGB PNG without alpha or
transparency through this local gate.

## Why this changed

The 2026-09-13 official-source recheck confirmed three current facts:

- Apple's current screenshot table requires a 13-inch screenshot set when an app runs on iPad,
  accepts one to ten screenshots per device set, and rejects alpha/transparency.
- Google's recommendation-eligible phone presentation uses four or more 1080-resolution 9:16 or
  16:9 screenshots; Play supports no more than eight screenshots for the phone device type.
- Google's new-app and update deadline still requires Android 16 / API level 36 from August 31,
  2026; Ask Crump's generated source already targets API 36.

The prior packet allowed one generic Apple screenshot and four through ten Android screenshots, and
did not validate dimensions or transparency. That was internally consistent but too weak for the
actual signed candidate and current store rules.

Official references:

- <https://developer.apple.com/help/app-store-connect/reference/app-information/screenshot-specifications>
- <https://developer.apple.com/help/app-store-connect/manage-app-information/upload-app-previews-and-screenshots/>
- <https://support.google.com/googleplay/android-developer/answer/9866151>
- <https://support.google.com/googleplay/android-developer/answer/11926878>

## Verification

- Store packet fail-closed self-test: 21/21 cases passed.
- Focused store/native tests: 37/37 passed.
- Complete Python suite: 1,049/1,049 passed.
- JavaScript validation: 54/54 passed.
- Production preflight, native web build, client-secret scan, store metadata, source privacy,
  signing-source, template JSON, and diff-integrity gates passed.
- Hosted Android API-36 unsigned App Bundle verification:
  [run 34790149297](https://github.com/CRUMP-AI/AskCrump/actions/runs/34790149297), passed.
- Hosted macOS unsigned iPhone+iPad Release compile and packaged privacy verification:
  [run 34790149321](https://github.com/CRUMP-AI/AskCrump/actions/runs/34790149321), passed.
- Hosted complete CI: [run 34790149269](https://github.com/CRUMP-AI/AskCrump/actions/runs/34790149269),
  passed.
- Production deployment `dpl_5cPdEWw9y1GijwdrdjSeUipzXEBy` is Ready. All four Ask Crump/Clever
  Crump health endpoints returned HTTP 200 at version 5.9.76. The initial thirty-minute runtime
  review found no grouped error and no 5xx response for the deployment.

## Preserved boundary

No screenshot, signed artifact, reviewer credential, developer-account record, product, price,
subscription, signing key, certificate, upload, submission, purchase, customer data, or spend was
created or changed. Store accounts, signed builds, physical-device evidence, screenshots, console
declarations, and explicit platform submission approval remain owner-controlled gates.
