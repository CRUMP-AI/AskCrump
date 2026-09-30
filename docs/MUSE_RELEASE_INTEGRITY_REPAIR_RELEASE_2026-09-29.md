# Muse release integrity repair evidence - 2026-09-29

Status: shipped on `main` as commit `9ed322251452574a642cd30dc2a15823667f29f3`; hosted CI,
production deployment, exact live asset/cache adoption, signed-in smoke testing, and post-deploy
runtime probes passed

## Product outcome

The repair keeps the useful visual polish introduced by the Muse-feel pass while restoring Ask
Crump's previously released user-controlled viewport and stable-image contracts.

- Completed replies render immediately in their final formatted form; the simulated client-side
  typewriter and caret are removed.
- Conversation rows no longer replay an entrance animation after a render.
- Presence expansion and rotating status copy update the visible label and live region in place
  instead of rebuilding the conversation.
- Only the explicit **Jump to newest message** action moves the feed, and it does so immediately.
- All four starter chips now update composer readiness through the normal input event without
  sending a message.
- The refinement stylesheet loads only with the authenticated workspace, and typing-dot animation
  is disabled under reduced-motion preferences.

These corrections restore the contracts recorded in
`docs/USER_CONTROLLED_CONVERSATION_SCROLL_RELEASE_2026-09-01.md` and
`docs/CONVERSATION_IMAGE_NODE_STABILITY_RELEASE_2026-09-08.md`.

## Safety and scope boundary

The repair changes client presentation, interaction ownership, asset delivery, and regression
coverage only. It adds no backend route, database migration, authentication policy, analytics
field, provider call, upload, generation, credit, entitlement, checkout, or billing behavior.
The current plan-status-line asset identity is reflected in the release contracts without changing
plan or checkout behavior.

Hosted CI also identified newly published PyJWT advisories against the pinned 2.13.0 release. The
production and package manifests now use the first patched release, PyJWT 2.14.0; authentication
and dependency-parity coverage remained green through merge and production release.

## Delivery boundary

- Browser/PWA/native source asset token: `5.9.76-muse-release-repair-1`.
- Service-worker cache: `ask-crump-new-body-v1-r254`.
- `crump-design-pass.css` moves from the signed-out shell into the authenticated runtime, increasing
  the authenticated runtime plan from 17 to 18 styles.
- The service worker now precaches the mascot required by the workspace visual layer.
- A dedicated real-browser transition seeds the immediate predecessor cache `r253`, installs the
  current worker, proves `r253` eviction, verifies the replacement assets and mascot, and confirms
  that all superseded URLs are absent.
- The older r249 document-delivery and r252 Image Studio transition proofs now correctly terminate
  at the current r254 cache.

## Verification

- Complete pytest suite: **100% passed with no failures**; one Starlette deprecation warning was
  reported.
- Production dependency audit under PyJWT 2.14.0: **no known vulnerabilities found**.
- Focused release contracts: **61/61 passed**.
- JavaScript release contract: **54 files validated**, including **24/24**, **10/10**, and **10/10**
  runtime/attribution cases and the **21/21** store-packet self-test.
- Browser-control matrix: **52/52 passed**.
- Public accessibility matrix: **33/33 passed** across phone, tablet, and desktop.
- Production preflight, Python compile guard, native web bundle generation, and client-credential
  boundary passed. Native store-project verification remains outside this web repair: this isolated
  checkout has no Android or iOS project and was built without RevenueCat public SDK keys.
- The dedicated r253-to-r254 proof reported `userControlledViewport: true`,
  `cachedRepairAssets: true`, and zero browser errors.
- The image/viewport proof held `scrollTop=420` through presence, reply, stream, history, delayed
  image load, attachment replacement, and attachment removal; generated- and uploaded-image identity
  held throughout, the explicit jump reduced the remaining distance to 0, and a later manual offset
  remained exact. Browser errors: zero.
- The same real-browser proof ran the real 2.8-second presence expansion and 4.2-second warm-status
  rotation timers. Both updated the existing presence node in place, caused no additional render,
  preserved image identity, and left the viewport unchanged; activity update behaved the same way.
- The first-action proof verified every starter prompt updates focus and composer readiness without
  clicking Send.
- `git diff --check` passed.
- Pull request `#47` merged as `9ed322251452574a642cd30dc2a15823667f29f3`. Head CI run
  `36656205226`, main CI `36656663658`, Android verification `36656663627`, iOS source verification
  `36656663596`, and the next scheduled public-destination run `36747024483` all completed
  successfully.
- Vercel deployment `dpl_8pQ6vitc51drFMMKHVRCqA4pCaK6` reached `READY` at
  `2026-09-30T01:46:23.689Z` for the exact merge commit and promoted without an alias error to the
  Ask Crump and Clever Crump production domains.
- Live `/api/health`, `/app`, `/`, the r254 worker, runtime loader, UI, and presence assets returned
  HTTP 200. The exact repair token, cache, and `refreshVisiblePresence` implementation were present;
  the inspected UI asset contained neither the retired typewriter nor smooth-autoscroll marker.
- The signed-in production workspace completed the two-stage service-worker handoff, reopened with
  the conversation list intact, filled the composer from a starter without sending, enabled Send,
  and returned to an empty disabled-Send state. Browser error/warning logs were empty.
- From production readiness through `2026-09-30T23:02:00Z`, Vercel reported no grouped runtime
  error, error/fatal log, 4xx, or 5xx response; the status view contained 1,588 HTTP 200 responses.

## External Stripe QR observation

A user-reported Stripe QR/passkey delay is outside Ask Crump. Repository and live-asset inspection
found no Ask Crump QR or device-code sign-in flow. Live health/session assets were healthy and the
existing authenticated Ask Crump session remained stable. Stripe's alternate authentication path
is the appropriate recovery route; the report does not justify an Ask Crump authentication change.

## Production evidence

The release gate is closed. The exact merge, hosted checks, Ready deployment, production assets,
signed-in starter behavior, service-worker transition, and post-deploy health window are recorded
above. Preserve the user-controlled viewport and stable-image contracts; require a new reproducible
defect or measured regression before changing those owners again.
