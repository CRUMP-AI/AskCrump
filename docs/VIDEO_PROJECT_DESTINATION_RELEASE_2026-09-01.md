# Video Project destination release

Date: 2026-09-01  
Feature commit: `13a9e84c8f83770bae12e83fb36c78bc0492e21b`  
Production deployment: `dpl_GjQzW3BiVNfy1Ab3brdqpEQhdmxQ`

## User problem

Opening a Project made it the active destination for later work. When that user moved to the
top-level Video destination, the finished generation still carried the Project ID, but the Project
chip was hidden on the launchpad and at phone widths. The useful continuity therefore looked like
an unexplained side effect: a user could not see where a paid generation would land or choose a
different destination before starting it.

## Shipped behavior

- Video Studio shows **Saving to Project** and the exact Project name whenever a Project is active.
- The card explains that a finished video will appear in both that Project and private Files.
- **Use Files only** leaves the Project target, removes it from the request, and confirms the new
  destination in the Studio status region.
- The destination action is disabled while generation or a private reference upload is busy, so a
  target cannot change after a request has started.
- Existing Project attachment, private storage, durable video-job recovery, metering, entitlement,
  provider, and reference-image behavior are unchanged.
- No account, Project record, conversation, file, content, generation, entitlement, credit,
  billing, analytics event, API release, database object, or customer data changed.

## Automated and local proof

- All **716 Python tests** passed.
- All **47 JavaScript validations** passed.
- Production preflight, native web bundling, store-metadata checks, signing-source controls, and
  diff integrity passed.
- A real-browser proof opened **Launch Operations**, moved directly to Video, verified the visible
  named destination, exercised Files-only, and reported zero errors at **1280×800** and **390×844**.
- Project/Create/Video destination, reference-image, File delivery, and File usability browser
  verifiers also remained green on desktop and phone.

## Production proof

GitHub deployed the exact feature commit to `READY` on all six production aliases with no alias
error. The canonical runtime serves `5.9.76-video-project-destination-1` for both Studio assets and
service-worker cache `ask-crump-new-body-v1-r183`.

After accepting the PWA update, a signed-in production walkthrough opened **Savannah Reading
Series** and moved directly to Video. The live Studio visibly named the Project, explained both
save locations, and exposed **Use Files only**. The Files-only action removed the destination and
announced the new state; the original Project choice was then restored. A visual phone-width
inspection showed a restrained stacked card with no overflow or blocked destination navigation.

Vercel reported no runtime-error cluster, no 4xx or 5xx release log, and no
warning/error/fatal release log.

## Rollback and remaining gate

Rollback is the single feature commit above. It requires no data repair. Before store screenshots,
repeat Project selection, Files-only selection, generation, completion, and Project attachment on a
physical iPhone with VoiceOver, safe areas, backgrounding, and the software keyboard. This release
proves destination clarity and control; it does not by itself prove retention lift.
