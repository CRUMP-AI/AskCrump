# Evidence-led search guides release — 2026-08-30

## Outcome

Three marketing-approved workflow guides now return direct production `200` responses instead of
`404` pages:

- `https://www.askcrump.com/guides/rough-idea-six-week-launch-plan`
- `https://www.askcrump.com/guides/what-ai-project-should-remember`
- `https://www.askcrump.com/guides/editable-ai-powerpoint-review`

Each page is an editorial field note rather than a duplicate feature page. The pages show authentic
Ask Crump screens or current-exporter slide renders, visibly identify Clever Crump as the author,
state the August 30 evidence date and testing method, disclose fictional or synthetic source
material, name the human-review boundary, link to an adjacent workflow, and provide one matched
product action.

The earlier audit spelling `/guides/editable-powerpoint-review-checklist` is not canonical. It now
returns a permanent `308` redirect to the marketing system-of-record path
`/guides/editable-ai-powerpoint-review`. Guide requests on Clever Crump similarly redirect to the
single Ask Crump host so no duplicate editorial origin is created.

## Evidence and claim boundary

The release uses the exact approved first-hand inputs:

- the fictional Savannah reading-series prompt, response, and saved Project;
- the current live presentation capability screen;
- three current-exporter slide renders; and
- the preserved PowerPoint inspection result for a ten-slide `.pptx` with native text on all ten
  slides, one native table, one native chart, and no embedded image media.

The seven public image files are byte-identical to the marketing evidence sources. Automated tests
pin every SHA-256 value, including the representative chart hash
`CD806EE318A086181CCCABD51407A8CB5CF0B63B45B79AAB6659FC7E81F07C24`.
No customer content, testimonial, private metric, generated person, reconstructed product screen,
rating, review schema, FAQ schema, or HowTo schema was added.

## Attribution contract

The guide paths now supply the correct creation intent before campaign validation:

| Guide | Intent | Campaign |
| --- | --- | --- |
| Rough idea → six-week plan | `projects` | `rough-idea-launch-plan` |
| Project memory boundaries | `projects` | `project-memory-boundaries` |
| Editable PowerPoint review | `presentation` | `editable-powerpoint-review` |

An allowlisted social tuple can therefore land on a guide without a redundant `intent` query and
remain intact through the relevant capability page and signup. A fresh canonical visit from a
recognized search referrer receives the registered content-free tuple
`organic-search / workflow-guide / guide campaign / search-article`. A direct or unlabeled visit is
not mislabeled as search. An existing unexpired first touch remains immutable; later guide or
campaign visits cannot overwrite it.

No prompt, response, filename, customer identifier, email address, referrer URL, or arbitrary
campaign value is stored by this change.

## Discovery and delivery

- Each guide has one self-referencing canonical, unique title and description, `Article` structured
  data, current author/date/method disclosure, social metadata, image dimensions and alt text.
- Projects links back to both Project guides; Presentations links back to the PowerPoint guide.
- The three clean canonical URLs are present once in the Ask Crump sitemap.
- The phone layout collapses to one column, keeps proof images at intrinsic aspect ratio, wraps the
  long evidence hash, and constrains the content shell to the viewport.
- The marketing spelling correction is represented only as a permanent redirect and is absent from
  the sitemap and canonical metadata.

## Verification

- Commit: `6c48206ebeca84adbce3d1347e30bbeaa0cdc7b9`
- Production deployment: `dpl_EPHRiHFTBW8tRvw6ewdXXgQqPA7R`
- Vercel state: `READY`, production, six aliases, no alias error
- Full automated suite: 612 tests passed
- Focused guide/routing/attribution suite: 42 tests passed
- JavaScript contract: 47 files validated
- Python lint and compilation: passed
- Production preflight and native web bundle: passed
- Store metadata and mobile signing-source controls: passed
- Diff integrity: passed
- All three canonical guide responses: HTTP `200`
- Old PowerPoint audit slug → canonical guide: HTTP `308`
- Clever Crump guide duplicate → Ask Crump canonical: HTTP `308`
- Live sitemap and responsive stylesheet: HTTP `200`
- Live representative chart: HTTP `200`, byte-identical SHA-256
- Deployment error scan: no runtime error cluster; no warning, error, or fatal runtime log; observed
  deployment responses were HTTP `200`

The local in-app browser runtime could not start because its Windows sandbox helper exited during
setup. No rendered screenshot or physical-phone overflow result is claimed. Automated phone-width
layout, intrinsic image sizing, alt-text, content-boundary, and no-long-token-overflow checks passed;
the marketing action-time physical-phone preview remains a separate publication gate.

## External-action boundary

This release did not publish a social post, edit a social profile, submit a sitemap to Search
Console, request indexing, start a campaign, spend advertising money, send lifecycle messaging, or
create production customer activity. Marketing publication and Search Console action remain held
for explicit action-time approval.

## Rollback

Revert commit `6c48206` and redeploy. The previous production deployment is
`dpl_HYErv8bb9k5tQFYFd84CA3xCDFro`.
