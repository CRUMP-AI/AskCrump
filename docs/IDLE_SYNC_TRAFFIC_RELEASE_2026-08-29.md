# Idle synchronization traffic release — 2026-08-29

## Outcome

An open Ask Crump workspace no longer uploads every conversation and performs two
full account reads every 20 seconds. Local changes still save immediately, offline
writes remain durable, reconnect and foreground entry still reconcile promptly, and
the steady visible-tab path now performs one incremental read per minute.

Production release:

- behavior commit: `191a0576db6e8498f013fc8cdce36089440353da`
- exact-source follow-up: `edba5dc977dd9c9d429621feb78a8bd0e8dd3237`
- final Vercel deployment: `dpl_4krm9V8a67QhsdRLWFKj8qE9fqRc`
- deployment state: `READY`
- production version: `5.9.76`
- immutable chat synchronizer URL:
  `/chat-sync.js?v=5.9.76-sync-cadence-1`

## Evidence before the correction

A read-only trailing-24-hour production log aggregation returned 11,630 HTTP 200
responses. The two synchronization routes accounted for 7,033 requests:

- `/api/sync/pull`: 4,688 requests
- `/api/sync/push`: 2,345 requests

The client contract explained that volume. Every 20-second interval ran a full pull,
serialized and pushed the complete local conversation collection even when nothing
had changed, and then ran a second full pull. The loop did not skip hidden documents,
and repeated authenticated initialization could add another foreground listener.

The same operating read found no runtime error cluster. The internal-excluded growth
snapshot still contained zero comparable external accounts, so changing signup or
activation UI from this evidence would have been speculation. Idle synchronization
was an independent, deterministic reliability and infrastructure-cost defect.

## Correction

- Explicit chat saves queue their latest account-scoped state before attempting the
  network, including while the device is offline.
- A single-flight flush prevents duplicate writes while preserving entries added
  during an in-flight request. The flight key is account-scoped so a rapid account
  switch cannot receive another account's result.
- Initial authenticated entry performs one full reconciliation for work left by the
  prior client contract. Empty accounts do not produce an empty startup write.
- The startup-prefetched server snapshot is consumed once rather than reused by later
  synchronization calls.
- The automatic path runs once per 60 seconds only while the document is visible. It
  flushes only an existing queue and then performs one incremental pull.
- Returning to the foreground or reconnecting triggers the same incremental path
  immediately. Stopping automatic sync clears the active timer, and the visibility
  listener has one owner.
- A server-rejected stale startup write triggers a full read so the database result
  remains authoritative.

No database schema, RLS policy, authentication rule, chat ownership rule, message,
Project, file, plan, entitlement, credit, payment, or provider behavior changed.

## Verification

- 465 Python regression tests passed.
- 45 JavaScript files passed syntax and integration validation.
- Production build preflight passed.
- Native web bundle rebuilt successfully.
- Apple and Google store-metadata source checks passed.
- A credential-free local browser fixture executed the real sync manager and chat
  synchronizer. One visible idle cycle produced one GET and zero POST requests; an
  offline save produced one durable queue entry; reconnect produced exactly one POST,
  removed that entry, and ended with zero browser errors.
- `https://www.askcrump.com/api/health` returned HTTP 200 on version `5.9.76`.
- The live runtime loader returned HTTP 200 and referenced the immutable corrected
  chat synchronizer URL.
- The exact live synchronizer and queue manager returned HTTP 200 and contained the
  60-second visible incremental path, queued-write flush, and account-scoped
  single-flight guard.
- The final deployment reached `READY`. Its first observed release window contained
  34 HTTP 200 responses and no runtime error cluster. Four pull and two push requests
  were present in the initial deployment window; that includes startup reconciliation
  and is not treated as a steady-state rate.
- Verification created no production account, conversation, message, Project, file,
  artifact, checkout, payment, or synthetic product event.

## Outcome boundary

The deterministic request contract is corrected; production savings and cross-device
outcomes require elapsed observation time. After the first complete 24-hour window:

- compare `/api/sync/pull` and `/api/sync/push` counts with the pre-release 4,688 and
  2,345 directional counts using the same production log boundary;
- confirm push volume follows startup reconciliation or real changes rather than idle
  time;
- confirm no new synchronization timeout, 5xx, or database-retry cluster; and
- treat a legitimate cross-device delay or lost-write report as a release blocker,
  while preserving queued writes and ownership boundaries in any correction.

Do not claim a user-growth or retention improvement from lower infrastructure traffic
alone.
