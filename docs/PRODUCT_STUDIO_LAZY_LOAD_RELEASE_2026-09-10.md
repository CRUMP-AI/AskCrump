# Product Studio on-demand loading release — 2026-09-10

## Decision

Keep every shipped Projects, Files, Manuscripts, Video, and Project-continuity
action, but do not make a clean authenticated workspace download and parse the
entire Product Studio before the person chooses one of those destinations.

This is a startup-delivery change, not a feature removal or a performance-lift
claim.

## Released behavior

- The authenticated runtime now loads `crump-product-loader.js` in place of the
  full Product Studio script and stylesheet.
- The loader preserves the complete public Product Studio action contract:
  open a destination, open a named Project, open Files, resolve Project
  continuity, keep a conversation or artifact, open a manuscript, and accept a
  creation handoff.
- Projects, Files, Manuscripts, Video, and Library receive a visible busy state
  while their first Product Studio load is in progress.
- Concurrent first actions share one load. Later actions reuse the loaded
  Product Studio without repeating the loading notice.
- A temporary script or stylesheet failure restores the controls and can be
  retried without duplicating the successful asset.
- A saved active Project, pending video request/job, existing conversation, or
  Project deep link still hydrates Product Studio automatically. That protects
  Project context injection and background video-status recovery.
- The native web runtime uses the same on-demand boundary. The full Product
  Studio assets remain packaged locally for later use.
- Cache revision `ask-crump-new-body-v1-r236` pre-caches the small loader but no
  longer pre-caches the full Product Studio script or stylesheet.

## Deterministic startup effect

The prior ordinary authenticated plan carried:

- `crump-product-5.3.js`: 146,213 raw bytes
- `crump-product-5.3.css`: 31,856 raw bytes

The replacement loader is 8,029 raw bytes. A clean workspace with no persisted
Project/video/conversation continuation therefore avoids 170,040 raw source
bytes and one startup stylesheet until Product Studio is actually needed.
Returning work intentionally loads the full module when continuity requires it.

## Executable proof

`scripts/verify-product-studio-lazy-load.cjs` proves in a real browser that:

1. a clean workspace starts with the public facade but requests neither full
   Product Studio asset;
2. the first Projects action exposes busy state and loads the script and
   stylesheet exactly once;
3. a later Video action uses the loaded implementation and emits no duplicate
   loading notice or request;
4. a one-time stylesheet failure restores the Projects control and the second
   action succeeds while reusing the already loaded script; and
5. a persisted Project resumes the full implementation without opening a
   destination or creating data.

The fail-closed browser inventory now requires 45 exact verifiers.

## Validation

- Python: 1,003/1,003 passed
- JavaScript: 54/54 validated
- attribution runtime fixtures: 22/22 rough-to-useful, 10/10 Word/PDF, and
  10/10 résumé-audit cases passed
- browser controls: 45/45 passed
- product loader retry/persisted-state browser proof: passed with zero browser
  errors
- production build preflight: passed
- native web bundle: passed
- public/native client-secret boundary: passed
- Ruff and Python compilation: passed
- store metadata and native privacy source checks: passed
- local signed-native verification remains inapplicable in this worktree because
  the generated Android/iOS projects and release-time billing keys are not
  present; the hosted platform workflows remain the authoritative source gate
- diff integrity: passed

## Release evidence

- product commits: `3514334`, `f0d76d8`, and cache-safe release `59c7eb9`
- production deployment: `dpl_6zU18YFZURenWL6HgEW1aTuV8rjT`
- CI: `34538797450`
- Android source/bundle verification: `34538797475`
- iOS source verification: `34538797466`
- the live `/app`, runtime, loader, full Product Studio script, full stylesheet,
  service worker, and health endpoint all returned HTTP 200
- the first six live files matched their committed SHA-256 bytes
- the live runtime and service worker include the loader and exclude the full
  Product Studio from the initial/pre-cache plan; the loader names both full
  assets for on-demand use
- a signed-in production replay adopted cache revision `r236`; the first
  **Start or open a Project** action showed **Opening Projects…** and opened the
  real owner-scoped Project list with the specific **Close Projects** control
- after Product Studio was loaded, the visible **Video** destination opened
  **Video Studio** without a duplicate loading notice

## Boundaries retained

No account, Project, conversation, file, image, video, manuscript, database,
provider, credit, plan, checkout, price, entitlement, credential, campaign, or
customer-content state changed. No provider run, upload, download, purchase,
destructive action, permission grant, social publication, external message, or
store submission occurred.

Field startup improvement and signed physical-device performance remain
unproven until comparable real-user evidence exists.
