# Outcome issue feedback and control sweep release — 2026-09-09

## Outcome

Ask Crump's complete credential-free browser control matrix now covers 35 independent flows.
The added flow verifies that a user who marks a response **Not yet** can optionally identify the
problem through one fixed category, recover from a failed analytics write, and see the saved state
after the conversation rerenders. The seven choices are facts/accuracy, instruction following,
format or clarity, image or video quality, reliability, safety or rejection, and other.

The follow-up stores no free text, prompt, response, filename, URL, account identifier, or
arbitrary metadata. Existing **Yes** feedback and referral behavior is unchanged.

## Button and interaction acceptance

- The fail-closed source inventory covers **181** rendered buttons and **93** programmatically
  created buttons: **274 reviewed construction sites** in total.
- Every programmatic button must declare `type="button"` and acquire a direct, delegated, form,
  or reviewed helper owner within its bounded declaration lifetime.
- The complete browser matrix passed **35/35** verifiers. It includes navigation, Chats, Create,
  Projects, Files/viewers, generated-output save/open, Image Studio stability and Precision Edit,
  live warmth/exposure/saturation preview, compare/reset/apply, Video/reference images, Library,
  Settings, plans/credits, account entry/recovery, lifecycle/referrals, attribution, guide starts,
  and close/back/retry behavior.
- The new 390×844 verifier forced the first category write to fail, proved that every choice was
  re-enabled, saved the second choice exactly once, rerendered the conversation, and confirmed no
  horizontal overflow, browser error, or fixture error.

Destructive, financial, provider-backed, and customer-data actions were not executed in
production. Those paths are verified through isolated fictional fixtures and their separate
release gates.

## Server and database boundary

The authenticated analytics route accepts `OutcomeIssueCategorized` only with an
`outcome-issue:` key, no plan, and one of the seven allowlisted values. Migration
`20260909165000 outcome_issue_categories` adds the matching database check and a stable,
security-invoker aggregate. Execute privilege is granted only to `service_role`; `anon` and
`authenticated` cannot call it. The first production aggregate was empty, as expected before the
interface release.

The post-migration advisor scan found only the project's pre-existing informational
RLS-with-no-policy and unused-index notices. The design intentionally keeps `product_events`
service-role-only rather than creating client table policies.

## Automated acceptance

- Focused analytics/button suite: **81 passed**.
- Full Python suite: **933 collected**, **931 passed**, two environment-dependent skips.
- JavaScript integration contract: **49 files** and **6/6** attribution cases passed.
- Ruff, Python compilation, production preflight, native web build, store metadata, native
  privacy verification, and diff integrity passed.
- Main CI `34379345119`, Android source/bundle verification `34379344962`, and iOS source
  verification `34379345192` completed successfully.

## Production identity

- Feature commit: `96010cc831967302363098e810626eabe60bebab`.
- Automatic production deployment: `dpl_7NyP3FKRqsSrRDczkZjqQujtbrn9`.
- Deployment state: READY on all six aliases with no alias error.
- Canonical `/api/health`, `/app`, runtime loader, `ui-functions.js`, `product-analytics.js`, and
  service worker returned HTTP 200. The four relevant runtime assets exposed the exact
  `outcome-issue-categories-1` or event marker.
- The first post-release runtime-error and deployment-scoped HTTP 5xx queries were empty.

## Evidence boundary

This release proves control ownership, deterministic browser behavior, database validation,
production delivery, and privacy-safe aggregation. It does not claim that all signed physical
devices, assistive technologies, external provider outcomes, payment states, or future UI states
have been exercised. The next real negative feedback category should be treated as directional
product evidence, not a statistically representative quality score.
