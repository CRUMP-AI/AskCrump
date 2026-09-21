# Ask Crump daily operating review — 2026-09-20 ET

Status: read-only production review plus local source-only safety candidates.
No production deploy, database migration, provider start, price change, spend,
publication, or customer-content inspection occurred.

## Production and business evidence

- At 2026-09-21 02:44 UTC, public HEAD checks returned HTTP 200 for
  `www.askcrump.com/`, `www.askcrump.com/app`, and `www.clevercrump.com/`.
  Ask Crump's GET `/api/health` returned HTTP 200 and version `5.9.76`.
  Reachability is not an authenticated workflow or successful PDF preview.
- The last available protected operating scan (2026-09-21 00:38 UTC, recorded
  in `CHECKOUT_ACCOUNT_ISOLATION_CANDIDATE_2026-09-20.md`) found 1,548
  HTTP 200 and two HTTP 404 responses with no 5xx in the preceding 24-hour
  runtime sample. It found zero external signups over seven days. The comparable
  30-day cohort was one activated account, without durable Project/artifact
  or payer milestone. These are historical window values, not a fresh query
  made for this note.
- Recognized revenue, refunds, variable cost, and therefore progress toward
  the $1 million revenue target are unavailable, not zero. The one-million-user
  target is not inferred from page views or this small cohort.
- Facebook/Instagram pages could not be reliably read from this environment;
  current activity and active-campaign performance are unavailable here.
  Marketing remains owned by the separate marketing task; no campaign was
  published or changed in this review.

## Highest-value task advanced

An isolated integration branch combines checkout account isolation, owner-scoped
video recovery, a staged server-side video/deletion fence, and conversational
document delivery verification. The client now retains the same idempotency
key when provider start is uncertain and blocks another start while the
server's owner-scoped job reports reconciliation pending. The server candidate
fences deletion before billing/storage cleanup, settles same-key claims,
blocks fresh starts while an unknown claim exists, and rotates shared
background-worker priority. Independent bounded review found no remaining
confirmed P1/P2 in those revised source paths, including demo reset.

The PDF Files viewer has a reproduced production policy mismatch: its private
same-origin content route redirects to signed Supabase storage, while the
deployed parent page lacks an allowed `frame-src` for that target. A source-only
exact-origin policy candidate and parity test pass; an offline browser probe
reached the synthetic 302 and PDF response, but headless Chromium did not
establish a visibly rendered PDF iframe. Do not call PDF Open fixed.

Combined local validation: full Python suite green except two known,
environment-dependent Argon2 tests excluded; 49/49 offline browser verifiers;
16 video-owner scenarios; 54 JavaScript files; focused PDF policy test;
targeted Ruff and diff integrity. The browser Files verifier still uses a
same-origin PDF mock and cannot prove the signed-storage experience.

## Decision, release blockers, next action

Keep production on `5.9.76`. Do not promote this candidate yet. The staged
video SQL has not been numbered, applied, or exercised by two concurrent
PostgreSQL connections; RLS/grants/triggers, old-worker quiescence, and an
operator/retention policy for no-provider-ID claims remain hard gates. The
modified client also needs service-worker/asset version bumps, a native build,
and CI before release. The exact-origin PDF header change is a security-policy
change and requires an authenticated owned-file signed-response check,
including small/large downloads, before production promotion. GitHub's
connected PR operation returned 403, and the browser route requires fresh
action-time confirmation; no alternate submission was attempted.

Exact next action: validate the staged SQL on a disposable two-connection
PostgreSQL instance, decide the unknown-claim operator policy, then package
the integrated code with fresh cache versions and full release checks. Hold
production deployment until the separate PDF signed-file boundary is proven.
