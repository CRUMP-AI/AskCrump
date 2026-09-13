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
approximately **2026-09-14 15:34 UTC**.

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
