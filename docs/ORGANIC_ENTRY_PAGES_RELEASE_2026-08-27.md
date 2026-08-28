# Organic entry-page release evidence

Date: 2026-08-27  
Release: 5.9.32 / native build 50932  
Code commit: `afd54732f6d12f71a9f2164b654deba0fe881a2d`  
Production deployment: `dpl_3VQGjdTVUeDNNzRHqRa1UprHHZ2e`

## Decision

The service-role growth funnel contained zero comparable external accounts after the current
measurement boundary. That evidence does not support another onboarding redesign: there is not yet
enough legitimate post-signup behavior to identify an activation step with a measurable drop-off.
Acquisition is the current bottleneck.

The safest acquisition work available without advertising spend, external posting, or an owner
submission was to expand truthful public discovery around capabilities already verified in
production. This release adds two focused entry pages instead of generating a large set of thin or
speculative pages.

## Delivered

- `/ai-resume-builder` explains the existing résumé-specific DOCX path, including editable output,
  restrained ATS-friendly structure, role-focused drafting, and private continuity.
- The résumé page repeatedly requires accurate user-supplied experience and explicitly rejects
  fabricated credentials, employers, dates, skills, metrics, and accomplishments. It does not
  promise parsing, ranking, interviews, or employment.
- `/ai-video-generator` explains the existing Quick, Extendable, and Cinematic paths without
  exposing provider-routing vocabulary as the product. It states that every generation spends the
  displayed Crump Credit amount and that availability, timing, compatibility, and output vary.
- The homepage now links to four reviewed creation paths. The presentation and document pages,
  footers, and the two new pages form a crawlable internal-link graph.
- The XML sitemap contains six canonical URLs. Each new page has a unique title, description,
  canonical URL, Open Graph/Twitter metadata, valid JSON-LD, first-party signup attribution, human
  review guidance, and a deterministic 1,200-by-630 social card.
- Release 5.9.32 advances the app/runtime asset query version and service-worker cache to `r66` so
  returning browsers do not retain mixed release assets.

## Verification

- 306 backend and contract tests passed.
- Ruff checks passed and all 41 JavaScript files passed the integration validator.
- Production preflight and the native web-bundle build passed.
- Android source regenerated and passed the 5.9.32/build 50932, API 36 release verifier. The local
  verifier still warns that the RevenueCat Android public key and `google-services.json` are not
  present in this shell/source checkout.
- Store metadata field limits and mobile signing source controls passed. Signing credentials,
  physical-device checks, screenshots, publisher consoles, billing, and final submission remain
  release-time gates.
- Local Windows configuration reached the expected missing-iOS-project boundary; hosted macOS run
  `33131314943` generated and compiled the unsigned iOS candidate successfully.
- Hosted CI run `33131314907` and Android run `33131314974` completed successfully.
- Desktop visual checks at 1,440 by 1,000 and phone layout checks at 390 by 844 found no horizontal
  overflow, missing primary CTA, broken canonical, or inaccessible main landmark. No CTA was clicked
  and no synthetic conversion event was created.
- Production health returned 5.9.32. Both clean entry URLs, both social-card assets, and the sitemap
  returned HTTP 200. Canonical and credit-disclosure content matched the released source.
- The production deployment is `READY` on the `www.askcrump.com`, `askcrump.com`,
  `www.clevercrump.com`, and `clevercrump.com` aliases. The inspected release window contained no
  runtime error cluster; the deployment log status group contained 32 successful 200 responses and
  no reported non-200 group.

## Outcome boundary

This is verified delivery, not verified acquisition lift. No traffic, signup, activation, revenue,
or retention improvement is claimed. Search Console sitemap submission remains a separate owner
gate, and no advertising spend, social post, mass outreach, price, billing setting, or external
account state changed in this release.
