# Studio destination isolation release

Date: 2026-09-01
Feature commit: `442f07f2b62b51897c61f0ba2a01dfa4b771e456`
Production deployment: `dpl_CLJzHSSqq1JTEt15fX4x18LyWSG7`

## User problem

A signed-in user-eye walkthrough opened a specific Project, closed it, and then entered the
top-level Video destination. Video Studio still exposed **Back to all Projects**, even though Video
is a peer of Projects in the product navigation. Direct Project-to-Video navigation could also
retain the Project deep link and Project-detail styling inside the shared sheet.

The release gate found a related ownership collision: the navigation layer correctly made the
covered Chats and workspace surfaces inert behind Create, but a later Chats-shell synchronization
could remove the sidebar guard while Create remained open. The visible destination navigation stayed
outside that covered background, as intended.

## Shipped behavior

- Entering Video, Library, or Manuscripts now clears the Project-only back control, Project-detail
  view marker, open-detail class, and `project` URL parameter before applying the destination's own
  title and accessible dialog name.
- The active Project selection, Project records, conversations, files, canon, and permissions are
  untouched; only stale Project navigation chrome and routing are reset.
- The destination owner marks the covered Chats/workspace surfaces while a persistent surface or
  Create is open. The Chats-shell owner honors that marker instead of removing `inert` during a
  later control refresh.
- Closing the destination restores the exact prior background accessibility state. The Ask,
  Projects, Create, Video, Library, and You controls remain outside the inert background.
- No account, Project, conversation, file, generation, provider, entitlement, credit, billing,
  analytics event, database object, or customer content changed.

## Automated and local proof

- All **714 Python tests** passed.
- All **47 JavaScript validations** passed.
- Explicit Python compilation, production preflight, native web bundling, store-metadata source
  checks, mobile signing-source controls, and diff integrity passed.
- `scripts/verify-studio-section-isolation.cjs` opened a real Project detail and switched directly
  into Video, Library, and Manuscripts at **1280×800** and **390×844**. Every transition had the
  correct title and accessible name, a hidden Project back control, an index Project view, no open
  Project-detail class, no Project route, and zero browser errors.
- `scripts/verify-create-destination-handoff.cjs` proved on desktop and phone that Create keeps only
  Chats and the workspace inert/hidden from assistive technology, leaves the visible destination
  control outside the guard, focuses Close, moves to Video in one action, and returns to Ask cleanly.
- Existing Video destination/tutorial, Files preview/download, and Files search/sort browser proofs
  remained green.

## Production proof

The GitHub-connected deployment reached `READY` on all six production aliases with no alias error.
The canonical runtime and exact `5.9.76-studio-section-isolation-1` and
`5.9.76-destination-background-guard-1` assets returned HTTP 200 and contained the released guards.

After accepting the PWA update, a signed-in production walkthrough opened **Savannah Reading
Series** and selected the persistent Video destination without first closing the Project. Video
Studio opened at `/app` with Video active, focus on the Video Studio title, the Project back control
hidden, Project view reset to index, and Project-detail styling absent.

The same live session opened Create and proved both Chats and the workspace were inert with
`aria-hidden="true"`, while the Create destination remained outside the inert subtree and focus
landed on Close. Returning to Ask removed the guard and left the app at `/app`. The signed-in browser
reported zero warning/error entries.

Vercel reported no runtime-error cluster, no 4xx or 5xx release log, and no
warning/error/fatal release log.

## Rollback and remaining gate

Rollback is the single feature commit above. Data, APIs, ownership, entitlements, generation, and
billing are unchanged. Before store screenshots, repeat Project → Video/Library/Create and the
corresponding return paths on a physical iPhone with VoiceOver, safe areas, and the software
keyboard. This release proves destination identity, routing, focus, and background containment; it
does not by itself prove retention lift.
