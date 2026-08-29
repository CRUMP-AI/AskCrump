# Startup transition correction — 2026-08-29

Status: verified in production; owner repeat-device confirmation pending

## Correction

The earlier entry-quality release fixed a real gate-release race, but the owner's repeat report
showed that the refresh defect was not fully resolved. A higher-frequency browser capture exposed a
second, independent cause: the deferred runtime physically moved the already-active primary
stylesheet to the end of the document. Chromium briefly detached that stylesheet during the move,
which exposed an oversized brand mark and partially styled workspace beneath the loading cover.

## Evidence before the change

- The owner still saw the glitch on refresh after the preceding release reached production.
- A signed-in production filmstrip reproduced one visibly malformed frame: the workspace mark
  expanded to its intrinsic size while only the composer retained partial styling.
- A DOM/CSS trace then isolated the transition. Once the workspace became visible, the loading gate
  temporarily changed from its intended `display: grid` to unstyled `display: block` while the
  stylesheet count advanced from 11 to 12. The correct gate styling returned after the live
  stylesheet was appended again.
- Source inspection confirmed that both runtime loaders used `appendChild(existing)` to move a
  loaded stylesheet. The startup mark was also marked for lazy, asynchronous loading even though it
  is visible in the loading cover.

## Change

- Both runtime stylesheet loaders now leave the active stylesheet attached.
- A cached clone takes the final cascade position, preserving the intended CSS authority without a
  style-free interval.
- The startup mark is preloaded at high priority and uses eager, synchronous decode semantics.
- Service-worker cache revision 116 distributes the corrected shell and runtime together.
- Authentication, session checks, user data, navigation, pricing, entitlements, providers, and
  analytics definitions did not change.

## Production proof

- Commit `53d5af2` deployed as `dpl_9szAKXJ5K1vR6XVwFpPMV3ibTJFG` and reached `READY` in production.
- The exact production assets returned HTTP 200 and contained the preload, eager mark, cloned
  stylesheet handoff, and cache revision 116.
- A signed-in production reload was sampled 44 times from 144 through 3,029 milliseconds. From the
  first frame where the workspace container became visible until the gate completed hiding, there
  were zero samples where the visible gate was not fully styled as a grid.
- The mark had decoded to its full 640-pixel natural width before the workspace became visible.
- Runtime readiness began the intended opacity transition only after all 22 stylesheets were active;
  the gate faded from 1 to 0 and then became hidden with no busy or inert residue.
- A separate signed-out local reload was sampled 32 times and recorded zero visible unstyled-gate or
  missing-mark frames before the sign-in surface appeared.
- A follow-on authenticated production refresh at a 393-by-659 iPhone-sized viewport loaded all 22
  workspace stylesheets, decoded the 640-pixel startup mark, removed the gate completely, cleared
  busy and inert state, preserved zero horizontal overflow, and produced no browser warning or
  error.
- The inspected deployment window contained 48 HTTP 200 responses and no runtime error cluster.

## Verification

- All 441 automated tests passed.
- All 45 JavaScript files validated.
- Production preflight, native web-bundle creation, and store-metadata checks passed.
- Verification used no credentials and created no account, conversation, message, artifact,
  Project, payment, social publication, or Search Console change.

## Outcome boundary

The previously reproducible stylesheet gap is eliminated in controlled production and signed-out
checks. The available desktop runner did not contain a WebKit binary, so no physical Safari result
is inferred from the iPhone-sized Chromium check. The release remains pending owner confirmation on
the affected real device; no activation, retention, or conversion improvement is claimed from this
visual correction.
