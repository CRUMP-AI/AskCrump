# Books-only Library and separate Files release

Date: 2026-08-29

Feature commit: `97d8298`

Production deployment: `dpl_Ha1Uk36qG4d94J5vZDJCGKmdEuRE`

## Outcome

Library now has one unambiguous job: it is the private bookshelf for manuscripts and books created
with Crump or imported by the user. Documents, images, videos, exports, and uploads remain available
through a separate **Projects → Files** view.

An aggregate, content-free production audit found existing private files that were not attached to
a named Project. The release therefore preserves the complete file collection in the Files view
instead of hiding records, attaching them automatically, or performing a data migration. No file,
book, manuscript, Project, conversation, or account record was changed by this release.

Finished video results now say **Saved to Files** and open the same Projects → Files destination.
The replayable tutorial, Apple and Google listing source, screenshot plan, generated-native runtime,
and PWA cache all teach the same boundary.

## Verification

- The complete 485-test regression suite passed.
- All 45 browser JavaScript files passed validation.
- Explicit backend compilation, production preflight, generated-native web bundling, and canonical
  store-metadata verification passed.
- A credential-free production-code fixture proved the books-only Library and Projects → Files
  boundary at 390 by 844 and 1280 by 800, with zero horizontal overflow.
- A signed-in, read-only production check proved the real Library contains the manuscript bookshelf
  and no saved-file grid. The separate Files view retained the private file controls and kept
  Projects active on both phone and desktop widths, with zero measured horizontal overflow.
- Production served the independently versioned Project assets, updated tutorial asset, and service
  worker cache revision `r132`.
- The deployment reached `READY` on all six aliases with no alias error. Its initial inspected
  window contained 109 HTTP 200 responses and four normal redirects, with no runtime-error cluster
  or warning/error/fatal deployment log.

## Product decision

This is an information-architecture release, not a storage migration. Library is easier to explain
and photograph for store review, while Files remains a durable private utility inside Projects.
The next outcome to observe is whether users reopen a book from Library or reuse a document/media
item from Projects → Files during legitimate work.
