# Project workspace and shell lockup release

Date: 2026-08-29

## Outcome

Ask Crump Projects now open as dedicated, named workspaces instead of silently
repopulating the Project editor. The app-shell identity also uses the approved
`An AI workspace for work that continues` lockup in a deterministic paint box.

## User-visible correction

- Projects first open to a clear index of the user's Projects.
- Each row has an explicit `Open` action and accessible Project-specific name.
- Opening a Project changes the sheet to that Project's workspace, including its
  description, instructions, reference files, created files, conversations,
  canon, and durable notes.
- `New chat in this Project` starts a clean presentation state with the Project
  selected and a Project-specific composer placeholder. It does not persist an
  unused blank conversation.
- `Back to all Projects` returns to the Project index.
- `New Project` uses a separate create state so the previously selected
  Project's content is not shown as part of an unsaved Project.
- On phone layouts the Project workspace occupies the available sheet and the
  Project index is hidden while a Project is open.

## Root cause

The Project row click previously selected a Project and repopulated an edit form,
but it did not create a distinct navigation state, title transition, workspace
view, or visible open affordance. The click technically ran, yet the interface
gave the user no reliable evidence that a Project had opened.

The remaining header-brand movement risk came from combining asynchronously
restored Project context with the brand container and from resampling a 1200 by
296 asset into a fractional presentation box.

## Brand correction

The app shell now uses `/assets/brand/crump-shell-lockup-light.png`, a dedicated
1200 by 300 RGBA asset generated deterministically from the approved current
lockup. Its SHA-256 is
`58bed52e4bbfc2910e01e9384f996e2c5f7491fb8b5d7f2727f79df367c28c10`.
Project context is rendered outside the brand container.

The signed-in production logo stayed at x=111, y=15.6667, 200 by 50 pixels from
the initial loaded sample through 5.375 seconds, with the same complete
1200-by-300 source in every sample.

## Verification

- 467 Python tests passed.
- 45 JavaScript files passed the integration validator.
- Production preflight, native web bundle, and store metadata checks passed.
- A credential-free real-client fixture proved Project index, named workspace,
  Back navigation, New Project, and Project-chat handoff with zero browser errors.
- A signed-in production click opened `The Last Distance` as
  `Ask Crump Project: The Last Distance`, exposing its Project files,
  conversations, instructions, canon, and `New chat in this Project`.
- Production Back navigation returned to the eight-Project index.
- Canonical health returned HTTP 200 for Ask Crump 5.9.76.
- The new logo asset and service worker returned HTTP 200; cache revision
  `ask-crump-new-body-v1-r124` precaches the new asset.
- The release window contained 54 HTTP 200 responses, no 4xx or 5xx response,
  and no runtime error cluster.

## Release

- Code commit: `a160dedcaed16b281514697a057f7e9ab254fc2f`
- Production deployment: `dpl_AuCrCSecFTyrvi7AHLERExkHsEFG`
- Production aliases: `askcrump.com`, `www.askcrump.com`,
  `clevercrump.com`, and `www.clevercrump.com`

