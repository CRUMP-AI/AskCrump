# Contextual Plan and credits recovery release

Date: 2026-08-30
Production version: `5.9.76`

## Outcome

When Ask Crump opens Plan & credits because work hit a real access boundary, the center now
explains why it opened and preserves the useful context needed to continue. A credit shortfall
shows the exact required credits and current balance without implying that a subscription upgrade
is required. A true subscription requirement identifies and highlights the applicable plan.
Project and daily-message limits receive their own clear explanations.

Opening Plan & credits still does not buy credits, change a subscription, or start checkout.
Those remain separate, explicit user choices.

## Evidence and decision

The feature-access recovery release correctly routed users into Plan & credits, but both live
billing owners still rendered the same generic center for every reason. The handoff also carried a
minimum tier for some credit failures, which could make a credit purchase problem look like a
subscription requirement.

This release preserves only bounded structured values and uses fixed interface copy for:

- `CREDITS_REQUIRED`
- `SUBSCRIPTION_REQUIRED`
- `FEATURE_LIMIT_REACHED`
- `PROJECT_LIMIT_REACHED`
- `USAGE_LIMIT`

Raw server messages are not rendered. Only `SUBSCRIPTION_REQUIRED` can set a plan intent.

## Product and safety contract

- Credit recovery displays the bounded required-credit count and current balance when present.
- Credit recovery does not preselect or recommend a subscription plan.
- A genuine subscription requirement can highlight only Professional or Enterprise.
- Project and daily-message limits remain distinct from credit exhaustion.
- The generic Settings entry remains a generic Plan & credits view.
- The center states that nothing changes before the user explicitly confirms checkout.
- No checkout request, purchase, subscription change, entitlement change, retry, or production
  record is created merely by opening the recovery view.
- No price, allowance, credit cost, tier policy, metering rule, provider route, database schema,
  RLS policy, payment route, or analytics payload changed.

## Verification

- All 504 Python tests passed.
- All 45 JavaScript files passed the repository integration validator.
- Production build preflight passed.
- The native web bundle rebuilt successfully.
- Store metadata source verification passed.
- A credential-free browser fixture exercised both live Plan-center owners and proved:
  - the generic entry has no recovery summary or highlighted plan;
  - a 60-credit requirement with a 12-credit balance shows those exact bounded values and no plan
    intent;
  - an Enterprise-only feature explains the requirement and highlights Enterprise;
  - the Project-cap explanation remains distinct and does not preselect a plan;
  - the 25-message daily-limit explanation remains distinct and does not preselect a plan;
  - all five states created zero checkout requests and zero browser errors.
- Diff integrity passed.

The native release verifier continued to report the pre-existing store-submission gates: the iOS
native project is missing, the RevenueCat Android and iOS public SDK keys are empty, and Android
FCM configuration is absent. These are unrelated to this web/PWA release and remain explicitly
unclaimed.

## Production release

- Feature commit: `0fa7cdb`
- Deployment: `dpl_GJaumEcpgPn5EqTMzUwzsjxYdwaJ`
- Deployment state: `READY`
- Alias state: six production aliases, no alias error
- Service-worker cache: `ask-crump-new-body-v1-r144`
- Runtime and changed assets: `5.9.76-contextual-plan-recovery-1`
- Canonical health: HTTP 200, service `Ask Crump`, version `5.9.76`

The canonical app, exact runtime loader, both billing owners, billing stylesheet, chat transport,
product controller, service worker, and health route returned HTTP 200 with their expected release
markers. More than one minute after the deployment became ready, Vercel reported no runtime-error
cluster and no error or fatal deployment log.

No production account, message, Project, manuscript, video, credit purchase, subscription,
payment, checkout, or synthetic funnel event was created for verification.

## Next operating decision

Observe the first legitimate access boundary through the contextual Plan-center review and either
an explicit checkout choice or a safe return to work. Use that content-free outcome to improve the
next conversion or recovery bottleneck before changing prices, allowances, or acquisition spend.
