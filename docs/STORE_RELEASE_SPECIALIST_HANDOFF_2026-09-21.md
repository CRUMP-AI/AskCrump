# Ask Crump store-release specialist handoff — 2026-09-21

## Purpose and authority

This document defines the only approved scope for an outside release specialist helping Ask Crump
reach Apple App Store and Google Play internal testing and review readiness. It is a technical
handoff, not permission to merge, deploy, migrate a database, spend money, change pricing, create a
publisher account, accept store agreements, submit an App Store app version, or submit a Google
Play production release. The work order may authorize only the named internal-test rollout.

The owner remains Gregory D. Crump Jr. The company must create and retain every publisher account,
app record, bundle/package identifier, signing identity, upload key, store product, listing, and
submitted artifact. The specialist is a temporary release operator, not the publisher, account
owner, product architect, or infrastructure administrator.

The predecessor hosted-green baseline was commit `1a7d23b` on draft
[PR #37](https://github.com/CRUMP-AI/AskCrump/pull/37). It predates this handoff and the version-three
packet gate, so it is not the contractor release commit and its run receipts cannot satisfy the new
packet. Before any access is granted, the owner must record one exact later approved release commit
in the work order and confirm that its required checks are green. The specialist must stop if the
checked-out commit differs, the PR is no longer the approved source, or a requested fix would change
product, privacy, billing, entitlement, backend, or database behavior.

## Predecessor evidence — context only

- Clean-checkout Python and JavaScript CI passed on `1a7d23b`:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35566340678>.
- The disposable PostgreSQL 17 race/security workflow passed on `1a7d23b`, including staged-SQL
  compilation, preflight rollback, grants/RLS, trigger gates, replay safety, both user-row lock
  orderings, acceptance/deletion races, and reconciliation leases:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35566340631>.
- Android structural verification passed on `1a7d23b`. It produced an **unsigned**, non-release-ready
  AAB of 45,194,502 bytes with SHA-256
  `ad96fbe579d218a7b1e80bbb071e4477663c55f0059e6cc5ae9c7ebe5ed68d8b`:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35566340621>.
- iOS structural verification passed on `1a7d23b` with Xcode 26.3, but used the former invalid
  single-component Apple build value `50976`. It remains compile/privacy evidence only and must be
  replaced by a run using a valid `CFBundleVersion`; it did not create a release-ready IPA:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35566340555>.
- The local browser-control matrix passed 52/52, including conversational DOCX/PDF/PPTX delivery,
  Files behavior, Projects, Video, image stability, Precision Edit, mobile navigation, and returning
  PWA behavior.

These results prove source and unsigned structural readiness only. They do not prove store signing,
physical-device behavior, purchases, push delivery, production migration compatibility, reviewer
access, or submission acceptance.

The final work order must use new run references whose head SHA matches its exact approved commit.
None of the predecessor run IDs below may be copied into a version-three final packet for a later
commit.

The final evidence format is the fail-closed version-three packet documented in
`docs/STORE_SUBMISSION_PACKET_GATE_2026-09-10.md`. It binds one clean source commit, three matching
CI receipt references, an explicit build number, artifact and screenshot hashes, the supplied public
signing-certificate fingerprint, a real internal-testing/TestFlight console record, operator and
work-order identity, and hashed access-closeout evidence. CI receipts are validated offline rather
than queried live. Certificate binding identifies the supplied public certificate; it does not by
itself extract or prove the binary signer.

## Allowed work

The specialist may work only against the owner-recorded release commit and may:

1. Generate reviewed Android and iOS native projects from the repository's existing scripts.
2. Configure owner-supplied, company-controlled signing through a revocable path.
3. Produce a signed AAB and IPA/archive without changing application behavior.
4. Install the exact artifacts through Play internal testing and TestFlight.
5. Execute the physical-device matrix in `docs/STORE_RELEASE_CHECKLIST.md` and
   `docs/STORE_LAUNCH_RUNBOOK.md` on current iPhone, iPad, and Android devices.
6. Capture screenshots from those exact signed artifacts and prepare offline draft listing and
   declaration fields using the repository's reviewed metadata and privacy documents. Console entry
   of privacy or policy declarations requires a separately recorded temporary permission and owner
   review; external TestFlight App Review is not part of the default scope.
7. Record defects, store warnings, and reviewer questions for repository review.
8. Run the non-publishing final packet verifier and deliver its evidence package to the owner.

The specialist may not directly fix a product, backend, database, privacy, billing, entitlement,
or security issue. Such findings return to PR review. The specialist may not substitute another
commit, suppress a failing gate, weaken a declaration, or patch production to make review pass.

## Access boundary

- Apple: begin with app-limited Developer access for build upload and internal TestFlight. Add
  app-limited Marketing only for ordinary listing metadata/screenshots. Add App Manager only if the
  work order explicitly requires App Privacy, export-compliance, or external-TestFlight work, then
  revoke it before the owner's final action. App Manager can submit an app and has limited user-
  invitation capability, so owner-only submission is a procedural control while that role is live.
- Apple app access must exclude **Access to Reports** and **Certificates, Identifiers & Profiles**;
  either entitlement defeats app limitation. Disable **Generate Individual API Keys** unless an
  exact work-order step requires it. The owner supplies company-controlled signing material.
- Google Play: grant permissions under **App permissions** for Ask Crump only. Start with **View app
  information (read only)** and **Release apps to testing tracks**. Add **Manage testing tracks and
  edit tester lists** only when needed. Add **Manage store presence** only for a recorded listing
  milestone, recognizing that it also reaches pricing, in-app products, distribution, ratings,
  promotions, and experiments. Add **Manage policy declarations** only for explicitly authorized
  console entry of Data Safety, app-access, ads, target-audience, or similar declarations.
- Record the invite date, permission set, intended expiry date, operator identity, and work-order ID
  before granting access. The owner independently records revocation or non-use in the final packet.
- Never grant Account Holder, **Admin (all permissions)** at any account or app scope, Google Play
  production-release/Play-App-Signing permission, Finance, orders/subscriptions, payments-profile,
  tax, banking, account-wide access, or unrestricted API-key access. Do not separately grant user-
  management access; if temporary Apple App Manager is unavoidable, record and monitor its inherent
  limited invite capability.
- Never share the founder's Apple or Google password, two-factor or recovery material, password
  manager, Supabase/Vercel/Stripe credentials, production database access, RevenueCat secret key,
  Play service-account key, APNs private key, or raw signing passwords in chat or Fiverr messages.
- Keep Android upload keys and Apple signing/provisioning material company-controlled. If a
  revocable temporary signing path is unavoidable, revoke or rotate it after acceptance.
- Remove the specialist's access after the final handoff or immediately after a stop condition.
- The owner alone accepts Apple/Google legal terms, configures or changes Play App Signing and key
  choices, selects **Submit for Review** in App Store Connect, sends a production Play change for
  review, starts either production rollout, turns managed publishing on or off, or releases a
  managed-publishing change.

Current role boundaries were checked against Apple's official guidance for
[app access](https://developer.apple.com/help/app-store-connect/manage-your-team/edit-access-to-apps),
[users and roles](https://developer.apple.com/help/app-store-connect/manage-your-team/add-and-edit-users),
[individual API keys](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api),
[build upload](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds),
[internal TestFlight](https://developer.apple.com/help/app-store-connect/test-a-beta-version/add-internal-testers),
and [submission](https://developer.apple.com/help/app-store-connect/manage-submissions-to-app-review/submit-an-app),
plus Google's official
[permission definitions](https://support.google.com/googleplay/android-developer/answer/9844686?hl=en),
[Play App Signing](https://support.google.com/googleplay/android-developer/answer/9842756?hl=en), and
[publishing workflow](https://support.google.com/googleplay/android-developer/answer/9859654?hl=en).

## Evidence-paid milestones

### Milestone 0 — reproducible checkout

- Exact owner-approved commit, version, and build number recorded.
- Operator identity, work-order ID, access scope, and access-expiry date recorded.
- Clean source checkout; no uncommitted product or configuration changes.
- Existing source, privacy, credential, metadata, and native gates pass.
- Missing owner inputs reported without placeholders being treated as complete.

### Milestone 1 — Android internal candidate

- Signed AAB SHA-256, byte size, application ID, version name, and version code recorded.
- Exact AAB accepted by Play internal testing and passes the 16 KB page-size gate.
- Current physical Android journey, notification, purchase/restore, offline/reconnect, deletion,
  AI-sharing consent/withdrawal, accessibility, and file/media tests recorded.
- Play pre-launch findings and draft Data Safety/app-access/content-rating answers delivered.

### Milestone 2 — iOS TestFlight candidate

- Signed archive/IPA SHA-256, byte size, bundle ID, marketing version, and build number recorded.
- Exact build accepted by TestFlight and privacy-manifest validation captured.
- Current physical iPhone and iPad journeys, push states, purchase/restore, deletion, AI-sharing
  consent/withdrawal, accessibility, and file/media tests recorded.
- Draft App Privacy, review notes, encryption/export, and reviewer instructions delivered.

### Milestone 3 — submission-ready packet

- Final screenshots are captured from the exact signed artifacts and meet the repository gate.
- Store products and RevenueCat mappings are reconciled without exposing secret keys.
- Reviewer account and contact data exist only in ignored, owner-controlled files.
- `npm run store:verify:submission` passes for each platform against the exact artifact, public
  certificate, ignored reviewer file, ignored access-closeout file, console record, and evidence.
- Deliverable includes artifact hashes, build/version numbers, console status, physical-device
  matrix, declarations, screenshots, reviewer notes, unresolved risks, and reviewer correspondence.
- Owner reviews the complete packet and gives a separate platform-specific action-time approval
  before any submission.
- External TestFlight App Review, App Store submission/release, Play production review/rollout, and
  managed-publishing release remain outside the specialist's default authority.
- From the owner account, the owner independently opens every CI and console reference, installs the
  exact hashed test builds, compares the signing identity with platform tooling, and confirms access
  removal. A specialist-authored JSON file, screenshot, PDF, or terminal transcript is not sufficient
  on its own.

Payment should follow accepted evidence milestones, not hours claimed, screenshots of a build
window, or an unsigned binary.

## Mandatory stop conditions

Stop and return the finding to the owner if any of the following occurs:

- the approved commit or artifact hash changes;
- a check, physical-device path, purchase/restore, push, deletion, consent, accessibility, or final
  packet gate fails;
- the requested work needs a production deploy, database migration, provider-secret change,
  product/catalog/price change, privacy-policy change, or new SDK;
- the store requests a different data-use statement than the application actually supports;
- native billing, account deletion, or a delayed/second-device flow can recreate or retain a
  provider identity after deletion;
- an owned PDF/file cannot be opened and downloaded reliably from the signed build;
- the console requests broader permissions, financial access, credentials, or agreement acceptance;
- a CAPTCHA, legal agreement, payment, or final submission step is reached without the owner's
  direct participation and required approval.

## Known holds that a specialist cannot waive

- The staged application SQL is not a production migration. A fresh remote migration-ledger review,
  numbered migration, migration-first rollout plan, and post-migration security review are separate
  engineering/owner gates.
- Native billing still requires owner-controlled RevenueCat public keys, exact store products,
  server credentials, and signed two-device tests covering delayed resume, account switching,
  deletion during SDK setup, and in-flight purchase/restore. Source rechecks are not an atomic
  guarantee around a third-party SDK call.
- The PDF Files viewer has source policy coverage, but a legitimate authenticated owned-file test
  of real signed-storage redirects, small/large PDF opening, and download remains required.
- The Android and iOS workflow artifacts cited above are unsigned structural proof. Missing
  RevenueCat public keys were intentionally allowed by those workflows.

## Final handback

The handback is complete only when the owner possesses every source reference, signed artifact,
hash, store record, screenshot, declaration, test result, reviewer exchange, signing/upload-key
backup, and recovery path; all contractor access is removed; access closeout is independently
recorded and hashed; and no credential or signing material is retained by the specialist. Store approval is never guaranteed, and neither platform may be
described as launched until its owner-controlled console shows the approved production release.
