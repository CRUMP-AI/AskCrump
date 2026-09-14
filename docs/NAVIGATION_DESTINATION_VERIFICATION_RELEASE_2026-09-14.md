# Navigation destination verification release — 2026-09-14

## Outcome

Ask Crump's primary application destinations now share a verified browser path and a privacy-safe
production discovery signal. Ask, Chats, Projects, Create, Video, Library, You, Intelligence, and
Code record a fixed `NavigationDestinationSelected` event only after their visible open path runs.
Code records only after its gated workspace reports a successful open, and Chats records only when
the conversation library changes from closed to open.

The signal is deliberately named **selected**, not **opened** or **completed**. It measures a user's
destination choice and does not claim that an external AI provider, checkout, download, or native
permission completed. Those workflows retain their separate server-authoritative success events.

## Privacy and database contract

Remote migration `20260914210257_navigation_destination_selection` adds only one allowlisted event
name, an exact nine-value destination constraint, and a service-role-only aggregate. The server
replaces the client key with one fixed destination/day key, so duplicate taps do not create an
unbounded event stream. Plan, artifact, attribution, URL, Project, conversation, filename, prompt,
response, and arbitrary metadata fields are not accepted.

The aggregate `product_navigation_discovery_snapshot` always returns nine fixed destination rows.
Its denominator is distinct eligible accounts with a workspace-open or destination-selection event
inside the same half-open environment-scoped window. It excludes deleted and internal accounts by
default and returns counts/rates only—never account identifiers or customer content.

A rollback-only production database proof confirmed:

- the exact constraint is validated;
- a valid Projects event records and an invalid `settings` destination fails closed;
- anonymous and authenticated database roles cannot execute the aggregate;
- the service role can execute it;
- the aggregate returns exactly the nine allowlisted destinations; and
- the rollback left no synthetic event behind.

Post-migration Supabase advisors remained at the existing informational baseline: 61 intentionally
policy-free, RLS-enabled service tables and 58 unused-index notices. The migration introduced no new
advisor category or count.

## Verification

- Full backend and product suite: **1,103/1,103** passed across 120 test files.
- JavaScript integration and syntax contract: **54/54** files passed.
- Browser control matrix: **48/48** passed across authentication, navigation, Projects, files,
  image editing, video, billing recovery, lifecycle, update recovery, and public entry paths.
- The mobile Projects proof closed the drawer, opened the Projects section, emitted exactly one
  allowlisted selection, and logged no browser or page error.
- Public accessibility matrix: **33/33** phone, tablet, and desktop scenarios passed.
- Live public destination proof: 67 unique first-party anchors, 12 canonical sitemap pages, 69 HTTP
  200 destinations, and two exact native-compatibility redirects passed.
- Production preflight, native web-bundle generation, client-credential scan, and diff integrity
  passed.

## Production acceptance

Commit `05307adc586fdb1f907a8239d5aea80e754cc709` deployed as
`dpl_FvL71Rv1m3xfoGnvUog8ussMUJ2D`, reached Ready, attached all six Ask Crump/Clever Crump aliases,
and reported no alias error. The live application exposes cache generation `r246`, references the
`5.9.76-navigation-discovery-1` runtime, and serves the five changed runtime assets at HTTP 200.
The deployment's post-release error/fatal log scan was empty.

GitHub CI `34897417769`, Android source verification `34897418161`, and iOS source verification
`34897418109` all completed successfully. Native store submission remains separately gated by the
platform projects, signing, and RevenueCat public SDK keys; this release does not weaken those gates.

The first protected external-production read returned all nine rows with zero active accounts and
zero selections after the `2026-09-14 20:57:00+00` boundary. That is a clean measurement boundary,
not evidence that users ignored a destination.

## Boundaries

This release verifies the controls Ask Crump owns and adds a content-free discovery denominator. It
does not guarantee external provider availability, approve spending, change pricing, submit native
apps, publish marketing, inspect customer content, or turn a synthetic control pass into retention
evidence. The first valid D1 cohort read remains due after 2026-09-15 00:00 UTC.
