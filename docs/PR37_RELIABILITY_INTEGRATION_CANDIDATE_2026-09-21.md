# PR 37 reliability integration candidate — 2026-09-21

Status: **local, staged, mid-merge, uncommitted, unpushed, undeployed.** This document records
evidence for review; it is not permission to apply a database migration, deploy production, sign a
native build, submit to either store, or spend money.

## Candidate identity and scope

The integration branch combines the local PR 37 tip `624a5d2` with reliability candidate
`6ba31cc`. The public PR head was still `372b9c4` when the remote was checked, and that remote head
is an ancestor of the local integration, so a later update can be a normal fast-forward without a
force push.

The candidate includes:

- conversational DOCX, PDF, and PPTX delivery through owned Ask Crump routes, plus direct-download
  and Files-viewer behavior that does not expose a Supabase tab;
- checkout/account owner isolation, owner-scoped video continuity, and a fresh PWA cache generation;
- native-store source gates, Android page-size verification, and the existing no-credential iOS and
  Android hosted workflows;
- a source-only video-provider-start/account-deletion fence and durable account-deletion recovery;
- a disposable real-PostgreSQL CI harness for the staged fence SQL; and
- a least-privilege, time-limited boundary for any outsourced store-release specialist.

The account-deletion recovery commits the users-row fence only through an atomic SQL function.
Begin, establish, recovery, and release serialize on `users` → `account_deletion_jobs` →
`video_account_deletion_fences` → provider claims. Recovery uses the locked, database-authored
video-fence `requested_at` value for freshness, preserves foreign/tombstoned fences, preserves
sticky native-billing cleanup evidence, and fails closed for a live durable job without a matching
fence. The route compensates ambiguous initial acquisition, replacement acquisition, billing
failure, and durable-begin failure with the exact operation token.

## Local verification

- Final focused deletion/fence/authority/demo suite: **124 passed**.
- Final independent source re-read: no remaining P0, P1, or P2 finding.
- Full Python suite: exactly two expected local-environment failures, both requiring Argon2:
  `test_successful_legacy_login_upgrades_password_hash` and
  `test_password_round_trip_and_rejection`. With only those two tests deselected, the complete
  remaining suite passed. `pyproject.toml` declares the Argon2 dependency for hosted CI.
- Conversational document-delivery and PDF policy suite: **4 passed**. Browser fixtures verified
  owned DOCX/PDF/PPTX download targets, zero new windows, and Files behavior at desktop and mobile
  sizes.
- JavaScript contract: **55 files**; attribution fixtures **24/24**, **10/10**, and **10/10**;
  submission-packet self-test **24/24**.
- Browser-control matrix: **52/52**, including returning-PWA cache, file delivery, image stability,
  precision editing, mobile navigation, Projects, Video, and owner continuity.
- Accessibility matrix: **33/33** phone, tablet, and desktop scenarios.
- Store-source tests: **29 passed**; metadata fits Apple and Google field limits; native privacy
  source gate passed.
- Production preflight, native web bundle, and generated-client credential scan passed.
- Relevant Ruff checks, Python compilation, staged and unstaged diff checks, conflict-marker check,
  and whitespace checks passed.

## Required hosted and owner gates

1. Hosted CI must run with the repository's required Node 22 and declared Python dependencies.
   This Windows host uses Node 24 and its bundled Python does not contain Argon2.
2. The disposable PostgreSQL 17 workflow must execute the staged SQL twice and pass its real
   multi-connection blocking, lock-order, permission, RLS, trigger, replay, preflight-rollback,
   lease, and recovery-order fixtures. This host has no PostgreSQL, Docker, WSL, or `psql`.
3. The SQL remains a staged source candidate. After hosted evidence and independent review, create
   and inspect one numbered Supabase migration against a fresh remote migration ledger before any
   migration-first rollout. Do not deploy dependent code first.
4. Publisher accounts, agreements, app records, Firebase, RevenueCat/store product identifiers,
   owner-controlled signing material, and reviewer access still require owner confirmation.
5. Exact signed IPA/AAB artifacts must pass physical iPhone, iPad, and Android journeys, purchases,
   restore, privacy permission, push, deletion, accessibility, screenshots, and the final packet
   hash gate before submission.
6. If an outside release specialist is used, hand over only the exact CI-green commit through the
   restricted roles and evidence milestones in `docs/STORE_LAUNCH_RUNBOOK.md`.

No production database, provider, customer content, developer account, store console, deployment,
pricing, billing configuration, or public campaign was changed while producing this candidate.
