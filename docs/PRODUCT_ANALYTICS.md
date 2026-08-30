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
referrer URL, campaign content, search term, or user identifier. Known search-engine hosts are
reduced to `organic`, known social referrers to their channel name, and all other external
referrers become `referral`.

Preview, production, and local-development events are separated at the server from the
request host. Replayed events are ignored by the database uniqueness constraint.

## Anonymous acquisition context

### Registered first-touch campaign attribution

Beginning with migration 20260830171056_weekly_growth_attribution_export.sql, a new
account may retain one content-free first-touch tuple: acquisition, placement, campaign,
creative family, and promised product intent. The tuple is immutable for 24 hours in the
current browser tab and is accepted only when it matches the exact campaign registry in
the landing runtime, auth runtime, Python boundary, and database constraints. Unknown or
inconsistent labels are discarded. Campaign fields are permitted only on AccountCreated;
no referrer URL, search term, content, filename, or arbitrary metadata is stored.

users.registration_environment is derived from the registration request host and is the
authoritative production-cohort boundary even when the optional analytics insert fails.
Existing pre-release accounts with no environment are excluded rather than backfilled.
product_weekly_attribution_export is service-role-only and returns grouped counts with
explicit denominators. Its D1/D7 populations contain activated accounts only and are
anchored on ActivationReached. Finance fields remain null until an authoritative aggregate
provider supplies them. The operator contract and release evidence are recorded in
docs/WEEKLY_ATTRIBUTION_RELEASE_2026-08-30.md.

Vercel Web Analytics provides aggregate, anonymous context before account creation. These browser
events are not written to `product_events` and must not be treated as server-authoritative account
milestones:

- `MarketingCTA` means a visitor selected a create-account CTA beginning with release 5.9.29.
- `MarketingSignin` means a visitor selected an existing-account sign-in link beginning with
  release 5.9.29. Before that boundary, these clicks were mixed into `MarketingCTA`.
- `SignupIntent` means the signup form was shown from a signup deep link or explicit auth link.
- `SignupStarted`, `SignupCredentialsReady`, and `SignupSubmitted` mark first form interaction,
  locally valid credentials, and form submission respectively.
- The browser-side `AccountCreated` event is directional only; the server-side `AccountCreated`
  milestone and comparable cohort boundary remain authoritative.

These counts may include internal or automated traffic. Never present them as a conversion rate
without explicit time boundaries, denominators, and reconciliation to the service-role account
snapshot.

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
| `RecentWorkResumed` | Authenticated client | The user opened a non-empty conversation from the clean-start launchpad or continued a conversation from its Project workspace. The server accepts only `launchpad` or `project`, derives a source-specific UTC-day key, and records at most one content-free milestone per account, source, and day; no Project ID, chat ID, title, prompt, response, or filename is sent. |
| `PlanCenterViewed` | Authenticated client | The user reached the Plan center from settings, explicit paid-plan intent, an upgrade prompt, or one fixed recovery category. Recovery sources are limited to `recovery_credits`, `recovery_subscription`, `recovery_feature`, `recovery_project`, and `recovery_usage`; counts, balances, prompts, content, IDs, and error text are never sent. The server records at most one event per account, source, and UTC day. |
| `PlanIntentReached` | Authenticated client | A paid-plan marketing intent reached the in-app plan review. |
| `ResponseShared` | Authenticated client | A user completed native sharing or a clipboard write was positively verified for branded share text, including the optional content-free referral offered after a useful outcome. A denied/unsupported clipboard write returns an error and records no event. The source is restricted to the four delivery paths (`native_share`, `clipboard`, `useful_prompt_native`, or `useful_prompt_clipboard`). Every shared link opens the public product page first and carries only the aggregate `referral` channel and fixed `response-share` placement through a later signup or sign-in action—never a user, conversation, message, content, or arbitrary source identifier. |
| `ArtifactRequested` | Server | An entitled document or presentation request reached generation. Only the artifact category and server-derived environment, platform, and plan are retained. |
| `ArtifactPackaged` | Server | The requested downloadable file was stored successfully. |
| `ArtifactPackagingFailed` | Server | File packaging failed after the response was written. No exception or error text is retained. |
| `ArtifactDownloaded` | Server | The first authenticated download redirect was prepared for a generated document or manuscript export. Inline opens and ordinary uploads are excluded. |
| `SubscriptionCheckoutOpened` | Server | Stripe created a subscription Checkout Session. |
| `SubscriptionCheckoutCompleted` | Stripe webhook | Stripe verified a completed subscription Checkout Session. |
| `CreditCheckoutOpened` | Server | Stripe created a credit-pack Checkout Session. Only the fixed pack code and server-issued session identity are used for attribution and idempotency. |
| `CreditCheckoutCompleted` | Server | Stripe verified a completed credit-pack Checkout Session, or RevenueCat returned a verified credit-pack transaction. Only the fixed pack code and provider transaction identity are used. |
| `BillingPortalOpened` | Server | Stripe created a customer portal session. |
| `SubscriptionStatusChanged` | Stripe webhook | Stripe changed or deleted a subscription. |

