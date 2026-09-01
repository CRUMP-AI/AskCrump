# Project chat context boundary release

Date: 2026-09-01

Feature commit: `e20d010c56d1bf4a0791439172e2df3372d9ca90`

Production deployment: `dpl_7p5FcuRgRmYrSiLgcDrcAtDv3GMR`

## User problem

Ask Crump used one client value for two different ideas: the Project a user had opened or chosen
as a save destination, and the Project whose instructions, canon, and reference files should shape
the current conversation. Merely browsing a Project could therefore add that Project to later chat
requests. The context indicator was also hidden at phone widths, so an unrelated conversation
could inherit Project context without a visible explanation or control.

## Shipped behavior

- A Project selected for browsing, file work, manuscript work, or a video save destination no
  longer becomes conversation intelligence implicitly.
- **Use in current conversation**, **New chat in this Project**, and **Keep in a Project** remain
  the deliberate ways to apply Project context.
- Opening an existing conversation already kept in a Project restores that owner-scoped Project
  relationship and its context.
- A fresh or unrelated conversation stays free of Project context even while the Project remains
  the visible save destination for work that explicitly uses it.
- Desktop shows a restrained **IN PROJECT · Project name** chip in the workspace header. Phone
  layouts show a named **IN PROJECT** strip directly above the composer, explain that context is
  applied to this conversation, and provide a one-tap **Leave** action.
- **Leave** pauses Project context for that conversation in the current app session without
  deleting the conversation, removing it from the Project, changing the Project save target, or
  altering any durable data.
- The browser confirms a content-free owner-scoped relationship before omitting Project context.
  If that lookup is unavailable, the chat server performs the same owner-scoped relationship
  recovery. An explicit Project ID still wins only after the existing ownership validation.
- The content-free `projectContextChecked` transport marker is removed before intelligence,
  generation, storage, or provider processing.
- No account, Project, conversation, file, prompt, response, generation, entitlement, credit,
  billing, analytics event, database object, separate API release, or customer data changed.

## Automated and local proof

- All **720 Python tests** passed.
- All **47 JavaScript validations** passed.
- Production preflight, native web bundling, store-metadata checks, signing-source controls, and
  diff integrity passed. Store submission still has its separate platform/signing/device gates.
- New backend tests prove owner-scoped relationship recovery, confirmed unrelated-chat bypass,
  marker removal, and explicit-Project precedence.
- A real-browser boundary fixture at **1280×760** and **390×844** proved:
  - browsing a Project preserved its save target but added no chat context;
  - an unrelated and a fresh chat sent no Project ID and carried the confirmed-null marker;
  - a linked chat restored the exact Project ID and named indicator;
  - Leave removed the Project ID and preserved the separate save target;
  - the phone dock expanded from 100px to 146px only while context was active; and
  - both viewports completed with zero browser errors.
- Eight adjacent Video, reference-image, File delivery, File findability, image-scroll, Studio,
  lifecycle-continuity, and persistent-destination browser flows remained green on desktop and
  phone.

## Production proof

GitHub deployed the exact feature commit to `READY` on all six production aliases with no alias
error. The canonical runtime serves `5.9.76-project-chat-boundary-1` for `app.js` and both Project
assets, plus service-worker cache `ask-crump-new-body-v1-r184`.

After accepting the PWA update, a signed-in user-eye walkthrough opened **Savannah Reading
Series** and returned to Ask. The Project remained available as a save destination, while the
conversation displayed no Project chip, no mobile context strip, the default composer prompt, and
an inactive chat-context state. Continuing the already-linked saved conversation restored the
exact named mobile strip in the live 543px browser panel. The measured dock height was 146px and
horizontal overflow was zero. Leave removed the strip, returned the dock to 100px, kept overflow at
zero, and did not perform a durable write. **Use in current conversation** then restored the
original context after verification. No message was sent and no customer content was created,
edited, copied, logged, or deleted for this proof.

The feature-deployment window contained 41 successful 200 responses, no 4xx or 5xx log, no
runtime-error cluster, and no warning/error/fatal runtime log.

## Rollback and remaining gate

Rollback is the single feature commit above and requires no data repair. Before store screenshots,
repeat browse-only Project selection, linked-conversation restoration, Leave, explicit reuse, a
real follow-up, and a fresh unrelated conversation on a physical iPhone with VoiceOver, safe areas,
backgrounding, and the software keyboard. This release proves context isolation and user control;
it does not by itself prove activation or retention lift.
