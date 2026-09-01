# Creation-sheet containment release — 2026-09-01

## Outcome

Ask Crump's document and image setup surfaces now behave like the focused creation dialogs they
visually present. The shared creation-sheet owner also gives its fallback **Add to conversation**
sheet the same complete interaction contract.

The signed-in production audit first reproduced the defect in **Create → Documents**: Document
Studio was an unlabeled generic section, its close control was announced only as **×**, focus stayed
in the workspace behind it, and the underlying application remained interactive and exposed to
assistive technology. The visual sheet was polished, but the interaction model was not.

The corrected owner now:

- exposes Document Studio as a named modal dialog and labels **Close Document Studio**;
- exposes Image Studio and the fallback Add sheet through the same modal boundary;
- moves focus to each sheet's named Close control when it opens;
- preserves and applies `inert` plus `aria-hidden` to every visible background root while leaving the
  live status/toast surface available;
- loops forward and reverse Tab navigation inside the open sheet;
- closes on Escape;
- restores the exact visible opener, or **Message Crump** when a transient Create chooser no longer
  exists; and
- restores every background root to its prior accessibility state.

Document outcomes, format choices, placeholders, tool selection, image reference behavior,
attachments, generation, delivery, prices, credits, plans, models, providers, Projects, Files, and
the already-verified conversational document-delivery route are unchanged.

## Release evidence

- Feature commit: `dc9dd736a486e1cf4ef6fce4fead937d291db30a`.
- Production deployment: `dpl_FcKD3JXqcw6QNpbeaRVxMYt5HsBK`, `READY` with no alias error on all
  six production aliases.
- Exact web/PWA/native script identity: `5.9.76-creation-sheet-containment-1`; runtime-loader
  identity: `5.9.76-creation-sheet-containment-loader-1`; service-worker cache:
  `ask-crump-new-body-v1-r200`.
- The canonical app, runtime loader, exact creation runtime, service worker, and health endpoint
  returned HTTP 200 after deployment. The live runtime contained the dialog labels, background
  isolation, focus containment, and fallback-sheet contract.
- A credential-free real-runtime fixture ran at 390×844 and 1280×720. Both sizes proved the named
  Document Studio and fallback attachment dialogs, background isolation and exact restoration,
  Close focus, reverse and forward focus wrapping, Escape, visible-opener and transient-opener
  recovery, the unchanged PPTX selection/composer handoff, and zero browser errors.
- The existing image-reference browser proof was extended to prove Image Studio background
  isolation, focus wrapping, exact focus return, and restoration while retaining optional reference
  upload, invalid replacement preservation, identity guidance, editable-image handoff, and zero
  browser errors.
- Adjacent Create → Video and image-safety-rejection recovery browser contracts remained green.
- Signed-in production proved Document Studio as an `aria-modal="true"` dialog named **Start with
  the outcome. Crump will structure the file.**, with **Close Document Studio** focused, the complete
  app root inert and hidden from assistive technology, Shift+Tab wrapping to **TXT Text**, Tab
  returning to Close, and Escape returning to **Message Crump** while restoring the app root.
- Signed-in production separately proved Image Studio with **Close Image Studio** focused and the
  same background boundary. No reference file was selected and no generation was sent.
- All **741 Python tests**, **47 JavaScript validations**, Python compilation, production preflight,
  native web-bundle generation, store metadata, mobile signing-source controls, and diff integrity
  passed.
- The inspected release window contained 77 HTTP 200 responses and five normal redirects, with no
  4xx or 5xx response, runtime-error group, or warning/error/fatal log.

No message, conversation, document, image, file, Project, account, credit, billing, analytics,
database, environment, campaign, publication, payment, or customer-content record was created or
changed during acceptance.

## Remaining evidence boundary

Repeat Document Studio and Image Studio open, focus wrapping, close, Escape, and format/reference
handoff on the exact signed iPhone and Android candidates with VoiceOver and TalkBack before store
screenshots. Observe legitimate external document/image setup → useful artifact → keep/download →
return outcomes before claiming activation or retention lift.
