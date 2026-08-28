# Ask Crump Search Console release gate — 2026-08-27

## Verified external state

- The `sc-domain:askcrump.com` property is verified and accessible in Google Search Console.
- The Overview page says performance and indexing data are still processing.
- The Submitted sitemaps table contains no rows (`0-0 of 0`). The sitemap is not entered,
  submitted, accepted, or read by Google yet.
- URL Inspection reports that `https://www.askcrump.com/` is on Google and indexed.
- URL Inspection reports that the AI presentation maker, AI document generator, AI résumé builder,
  and AI video generator are not on Google because each URL is currently unknown to Google. None
  reports a referring sitemap or referring page in the indexed-data view.
- A read-only live URL test of `https://www.askcrump.com/ai-video-generator` passed on 2026-08-27:
  Search Console reports that the URL is available to Google and the page can be indexed. No
  indexing request was made.
- Search Console reports `No issues detected` for both Manual Actions and Security Issues.
- `https://www.askcrump.com/sitemap.xml` returns HTTP 200 as XML and contains the six intended
  canonical URLs: home, AI presentation maker, AI document generator, AI résumé builder, AI video
  generator, and legal/privacy.
- `robots.txt` returns HTTP 200 and points to the canonical sitemap.
- The canonical pages and production health endpoint return HTTP 200 on release 5.9.32.

## HTTPS reconciliation

Search Console's HTTPS report was last updated on 2026-08-26, before the current discovery release.
It lists one HTTPS example (`https://askcrump.com/`, last crawled July 8, 2026) and one
`HTTPS not evaluated` item. That stale, unevaluated item is not evidence of current insecure delivery.

Direct production checks confirm that all four origin variants redirect to the canonical HTTPS host:

- `http://askcrump.com/` → `https://www.askcrump.com/`
- `http://www.askcrump.com/` → `https://www.askcrump.com/`
- `https://askcrump.com/` → `https://www.askcrump.com/`
- `https://www.askcrump.com/` remains canonical

The final response includes HSTS and the page declares `https://www.askcrump.com/` as canonical.

## Owner-confirmed submission action

After Greg explicitly says **submit sitemap**, enter exactly:

`https://www.askcrump.com/sitemap.xml`

Then click Search Console's **Submit** button and record the resulting status, submission time,
discovered-page count, and first/last read evidence. Do not claim the sitemap is accepted or the
pages are indexed until Search Console shows those states.

## Post-submission evidence gate

- Search Console lists the sitemap and reports a non-error status.
- Google discovers the intended canonical URLs.
- URL inspection/index coverage distinguishes discovered, crawled, and indexed states.
- The first impression/click data is reconciled with Ask Crump's privacy-safe `organic`
  account-creation attribution.
- No paid acquisition scales from impressions alone; activation and durable-value outcomes remain
  the decision metric.
