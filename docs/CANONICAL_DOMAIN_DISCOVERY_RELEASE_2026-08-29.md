# Canonical domain and discovery release — 2026-08-29

## Outcome

Ask Crump and Clever Crump now expose one canonical public identity each. Direct
requests for internal landing slugs no longer produce duplicate 200 pages, Ask-product
routes opened on the Clever Crump host move to AskCrump.com, and each domain resolves
its own robots and sitemap content.

Production release:

- commits: `b59b7fed0534e77bd345a19acf95af17d44865fb` and
  `0d9167f2bab02c883b14cf51df00eb03f24bba92`
- final Vercel deployment: `dpl_9mWErW7aui3eoV2Xp3FddCDia4hL`
- deployment state: `READY`
- production aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project aliases
- custom Python/static framework; final build duration approximately 47.7 seconds

## Evidence before the correction

Read-only production requests established four structural acquisition problems:

- `https://www.askcrump.com/` and `/ask-crump` both returned HTTP 200 with the
  same 17,063-byte product page.
- `https://www.clevercrump.com/` and `/clever-crump` both returned HTTP 200 with
  the same 8,975-byte company page.
- `https://www.askcrump.com/clever-crump` also returned the company page as 200.
- CleverCrump.com served AskCrump.com’s `robots.txt` and sitemap; its own homepage
  was absent from the sitemap response.

The HTML canonical tags were correct, but canonical hints are weaker than eliminating
duplicate crawlable responses at the routing layer.

## Correction

- `/ask-crump` permanently redirects to `https://www.askcrump.com/`.
- `/clever-crump` permanently redirects to `https://www.clevercrump.com/`.
- Clever-host requests for `/app`, the four public creation pages, `/legal`, and
  `/delete-account` permanently redirect to their AskCrump.com counterparts.
- Campaign, plan, signup, and other query parameters remain intact through every
  redirect; no attribution value is parsed, logged, or rewritten by the rule.
- Ask Crump’s robots file now blocks the clean `/delete-account` path rather than
  only the noncanonical `.html` form.
- Clever Crump has a dedicated robots file and a one-URL sitemap containing only
  `https://www.clevercrump.com/`.

The initial production deployment also proved that Vercel’s static-file resolution
precedes host-specific rewrites for existing `robots.txt` and `sitemap.xml` files.
Commit `0d9167f` replaced those two ineffective rules with same-host permanent
redirects, which Vercel evaluates before the static-file response and standard search
crawlers follow.

## Verification

- 462 Python regression tests passed.
- 45 JavaScript files passed syntax and integration validation.
- Production build preflight passed.
- Native web bundle rebuilt successfully.
- Store metadata source verification passed.
- Both canonical roots return direct HTTP 200 responses with zero redirects.
- Ask `/ask-crump` resolves to the Ask root in one redirect; the noncanonical apex
  form resolves in two because the existing apex-to-www redirect runs first.
- Both direct company-slug variants resolve to the Clever root in one redirect.
- Clever `/app?signup=1&source=audit&plan=free` resolves to the exact Ask app URL
  with all three query values intact.
- Clever public creation-page queries resolve to their exact Ask counterparts with
  attribution intact.
- Clever `/robots.txt` and `/sitemap.xml` each resolve in one redirect to 200
  same-host content. The final Clever sitemap contains CleverCrump.com and no
  AskCrump.com URL; the Ask sitemap contains AskCrump.com and no CleverCrump.com URL.
- The final deployment reached `READY` with all six aliases and no alias error.
- The observed final release window contained 18 HTTP 200 runtime responses, no
  4xx or 5xx runtime response, and no runtime error cluster.

## Outcome boundary

The routing defect is corrected; organic growth impact is not yet proven. Review the
first complete 28-day post-release window against the preceding 28 days for:

- organic entry sessions on both canonical homepages;
- search impressions and clicks by canonical page when Search Console data is
  available;
- duplicate/alternate-canonical coverage state after recrawl; and
- signup intent and account creation attributed to the existing allowlisted search
  acquisition category.

Do not infer growth from crawl correctness alone. No sitemap was submitted to Search
Console in this release because the separate required owner approval phrase was not
provided.
