# Plan value and conversion measurement release — 2026-08-29

## Outcome

Ask Crump now explains the material difference between Free, Professional, and
Enterprise before checkout, using the enforced daily allowances and Project
limits. The signed-in Plan & credits center and public pricing page use the same
facts, and both state that premium video and other high-compute generations use
Crump Credits.

The plan center also records one privacy-minimized daily view so the business
can measure plan-detail views to checkout opens and completions without storing
page content, prompts, filenames, email addresses, payment data, or free-form
values.

## Delivery

- `7df3503` added exact public/signed-in plan facts, the allowlisted event, the
  aggregate report, migration, and regression coverage.
- `84b787e` wired measurement into the final billing override that owns the
  visible production modal.
- `c889adf` added a direct fail-open intake fallback for environments where the
  shared analytics helper is late or unavailable.
- `af99087` preserved the verified plan flow while completing the official
  header refresh correction and cache revision `r121`.
- Production deployments: `dpl_3QyWqw1qAiJog1tUKvY5hMmhbo5U`,
  `dpl_D58zqDoRHbMThKsycuGbjyQxHPA6`,
  `dpl_6datW8eSAgA4fHVRyHd6dDB2Yf4Z`, and final
  `dpl_5sinMLpbfLYZLH36GPVDZ8LjXp1f` (`READY`).
- Supabase migration `plan_center_conversion` was applied as version
  `20260829141423`.

## Measurement boundary

- Client payload: `eventName=PlanCenterViewed`,
  `eventKey=plan-center-viewed`, and one of `settings`, `plan_intent`, or
  `upgrade_prompt` as source.
- The server rewrites the key to a UTC daily key, so repeated opens do not
  inflate the account count.
- The event accepts no plan name, account identifier, URL, referrer URL, user
  content, prompt, filename, credential, or payment field.
- The aggregate conversion function is security-invoker and executable only by
  the service role. It returns counts and percentages, never account rows.

## Verification

- The local missing-helper browser fixture recorded the exact three-field event
  and returned `accepted:settings` from the final billing layer.
- Signed-in production opened the final Plan & credits modal, showed the exact
  Professional and Enterprise allowances, contained no stale “Coming soon” or
  “Not live yet” copy, and returned `accepted:settings` without entering
  checkout.
- The production endpoint returned HTTP 200. The internal-included 15-minute
  aggregate then reported one plan-center-view account, zero checkout-open
  accounts, and zero checkout-complete accounts. No synthetic account, event,
  payment, or checkout was created.
- The final combined pass covered 455 Python tests, 45 JavaScript files,
  production preflight, native web build, and store metadata. The final release
  window contained 60 HTTP 200 responses and no warning/error/fatal log or
  runtime error cluster.

## Unchanged native-store gates

RevenueCat public SDK keys, Android Firebase configuration, and generating the
iOS project remain owner-controlled store submission gates. They do not block
the deployed web/PWA release.
