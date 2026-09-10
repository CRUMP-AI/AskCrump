# Word/PDF public organic-search guide release — 2026-09-10

## Outcome

Ask Crump now publishes one indexable, self-canonical guide at
`https://www.askcrump.com/guides/word-or-pdf-ai-document-output`. It uses four
accepted authentic product-evidence images, explains when an editable Word file
or fixed-layout PDF is appropriate, includes one honest internal link from the
public document page, and appears exactly once in the sitemap.

The guide contains one Free-start action. Its raw fallback is deliberately
campaign-free:

| Signup | Plan | Acquisition | Source | Intent |
| --- | --- | --- | --- | --- |
| `1` | `free` | `direct` | `word-pdf-start` | `document` |

The existing first-touch resolver upgrades that action only after a recognized
organic-search guide entry:

| Acquisition | Placement | Campaign | Creative | Intent |
| --- | --- | --- | --- | --- |
| `organic-search` | `workflow-guide` | `word-or-pdf-decision` | `search-article` | `document` |

A direct or unlabeled visit remains direct with no campaign or creative. An
existing valid first touch remains immutable through later campaign URLs,
verification return, and sign-in.

## Review correction

The first pushed page sent its Free-start action to the document capability page
and embedded search labels in the fallback URL. Marketing's independent
pre-deployment review rejected that behavior because a direct visitor should not
be labeled as search traffic and a button labeled “Start free” should open
registration.

Commit `7fbde4b713ab3e4359c197c9297b72f001b28740` superseded the earlier build
with the established direct-safe registration pattern and executable direct,
recognized-search, immutable-first-touch, verification-return, and sign-in
coverage. The corrected build is the current production deployment.

## Database and privacy boundary

Migration `20260910141831 release_word_pdf_search_attribution` adds only
`word-or-pdf-decision` to the campaign allowlist, adds its one exact registry
branch, and updates the existing AccountCreated writer. It does not add the held
`word-or-pdf-social` campaign or any social creative.

The writer remains `SECURITY INVOKER`, has an empty search path, denies execute
to PUBLIC, `anon`, and `authenticated`, and grants execute only to
`service_role`. Both updated constraints are validated.

A rollback-only production exercise proved:

1. the exact organic-search tuple writes once;
2. an identical retry is idempotent;
3. wrong source, placement, creative, intent, and blank-creative variants fail
   closed without retaining campaign or creative;
4. a direct invalid cross-product violates the database constraint;
5. the exact tuple appears in the privacy-safe weekly aggregate;
6. the writer's privilege boundary remains intact; and
7. rollback leaves zero synthetic users and zero synthetic events.

After the live migration, the two updated constraints were validated, the writer
contained the exact new campaign, the privilege checks remained unchanged, and
production contained zero `word-or-pdf-decision` events. No tracked campaign
visit or customer event was manufactured.

Supabase advisors remained at the pre-existing informational baseline: one
`rls_enabled_no_policy` category covering 61 service-role-only tables and one
`unused_index` category covering 59 indexes. No new warning or error appeared.

## Validation and delivery

- Final commit: `7fbde4b713ab3e4359c197c9297b72f001b28740`.
- Complete Python suite: **978 passed**.
- JavaScript contract: **49 files**, **21/21** rough-to-useful cases, and
  **10/10** Word/PDF cases passed.
- Button/browser matrix: **37/37** verifiers passed.
- Marketing source gate: **35/35** checks passed without opening a tracked URL.
- Live marketing gate: **55/55** checks passed.
- Phone and desktop guide renders had no horizontal overflow, missing image,
  console error, or unintended external request.
- Ruff, Python compilation, production preflight, native web build, and diff
  integrity passed.
- GitHub Actions:
  - CI `34488720250` — success;
  - Android Store Bundle Verification `34488720301` — success;
  - iOS Store Source Verification `34488720283` — success.
- Production deployment
  `dpl_7mEEXrJMrhfcDpshPJifRqFFhJU9` is READY for the final commit.
- The guide, four evidence assets, landing JavaScript, authentication JavaScript,
  sitemap, public inlink, and private-app noindex boundary passed live
  byte/contract verification.
- All four custom-domain health checks returned HTTP 200 on Ask Crump 5.9.76.
- The initial 30-minute runtime-error, HTTP 5xx, and warning/error/fatal scans
  were empty.

## Decision boundary

This release authorizes the public organic-search guide and its exact
measurement destination only. It does not authorize social publication, the
held `word-or-pdf-social` campaign, Search Console action, paid traffic,
advertising, billing changes, purchases, spend, or performance claims. No such
action occurred.
