# Cross-device settings sync release — 2026-09-09

## Outcome

An open Ask Crump device now adopts an account's synchronized assistant name and work-mode hours
after another device saves them. The server already stored those four settings and returned them on
every conversation-sync pull, but the client previously ignored the returned settings object. A
person therefore saw stale account behavior until signing in again or reloading through the full
authentication path.

The corrected contract:

- accepts only `assistant_name`, `work_mode`, `work_start`, and `work_end` from the existing
  server-owned settings response;
- writes only values that actually changed into the already account-scoped local cache;
- emits one content-free settings-applied event only when at least one value changes;
- immediately refreshes the assistant name and composer identity;
- refreshes a visible Settings form only when it has no local draft, preserving fields the person
  is actively editing; and
- treats an explicit unsuccessful queue flush as the existing recoverable **saved on this device;
  server sync will retry** state instead of displaying an unconditional synchronized success.

Conversation conflict resolution, image-node preservation, the one-minute visible-tab cadence,
offline queueing, profile identity, presence/check-in preferences, and server-side model settings
remain unchanged. No arbitrary settings keys are accepted.

## Browser proof

A credential-free local browser ran the real sync manager and chat synchronizer together. One
incremental pull returned a changed assistant name and work schedule while an active conversation
and loaded image were present. The fixture proved:

- sync interval: **60,000 ms**;
- idle pulls: **1**;
- idle pushes: **0**;
- all four allowlisted settings applied: **true**;
- settings-applied events: **1**;
- unchanged active image node preserved: **true**;
- offline queued writes before reconnect: **1**;
- reconnect pushes: **1**;
- queue remaining after reconnect: **0**; and
- browser warnings/errors and fixture errors: **0**.

The fixture uses a fictional account ID and local response data. It contains no credentials and
makes no production request.

## Verification

- Focused sync/settings coverage: **19/19** checks passed.
- Complete Python suite: **927 collected**, **925 passed**, two environment-dependent skips.
- JavaScript integration contract: **49 files** and **6/6** attribution cases passed.
- Ruff, Python compilation, production preflight, native web build, and diff integrity passed.
- Feature commit: **c72cdd2d7d4116ed238e8dc76acd3d2fcfa2009b**.
- Main CI run **34368556277** passed.
- Android Store Bundle Verification **34368556197** and iOS Store Source Verification
  **34368556324** passed.

## Production boundary

Automatic production deployment **dpl_3MiPAQfLEfDEYJUGr4RQBmuWuTqs** is READY on all six aliases
with no alias error. The live deferred runtime references
`/chat-sync.js?v=5.9.76-settings-sync-1`. Both changed customer assets returned HTTP 200 and
matched the committed files byte-for-byte:

- `chat-sync.js`: `FAA74986C8B4E222FCD8CE87CDB49A5911732FCC4C355E86F643863B4781AB0C`;
- `app.js`: `031F7CAC4886457352C7120F1ACBFE16367F2BD2A77C689793BF44AE3EF0E552`.

All four Ask Crump/Clever Crump custom-domain health endpoints returned HTTP 200 at version 5.9.76.
The first 30-minute runtime-error aggregate was empty, and the exact deployment had no warning,
error, or fatal log.

No production account, setting, conversation, database row, analytics event, provider request,
credit, or payment was created or changed for verification. A legitimate simultaneous two-device
settings change remains the real-world observation boundary; this release does not claim a measured
retention lift.
