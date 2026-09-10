# Library lazy-load and complete-control release — 2026-09-10

## Decision

Keep all 276 shipped button construction sites behind deterministic action ownership, while moving
the books-only Library interface off the ordinary authenticated startup path. Preserve image and
video save behavior everywhere through a small independent media module.

This is a reliability and startup-efficiency release. It does not claim that every external
provider, purchase, upload, permission, destructive confirmation, or signed physical-device
outcome was exercised in production.

## Released behavior

The previous authenticated plan loaded the complete Library script and stylesheet before a user
chose Library:

- `crump-library-5.7.js`: 65,362 raw bytes; and
- `crump-library-5.7.css`: 37,386 raw bytes.

Commit `73c3829` replaces those 102,748 startup bytes with:

- `crump-media-save.js`: 6,376 raw bytes, retaining cross-workspace image/video save behavior; and
- `crump-library-loader.js`: 4,312 raw bytes, owning one-time Library entry and recovery.

The ordinary plan therefore avoids **92,060 raw bytes** until Library is explicitly opened and
loads 18 styles instead of 19. Script count changes from 33 to 34 because the prior full Library
script is replaced by two intentionally small, separately owned modules.

When Library is chosen, the destination now:

1. announces **Opening Library…** and temporarily disables every Library destination;
2. loads the existing Library script and stylesheet together and only once;
3. replays the original Library action so the existing navigation owner retains focus, active-state,
   dialog, and cleanup behavior;
4. restores all Library destinations after success or failure; and
5. removes only incomplete lazy assets so a later press can recover after a temporary failure.

The web/PWA and generated native web plan use the same boundary. The service worker pre-caches the
small media and loader modules; the full bookshelf remains an on-demand, subsequently cached asset.

## Complete control proof

The fail-closed source inventory covers **182 rendered + 94 programmatic = 276** button
construction sites. Every control must declare a behavior type and have a bounded direct or
explicitly reviewed delegated owner. The complete real-browser matrix passed **43/43** flows,
covering account entry, chats, composer state, Projects, files and foreground preview, Create,
Image Studio, Precision Edit, Video, Library, Settings, Intelligence, plans and credits, referral
recovery, lifecycle prompts, public guides, service-worker return, and focus/containment behavior.

The new Library verifier proves:

| Case | Full Library JS | Full Library CSS | Result |
| --- | ---: | ---: | --- |
| Startup | 0 requests | 0 requests | Library absent; media Save remains available |
| First explicit open | 1 request | 1 request | busy state clears and the owned navigation action runs once |
| Repeated open | still 1 | still 1 | no duplicate assets; navigation runs once per press |
| Temporary stylesheet failure | 1 request | 2 requests | first press releases controls; second press succeeds |

Sensitive actions stopped at safe deterministic boundaries: no purchase, generation, upload,
destructive confirmation, sign-out, permission grant, external message, or data mutation was
performed by the automated control sweep.

## Validation

- complete Python suite: **998/998 passed** with repository-pinned FastAPI 0.116.1;
- JavaScript inventory and integration contract: **53 files passed**;
- real-browser control matrix: **43/43 passed**;
- production preflight, native web bundle, and client-credential boundary: passed;
- Python compilation, Ruff, and diff integrity: passed;
- GitHub CI `34527302176`: passed;
- Android store-bundle verification `34527302160`: passed; and
- iOS source verification `34527302140`: passed.

## Production acceptance

Production deployment `dpl_GumgE795YnTj7saXj31JwewG7DUy` reached **Ready** as the current
production release. The committed app shell, workspace runtime, media-save module, Library loader,
full Library script, and service worker matched the canonical production bytes exactly.

A signed-in canonical update activated cache revision `r231`. Before Library was pressed, the page
contained zero full Library scripts and zero Library styles. The first live Library press displayed
the complete private bookshelf, requested one full script and one stylesheet, and restored every
Library destination to enabled/not-busy. Grid, Book, and List each changed the selected layout, and
safe live navigation moved through Projects, Create, Video, You, and back to Ask with the active
destination changing every time. The inspected release log showed zero warning, error, or fatal
entries; all visible requests completed with HTTP 200.

## Remaining boundary

This release proves deterministic source ownership, real-browser behavior, deployment parity,
retry safety, and reduced startup work. It does not prove field-performance or conversion lift,
external provider quality, payment completion, destructive actions, or every signed-device
permission/download result. Investigate another control only from a reproducible user report or a
failing regression gate, and preserve paid and irreversible action-time boundaries.
