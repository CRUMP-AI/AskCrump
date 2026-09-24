# PR 37 reliability integration candidate — 2026-09-21

Status: **draft PR #37, unmerged, and undeployed.** The current reviewed behavior head is
`653d576076095c3bceab8131b0d88b94f5ec0bfa`; the predecessor hosted-green head at the start of
this release-hardening pass was `1a7d23bf5f4193c83304d522b9655f3af060f76a`. This document records evidence for review; it is not
permission to apply a database migration, deploy production, sign a native build, submit to either
store, or spend money.

## Candidate identity and scope

The integration branch combines PR 37's native privacy work through `624a5d2` with reliability
candidate `6ba31cc`, plus hosted-validation corrections through `1a7d23b` and this later
release-hardening candidate. The exact contractor source and its new hosted run receipts must be
recorded in the final work order; predecessor receipts cannot authorize a later commit.

The candidate includes:

- conversational DOCX, PDF, and PPTX delivery through owned Ask Crump routes, plus direct-download
  and Files-viewer behavior that does not expose a Supabase tab; an explicitly selected DOCX, PDF,
  PPTX, or XLSX format remains authoritative over conflicting image, video, or book keywords, and
  the same precedence now applies when the user types the explicit format without using the picker;
- generated artifact cards expose the existing owner-scoped in-app Open viewer as well as Download
  and Add to Project, with an `r257 → r258` returning-PWA cache proof;
- confirmed image references remain ordered, role-mapped edit inputs; reference review receipts are
  persisted; video reference limits are disclosed; and exact logo/wordmark pixels can be placed by
  the deterministic no-AI/no-credit overlay path;
- checkout/account owner isolation, owner-scoped video continuity, and a fresh PWA cache generation;
- native-store source gates, Android page-size verification, and the existing no-credential iOS and
  Android hosted workflows;
- a source-only video-provider-start/account-deletion fence and durable account-deletion recovery;
- a server-authoritative activation boundary that rejects browser-submitted activation and records
  activation telemetry only after durable reply persistence;
- a disposable real-PostgreSQL CI harness for the staged fence SQL; and
- a least-privilege, time-limited boundary for any outsourced store-release specialist, structured
  by a version-three packet covering source, CI references, public certificate identity, store
  console evidence, operator identity, and access closeout, followed by independent owner checks.

The account-deletion recovery commits the users-row fence only through an atomic SQL function.
Begin, establish, recovery, and release serialize on `users` → `account_deletion_jobs` →
`video_account_deletion_fences` → provider claims. Recovery uses the locked, database-authored
video-fence `requested_at` value for freshness, preserves foreign/tombstoned fences, preserves
sticky native-billing cleanup evidence, and fails closed for a live durable job without a matching
fence. The route compensates ambiguous initial acquisition, replacement acquisition, billing
failure, and durable-begin failure with the exact operation token.

## Local verification through `653d5760`

- Final focused deletion/fence/authority/demo suite: **124 passed**.
- Final independent source re-read: no remaining P0, P1, or P2 finding.
- Full Python suite with the exact `pyproject.toml` Argon2 pins loaded: **1,363/1,363 passed**.
- Focused conversation, artifact, and routing regressions: **70/70 passed**. Browser fixtures
  verified owner-scoped DOCX/PDF/PPTX Open and Download targets, zero new windows, Files-layer
  ordering, and behavior at desktop and mobile sizes.
- Activation-authority regressions passed: the authenticated client endpoint returns **422** for
  `ActivationReached`; browser completion has no activation sender; a durably persisted reply
  records the exact server key; exception and malformed-receipt persistence failures return **503**
  without activation; and status GET plus cached-job recovery remain mutation-free. Durable growth
  reports retain their existing completed-job activation fallback. The returning-PWA browser
  proof uses hash-verified frozen copies of the exact committed r253 app and analytics assets. It
  passed the immediate **r253 → r254** cache transition, including the real retired activation POST
  rejected with **422**, preserved completed message state, and replaced both stale senders.
- Adjacent artifact/manuscript routing regression suite: **52 passed**, including selected-format
  precedence and intentional long-form DOCX preservation.
