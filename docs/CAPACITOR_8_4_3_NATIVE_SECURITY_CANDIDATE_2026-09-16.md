# Capacitor 8.4.3 native security candidate — 2026-09-16

State: **SOURCE CANDIDATE / NOT DEPLOYED OR SUBMITTED**

## Decision

Advance Ask Crump's four aligned Capacitor framework packages from 8.4.2 to 8.4.3. The official
8.4.3 release is a narrow patch that blocks navigation to Capacitor's internal HTTP proxy path,
including subframes. Package and lockfile versions remain exact and aligned.

The newer 8.5.2 line was evaluated first and rejected. Its CLI adds the `xcode` dependency, which
resolved `uuid` 7.0.3 and caused the repository audit to report three moderate findings, including
GHSA-w5hq-g745-h8pq. Ask Crump does not trade a native patch upgrade for a known supply-chain
regression. Capacitor 8.4.3 retains the security-relevant proxy-path fix with a zero-finding audit.

Official release evidence:

- https://github.com/ionic-team/capacitor/releases/tag/8.4.3
- https://github.com/advisories/GHSA-w5hq-g745-h8pq

## Exact source change

- `@capacitor/core`: 8.4.2 → 8.4.3
- `@capacitor/android`: 8.4.2 → 8.4.3
- `@capacitor/cli`: 8.4.2 → 8.4.3
- `@capacitor/ios`: 8.4.2 → 8.4.3
- `package-lock.json`: regenerated from the reviewed package manifest with exact parity

No application JavaScript, Python, HTML, CSS, native configuration, entitlement, price, database
object, environment variable, public page, customer data, or production deployment changed.

## Local verification

- npm lockfile audit: 0 information, low, moderate, high, or critical vulnerabilities across 134
  dependencies
- complete Python suite: 1,135/1,135 passed
- native/store-focused Python suite: 70/70 passed
- JavaScript validation: 54/54 files passed, including every attribution and store-packet case
- browser control matrix: 48/48 passed in real Edge
- public accessibility matrix: 33/33 passed
- production preflight and native web build: passed
- client credential boundary: passed
- store metadata and native privacy source checks: passed
- Capacitor Android add/sync with 8.4.3: passed; all nine configured native plugins resolved
- Android API 36 source configuration and native release-source verification: passed
- diff integrity and manifest/lockfile version parity: passed

The generated Android source remains intentionally untracked. The local workstation has Java 25,
while this release train requires the reviewed Java 21 toolchain, so unsigned Android compilation
is reserved for the existing hosted Java 21 gate. iOS compilation remains reserved for the hosted
macOS gate. Signing credentials, RevenueCat public keys, FCM/APNs configuration, physical-device
testing, screenshots, store declarations, signing, and submission remain separate owner-controlled
release gates.

## Release boundary

Do not describe Ask Crump as store-ready or available in either store from this candidate. Merge
only after the hosted CI, Android Java 21, and iOS macOS source-verification workflows pass. This
candidate requires no Vercel deployment because it changes only future native-build dependencies.
