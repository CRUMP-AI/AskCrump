# Ask Crump first comparable account observation — 2026-09-13

Observation time: 17:56 UTC

Scope: the first external production account created after the comparable
measurement boundary, plus aggregate production-runtime health

Privacy boundary: content-free aggregate counts only. No account identifier,
email, prompt, response, filename, Project name, URL, or customer content was
read or retained in this review.

## Decision

Preserve the current product. A legitimate comparable account has now moved
through account creation, verification, workspace entry, starter intent, and a
successful AI response. The account is only about 2.3 hours old, so the absence
of a Project, file, explicit result rating, or return is an observation—not a
failure and not an eligible retention denominator.

The next decision point is the account's 24-hour value window. Product work
should respond only if the content-free journey identifies a real break or if a
reproducible tester report establishes one. Do not redesign onboarding, Project
continuity, or pricing from this single immature account.

## Account and first-session evidence

| Measure | Result |
| --- | ---: |
| Comparable September production accounts | 1 |
| Account-created event recorded | 1 |
| Verified now | 1 |
| Workspace opened | 1 |
| Starter intent reached | 1 |
| Activation reached | 1 |
| Completed chat jobs | 3 |
| Failed chat jobs | 0 |
| Project-save intent / completion | 0 / 0 |
| Active Projects / files | 0 / 0 |
| Artifact journeys | 0 |
| Media jobs | 0 |
| Explicit useful / needs-work rating | 0 / 0 |
| Plan center viewed / Checkout opened | 1 / 0 |
| D1 eligible / returned | 0 / 0 |
| D7 eligible / returned | 0 / 0 |
| Active paid | 0 |

The immutable first-touch acquisition value is `clevercrump`; placement,
campaign, creative, and intent are empty. The content-free event sequence is
AccountCreated, WorkspaceOpened, StarterIntentReached, ActivationReached, and
PlanCenterViewed. The starter-intent category is the allowlisted `focus` value.

Across all current external accounts, the aggregate is now four accounts,
three verified accounts, three accounts with completed AI jobs, 17 completed
chat jobs, zero failed chat jobs, zero Projects, zero files, and zero active
paid accounts. Three of four profiles contain a completed display name.

## Runtime health

The trailing six-hour Vercel production view contained 476 HTTP 200 responses,
five HTTP 302 responses, one HTTP 303 response, and two HTTP 503 responses.
Both 503s were hourly check-in scheduler calls whose database read exhausted
four attempts after upstream HTTP 504 responses. The same scheduler returned
HTTP 200 at 16:00 and 17:00 UTC; the 14:00 run also recovered after its first
database retry. A separate 08:00 manuscript scheduler call had the same
transient database timeout pattern.

These scheduler failures deserve continued observation, but they are not
evidence of a dead interface control or failed customer generation. The grouped
runtime-error report contained no customer-facing route cluster, and the new
external cohort recorded three completed chat jobs with no failure.

## Next evidence gate

At or after the account's full 24-hour observation window:

1. refresh the privacy-safe attribution and growth exports;
2. distinguish no return from a failed return path;
3. inspect Project-save intent before Project-save completion;
4. preserve zero-denominator and small-sample labels; and
5. change the product only from a reproducible break or repeated cohort signal.

## Pre-eligibility follow-up — 18:51 UTC

The protected production reports were refreshed after the result-to-Project
handoff release. The same single `clevercrump` acquisition cohort remains
present through account event coverage, current verification, workspace open,
starter intent, and activation. It still has no Project-save intent or
completion, artifact journey, payer, or eligible 24-hour/D1/D7 denominator.
This is a still-maturing observation, not a second account or a diagnosed
drop-off.

The latest one-hour Vercel view contained 126 HTTP 200 responses and no 3xx,
4xx, or 5xx entry. The grouped runtime-error report was empty. No product
mutation is justified before the full 24-hour value window; the next protected
refresh should distinguish absent intent from attempted-save failure before any
further continuity change.

## Post-lifecycle-release checkpoint — 23:00 UTC

The protected reports were refreshed again after the idle lifecycle-action fix reached
production. The same single comparable account remains verified and activated with no Project-save
intent/completion, artifact, explicit outcome rating, Checkout, payer, or eligible retention
denominator. At the query boundary, approximately **59,948 seconds** remained before the account's
first complete 24-hour window—about **16 hours 39 minutes**, placing the next valid checkpoint at
approximately **2026-09-14 15:34 UTC**. This was an early operational estimate; the later
authoritative aggregate below supersedes it with the exact account-creation boundary.

All five in-product lifecycle controls remain enabled with a 20% account-stable holdout. No
lifecycle state or event exists for the comparable cohort yet. That is expected until a legitimate
post-release session requests a server decision; no prompt, event, or account state was synthesized
to manufacture evidence.

The production feature deployment and its evidence-only successor are both Ready. Their initial
windows contain no 4xx/5xx response or grouped runtime error. The trailing 24-hour error clusters
remain the already classified transient database timeouts and deferred Crump Code reconciliation
from an older deployment, not a new release regression.

Supabase's current advisor output contains only informational findings: RLS-enabled tables without
client policies and unused indexes. The former is the intentional service-role-only denial design;
the latter is expected at the current traffic volume and is not evidence that indexes should be
removed. No schema mutation is justified from either informational signal. References:
[RLS enabled without policy](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)
and [unused index](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index).

