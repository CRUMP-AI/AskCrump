# Ask Crump five-destination workspace release

Date: 2026-08-27

Release: 5.9.30 / native build 50930

Code commit: `86dfb2c8b43bf4d472898e0f159d577032cbc078`

Production deployment: `dpl_8q5SK1mLXcqcExhLBvH9wgHPeTbT`

## Outcome

Ask Crump now presents one consistent signed-in product hierarchy: **Ask, Projects, Create,
Library, and You**. Desktop uses a labeled rail and mobile uses the same five destinations in a
safe-area tab bar. The first slice reorganizes the existing product without migrating or replacing
accounts, conversations, Projects, files, generated artifacts, entitlements, APIs, or public links.

Create opens a non-generating outcome chooser for documents, editable PowerPoint, images,
manuscripts, and video. Each choice hands off to the existing tool and its existing cost,
entitlement, provider, storage, and send controls. Nothing in the new hub calls an API or spends
credits before the user reviews the setup and sends a request.

## Verification

- The local suite passed 303 backend and contract tests, Python lint/compile checks, 41 JavaScript
  validations, production preflight, native web-bundle generation, store-metadata checks, and
  mobile signing-source controls.
- Desktop review at 1440 by 960 and mobile review at 390 by 844 confirmed readable destinations,
  active state, safe-area clearance, composer clearance, Create-dialog fit, keyboard focus entry,
  close/escape behavior, and reduced-motion coverage.
- Hosted CI [33129397532](https://github.com/CRUMP-AI/AskCrump/actions/runs/33129397532), Android
  unsigned App Bundle verification [33129397531](https://github.com/CRUMP-AI/AskCrump/actions/runs/33129397531),
  and iOS unsigned Release compile [33129397539](https://github.com/CRUMP-AI/AskCrump/actions/runs/33129397539)
  all completed successfully. Neither native workflow had signing or upload credentials.
- Production health returned 5.9.30. The app, runtime loader, both navigation assets, and r64
  service worker returned 200. An authenticated live workspace rendered all five destinations;
  Projects opened the existing Project dialog, Create opened without generation, and the mobile
  composer remained above the tab bar.
- Deployment-scoped observation contained 23 successful 200 responses, no 5xx response, no
  warning/error/fatal log entry, and no runtime error cluster in the inspected release window.

## Safety and rollback

The production rollback candidate remains the previous verified deployment. A device-local
diagnostic rollback is also available by setting local storage key `askcrump.navigation.mode` to
`legacy` and reloading; removing the key restores the five-destination layer. Neither rollback
changes server data.

## Remaining product and store gates

This release verifies the information-architecture foundation, not improved activation or
retention. The comparable external cohort remains empty, so no growth outcome is claimed. Additional
task-flow refinement should be driven by legitimate post-instrumentation use and moderated sessions.
Final store screenshots remain blocked until exact signed Android and iOS candidates pass physical-
device, billing, restoration, push, accessibility, privacy, reviewer-access, and console gates and
receive owner approval.
