# Public accessibility release evidence

Date: 2026-08-27
Release: 5.9.33 / native build 50933
Code commit: `8d03ce7629da6791626377320ddc215f59960879`
Production deployment: `dpl_9sMBVqXWhqSS3QgRkXYKr1G3b62o`

## Decision

The 5.9.32 public pages were fast, stable, and technically discoverable, but a mobile Lighthouse
baseline found repeated low-contrast supporting copy. That is a material first-visit quality defect:
important qualification, pricing, engine, and workflow text should not require ideal vision or an
ideal display to read.

The correction is deliberately narrow. It raises muted foreground colors to WCAG 2.1 AA contrast
without changing the black/charcoal/gold brand, page structure, claims, authentication, billing,
private data, or acquisition attribution.

## Delivered

- The homepage's stage label, composer text, engine labels, engine notes, price notes, credit note,
  fine print, hero footnote, and muted stage-card text now meet a minimum 4.5-to-1 contrast ratio
  against their actual dark surfaces.
- Use-case proof text now uses the same accessible muted foreground and meets the same threshold.
- A deterministic WCAG relative-luminance test covers ten selector/background pairs so these exact
  public text roles cannot silently regress below 4.5-to-1.
- Marketing stylesheet URLs advance to 5.9.33 and the application service-worker cache advances to
  `r67`, preventing returning clients from mixing old foreground colors with new release assets.

## Baseline and result

The production 5.9.32 mobile baseline reported 13 contrast failures on the homepage and four on the
resume page. Representative failing ratios included 3.31-to-1 for composer copy, 3.33-to-1 for
pricing fine print, 3.49-to-1 for engine notes, 4.12-to-1 for price notes, 4.27-to-1 for the stage
label, and 4.33-to-1 for use-case proof text.

| Page | Production 5.9.32 | Production 5.9.33 |
| --- | --- | --- |
| Homepage | Performance 99, accessibility 95, best practices 100, SEO 100; 13 contrast failures | Performance 100, accessibility 100, best practices 100, SEO 100; zero contrast failures |
| Résumé page | Performance 100, accessibility 95, best practices 100, SEO 100; four contrast failures | Performance 100, accessibility 100, best practices 100, SEO 100; zero contrast failures |

The 5.9.33 production mobile runs recorded 0.9-second first contentful paint, 1.7-second largest
contentful paint, zero blocking time, zero layout shift, and 40-millisecond root-document response
time on both pages. The homepage speed index was 1.0 seconds and the résumé page speed index was
0.9 seconds. These are point-in-time verification runs, not a claim that the color change caused a
performance improvement.

## Verification

- 307 backend and contract tests passed, including the deterministic WCAG selector checks.
- Ruff checks passed and all 41 JavaScript files passed the integration validator.
- Production preflight, native web-bundle generation, Android 5.9.33/build 50933/API 36 verification,
  store metadata limits, and signing source-control checks passed.
- Hosted CI run `33132384656`, Android run `33132384622`, and iOS run `33132384717` completed
  successfully. The iOS workflow generated and compiled the unsigned candidate; final signing and
  device gates remain owner-controlled.
- Production health returned 5.9.33. The homepage and résumé page returned HTTP 200 and referenced
  the 5.9.33 landing stylesheet; the résumé page also referenced the 5.9.33 use-case stylesheet.
- Phone-size browser checks at 390 by 844 found no horizontal overflow, missing primary action,
  browser-console warning, or browser-console error on either page. No CTA was clicked and no
  synthetic conversion event was created.
- The deployment is `READY` on every Ask Crump and Clever Crump production alias. The inspected
  release window contained no runtime error cluster; all displayed deployment log responses were
  HTTP 200.

## Outcome boundary

This is verified accessibility and delivery quality, not verified acquisition or conversion lift.
No advertising spend, social post, mass outreach, price, billing setting, authentication behavior,
private record, sitemap submission, or indexing request changed in this release.

Google has already confirmed that a capability page is live-crawlable, while Search Console still
shows zero submitted sitemaps. Discovery remains gated on the owner's exact `submit sitemap`
instruction. The separate manual sign-out and credential-entry recheck remains the final human proof
for the earlier web-session repair.
