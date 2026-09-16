# Capacitor 8.4.3 native security candidate — 2026-09-16

State: **RELEASED TO SOURCE / NOT SUBMITTED TO EITHER STORE**

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
was completed by the existing hosted Java 21 gate. iOS compilation completed in the hosted macOS
gate. Signing credentials, RevenueCat public keys, FCM/APNs configuration, physical-device testing,
screenshots, store declarations, signing, and submission remain separate owner-controlled release
gates.

## Hosted and production verification

- Pull request: `#36`, exact source commit `8abb032b1c1fa0029ffb04ecf4597b08fc350b01`
- Pull-request CI: `35122809253`, Python and JavaScript jobs passed
- Pre-merge Android Java 21 gate: `35123315753`, passed
- Pre-merge iOS macOS gate: `35123317953`, passed
- Main merge commit: `0e93620ad3bac0009661299237ba81a50cb60aa5`
- Main CI: `35123928372`, Python and JavaScript jobs passed
- Main Android Java 21 gate: `35123928343`, passed
- Main iOS macOS gate: `35123928415`, passed
- Dependabot check: `35124068408`, passed
- Vercel production deployment: `dpl_Cd2FGrDeCRShtBN4KaR1TKkXeuF7`, Ready on all six aliases
- Production probes: Ask Crump home, `/app`, `/api/health`, and Clever Crump home returned HTTP 200
- Post-release Vercel review: zero runtime-error groups; sampled production requests returned HTTP 200

The production deployment is an automatic consequence of the reviewed `main` merge; the shipped
web application bytes and behavior are unchanged by this native dependency-only release.

## Release boundary

Do not describe Ask Crump as store-ready or available in either store from this source release.
Unsigned compilation proves buildability, not signing, billing, push delivery, physical-device
behavior, store-console declarations, review acceptance, or availability.
