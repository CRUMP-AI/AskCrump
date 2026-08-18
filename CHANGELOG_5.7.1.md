# Ask Crump 5.7.1 — Library Refinement

Ask Crump 5.7.1 is a pre-store stabilization release focused on the Library experience and safe manuscript lifecycle management.

## Mobile Library refinement

- iPhone and narrow mobile layouts now use one calm book row per line instead of squeezing two book cards together.
- The Projects & Create header and sticky tabs are reduced and spaced specifically for the Library so tabs no longer crowd the first row of content.
- Long source filenames no longer dominate or overflow book cards.
- Book metadata, actions, touch targets, spacing, and truncation have been rebalanced for a finished-app mobile feel.

## Library views

- Grid view remains the default browsing mode.
- List view provides a denser management view.
- Book view unlocks when a front cover exists and adds restrained cover/spine depth rather than a novelty bookshelf treatment.
- Layout, sort, and cover-filter preferences persist locally on the device.
- Search, status filtering, cover/source filtering, and sorting now live together in the Library toolbar.
- Front-cover books can open a focused Book Preview; front + back cover books show both sides with a subtle virtual spine.

## Safe deletion

- Books can be moved to Recently Deleted from the `•••` menu.
- The user may optionally remove an imported original source from Files at the same time.
- Shared source files are protected automatically.
- Recently Deleted books can be restored.
- Permanent deletion requires a second explicit confirmation and is available only after a book has been moved to Recently Deleted.
- Active manuscript-generation runs block trash/permanent deletion to avoid destroying work in progress.
- Projects and cover files remain intact when a manuscript is deleted.

## Release integrity

- No Supabase migration is required; this release uses the existing manuscript `archived_at` and private-file `deleted_at` model.
- Service-worker cache generation advances to `ask-crump-new-body-v1-r14` so mobile browsers receive the refined Library assets.
- Stale Python release-contract assertions are aligned with the current service-worker generation.
- The release remains in pre-store stabilization and does not submit Ask Crump to an app store.