## Service-role lifecycle guidance evidence

Migration `20260830175952_in_product_lifecycle_activation.sql` adds a separate,
allowlisted lifecycle evidence boundary. Eligibility is selected by the authenticated
server from content-free account and product-milestone facts; the client cannot choose
a message family or supply rendered copy.

The server enforces an account-stable holdout per message key, a default 20% holdout,
per-key kill switches, stale-state revalidation, one shown prompt per page session, two
shown prompts per seven days, and message-specific cooldowns.

The service-role-only `product_weekly_lifecycle_export` returns aggregate rows grouped by
fixed message key, intent, prompt/holdout cohort, and suppression category. It excludes
deleted and internal accounts, respects the registration-environment boundary, and never
returns account identifiers, prompts, responses, Projects, conversations, filenames, URLs,
or rendered lifecycle copy. Release evidence is recorded in
`docs/IN_PRODUCT_LIFECYCLE_ACTIVATION_RELEASE_2026-08-30.md`.

## Operating queries

All operating queries must filter `environment = 'production'`. The primary weekly view is
the number of distinct accounts reaching each funnel milestone. Retention is calculated from
the first `AccountCreated` or `ActivationReached` event to daily `WorkspaceOpened` events at
D1, D7, and D30. Preview rows are kept out of business reporting.

No acquisition spend should increase until production data can distinguish: account created,
workspace opened, starter intent reached, activated, durable value reached, paid intent reached,
subscription or credit checkout opened, and subscription or credit checkout completed.
The first comparable cohort begins at `2026-08-23 09:10:55.602863+00`, the first observed production
product-event timestamp. Migration `20260827180833_product_growth_measurement_boundary.sql` enforces
that lower bound even when an operator requests an earlier reporting window. Historical account
behavior is not silently reconstructed from conversation or file content. Account/job/file/Project
aggregates may be used to diagnose historical product use, but they must be labeled separately from
event-based cohort rates and never converted into synthetic events.

## Service-role growth snapshot

Migration `20260827180833_product_growth_measurement_boundary.sql` installs the current version of
`product_growth_funnel_snapshot`, a service-role-only aggregate report for a half-open
account-creation window bounded by the first observed production event. It returns ordered counts,
eligible populations, and conversion rates for:

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

## Service-role Plan-center conversion snapshot

Migration `20260830053822_monetization_recovery_measurement.sql` updates
`product_plan_conversion_snapshot`, a service-role-only aggregate report for a half-open event
window. It preserves the existing Plan-center, subscription Checkout-opened, and subscription
Checkout-completed metrics, then adds credit Checkout open/completion and distinct-account counts
for the five fixed recovery categories. The report excludes deleted and internal accounts by
default and returns no account identity, content, balance, price, or payment detail. Migration
`20260830055322_consolidate_monetization_index.sql` replaces the overlapping report indexes with
one covering index for the subscription, credit, and recovery journey.

```sql
select *
from public.product_plan_conversion_snapshot(
  p_since => timestamptz '2026-08-30 00:00:00+00',
  p_until => now(),
  p_environment => 'production',
  p_include_internal => false
);
```
