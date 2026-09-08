# Guide proof-to-start release — 2026-09-08

## Outcome

The public rough-idea workflow guide now gives a visitor two early, truthful ways to start:

- a persistent navigation action labeled **Start free**; and
- a hero action labeled **Start free with your rough idea**.

The hero action is followed by the existing offer boundary:
**Start free with 2 private Projects · No card required**.

This closes the verified gap where the first in-article continuation action sat at document
Y=6,964 on a 7,731-pixel phone page and the only `/app` navigation link was hidden on mobile.
The guide's evidence, fictional-example disclosure, article body, canonical, Open Graph image,
bottom matched CTA, pricing, registration, and application behavior remain unchanged.

## Independent integration decision

The marketing-owned source candidate was replayed onto then-current `main` and independently
reviewed. Its initial `5.9.77` guide stylesheet token was revised to
`5.9.76-guide-proof-to-start-1` because the application remains version `5.9.76`. The final
release changes exactly:

- `public/guide.css`;
- `public/guides/rough-idea-six-week-launch-plan.html`; and
- `tests/test_search_guides.py`.

The two new links retain campaign-free direct fallbacks and use the existing `data-cta` resolver.
That resolver carries a valid immutable first touch when one exists. No campaign, creative, event,
offer, price, allowance, checkout, or funnel stage was created.

## Browser acceptance

The exact feature was served from a credential-free `127.0.0.1` origin before release. The local
surface had no Supabase credentials and no production Analytics endpoints.

- At 390×844, the navigation action was visible from Y=12 through Y=56 and the hero action from
  Y=606 through Y=656. The document had no horizontal overflow.
- At 1280×720, the navigation action was visible from Y=17 through Y=59; the hero action began at
  Y=746, immediately after the hero explanation.
- Both untagged fallbacks retained `acquisition=direct`, `intent=projects`, and no campaign or
  creative.
- The exact Facebook Feed first touch rewrote both actions to
  `facebook / organic-social / rough-to-useful-v2 / rough-to-useful-current-feed / projects`.
- A later organic-search campaign in the same tab could not replace that first touch.
- A fresh organic-search first touch rewrote both actions to
  `organic-search / workflow-guide / rough-idea-launch-plan / search-article / projects`.
- The real browser reported no page errors.

The production check opened only the canonical untagged guide and did not click either action.
After stylesheet settlement, both links were visible with the exact copy, direct fallbacks, and
`5.9.76-guide-proof-to-start-1` stylesheet.

## Automated and release verification

- Full Python suite: **894 collected**, **892 passed**, two environment-dependent tests skipped.
- Focused search/attribution/public-destination/revenue suite: **45 passed**.
- JavaScript integration contract: **49 files** and **6/6** rough-to-useful runtime cases passed.
- Ruff, Python compilation, production preflight, native web build, and diff integrity passed.
- Main CI `34255604311`: success.
- Android Store Bundle Verification `34255604320`: success.
- iOS Store Source Verification `34255604266`: success.
- Production deployment `dpl_DoFMdKCk8c4dHp8kaJ4rNMgh3mUq`: READY on all six aliases with no
  alias error.
- Canonical guide and `/api/health`: HTTP 200.
- Initial 30-minute runtime-error query: empty.

## Release identity and exact bytes

- Feature commit: `dadd5d17f153790235bf5dae6ca0797f2b129e57`
- Base: `07b567dd2be9e967229a88c775777fb3159423fe`
- `public/guide.css` live/local SHA-256:
  `9217FB1462986DF1206309F5B22BBBC72ECF3C2C68C5E56B0E7E83BE8F395736`
- `public/guides/rough-idea-six-week-launch-plan.html` live/local SHA-256:
  `07ACCCC9D5AFA6799DE66BE401AED76D8EE443EFF3B84D1860B25C809044162C`
- `tests/test_search_guides.py` SHA-256:
  `B23B4D9F5A7C521D724651B311959116469D94BB61C0EA0C123833060AE234E4`

## Boundary and next evidence

No production tagged URL, CTA click, account, registration, session, product event, campaign,
composer action, publication, Featured-state change, boost, advertisement, checkout, payment, or
spend was created during this release. The separate Reel attribution candidate remains local-only
and production still rejects that Reel creative.

Observe legitimate untagged and separately authorized campaign traffic through start, account
creation, activation, durable Project/artifact value, and return before claiming conversion lift.
Do not interpret page views or button presence as users, activation, retention, payers, or revenue.
