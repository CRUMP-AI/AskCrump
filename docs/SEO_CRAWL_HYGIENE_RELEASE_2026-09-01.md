# SEO Crawl Hygiene Release — 2026-09-01

Status: **RELEASED — CODE STEP ONLY**  
Base: `80ad5fa9768ca9ddbf01c4bb7500c37b67346501`  
Code commit: `dc02d85a894e486656680b9b731f8d9760b957d7`  
Production deployment: `dpl_GrNYVNoACdRimxudZavnes6Y4uDz` (`READY`, six aliases)

## User and search outcome

Ask Crump's signed-out `/app` shell can now be fetched by crawlers so they can receive two independent no-index directives. The shell remains excluded from search results by both the rendered `noindex,nofollow` meta directive and the exact HTTP `X-Robots-Tag: noindex, nofollow` response header. Public acquisition pages remain indexable. `/api/` and `/delete-account` remain blocked in robots, and `/app` remains absent from the sitemap.

The release changed exactly three code paths:

1. `public/robots.txt` removed only `Disallow: /app`.
2. `vercel.json` added only the exact `/app` response-header rule.
3. `tests/test_revenue_conversion.py` now enforces the crawl/no-index boundary and the unchanged public-indexability boundary.

No copy, canonical, sitemap membership, authentication, attribution, analytics, billing, API, database, migration, cache-version, native source, or customer data changed.

## Verification

- Complete Python suite: 711 passed.
- JavaScript contract: 47 files passed.
- Production preflight and native web bundle: passed.
- Store metadata and signing-secret source controls: passed; store credentials, screenshots, privacy forms, and console submission remain release-time gates.
- Exact three-path release verifier and immutable trust-boundary hashes: passed.
- Production `/app` and `/app?signup=1`: HTTP 200 with `X-Robots-Tag: noindex, nofollow`.
- Rendered signed-in `/app`: `meta[name=robots]` equals `noindex,nofollow`; Projects opened and closed; the Ask composer remained usable.
- Public `/ai-document-generator`: HTTP 200 with no response-level no-index header.
- Live robots body contains only `Allow: /`, the `/api/` and `/delete-account` blocks, and the canonical sitemap line.
- Production deployment window: no runtime error clusters.

## Held actions

The separate `askcrump.com` redirect change remains **not executed**. Live behavior is still one HTTP 307 hop to the same `https://www.askcrump.com` target with path and query preserved. A possible 307-to-308 change must receive its own exact action-time review and verification.

No Search Console, sitemap-submission, DNS, publication, social, email, account, payment, or spend action was performed.

Machine-verifiable release evidence is in `docs/seo-crawl-hygiene-release.json` and `scripts/verify-seo-crawl-hygiene-release.mjs`.
