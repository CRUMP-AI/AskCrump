# Button integrity release — 2026-09-07

## Outcome

The authenticated Ask Crump workspace was exercised as a user on desktop and at a
390-by-844 phone viewport. Two real interaction failures were found and corrected:

1. **Add → Create image** and **Add → Create document** looked actionable but only
   changed hidden legacy composer state. They now open the authoritative Image Studio
   and Document Studio, respectively.
2. Closing or sending a specialized image/document composer mode could leave its old
   placeholder behind, including after opening another conversation. Mode removal now
   restores the normal Ask placeholder, preserves the active Project context, and returns
   keyboard focus without scrolling the page.

## Interaction coverage

The release audit covered the visible authenticated controls for Ask, Chats, Projects,
Files, Create, Video, Library, Intelligence, and You. It also covered conversation menus,
project/file handoffs, image and PowerPoint viewers, Image Precision Edit controls,
Document Studio, Video Studio references and saved-job navigation, Library layouts and
Recently Deleted, settings tabs, plan handoff, the mobile Chats drawer, and the six-step
tutorial.

Destructive account, conversation, Project, file, memory, and library operations were
verified through their safe confirmation boundary; no customer data was deleted or
changed for this audit.

## Automated proof

- 849 Python tests collected: 847 passed and two environment-dependent tests skipped.
- All 49 JavaScript assets passed syntax, duplicate-action, runtime-version, cache, and
  attribution validation.
- Ruff, Python compilation, production preflight, native web-bundle creation, and diff
  integrity passed.
- Fourteen browser verifier runs covered the new fixes plus creation handoffs, files,
  settings, Project save/recovery, Video, tutorial, the mobile drawer, section isolation,
  and the complete Precision Edit workflow. Their browser-error arrays were empty.
- New executable desktop and phone fixtures prove that both Add-menu creation actions
  open visible, focused studios and never set the retired hidden creative mode.
- A new composer-state fixture proves neutral and Project-context placeholder recovery,
  chip removal, and focus restoration.

The optional native store verifier remains blocked by the already-recorded owner/platform
gates: the repository does not contain generated Android/iOS projects and the local build
does not have the owner-controlled RevenueCat public SDK keys. Those conditions do not
affect this web/PWA release; no store-readiness claim is made here.

## Production acceptance

Commit `42c4472` deployed as `dpl_8YF4LFiLvmED2J9ifrtvpqW5yyWH`. Vercel reported the
deployment READY with all six production aliases and no alias error. All four public
domains returned health version `5.9.76` and served the exact committed bytes for both
corrected assets:

- `crump-5.0.js` — SHA-256
  `249760a3db6f0910463c60461f3225279493caaf00942eba385dfee7c45f6d3f`
- `crump-5.2.js` — SHA-256
  `b9c0d9c4d203391727aa8f383e178f188e5a178575c7336f5d6f38db6cd5ad93`

A fresh isolated signed-in production tab then proved Add → Create image, Add → Create
document, DOCX-mode entry, chip removal, neutral placeholder restoration, and composer
focus on desktop. At 390 by 844 it proved both studios visible with their close controls
focused. The existing owner tab and its unsaved image-editor state were not reloaded or
changed. No prompt was sent, no file was uploaded or generated, and no account, Project,
conversation, payment, credit, provider job, or customer content was mutated for proof.

The first 30-minute post-deployment runtime-error query returned no clusters; the
deployment-scoped warning/error/fatal log query returned no entries.
