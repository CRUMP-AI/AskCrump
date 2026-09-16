# Ask Crump operating checkpoint — 2026-09-16 16:05 UTC

State: **PRESERVE PRODUCTION / ACQUISITION READINESS IS THE NEXT LEVER**

## Protected aggregate evidence

A read-only service-role query refreshed the production-only, external-account operating
aggregates for the half-open window beginning `2026-09-01T00:00:00Z` and ending
`2026-09-16T16:05:38.502037Z`. The query returned only fixed aggregate fields; it read no account
identifier, email, prompt, response, filename, Project name, URL, or customer content and performed
no write.

| Evidence | Observed |
|---|---:|
| Comparable accounts created | 1 |
| AccountCreated event coverage | 1 / 1 |
| Verified now | 1 / 1 |
| Workspace opened | 1 / 1 |
| Starter intent reached | 1 / 1 |
| Activation reached | 1 / 1 |
| D1 eligible / returned | 1 / 1 |
| D7 eligible / returned | 0 / 0 |
| Useful outcome / needs-work outcome | 0 / 0 |
| Durable value reached | 0 / 1 eligible |
| Recent work resumed | 0 / 1 |
| Response shared | 0 / 1 |
| Project-save offers / intents / completions / later resumes | 0 / 0 / 0 / 0 |
| Artifact journey rows | 0 |
| Plan-center views | 1 |
| Subscription or credit Checkout opened / completed | 0 / 0 |
| Distinct payers / active paid | 0 / 0 |

The lifecycle aggregate still contains one eligible and shown `continuity-assist` account with no
action, dismissal, or 24-hour target completion. Its active-work and session-collision
suppressions remain intact. Navigation discovery has no active external workspace account inside
its post-`2026-09-14T20:57:00Z` measurement window. The sanitized-demo proof remains seven false
booleans because the protected identity is not configured.

## Runtime health

The production Vercel review found no grouped runtime error in the trailing 24 hours. The latest
six-hour status view contained 400 HTTP 200 responses and no grouped 3xx, 4xx, or 5xx request path.
There is no unresolved Vercel toolbar feedback for the project. This is reliability evidence only;
it does not prove acquisition, retained value, or revenue.

## Dependency health

A read-only dependency review completed on 2026-09-16 and was repeated against the released native
lockfile at exact production source commit `7833d89e2e5ee419fd27757f82c4fff92beed295`. The JavaScript lockfile audit reported zero known
information, low, moderate, high, or critical vulnerabilities across 134 production, development,
and optional dependencies. The Python requirements audit reported zero known vulnerabilities
across every declared requirement and resolved dependency. Both audits exited successfully, the
production worktree remained clean, and no dependency, lockfile, environment, deployment, or
database state changed.

## Native dependency release

Capacitor core, Android, CLI, and iOS advanced together from 8.4.2 to 8.4.3 at merge commit
`0e93620ad3bac0009661299237ba81a50cb60aa5`. This narrow patch blocks navigation to Capacitor's
internal HTTP proxy path, including subframes. The newer 8.5.2 line was tested and rejected because
its CLI introduced a moderate-vulnerability path through `xcode` and `uuid`; no override hid that
finding. Pull-request CI, hosted Java 21 Android, hosted macOS iOS, main Python/JavaScript/Android/
iOS/Dependabot gates, and deployment `dpl_Cd2FGrDeCRShtBN4KaR1TKkXeuF7` passed. All six aliases
are Ready; home, app, health, and company probes returned HTTP 200; and the initial Vercel runtime-
error review was empty. This is a source/runtime foundation release, not evidence of signing,
physical-device, billing, push, store review, or store availability.

## Control reliability revalidation

The released 5.9.76 workspace was revalidated after the native dependency release. The fail-closed
source inventory still covers 182 rendered and 94 programmatic button construction sites, for 276
reviewed controls. The complete credential-free browser matrix passed 48/48 and 93/93 focused
button, mobile, Files, Projects, image, Library, and Video tests passed. A signed-in production
smoke pass then exercised Chats and conversation options, Projects and Files, foreground image
preview, Create, Video, Library, You and every Settings section, and Intelligence. Each requested
surface opened in front of its owner, and the browser error/warning log was empty. Destructive,
payment, provider-generation, permission, and external-communication outcomes remained behind
their existing guarded test boundaries and were not executed against production.

## Candidate readiness

- `draft-to-clearer`: prepared from the prior production base `8545cea72a7b8f1af0072f635e19bc19d5d736a2`;
  functional commit `0a942111324517a84a41e509ddef2fda23dfc41d`; evidence HEAD
  `78bb2f4b503550c0342da7499ca07ed1bb06ea61`. Marketing independently accepted that frozen
  source/staged candidate. It now requires a refresh onto current production before any release;
  public release remains held.
- `resume-you-can-defend`: rebased onto exact current production base
  `7833d89e2e5ee419fd27757f82c4fff92beed295`; Feed registration commit `ee84101`; Instagram
  profile-link extension commit `4592aad`; evidence HEAD
  `0d201eb095efa201c0a20fd86267f30371367b64`. The exact added route is `instagram / profile-link /
  resume-you-can-defend / [no creative] / resume`; both existing Feed routes remain unchanged.
  Full Python passed 1,156/1,156, focused attribution/button coverage 80/80, JavaScript 54 files
  with 25/25 campaign cases, browser controls 49/49, and build, credential, lint, compile, diff, and
  dependency gates are green. Marketing independently accepted the exact source and hashes. The
  candidate is unpushed and unapplied; public release remains held.
- Ask Crump API `v0.134.0`: private hosted-tool scheduler candidate passed 343 hosted checks at
  commit `22c41595e35480ace484c49000ea127abff6bc83`. It changes no client schema or shared Product
  table. Stable API production remains `v0.49.1`; no Product integration, deployment, or parity
  claim is authorized from that receipt.

Neither campaign candidate is present on a remote branch. Neither migration has been applied.
No tagged production URL, account, analytics event, public guide, social object, advertisement,
purchase, or spend was created during candidate preparation or this checkpoint.

## Decision

Preserve production 5.9.76. The healthy runtime and funnel evidence do not support another onboarding, Project-continuity,
pricing, or navigation redesign: the only comparable account activated and returned on D1, while
the sample remains one account and no post-offer Project behavior or D7 denominator exists.

The next safe growth dependency is qualified acquisition readiness:

1. keep both independently accepted campaign releases isolated until their explicit publication
   gates reopen, with the rough-to-useful Facebook challenger remaining first in the external queue;
2. obtain legitimate new post-instrumentation accounts before interpreting activation, durable
   value, D7, checkout, or payer conversion; and
3. preserve the no-synthetic-events and aggregate-only privacy boundary.

Do not deploy either candidate, apply either migration, submit Search Console or store actions,
publish social content, or spend without the governing action-time authorization.
