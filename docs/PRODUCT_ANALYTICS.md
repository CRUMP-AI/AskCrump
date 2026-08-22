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

Preview, production, and local-development events are separated at the server from the
request host. Replayed events are ignored by the database uniqueness constraint.

## Milestones

| Event | Authority | Meaning |
| --- | --- | --- |
| `AccountCreated` | Server | A new account row was created. |
| `OnboardingCompleted` | Server | The account supplied its initial display name. |
| `WorkspaceOpened` | Authenticated client | The workspace opened; at most one row per UTC day. |
| `ActivationReached` | Server | The first successful, persisted AI response completed. |
| `AhaReached` | Server | The first durable artifact, generated image, or manuscript workspace completed. |
| `PlanIntentReached` | Authenticated client | A paid-plan marketing intent reached the in-app plan review. |
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
activated, durable value reached, paid intent reached, checkout opened, and checkout completed.
The first comparable cohort begins with release 5.8.2; historical account behavior is not
silently reconstructed from conversation or file content.
