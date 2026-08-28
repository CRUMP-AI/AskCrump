# Ask Crump operating snapshot — 2026-08-27 21:40 ET

This snapshot records the decision boundary after production 5.9.34. It separates protected
account evidence from anonymous website activity so that traffic is not misreported as users or
conversion.

## Protected product evidence

The content-free, service-role aggregate was refreshed at `2026-08-28T01:40:14.988164+00`.

- Every stage in the comparable post-instrumentation growth funnel is zero: account creation,
  verification, workspace open, activation, durable value, recent-work continuation, sharing,
  plan intent, checkout, paid status, D1 return, and D7 return.
- The aggregate artifact journey has no rows.
- The aggregate account-acquisition report has no rows.
- There are no external production product events after the comparable measurement boundary.

The query returned counts and aggregate JSON only. It did not return customer identifiers,
prompts, responses, files, or other customer content.

## Anonymous production traffic context

Vercel Web Analytics reported the following production-only context:

| Window | Visitors | Page views | Bounce |
| --- | ---: | ---: | ---: |
| Aug 20 21:00–Aug 27 21:59 ET | 87 | 233 | 62% |
| Aug 26 22:00–Aug 27 21:59 ET | 15 | 68 | 53% |

Over seven days, `/app` reached 60 visitors and the homepage reached 45. Facebook supplied 22
visitors across `facebook.com` and `m.facebook.com`; `clevercrump.com` supplied seven. The device
mix was 61% desktop and 39% mobile. The anonymous event view contained 20 `SignupIntent` visitors,
eight `MarketingCTA` visitors, two `SignupStarted` visitors, and one historical client
`AccountCreated` visitor. That window crosses the comparable measurement boundary and can include
owner, internal, or automated traffic.

In the latest 24 hours, the homepage reached 12 visitors and `/app` reached six. The event view
contained three `MarketingCTA` visitors, two `SignupIntent` visitors, two `SignupStarted` visitors,
and one `MarketingExplore` visitor. It contained no `SignupCredentialsReady`, `SignupSubmitted`,
`AccountCreated`, or `MarketingSignin` event.

## Decision

Ask Crump has anonymous onsite interest but still has no comparable external account journey.
Neither the seven-day counts nor the two latest form starts establish a registration conversion
rate or a specific credential-field defect. Rewriting signup from this sample would be an
unsupported intervention.

The current actions are therefore:

1. Complete the owner-run sign-out and manual credential-entry check without inspecting or
   recording credentials.
2. Submit the verified canonical sitemap only after the owner gives the exact required approval;
   the capability pages are technically crawlable but remain undiscovered in Search Console.
3. Observe the first legitimate, consented post-boundary account through verification, useful
   work, durable value, and return before scaling acquisition spend or changing the funnel.

No synthetic account, event, artifact, checkout, payment, or analytics data was created during
this review. The analytics tab used for the read-only audit was closed afterward.
