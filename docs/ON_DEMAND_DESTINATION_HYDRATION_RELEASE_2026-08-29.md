# On-demand private-destination hydration release

Date: 2026-08-29

Feature commits: `8ed0f64`, `d529287`

Production deployment: `dpl_7GkVgrSJdsFsaNp4W7mEEsCPtEUw`

## Outcome

The signed-in Ask workspace now restores the conversation experience without eagerly loading
Projects, Library books and covers, Create availability, or Project Files. Each private destination
hydrates when the user intentionally opens it. A direct owned-Project URL remains an exception: it
restores that named Project immediately and loads its files only after the Project detail view is
visible.

This reduces avoidable authenticated startup work while preserving the reorganized five-destination
workspace. The change does not create, migrate, edit, attach, publish, or delete any Project, file,
book, manuscript, conversation, account, analytics record, or payment record.

## Verification

- The complete 485-test regression suite passed.
- All 45 browser JavaScript files passed validation.
- Production preflight, generated-native web bundling, and canonical store-metadata verification
  passed. Native store submission remains separately gated by the documented iOS project and
  owner-supplied billing/notification credentials.
- A credential-free production-code fixture proved that normal signed-in startup made zero feature,
  Project, Library-book, or deleted-book requests and produced zero browser errors.
- The direct-Project fixture restored the named detail view, made exactly one Project-file request,
  and produced zero browser errors.
- A signed-in, read-only production trace proved that normal Ask startup made no Projects,
  Library-book, feature, or Project-file request. Opening Projects then loaded the Project index;
  opening one existing Project loaded its details, conversations, and files on demand. No private
  record was changed.
- Production serves service-worker cache revision `r134`, the independently versioned destination
  assets, and the Project-detail visibility guard.
- The deployment reached `READY` on all six aliases with no alias error. Its inspected release
  window contained successful responses and normal redirects only, with no runtime-error cluster or
  warning/error/fatal application log.

## Product decision

Read-only production path review showed repeated destination reads that were not required to open
Ask. Exact internal usage figures remain outside the public repository. This release removes the
deterministic excess without changing the signup experiment, acquisition attribution, pricing,
entitlements, storage boundaries, or user content.

The next outcome to observe is whether the lower startup request footprint holds through ordinary
production traffic while intentional Project, Library, and Create opens remain reliable.
