# Ask Crump product analytics

Ask Crump records a deliberately small set of account-level milestones so activation,
durable value, retention, and subscription conversion can be measured without storing
conversation text or payment data.

## Data contract

`product_events` is server-only. Browser and native clients cannot read it. Each row may
contain only an allowlisted event name, an idempotency key, environment, platform, source,
plan, artifact category, and timestamp. It must never contain prompts, responses, filenames,
email addresses, customer details, card details, prices, or arbitrary metadata. Rows are
deleted when the owning account is deleted.

The `source` on account creation is privacy-minimized first-touch acquisition attribution.
It is limited to 32 lowercase letters, numbers, underscores, or hyphens. Ask Crump keeps no
referrer URL, campaign content, search term, or user identifier. Known social referrers are
reduced to their channel name and all other external referrers become `referral`.

Preview, production, and local-development events are separated at the server from the
request host. Replayed events are ignored by the database uniqueness constraint.

## Milestones

| Event | Authority | Meaning |
| --- | --- | --- |
| `AccountCreated` | Server | A new account row was created. |
| `OnboardingCompleted` | Server | The account supplied its initial display name. |
| `WorkspaceOpened` | Authenticated client | The workspace opened; at most one row per UTC day. |
| `StarterIntentReached` | Authenticated client | The account selected its first task category from the launchpad. Only one allowlisted category such as `research`, `file`, or `projects` is stored in `source`; no prompt or content is stored. |
| `ActivationReached` | Server | The first successful, persisted AI response completed. |
| `AhaReached` | Server | The first durable artifact, generated image, manuscript workspace, or ownership-checked conversation-to-Project transition completed. Project analytics retain only the `project` category—not the Project ID, name, chat ID, title, or content. |
| `OutcomeFeedbackSubmitted` | Authenticated client | The user answered whether one result moved the work forward. Only `useful` or `needs_work` is stored in `source`; no prompt, response, filename, comment, or other content is accepted. |
| `RecentWorkResumed` | Authenticated client | The user opened the most recent non-empty conversation from the clean-start launchpad. The server derives the UTC-day key and records at most one content-free milestone per account per day with source `launchpad`; no chat ID, title, prompt, response, or filename is sent. |
| `PlanIntentReached` | Authenticated client | A paid-plan marketing intent reached the in-app plan review. |
| `ResponseShared` | Authenticated client | A user completed native sharing or copied branded share text from a response, including the optional content-free referral offered after a useful outcome. The source is restricted to the four delivery paths (`native_share`, `clipboard`, `useful_prompt_native`, or `useful_prompt_clipboard`). Every shared signup link carries only the aggregate `referral` channel and `response-share` placement—never a user, conversation, message, or content identifier. |
| `ArtifactRequested` | Server | An entitled document or presentation request reached generation. Only the artifact category and server-derived environment, platform, and plan are retained. |
| `ArtifactPackaged` | Server | The requested downloadable file was stored successfully. |
| `ArtifactPackagingFailed` | Server | File packaging failed after the response was written. No exception or error text is retained. |
| `ArtifactDownloaded` | Server | The first authenticated download redirect was prepared for a generated document or manuscript export. Inline opens and ordinary uploads are excluded. |
| `SubscriptionCheckoutOpened` | Server | Stripe created a subscription Checkout Session. |
| `SubscriptionCheckoutCompleted` | Stripe webhook | Stripe verified a completed subscription Checkout Session. |
| `BillingPortalOpened` | Server | Stripe created a customer portal session. |
| `SubscriptionStatusChanged` | Stripe webhook | Stripe changed or deleted a subscription. |

## Operating queries

All operating queries must filter `environment = 'production'`. The primary weekly view is
the number of distinct accounts reaching each funnel milestone. Retention is calculated from
the first `AccountCreated` or `ActivationReached` event to daily `WorkspaceOpened` events at
D1, D7, and D30. Preview rows are kept out of business reporting.

No acquisition spend should increase until production data can distinguish: account created,
workspace opened, starter intent reached, activated, durable value reached, paid intent reached,
checkout opened, and checkout completed.
The first comparable cohort begins only after the complete 5.8.2+ event sequence is observable in
production traffic. Historical account behavior is not silently reconstructed from conversation or
file content. Account/job/file/Project aggregates may be used to diagnose historical product use,
but they must be labeled separately from event-based cohort rates and never converted into synthetic
events.

## Service-role growth snapshot

Migration `20260824234612_recent_work_resumed.sql` installs the current version of
`product_growth_funnel_snapshot`, a service-role-only aggregate report for a half-open
account-creation window. It returns ordered counts, eligible populations, and conversion
rates for:

- accounts created and matching `AccountCreated` event coverage;
- current verification and onboarding;
- workspace use, first launchpad intent, activation, durable value, and recent-work continuation;
- explicit useful-result and needs-work feedback among activated accounts;
- response sharing, plan intent, Checkout open/completion, and current paid status;
- D1 and D7 workspace return among accounts whose full UTC observation window has elapsed.

Internal accounts are excluded by default. Retention is anchored on the first activation
when one exists and otherwise on account creation. `verified_now` and `active_paid_now` are
explicitly current-state metrics rather than historical claims.

Call this function only from a trusted service-role operating session. It is not available
to `public`, `anon`, or `authenticated`, and it returns no account identifier, email,
prompt, response, filename, or arbitrary metadata. The migration also adds narrow cohort
and event-journey indexes so weekly reporting remains bounded as the account base grows.

```sql
select *
from public.product_growth_funnel_snapshot(
  p_since => timestamptz '2026-08-23 00:00:00+00',
  p_until => now(),
  p_environment => 'production',
  p_include_internal => false
);
```

## Service-role artifact journey snapshot

Migration `20260827050550_artifact_journey.sql` installs
`product_artifact_journey_snapshot`, a service-role-only aggregate report for a half-open
event window. It returns requested, packaged, packaging-failed, and first-download counts by
allowlisted artifact category, plus request-to-package and package-to-download rates. It never
returns an account, message, file, prompt, response, URL, filename, or exception value.

```sql
select *
from public.product_artifact_journey_snapshot(
  p_since => timestamptz '2026-08-27 00:00:00+00',
  p_until => now(),
  p_environment => 'production'
);
```