## First legitimate lifecycle delivery — 2026-09-14 00:04 UTC

The protected, content-free lifecycle export now contains one external production account in the
`continuity-assist` / `projects` prompt cohort. The account was eligible and the card was recorded
as shown. No acted, dismissed, target-completed-within-24-hours, D7-eligible, or D7-returned account
is present. One later `active-work` suppression and one `session-collision` suppression show that
the existing interruption and same-session controls remained active after delivery.

This is the first legitimate evidence that the idle-composer repair reaches a real account. It is
visibility evidence only: the user did not activate the card, and the account still has no elapsed
D7 denominator. No prompt, response, filename, account identifier, or customer content was read or
retained, and no event was created for this review.

The complete control boundary was replayed after this observation using the installed Edge browser.
All **47/47** functional verifiers passed, including Files/downloads, image stability, Precision Edit
live adjustments and apply flow, Projects, login recovery, mobile navigation, plan actions, Video
references, lifecycle actions, and sync recovery. The phone/tablet/desktop accessibility matrix
passed **33/33**, and the focused button-ownership, lifecycle, and sync contracts passed **54/54**.

## Pre-D1 protected refresh — 2026-09-14 04:49 UTC

The same single comparable production account now has four completed chat jobs with zero failed
chat job. It opened the workspace twice, first during activation and again at 00:04 UTC, but the
second same-day visit is only an intra-day return: it occurred well before the complete D1 window
and must not be counted or described as D1 retention.

The current growth export remains one account through creation, event coverage, verification,
workspace entry, starter intent, and activation. It still contains no explicit useful/not-yet
outcome, durable value, recent-work resume milestone, response share, paid-plan intent, Checkout,
or active payer. The Project-continuity export contains zero save intents, zero completions, and
zero later resumes. The artifact report is empty; the account owns zero active Project, ready file,
Project-file link, or media job.

The separate Plan-center report records one ordinary Plan-center view and no subscription or credit
Checkout opening or completion. The lifecycle export remains one eligible and shown
`continuity-assist` prompt with no action, dismissal, or target completion, plus one `active-work`
and one `session-collision` suppression. These observations return only fixed aggregate categories;
no account identifier, prompt, response, Project, filename, URL, payment detail, or customer content
was read or retained.

This refresh adds legitimate use and intra-day return evidence without identifying a broken path or
creating a decision-grade denominator. Preserve the current activation, result-to-Project,
lifecycle, and Plan-center behavior until the full 24-hour value checkpoint. D1 uses a separate
completed-calendar-day denominator and must not be inferred from that 24-hour boundary.

## Authoritative value and D1 boundaries — 2026-09-14 14:54 UTC

A service-role aggregate returned one comparable production account, with no identifier or customer
content. Its exact account-creation time is **2026-09-13 15:37:52.831833 UTC**, so the 24-hour
activation/value observation becomes complete at **2026-09-14 15:37:52.831833 UTC**. Its first
activation was **2026-09-13 15:40:16.183512 UTC**.

The weekly decision-grade export defines D1 as a return on the next UTC calendar date and does not
call that denominator complete until the following UTC date begins. The first valid D1 denominator
therefore opens at **2026-09-15 00:00:00 UTC**, not at the 24-hour value boundary. Refresh the
24-hour value metrics after 15:37:52 UTC today, then refresh D1 separately after midnight. This
prevents an intraday return from being misreported as D1 retention and preserves the small-sample
boundary.

Commit `2414819` turns that completed-calendar-day rule into an exact regression boundary for both
the overall and weekly service-role reports: D1 eligibility cannot open before activation date plus
two UTC dates, and D7 eligibility cannot open before activation date plus eight UTC dates. The
focused retention suite passed **24/24**, GitHub CI `34860184460` passed, production deployment
`dpl_Gac7fvRQHgyHham3EiJZXdZ9qkQc` reached Ready, all four canonical health checks returned 200, and
the initial release window contained only HTTP 200 responses with no grouped runtime error. This is
a measurement-integrity release; it does not turn the still-open value or D1 window into observed
retention evidence.

## First complete 24-hour value window — 2026-09-14 15:38 UTC

The protected weekly export now contains one activation-eligible account and one account that
reached activation within 24 hours. The same account is also the first durable-value-eligible
account, but it recorded no durable value within 24 hours. Its content-free value components are all
zero: useful feedback, Project creation, Project-file attachment, ready file, and decision-grade
value. D1 and D7 eligibility remain zero because their completed-calendar-day windows have not
opened.

The supporting aggregate still shows four completed chat jobs with no failed chat job, two workspace
opens, no media job, no active Project, no ready file, and no Project-file link. Project continuity
contains no save intent, save completion, or resume. The artifact journey remains empty. The Plan
center was viewed once with no subscription or credit Checkout opening. The one eligible and shown
`continuity-assist` card still has no action, dismissal, or target completion.

This is the first valid indication that technical activation did not become durable work, not proof
of a broken save path: there was no attempted save to fail. The result-to-Project action and
lifecycle prompt also reached production after the account's initial session, so this single account
cannot measure their effect. Preserve the current controls, recruit the remaining consented
observations, and inspect the next legitimate intent → completion journey before changing the
interface. Do not present one eligible account as a conversion rate or retention claim.
