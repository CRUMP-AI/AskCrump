# Settings save isolation release — 2026-09-09

## Outcome

The Settings **Save changes** action now completes each independent save owner even when another
owner fails. Previously, a failed conversation/settings queue flush prevented check-in,
notification, haptic, and follow-up preferences from being submitted at all. The sheet then closed
and described the operation as a recoverable device save, even though those preference changes
existed only in the dismissed form.

The corrected contract:

- attempts profile identity, cross-device assistant/work settings, and presence/check-in
  preferences independently;
- keeps device-cached assistant/work settings and their existing queued-sync recovery behavior;
- never lets a profile or sync failure suppress the preference request;
- keeps the Settings sheet open with the draft intact when profile or preference data did not save;
- re-enables **Save changes** for a deliberate retry and gives the unsaved area a truthful name;
- closes only after every non-queued owner succeeds; and
- reconciles the button's disabled, `aria-disabled`, title, busy state, and visible label after every
  outcome.

The API, database schema, preference defaults, consent meaning, notification permission flow,
subscription state, pricing, and analytics remain unchanged.

## Executable browser proof

A credential-free fixture exercised the real Settings runtime at 1280×760 and 390×844, plus three
forced partial-failure cases at phone width:

- cross-device sync failure: profile/presence were not blocked, the sheet closed with the existing
  device-save/pending-sync boundary, and the button ended disabled with matching accessibility
  state;
- presence preference failure: sync was still attempted exactly once, the sheet stayed open, the
  draft remained dirty, and **Save changes** was enabled for retry;
- profile failure: both sync and presence were still attempted exactly once, the sheet stayed open,
  and the unchanged name remained an explicit retryable draft; and
- every case produced zero browser errors, unhandled rejections, horizontal overflow, credentials,
  production requests, or customer writes.

## Verification

- Complete Python suite: **927 collected**, **925 passed**, two environment-dependent skips.
- JavaScript integration contract: **49 files** and **6/6** attribution cases passed.
- The Settings browser verifier passed desktop, phone, guest, sync-failure, preference-failure, and
  profile-failure cases.
- Ruff, Python compilation, production preflight, native web build, and diff integrity passed.
- Feature commit: **98f2a9c2b9d36497f681ce9a7c1cef06d31e9f96**.
- Main CI **34371030541**, Android Store Bundle Verification **34371030602**, and iOS Store Source
  Verification **34371030533** passed.

## Production boundary

Automatic production deployment **dpl_8zEzid6srKAGzTk2nnZjcktrQJAe** is READY on all six aliases
with no alias error. The live deferred runtime references
`/app.js?v=5.9.76-settings-save-isolation-1`; its served SHA-256
`E401B87112C4E8C17CFBA7F19DFE27A958BCBF2120182A05A41C912307F32E41` matches the committed file
byte-for-byte. All four Ask Crump/Clever Crump custom-domain health endpoints returned HTTP 200 at
version 5.9.76. The initial runtime-error aggregate was empty and the exact deployment returned
only successful runtime traffic during inspection.

No production account, profile, setting, notification preference, conversation, database row,
analytics event, provider request, credit, or payment was created or changed for verification. A
legitimate preference save during a real network interruption remains the real-world observation
boundary; this release does not claim a measured activation or retention lift.
