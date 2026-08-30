# Monetization recovery measurement release

Date: 2026-08-30
Production version: `5.9.76`

## Outcome

Ask Crump can now distinguish why a user reached Plan & credits and whether that journey later
opened or completed a subscription or credit checkout. This closes a decision gap: a legitimate
credit purchase no longer looks like a failed conversion, and credit, subscription, feature,
Project, and daily-usage recovery are no longer collapsed into the generic Settings entry.

## Product and privacy contract

- Plan-center recovery records only one fixed category per account, category, and UTC day.
- Allowed recovery categories are credits, subscription, feature, Project, and daily usage.
- Credit-checkout open and completion milestones are created only by verified server flows.
- Stripe uses the server-issued Checkout Session identity; RevenueCat uses the verified
  transaction identity. Both retain only the fixed catalog pack code as their source.
- Browser and native clients cannot submit credit-checkout milestones.
- No prompt, response, filename, message, balance, required-credit count, price, card detail,
  customer detail, payment detail, or arbitrary metadata is stored.
- Analytics remain fail-open and cannot prevent checkout, credit delivery, or provider retry.
- No price, allowance, entitlement, checkout behavior, or plan changed in this release.

## Private operating report

Two production migrations extend the product-event allowlist and the service-role-only
`product_plan_conversion_snapshot`. The report preserves the prior subscription stages and adds
credit Checkout open/completion plus the five fixed recovery categories. It remains security
invoker with an empty search path; `public`, `anon`, and `authenticated` execution are denied,
while `service_role` is allowed. The report returns aggregates only and was invoked successfully
over a bounded production window without publishing its counts.

The post-migration advisor pass introduced no security finding. An initially overlapping report
index was replaced with one covering index, removing the overlap before release evidence was
recorded.

## Verification

- All 517 Python tests passed.
- All 45 JavaScript files passed the repository integration validator.
- Production build preflight passed.
- The native web bundle rebuilt successfully.
- Store metadata and signing-source controls passed.
- A credential-free browser fixture exercised the generic, credit, Enterprise, Project-cap, and
  daily-limit paths. Every path rendered the correct restrained context, with zero checkout
  requests and zero browser errors.
- Production database checks verified both credit-event allowlist entries, all ten report rows,
  the covering index, service-role-only execution, security-invoker behavior, and the empty search
  path.
- Diff integrity passed.

The native release verifier continues to report the pre-existing store-submission gates: the iOS
native project is missing, the RevenueCat Android and iOS public SDK keys are empty, and Android
FCM configuration is absent. These remain explicitly unclaimed and are unrelated to this web/PWA
release.

## Production release

- Feature commit: `283e500`
- Deployment: `dpl_3tvSsSTw1G2QZ41uzMR21oXcUJu2`
- Deployment state: `READY`
- Alias state: six production aliases, no alias error
- Service-worker cache: `ask-crump-new-body-v1-r145`
- Changed runtime assets: `5.9.76-monetization-recovery-1`
- Canonical health: HTTP 200, service `Ask Crump`, version `5.9.76`

The canonical app, exact runtime loader, both Plan-center controllers, service worker, and health
route returned HTTP 200 with their expected release markers. More than one minute after the
deployment became ready, Vercel reported no runtime-error cluster and no warning, error, or fatal
deployment log.

No production account, message, Project, manuscript, video, credit purchase, subscription,
payment, checkout, or synthetic funnel event was created for verification.

## Next operating decision

Observe legitimate Plan-center recovery journeys and provider-confirmed checkout outcomes. Use the
first content-free evidence to improve the largest measured recovery or conversion drop before
changing prices, allowances, or acquisition spend.
