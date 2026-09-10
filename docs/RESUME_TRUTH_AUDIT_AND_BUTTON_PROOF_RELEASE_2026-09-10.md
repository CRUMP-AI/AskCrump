# Résumé truth-audit and button-proof release — 2026-09-10

## Outcome

Ask Crump now publishes one restrained, indexable guide at
`https://www.askcrump.com/guides/audit-ai-resume-bullets`. The guide teaches a
five-part proof test for verbs, scope, metrics, causation, and interview
defensibility using an authentic Ask Crump Word-exporter résumé example. It
contains one direct-safe Free-start action, one crawlable public inlink, and one
sitemap entry. It makes no hiring, ATS, customer, or provider-quality claim.

The exact recognized first-touch tuple is:

| Acquisition | Placement | Campaign | Creative | Intent |
| --- | --- | --- | --- | --- |
| `organic-search` | `workflow-guide` | `resume-bullet-truth-audit` | `search-article` | `resume` |

The raw button remains direct and campaign-free:

`/app?signup=1&source=resume-audit-start&plan=free&intent=resume&acquisition=direct`

No tracked campaign URL, social distribution, Search Console action, checkout,
spend, or customer event was created during the release.

## Button integrity

The release revalidated the complete current control inventory rather than
assuming that visible controls are wired:

- **182** rendered button tags and **94** programmatically created buttons are
  inventory-locked: **276 total button sites**.
- Every rendered control has an explicit form action or bounded runtime click
  owner. Every dynamic button declares its behavior type and has a direct or
  reviewed delegated click owner.
- The five hash-only authentication actions—Create account, Forgot password,
  both Sign in returns, and Back to sign in—are now separately inventory-locked
  and exercised in a real 390×844 browser.
- The fail-closed browser matrix passed **38/38** verifiers across Ask,
  Projects, Files, Library, Create, Video, Image/Precision Edit, Settings,
  authentication, checkout recovery, and desktop/mobile navigation.
- The live public-entry proof passed on `www.askcrump.com`, including all five
  authentication transitions and the five creation-destination handoffs.

Account deletion, real checkout, real provider spend, and other destructive or
billable outcomes remain verified through isolated confirmation/cancel/recovery
fixtures rather than being executed against a customer's production account.
No dead control was found in this audit.

## Database and privacy boundary

Remote migration `20260910155004 release_resume_bullet_search_attribution`
adds only the organic résumé guide campaign to the allowlist and its exact
source/placement/creative/intent branch. The AccountCreated writer remains
`SECURITY INVOKER`, keeps an empty search path, denies execute to PUBLIC,
`anon`, and `authenticated`, and grants execute only to `service_role`.

A rollback-only production exercise proved that the valid tuple writes once,
an identical retry is idempotent, five malformed variants retain neither
campaign nor creative, a direct cross-product is rejected by the database, and
the valid tuple reaches the privacy-safe weekly aggregate. Rollback left zero
synthetic users and zero synthetic events.

Supabase advisors remained at the pre-existing informational baseline: one
`rls_enabled_no_policy` category covering 61 service-role-only tables and one
`unused_index` category covering 59 indexes. No new warning or error appeared.

## Validation and delivery

- Product commit: `9ea418f6b09f282b80130185ca0147b5ccdee45b`.
- Complete Python suite: **984/984** passed.
- JavaScript contract: **49 files**, **21/21** rough-to-useful cases,
  **10/10** Word/PDF cases, and **10/10** résumé-audit cases passed.
- Browser control matrix: **38/38** passed.
- Independent source gate: **40/40** passed.
- Independent live release gate: **56/56** passed with zero failures and no
  tracked URL opened.
- Ruff, Python compilation, production preflight, native web build, and diff
  integrity passed.
- GitHub Actions: CI `34498814098`, Android Store Bundle Verification
  `34498814361`, and iOS Store Source Verification `34498814303` all passed.
- Production deployment `dpl_97Bk7rQF3TukruvGgohMNrHkMkpc` is READY with all
  six expected aliases.
- The guide, both authentic evidence assets, landing runtime, authentication
  runtime, sitemap, public inlink, app noindex boundary, and guide stylesheet
  passed live byte/contract verification.
- All four custom-domain health checks returned HTTP 200. The release-window
  runtime scans contained no error, fatal, warning, or HTTP 5xx log.

## Decision boundary

This release authorizes the public organic-search guide and its exact
measurement destination only. It does not authorize social publication,
Search Console action, paid traffic, advertising, pricing or billing changes,
purchases, customer-content inspection, or performance claims.
