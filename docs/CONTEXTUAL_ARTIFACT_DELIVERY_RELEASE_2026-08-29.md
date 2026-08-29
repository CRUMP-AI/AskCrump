# Contextual artifact delivery reliability release — 2026-08-29

Status: verified in production; legitimate external artifact outcome pending

## Decision

Extend the shipped conversational document-delivery fix so ordinary follow-ups such as “make that
downloadable,” “export it,” and “turn that into a file” do not depend on a successful semantic-router
call. Preserve the existing answer-in-chat path when the request is ambiguous or the newest creation
context is an image, video, or manuscript.

## Evidence before the change

- Commit `c4ef9ee` already guaranteed that an explicit phrase such as “deliver this in a document
  format” could not be downgraded to another clarification.
- The deterministic artifact detector only received the current message. A shorter contextual
  follow-up contained no format noun, so a temporarily unavailable or inconclusive semantic router
  left no artifact format to package.
- The internal-excluded production funnel still contained zero eligible external accounts at every
  stage, and the protected artifact-journey snapshot remained empty. This release therefore repairs
  a reproducible contract; it does not claim conversion or customer impact.

## Change

- `ArtifactService.detect_request` now accepts recent conversation history as an optional input.
- A contextual fallback runs only when the current message contains both a bounded delivery action
  and an anaphoric/file reference.
- Format recovery reads at most the last 12 history entries, considers only user-authored text, and
  selects the most recent supported document class: PowerPoint, Excel, Word/document, PDF, Markdown,
  or text.
- A newer image, video, or manuscript request stops the search. It cannot inherit an older document
  format.
- “Save it” remains too ambiguous and stays on the ordinary chat path.
- The active Crump 5.2 compatibility override now preserves the history-aware detector signature.
- The chat route passes the existing bounded history into detection before intelligence preparation;
  no new stored field, event property, entitlement, provider, or customer-facing claim was added.

## Executable proof

The detector regressions prove:

- a résumé followed by “Make that downloadable” resolves to DOCX;
- a presentation followed by “Can you export it?” resolves to PPTX;
- an Excel workbook followed by “Turn that into a file I can download” resolves to XLSX;
- no history, image-only history, “Save it,” and newer image context all fail closed.

A real FastAPI `/api/chat` regression deliberately returns no semantic creation intent, then submits
“Can you export it?” after a presentation conversation. The route:

1. resolves `artifactFormat=pptx`;
2. adds the artifact-creation guidance to the model payload;
3. packages a PPTX response artifact;
4. emits content-free `ArtifactRequested` and `ArtifactPackaged` milestones with the presentation
   category; and
5. returns a successful API response.

## Verification

- Feature commit: `26e41e4` (`Harden contextual artifact delivery`).
- Production deployment: `dpl_HXwQSeb1bqirPBfvC1tBpeWAZpRt`, `READY` on all six Ask Crump and
  Clever Crump aliases with no alias error.
- All 440 regression tests passed.
- Explicit Python compilation passed.
- All 45 JavaScript files validated.
- Production preflight, native web-bundle creation, and store-metadata checks passed.
- Canonical production health returned HTTP 200, success, and version 5.9.75 with no browser error.
- The release window contained no Vercel runtime error cluster and no warning, error, or fatal log
  for the deployment.
- Verification created no production conversation, message, artifact, account, event, Project,
  payment, social post, or Search Console change.

## Outcome boundary

Delivery reliability is verified. Acquisition-to-artifact conversion remains unproven until a
legitimate external account requests, receives, and downloads a file. Review the first real
artifact-journey row rather than generating production evidence.
