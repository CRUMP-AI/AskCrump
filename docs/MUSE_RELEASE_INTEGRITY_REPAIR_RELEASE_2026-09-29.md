# Muse release integrity repair evidence - 2026-09-29

Status: local release candidate verified; hosted CI, merge, production deployment, exact live
asset/cache adoption, and post-deploy probes remain required before this is called shipped

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

## External Stripe QR observation

A user-reported Stripe QR/passkey delay is outside Ask Crump. Repository and live-asset inspection
found no Ask Crump QR or device-code sign-in flow. Live health/session assets were healthy and the
existing authenticated Ask Crump session remained stable. Stripe's alternate authentication path
is the appropriate recovery route; the report does not justify an Ask Crump authentication change.

## Production gate

Push the isolated repair, open the pull request, and require hosted CI. After merge, verify the
exact deployment is Ready; confirm the r254 worker and `5.9.76-muse-release-repair-1` assets on the
production aliases; replay the signed-in starter, presence, image-stability, and explicit-jump
paths; then inspect the initial runtime-error and severe-log window. Record those identifiers before
calling the repair shipped.
