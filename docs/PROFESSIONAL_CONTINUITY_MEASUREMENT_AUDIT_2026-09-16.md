# Professional continuity measurement audit

Date: 2026-09-16

Source revision: `57265b327984be71d402ce55f03ce5289a392f20`

## Decision

The existing privacy-safe aggregates are sufficient to observe much of the proposed
Project-continuity-to-Professional journey, but they are **not yet sufficient to qualify the whole
revenue wedge**. Keep the Project-limit application flag and database control off. Do not create
assignments, exposures, synthetic Projects, synthetic events, or a public revenue claim.

The first safe implementation opportunity begins only after the active Facebook observation closes
at **2026-09-17 13:28 EDT** and its checkpoint is sealed.

## What the current aggregate can prove

The current `product_weekly_attribution_export` is service-role-only, content-free, excludes
internal/deleted/non-production accounts by default, and separates cohort denominators. It exposes:

| Required signal | Current evidence | Status |
| --- | --- | --- |
| Registered account and immutable first touch | `accounts_created`, `account_event_recorded`, and acquisition tuple | Covered |
| Activation within 24 hours | completed chat job or `ActivationReached` | Covered |
| Decision-grade value | activation plus useful feedback or durable value | Covered |
| Durable Project/file value | Project chat, Project file, or ready generated file contributes to durable value; Project/file counts are separate | Partially covered |
| D1 and D7 return | activation-based elapsed denominators and `WorkspaceOpened` | Covered |
| Subscription Checkout | opened and completed counts | Covered |
| Provider-backed payer/entitlement | Stripe/RevenueCat-backed payer and active subscription counts | Covered |
| Finance-recognized revenue and variable cost | returned as `null` | Truthfully unavailable |

## Missing decision-grade fields

1. **Nonempty Project value is not isolated.** `project_created_reached_24h` can include a bare
   Project. Durable value can come from a Project chat or file, but the export does not return the
   number of accounts with at least one Project containing a nonempty assistant response or ready
   file.
2. **Second active nonempty Project is absent.** The export has no count for accounts with at least
   two distinct active Projects that each meet the nonempty-work rule.
3. **Natural third-Project attempt is unobservable while the experiment is off.** The dormant
   `claim_project_limit_plan_message` function deliberately returns before writing assignment or
   event state whenever either gate is disabled. This correctly prevents exposure, but also means
   the current experiment snapshot cannot count a natural server `PROJECT_LIMIT_REACHED` attempt.
4. **Plan-center view is not isolated in the weekly export.** `PlanIntentReached` is available, but
   the distinct `PlanCenterViewed` milestone required by the revenue packet is not returned.
5. **Paid continuation and recognized revenue remain unavailable.** Checkout and entitlement are
   diagnostics; neither is finance-recognized revenue.

## Smallest safe post-isolation change

Add a service-role-only, content-free continuity qualification aggregate (or extend the existing
weekly export without breaking its signature) with these account-level counts and explicit
denominators:

- `nonempty_project_accounts`;
- `second_nonempty_project_accounts`;
- `natural_project_limit_attempt_accounts`;
- `plan_center_view_accounts`;
- the existing Checkout, entitlement, payer, D1, and D7 fields; and
- recognized-revenue/cost fields that remain `null` until an approved finance source supplies them.

To measure the natural limit attempt without enabling treatment, record one server-authoritative,
content-free, idempotent fact immediately after the Projects route has proven
`PROJECT_LIMIT_REACHED` and before the dormant experiment gate is consulted. That fact must contain
only an account ID inside the private database, environment, fixed reason, UTC time, and an
idempotency key. It must not assign an arm, create an exposure, open Plans or Checkout, or include a
Project name, prompt, response, filename, URL, or other customer content.

## Acceptance tests

- bare Projects do not count as nonempty;
- one qualifying Project does not count as a second Project;
- two distinct qualifying active Projects count once per account;
- archived, internal, preview, deleted, and unverified accounts are excluded;
- repeated third-Project retries deduplicate without losing the first natural attempt;
- the natural-attempt recorder works while both experiment controls remain off and creates no
  assignment or exposure;
- `PlanCenterViewed`, Checkout, entitlement, and payer remain separate milestones;
- zero denominators return unavailable rates, not zero percent;
- all functions are fixed-search-path, service-role-only, content-free, and return counts only.

## Release boundary

This audit authorizes no product, database, billing, pricing, campaign, experiment, or production
change. Recheck the remote migration ledger and the sealed Facebook checkpoint before preparing a
schema candidate. Any later source change requires disposable/staging SQL tests and an independent
privacy/measurement review before deployment.
