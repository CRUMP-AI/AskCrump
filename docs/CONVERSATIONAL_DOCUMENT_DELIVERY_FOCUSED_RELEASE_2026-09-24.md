# Conversational document delivery focused release

Date: 2026-09-24
Base: `5e96bc6eb0ef84b01e897d464db06a63eeafb924`
Branch: `release/document-delivery-focused-20260924`
Status: deployed and live-verified on production deployment `dpl_CRzcktWawEagAY8XYiBDoDNnh19c`

## User outcome

Ask Crump can now treat a direct file request as authoritative even when semantic routing notices
words such as “video,” “image,” “book,” or “novel.” Short-form Word, PDF, PowerPoint, and Excel
requests produce a durable private artifact in chat. Intentional book-scale DOCX, PDF, and EPUB
requests remain in the persistent Manuscript workflow instead of being collapsed into one chat
answer.

Generated artifact cards expose distinct **Open**, **Download**, and **Add to Project** actions.
Open stays inside Ask Crump. PDF previews follow the authenticated `/api/files/{id}/content`
redirect and can frame only the exact configured Supabase project origin. Word, PowerPoint, Excel,
and other non-previewable formats show the existing in-app download handoff.

## Reliability and privacy boundaries

- Generated documents receive a private semantic fingerprint derived from their render inputs.
  An identical retry reuses the same confirmed private version. Changed content receives a new,
  immutable fingerprint-derived file ID and one-write Storage path. Only after the assistant reply
  containing that exact version is durable does the service soft-retire older rows for the same
  logical message output. The fingerprint and logical identity are stripped from every public file
  response.
- A retry first reconciles an already committed assistant reply from the durable conversation. This
  covers the case where persistence committed but the client received a transport error, avoiding
  a second AI call or a mismatched replacement artifact.
- Signed read URLs fail closed unless they use HTTPS, the exact configured Supabase host, no
  credentials/port/fragment, the exact requested private object path in the configured bucket, and
  a non-empty token. A valid URL for a different object in the same bucket is rejected.
- Native image, video, and PDF previews resolve owner-scoped signed URLs. Native Word, PowerPoint,
  and Excel Open actions no longer depend on Storage signing because they use the local download
  handoff. Native generated-document/manuscript downloads emit the same content-free, idempotent
  `ArtifactDownloaded` measurement as the authenticated web content route.
- The exact source-controlled PDF frame origin contract is enforced for both Vercel production and
  preview deployments, so a preview cannot start with a Supabase origin that its CSP would block.
- AI- or attachment-derived spreadsheet cells can execute only a small local formula allowlist
  (A1 arithmetic plus safe aggregates). Network-capable, external-workbook, named-range, quoted,
  and unknown formulas remain literal text.
- Reply ownership uses an eight-minute lease plus a per-claim UUID. Every completion/failure
  transition is token-fenced, legacy rolling callers clear inherited tokens, unexpected
  pre-persistence failures release only their own claim, and confirmed usage is refunded before a
  safe retry. Once persistence is ambiguous, the claim stays fenced and the client is told to wait
  for the full lease rather than regenerate after three seconds.
- Keyed allowance and paid-credit RPCs retry transient transport failures safely. A response lost
  after commit converges to an ownership-neutral duplicate receipt, cannot double-charge, and
  cannot refund the original successful owner. Legacy unkeyed v1 actions remain single-attempt.
- New generated files and new direct uploads use `cacheControl=0`. API redirects and signed-URL
  responses remain `no-store`. Existing objects keep their historical Storage metadata until a
  separately bounded rewrite or natural replacement; this release does not mutate old objects.
- The PWA advances from the deployed cache `r249` to `r251` and versions both the runtime loader and document
  composer as `5.9.76-document-delivery-focused-1`, so returning devices do not retain the old
  artifact card or upload behavior.

## Required deployment order

1. The separate durable account-Storage deletion release is deployed and verified. It remains the
   privacy prerequisite because immutable version paths must stay covered by the product's
   permanent account-deletion promise.
2. `migrations/20260924213808_align_chat_job_lease_with_ai_timeout.sql` was applied and its ledger
   entry verified **before** deploying this application commit. The app immediately calls
   `claim_chat_job_v2`, `release_chat_job_claim`, and
   `retire_generated_document_versions`; reversing this order breaks normal chat requests.
3. Deploy the application commit, then run the founder-owned production acceptance below.

The migration is additive and backward-compatible with the prior app. A rollback may therefore
move the app back first; legacy `claim_chat_job` explicitly clears v2 ownership tokens during
reclaim.

## Executable evidence

- Full Python test suite on the rebased privacy foundation: **1,325/1,325 passed**.
- Final combined focused backend review: **233 passed**. Native/web file-delivery, CSP, analytics,
  billing transport, cache, button, retry, and persistence fixtures also passed their focused gates.
- PostgreSQL 17 migration gate: passed for claim creation/busy/takeover, stale-token rejection,
  legacy rolling-deploy fencing, completed-response reconciliation, service-role-only privileges,
  and owner-scoped artifact-version retirement. Production ledger entry
  `20260924213808 align_chat_job_lease_with_ai_timeout` is verified.
- Ruff on every changed Python file: passed.
- JavaScript integration contract: 54 files passed, including 24/24 rough-to-useful, 10/10
  Word/PDF, 10/10 résumé, and 21/21 store-packet cases.
- Browser control matrix: 49/49 passed.
- Mobile and desktop document browser proof: DOCX/PDF/PPTX Open and Download actions, Files overlay
  layering, exact signed PDF origin request, zero new windows, zero CSP violations, zero console
  errors.
- Returning-PWA proof: frozen `r249` cache removed; `r251` served the focused runtime and composer.
- Visual upload proof: multipart upload carried `cacheControl=0`; reference preview remained stable.
- Production preflight, native web bundle, client-secret scan, and `git diff --check`: passed.

All browser evidence used local fixture accounts/content. The exact signed PDF transport was blocked
at Chromium’s network layer after CSP acceptance; no customer file or production signed object was
requested. The additive database migration was applied after the hosted PostgreSQL gate; no
customer data or storage object was read or changed. The application deployment, pricing, and
public surface remain unchanged at this checkpoint.

## Release boundary

The privacy prerequisite, hosted PostgreSQL gate, and database-before-app order above are proven.
The application commit is merged and production now serves cache `r251` and runtime
`5.9.76-document-delivery-focused-1` with no browser-console or recent Vercel runtime errors.
Founder-owned acceptance should verify: create a DOCX and PDF in chat, Open each
while Files or a Project overlay remains mounted,
download both on desktop and iPhone/PWA, refresh, and confirm the same artifacts remain attached to
the same conversation. Also regenerate one changed version from the same message and confirm the
conversation exposes only the newly committed version.
