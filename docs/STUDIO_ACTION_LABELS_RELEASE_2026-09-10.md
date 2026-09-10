# Studio action labels release — 2026-09-10

## Outcome

Ask Crump's Projects, Files, Manuscripts, Video, and Library workspaces now name
their actions for the exact destination or item they affect. This closes the
remaining vague-control gap found during the whole-product button audit without
changing creation, storage, billing, provider, or destructive behavior.

## Product behavior

- The shared workspace close control now announces Projects, Files, a named
  Project, new Project, Manuscripts, Video Studio, or Library according to the
  visible destination.
- Files refresh announces `Refresh private Files`.
- manuscript Pause, Resume, and Cancel controls include the active manuscript
  title when one is open.
- section Save and Draft controls include the active section title.
- the Video Studio reference control announces `Add video reference image`.
- context labels normalize whitespace and stop at 120 characters so an imported
  title cannot create an unbounded accessible name.

## Automated evidence

Product commit `f86fad8` adds the exact names and expands the existing studio
isolation verifier on desktop and phone widths. The verifier now reopens a named
Project before every destination transition, proves its exact close label, and
then covers Projects, Files, new Project, Video Studio, Library, and Manuscripts,
including the Files refresh and Video reference controls.

The complete release gate passed:

- **1,002/1,002** Python tests;
- **53/53** JavaScript file validations;
- **44/44** real-browser control flows;
- production preflight, native web build, client-credential boundary, compilation,
  Ruff, and diff integrity;
- GitHub CI **34535247208**, Android **34535247232**, and iOS source verification
  **34535247234**.

## Production evidence

Production deployment `dpl_8pNsm1VvmB7ztyms1Mipcyac31k4` is Ready for commit
`f86fad8`. The live app shell, runtime body, product controller, and service worker
all returned HTTP 200 and contained the expected `studio-action-labels-1` release
or cache `r234` marker.

A signed-in production replay used the actual controls and visibly proved:

- `Close Projects`, `Close Files`, and `Refresh private Files`;
- `Close new Project` after opening the new-Project form without saving it;
- `Close Video Studio` and `Add video reference image` without uploading or
  generating;
- `Close Manuscripts` after entering through Create; and
- `Close Library` on the books-and-manuscripts-only Library.

The matching deployment's filtered 30-minute production log showed **0 Warning,
0 Error, and 0 Fatal** entries during the replay.

## Safety boundary

No Project, file, manuscript, book, image reference, or video was created,
changed, uploaded, downloaded, generated, or deleted during production
acceptance. No customer prompt, response, filename, email, or identifier was
recorded. Purchases, destructive confirmations, provider execution, permissions,
uploads, downloads, and signed physical-device outcomes retain their existing
action-time gates.
