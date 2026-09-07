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

Production acceptance requires the READY deployment to serve the exact versioned
`crump-5.0.js` and `crump-5.2.js` bytes, the health endpoint to remain ready, and fresh
desktop and phone-width checks to prove both creation routes and composer reset behavior
without console errors. Deployment identifiers and live proof are appended only after
that acceptance is complete.
