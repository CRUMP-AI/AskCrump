# Files progressive-disclosure release

**Date:** 2026-09-01

**Product commit:** `2b42332cea027004ba6d94ac87521f0b18d72196`

**Production deployment:** `dpl_syJJ4MZLvKFFx4v48wFi73koTg5T`

**Runtime asset:** `5.9.76-file-library-window-1`

**PWA cache:** `ask-crump-new-body-v1-r189`

## Outcome

Files now presents a useful first set instead of turning a large private library into one long
mobile wall. The first view renders 12 matching items, reports the exact shown and total counts,
and exposes one restrained **Show more files** action. Each action reveals up to 12 more items.
Search, category, sort, refresh, and a fresh Files visit reset the window to the predictable first
set so an old expanded state cannot make the next visit feel heavy or disorienting.

No storage, file, Project, search, sort, preview, download, attachment, signed-URL, generation,
entitlement, credit, billing, or analytics contract changed.

## User-eye finding

A signed-in production walkthrough first reconfirmed the earlier preview-layer repair: opening a
private image placed its viewer above the Files workspace, and **Done** returned to the same Files
surface. The next deterministic friction was scale. The account had 65 private items—18 videos,
23 images, and 24 documents—and the old first view created all 65 cards and all 18 video preview
elements in one surface even though secure video playback itself remained intersection-gated.

The released production walkthrough then proved:

- first Files view: 12 cards with **Showing 12 of 65 saved items**;
- reveal action: 24 cards with focus retained on **Show 12 more files**;
- Images category: reset to 12 cards with **Showing 12 of 23 matches** and **Show 11 more files**;
- private preview: **Done** remained visible above Files and returned to Files;
- closing Files returned to the signed-in Ask composer; and
- the inspected browser produced zero warning or error entries.

No file was uploaded, changed, downloaded, attached, renamed, deleted, or shared. No generation,
message, checkout, credit, or customer-data mutation occurred.

## Implementation boundaries

- `LIBRARY_PAGE_SIZE` is fixed at 12.
- The full owner-scoped file result remains available in memory for local search, filter, and sort;
  only the rendered card window is bounded.
- The status distinguishes total saved items from current matches and currently rendered items.
- The reveal button is hidden when every current match is visible and announces the exact next and
  remaining counts.
- Search input, category changes, sort changes, refresh, and a fresh Files entry reset the visible
  limit. The current-session sort choice otherwise remains intact, preserving the existing return
  behavior.
- Secure video previews remain lazy and intersection-gated; image previews retain native lazy
  loading.

## Verification

- **726 Python tests passed, 0 failed.**
- **47 JavaScript files validated.**
- The expanded deterministic Files fixture passed at 1440×1000 and 390×844 with zero errors. It
  proved initial 12-of-15 rendering, exact reveal counts, all-item completion, filter/search/sort
  resets, preserved return state, phone-safe 16-pixel search input, and no horizontal or dialog
  overflow.
- Adjacent real-browser checks passed for private file delivery, Project/Files/Video/Library studio
  isolation, direct Video navigation, Create → Video, and every six-step tutorial destination.
- Python compilation, production preflight, native web-bundle generation, store-metadata source
  checks, mobile signing-source controls, and Git diff integrity passed.
- The native verifier retained only the existing release-time gates: generated Android/iOS projects
  and RevenueCat public SDK keys are absent in this shell. No signed native-candidate claim is made.

## Production evidence

Deployment `dpl_syJJ4MZLvKFFx4v48wFi73koTg5T` reached **READY** on:

- `www.askcrump.com`
- `askcrump.com`
- `www.clevercrump.com`
- `clevercrump.com`
- the production project alias; and
- the `main` branch alias.

Health, service worker, runtime loader, and both versioned Files assets returned HTTP 200. The live
loader and worker contained `5.9.76-file-library-window-1`; the worker contained cache `r189`.
The deployment-scoped release window contained 29 HTTP 200 and seven expected redirect responses,
with no 4xx/5xx response, no grouped runtime error, and no warning/error/fatal log.

## Remaining gate

The web/PWA release and native-bundle inclusion are verified. Repeat large-library reveal,
search/filter/sort, private preview, download, and return behavior on exact signed iPhone and Android
candidates with VoiceOver/TalkBack, safe areas, and slow connectivity before store screenshots.
Observe legitimate Files return behavior before claiming a retention or performance lift.
