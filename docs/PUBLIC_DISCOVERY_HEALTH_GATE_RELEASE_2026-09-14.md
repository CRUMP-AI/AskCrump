# Public discovery health gate release — 2026-09-14

## Outcome

Ask Crump's existing daily, credential-free public-destination check now protects the full
technical discovery surface instead of proving only that links return HTTP 200. Every canonical
sitemap page must keep one nonempty title, description, H1, responsive viewport, explicit
index/follow directive, and matching canonical. Search-facing pages must also keep valid JSON-LD,
matching Open Graph and Twitter metadata, and a directly retrievable first-party preview image.

The verifier fails on missing or duplicate page identity, broken structured data, a noindex or
nofollow regression, a mismatched social image, an image served with the wrong media type, or an
unexpected redirect. It remains a safe GET-only check with bounded transient retries, no secrets,
no login, and no database or account access.

## Live production proof

The strengthened verifier passed against production with:

- **67** unique first-party anchor destinations;
- **12** canonical sitemap pages;
- **69** direct HTTP 200 destinations;
- exactly **2** reviewed native-compatibility redirects;
- **9** distinct first-party social-preview images; and
- valid title, description, H1, indexability, canonical, structured data, and responsive viewport
  across the applicable sitemap pages.

A separate user-eye browser walkthrough applied the ready application update and safely exercised
Projects, Files, a foreground image preview and return, Video, Library, You, Plan & credits, Account,
Create → Document Studio, Intelligence, Chats, and Continue. Each destination opened its owned
surface and returned without a browser-visible failure. The walkthrough did not purchase, delete,
sign out, upload, download, generate provider media, change account settings, or invoke a native
permission.

The public browser also opened the homepage's **See a real workflow** action into the canonical
rough-idea guide. Direct entry correctly remained campaign-free; the existing browser contract
separately proves that genuine organic-search entry receives only the approved
`organic-search / workflow-guide / rough-idea-launch-plan / search-article / projects` tuple.

## Verification

- focused discovery/search tests: **24/24**;
- complete Python suite: **1,108/1,108**;
- JavaScript validation: **54/54** files;
- browser control matrix: **48/48**;
- live public discovery proof: passed;
- whitespace guard: passed.

The first browser-matrix attempt failed before a product assertion because the local default
Python command was unavailable. A second launch used the configured validation Python and Edge
runtime and passed all 48 verifiers. This was an environment invocation correction, not a product
failure.

## Boundary and next evidence

This release improves the durability of organic discovery evidence. It does not submit the sitemap,
claim indexing or ranking, create visits or accounts, prove guide conversion, or authorize
publication or spend. Search Console submission remains owner-gated. The next product decision still
depends on the first valid D1 read after 2026-09-15 00:00 UTC and legitimate guide → account → useful
work → Project or artifact evidence.
