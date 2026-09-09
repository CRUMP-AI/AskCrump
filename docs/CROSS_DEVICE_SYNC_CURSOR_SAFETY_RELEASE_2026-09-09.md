# Cross-device sync cursor safety release — 2026-09-09

## Outcome

Cross-device conversation sync no longer advances a device's read watermark merely because that
device successfully pushed its own work. A push confirms that one write was accepted; it does not
prove that the device read a change another device saved at the same time. Treating the push time
as a read cursor created a narrow but real gap in which the concurrent change could be skipped by
later incremental pulls.

The corrected contract has two parts:

- only a successful pull can update `crump_last_sync_v4`; a push continues to clear only the exact
  queued entries the server accepted; and
- the pull endpoint captures its response watermark before the database read, so a write that
  lands while the read is in flight remains newer than the returned cursor and is eligible for the
  next incremental pull.

The existing one-minute, visible-tab synchronization cadence, offline queue, single-flight flush,
full startup reconciliation, account scoping, and conflict resolution are unchanged. No interface,
database schema, billing, provider, analytics, or customer-content contract changed.

## Executable proof

The JavaScript release contract now runs the real sync manager through this race:

1. an authenticated fixture device pushes a local conversation;
2. the push response has a later server time representing the unsafe cursor;
3. another conversation is treated as having arrived concurrently;
4. the fixture performs an incremental pull and proves the request has no unread push cursor;
5. the concurrent conversation is returned; and
6. only that completed pull establishes the cursor used by the following incremental request.

A separate asynchronous route test proves the server watermark is captured before the database
read. Static ownership checks also prevent the cursor write from returning to the push flush.

## Verification

- Focused sync coverage: **21/21** checks passed.
- Complete Python suite: **925 collected**, **923 passed**, two environment-dependent skips.
- JavaScript integration contract: **49 files**, **6/6** attribution cases, and the executable
  concurrent-sync cursor fixture passed.
- Ruff, Python compilation, production preflight, native web build, and diff integrity passed.
- Feature commit: **e46bb05f5e19735c42b03aadd5f68595f32c78a0**.

## Production boundary

Automatic production deployment **dpl_CgfqAeCCgExBwkNMYQxsdPLxvg4L** is READY on all six aliases
with no alias error. The live deferred runtime references
`/sync-manager.js?v=5.9.76-sync-cursor-1`, and the live asset SHA-256 exactly matches the committed
file: `28588D772D182A20C44D6906EDD65BE32DBBE4314AC39F98939A67B1EE617CEF`.

All four Ask Crump/Clever Crump custom-domain health endpoints returned HTTP 200 at version 5.9.76.
An unauthenticated sync pull failed closed at HTTP 401. The first 30-minute project runtime-error
aggregate was empty, and the exact deployment had no warning, error, or fatal log.

This verifies the web/PWA/backend correction and its native-web inclusion without creating an
account, conversation, database row, analytics event, provider request, or payment. A legitimate
two-device signed session remains the final real-world observation boundary before claiming
cross-device continuity performance.