- JavaScript contract: **55 files**; attribution fixtures **24/24**, **10/10**, and **10/10**;
  submission-packet self-test **51/51**.
- Browser-control matrix: **52/52**, including the new `r257 → r258` returning-PWA transition,
  chat artifact Open/Download, file delivery, image stability,
  precision editing, mobile navigation, Projects, Video, and owner continuity.
- Accessibility matrix: **33/33** phone, tablet, and desktop scenarios.
- Store-source tests: **29 passed**; metadata fits Apple and Google field limits; native privacy
  source gate passed.
- Production preflight, native web bundle, and generated-client credential scan passed.
- Relevant Ruff checks, Python compilation, staged and unstaged diff checks, conflict-marker check,
  and whitespace checks passed.

## Predecessor hosted verification on `1a7d23b`

- Clean-checkout CI passed in Python 3.12 and JavaScript, including browser controls,
  accessibility, production bundle, and store evidence:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35566340678>.
- Disposable PostgreSQL 17 verification passed, including candidate compilation and reapply,
  preflight rollback, backfill, grants/RLS, trigger gates, idempotent RPCs, both user-row lock
  orderings, acceptance/deletion races, and reconciliation leases:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35566340631>.
- Android no-upload structural verification passed and produced an unsigned release AAB; the
  16 KB static gate passed:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35566340621>.
- iOS no-upload structural verification passed with Xcode 26.3 and reconciled privacy manifests,
  but its former single-component build value `50976` is invalid for Apple. It is compile/privacy
  evidence only and must be superseded by a valid-build run:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35566340555>.
- The Vercel preview is Ready. GitHub reports seven successful checks and no conflict with `main`.

These runs superseded this document's earlier pending-hosted-check statements for their exact SHA.
They do not cover later release-hardening changes, apply the staged SQL, or prove signed
physical-device/store behavior.

## Current behavior-head hosted verification on `653d5760`

- Clean-checkout CI passed Python 3.12 and JavaScript, including the complete test suite, browser
  controls, accessibility, production bundle, client-secret, and store-evidence gates:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35964017283>.
- Disposable PostgreSQL fence verification passed:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35964017124>.
- Android unsigned structural verification passed:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35964017134>.
- iOS unsigned structural verification passed:
  <https://github.com/CRUMP-AI/AskCrump/actions/runs/35964017328>.
- Vercel preview `dpl_6dSmABiXUUvQWr3iRuFXeJNAJG5g` is Ready for exact commit `653d5760`.
  Authenticated protected-preview reads returned HTTP 200 for health, `/app`, the versioned
  runtime, composer, and worker, with the expected reference-plan, artifact Open, runtime token,
  and `r258` markers.

These runs cover the behavior commit only. They do not apply the staged SQL, deploy production,
sign a native artifact, or prove physical-device/store behavior.

## Remaining owner and release gates

1. The SQL remains a staged source candidate. Create and inspect one numbered Supabase migration
   against a fresh remote migration ledger before any migration-first rollout. Do not deploy
   dependent code first.
2. Publisher accounts, agreements, app records, Firebase, RevenueCat/store product identifiers,
   owner-controlled signing material, and reviewer access still require owner confirmation.
3. Exact signed IPA/AAB artifacts must pass physical iPhone, iPad, and Android journeys, purchases,
   restore, privacy permission, push, deletion, accessibility, screenshots, and the final packet
   hash gate before submission.
4. Native billing requires signed two-device deletion, delayed-resume, account-switch, and in-flight
   purchase/restore verification. Per-operation source checks do not make a third-party SDK call
   atomic with account deletion.
5. The source PDF policy correction still needs an authenticated owned signed-storage check for
   real small/large PDF opening and download.
6. If an outside release specialist is used, hand over only the owner-recorded CI-green commit
   through the restricted roles and evidence milestones in
   `docs/STORE_RELEASE_SPECIALIST_HANDOFF_2026-09-21.md` and `docs/STORE_LAUNCH_RUNBOOK.md`.

No production database, provider, customer content, developer account, store console, deployment,
pricing, billing configuration, or public campaign was changed while producing this candidate.
Existing production activation cohorts remain provisional until a post-deployment cohort is mature;
this source correction does not retroactively certify earlier D1/D7 measurements.
