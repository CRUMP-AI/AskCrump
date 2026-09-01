# Mobile Chats-to-Destination Handoff Release — 2026-09-01

Status: **VERIFIED PRODUCTION RELEASE**  
Code commit: `1ccc78ba35a628fb4c47ab6653f6eca273ff7f22`  
Production deployment: `dpl_DfcwECVmo3YnTgKKnjGacavgz1dw` (`READY`, six aliases)

## User outcome

On phone-sized screens, the Chats drawer and its dimming layer now stop above Ask Crump's persistent destination bar. A person can open Chats and then move directly to Ask, Projects, Create, Video, Library, or You with one tap. The destination action closes Chats and opens the requested workspace instead of appearing to ignore the tap or requiring a second attempt.

The layout retains the existing iPhone safe-area allowance. The drawer remains modal over the conversation workspace, conversation options remain available inside the drawer, and the destination bar remains the single mobile product-navigation surface.

## Scope

- `public/crump-navigation-5.9.30.css` bounds the mobile Chats drawer and overlay above the persistent destination bar.
- The web/PWA and native loaders use the exact `5.9.76-mobile-drawer-destinations-1` stylesheet revision.
- The service worker pre-caches that exact revision.
- The production-layer fixture now represents the real drawer, overlay, and expanded state.
- A deterministic 390-by-844 browser verifier proves that the drawer and overlay end at the navigation boundary and that one Projects tap closes both layers and opens Projects.

No navigation destination, account behavior, conversation, Project, file, Library item, billing state, entitlement, API, database, analytics schema, model request, credit, or customer data changed.

## Verification

- Complete Python suite: 712 passed.
- JavaScript/runtime contract: 47 files passed.
- Production preflight and native web bundle: passed.
- Store metadata and signing-secret source controls: passed; store credentials, screenshots, privacy forms, and console submission remain release-time gates.
- Automated phone-width geometry: drawer bottom `776`, overlay bottom `776`, destination-bar top `776`, destination-bar height `68` at 390 by 844.
- Automated user action: one Projects tap changed `drawerOpen` and `overlayOpen` to false, opened the destination studio, and selected the `projects` section with zero browser errors.
- Signed-in production at phone width reproduced the exact sequence: Open Chats → Projects once → Projects visible, Chats closed, rendered app no-index boundary intact.
- Exact live runtime, service worker, and stylesheet revision returned from production; the release window had no runtime-error cluster.

## Rollback

If a physical-device check finds a safe-area, scrolling, or keyboard regression, restore the prior full-height mobile drawer/overlay rules and the previous stylesheet revision, then redeploy the last verified release. The existing destination handlers require no rollback or data repair.
