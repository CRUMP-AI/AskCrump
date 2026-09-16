# Facebook cell 118-minute technical observation

Observed through: 2026-09-16 19:25:41 UTC

Publication boundary: 2026-09-16 17:28:00 UTC

Exact tuple: `facebook / organic-social / rough-to-useful-v2 / rough-to-useful-current-feed / projects`

## Read-only evidence

- Vercel's grouped runtime-error report returned no error cluster from the publication boundary.
- Production runtime logs contained at least **165 HTTP 200** responses.
- Explicit grouped queries for HTTP **3xx**, **4xx**, and **5xx** request paths were empty.
- A production log query for `warning`, `error`, and `fatal` entries was empty.
- The service-role-only, production-only weekly attribution export returned no row for the exact
  campaign tuple.

## Interpretation

The application remained technically healthy through this observation. The missing attribution row
means that no production account has yet been recorded with the exact first-touch tuple. It does not
prove a conversion failure: the governing 24-hour window is incomplete, the legitimate exposure
denominator remains unavailable, and the operating rule classifies fewer than 25 viewers with zero
eligible accounts as under-distribution rather than a product-conversion verdict.

Preserve the product, post, Featured state, and distribution variables through the conservative
boundary at 2026-09-17 13:28 EDT. Do not create synthetic traffic, broaden distribution, spend,
deploy the held product candidate, or change the landing/sign-up experience from this early sample.
