# Ask Crump daily operating review — 2026-09-20

## Boundary

Read-only production, private aggregate, and signed-in social checks; source-only work on draft PR #37. No production schema, provider customer, pricing, campaign, social post, or store listing was changed. This is not a weekly owner report or monthly strategy review.

## Evidence

- Production remains on `main` commit `d2aa857`, separate from the draft PR. `/api/health` returned HTTP 200, and the trailing 24-hour Vercel read found no 5xx or grouped runtime-error cluster. Supabase health was normal. The latest remote migration remained `20260917233900`; the September 18 draft migrations and the native-identity migration are not applied.
- The protected production cohort still contains one comparable external September account, with a verified/activated journey and D1 return at **1/1**. No new comparable account appeared after September 20 00:00 UTC. No durable Project or payer outcome was observed. D7 remains ineligible. Recognized revenue and matched variable cost are **unavailable**, not zero. This sample cannot support a retention rate, product-market-fit claim, or paid-acquisition decision.
- Ask Crump Facebook had 5 followers and no visible active ad or Reel. The existing feed proof post showed 41 views from 4 viewers, with zero engagement, comments, or follows; its link-click insight was unavailable. The caption's “See the full walkthrough” truth correction remains unexecuted. Messenger and comments queues were empty.
- Instagram `@askcrump` had one post, 2,767 followers, and no clickable website link. That post showed 5 views and zero interactions or profile actions. No newer inbound Primary reply was visible; General and request queues were empty. A distinct Clever Crump social account could not be verified. The marketing growth board, last updated September 17, holds the Reel preview, Instagram/Story, and paid spend at $0. These channels remain marketing-owned.
- Recent product feedback remains the known image-editing stability, file-preview, video continuity, and store-distribution requests; no new support failure was visible in the checked social queues. In the current source branch, the highest-value safe correction is durable evidence that a free native user may have a RevenueCat identity, even if native billing is later disabled.

## Decision and next action

Keep PR #37 draft and production unchanged. The source candidate records the authenticated user before the native SDK can configure or log in, and carries that possible-provider-identity obligation into durable account deletion. Focused native/deletion/API tests passed **51/51**; JavaScript, production preflight, native web bundle, returning-app worker, credential boundary, Ruff, and diff integrity passed. The full local Python suite passed with the two known host-missing-Argon2 tests excluded. The local browser matrix could not launch Chromium (`spawn UNKNOWN`). No migration was applied. Complete CI and signed-device verification remain outstanding.

Independent review identified a P1 cross-device race: a native client paused after marker confirmation may resume SDK setup after another device has deleted the account and completed provider cleanup. The marker and 30-hour sweep reduce risk but do not prove no recreation. Resolve this before enabling native billing; do not apply the migration or merge/deploy native billing until server credentials, exact products, physical-device purchase/restore/deletion evidence, and store-owner gates are satisfied. RevenueCat's own [customer API](https://www.revenuecat.com/docs/api-v1/customers) and [account-deletion guidance](https://www.revenuecat.com/blog/engineering/app-store-account-deletion) support the risk.

Ambiguous account-deletion responses still require a durable pre-provider attempt and server-confirmed status reconciliation before the client can safely clear its billing guard; do not infer safety from a timeout or a missing job. Preserve the existing result-to-Project experience and collect a legitimate save/return journey before changing activation UX or scaling acquisition.

## Continuation — native client race reduction

The draft client now rechecks the server-authoritative owner/deletion fence around native SDK configuration and login, when adopting an existing SDK identity, and immediately before native purchase, restore, or customer refresh. A deterministic regression reproduces a stale account-A check failing while account B is purchasing and verifies A cannot log B out. An independent replay found no new cross-account logout, purchase bypass, or promise hang. JavaScript contracts validated 55 files; the focused Python suite passed 36/36; production preflight, native web bundle, client-secret boundary, returning-PWA worker, and diff integrity passed. Production remains unchanged and native billing remains OFF.

These checks reduce the usual stale-client window; they cannot make a server check atomic with a third-party SDK call. A paused device can still resume after account deletion/provider cleanup, and a purchase already in flight remains a store-release risk. Exact next action: keep PR #37 draft; complete CI for this candidate, then obtain a provider/architecture decision and signed two-device deletion, delayed-resume, account-switch, and in-flight purchase evidence before any native-billing enablement, migration application, merge, or store submission.

## CI closure

Commit `2c1207e` was pushed only to draft PR #37. GitHub CI run `35547551285` completed successfully in both Python 3.12 and JavaScript lanes, including interactive browser controls, accessibility, production bundle, and store-evidence checks. The branch was clean after the push. No production deployment, remote migration, native-billing enablement, provider mutation, or store submission occurred. The exact next action is the provider/architecture decision and signed two-device deletion, delayed-resume, account-switch, and in-flight purchase/restore verification; passing source tests is not a release signoff.
