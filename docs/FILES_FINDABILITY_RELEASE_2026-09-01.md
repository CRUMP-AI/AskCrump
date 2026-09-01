# Files findability release

Date: 2026-09-01  
Feature commits: `2d7cb3f06ae7ea913b568bac84317b644ec997c7`,
`b3a3cfe689d5d164e522d9c47bcc10acaf00e9ee`
Final production deployment: `dpl_9mjVqNTGosN7zsRPqrCVKTuymkbz`

## User problem

The preceding preview-layer repair made private files open in front of Projects, but a user with a
real history still had to scan one long newest-first wall. The signed-in production account used for
verification contained 65 saved items across images, videos, presentations, documents, uploads, and
manuscript exports. Files had type filters, but no way to search a remembered name or prompt and no
way to change ordering.

This was a findability and return-to-work problem. It did not require a file-storage, account,
Project, signed-URL, download, or database change.

## Shipped behavior

- Files now provides an explicitly labelled search field matching saved names, titles, prompts,
  MIME/file types, kinds, and video-engine labels.
- Search is case-insensitive and accent-insensitive, so an ordinary query such as `resume` finds a
  saved `résumé`.
- Users can sort by newest, oldest, or name while the current type filter and search remain active.
- All, Video, Image, and Document filters show live account counts and expose synchronized
  `aria-pressed` state.
- The status explains both the visible result count and total saved count while searching or
  filtering; an unmatched query receives a specific empty result instead of a misleading empty
  category.
- Each fresh Files visit clears the prior search and type filter so returning users always see their
  complete account library; the user's current-session sort preference remains intact.
- The phone layout stacks the controls, retains a 16-pixel search/sort input size, and preserves the
  existing one-column file cards without horizontal overflow.
- Existing inline video hydration, in-app image/document viewers, downloads, Use in chat, and
  Continue scene behavior are unchanged.
- No account, file, Project, conversation, generation, provider, credit, entitlement, price,
  checkout, payment, subscription, analytics event, database object, or customer content changed.

## Automated and local proof

- All **713 Python tests** passed.
- All **47 JavaScript validations** passed.
- Explicit Python compilation, production preflight, native web bundling, store-metadata source
  checks, mobile signing-source controls, and diff integrity passed.
- `scripts/verify-file-library-usability.cjs` exercised the real Files implementation at
  **1440×1000** and **390×844** with a four-format fixture. It proved count labels, newest/oldest/name
  ordering, accent-insensitive search, search-specific empty feedback, synchronized pressed state,
  16-pixel phone inputs, no horizontal/dialog overflow, fresh-visit search/filter reset with retained
  sorting, and zero browser errors.
- `scripts/verify-file-delivery.cjs` continued to prove that PowerPoint and image viewers stay above
  Files, keep the user inside Ask Crump, download to the device only after deliberate activation,
  and restore focus when closed.
- The native release verifier continues to report only the known store-build gates: generated
  Android/iOS projects and RevenueCat public keys are not present in this web release worktree. No
  signed-build or store-submission claim is made.

## Production proof

The final GitHub-connected deployment reached `READY` on all six production aliases with no alias
error. The canonical runtime and exact `5.9.76-file-library-usability-2` asset returned HTTP 200 and
contained the released controls and fresh-visit reset.

A signed-in production walkthrough loaded all **65** existing items and reported **18 videos**, **23
images**, and **24 documents**. Searching `Kindling` reduced the result to the one intended
PowerPoint and announced `1 of 65 saved items shown`. Oldest and newest ordering produced different,
correct first items. Image filtering produced exactly 23 cards. Both the real image and PowerPoint
preview opened above Files at z-index 120,100, with the PowerPoint retaining its in-app
`Download to this device` action.

At **390×844**, the Files sheet remained within the viewport, search controls and cards shared the
same 322.67-pixel content width, the search input computed to 16 pixels, and document width remained
exactly 390 pixels. A final signed-in return check searched for `Kindling`, selected Images, closed
Files, and reopened it: the search was blank, All was selected, all 65 items were visible, and the
sort preference remained available. The signed-in browser produced no warning/error log.

Vercel reported no runtime-error cluster, no 4xx or 5xx release log, and no
warning/error/fatal release log for the final deployment. The initial feature deployment's observed
traffic contained 27 HTTP 200 responses and seven expected redirects.

## Rollback and remaining gate

Rollback is the two feature commits above; file APIs, records, ownership checks, signed-content
delivery, and underlying viewer behavior are untouched. Before store screenshots, repeat search,
filter, sort, preview, close, reopen, and download on a physical iPhone with VoiceOver and the
software keyboard. Legitimate return-to-file and download outcomes remain observation gates; this
release proves delivery and usability, not retention lift.
