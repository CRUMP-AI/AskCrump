# Ask Crump 5.9.76 image-reference entry release

Date: 2026-09-01

Feature commit: `5c11d86355e5afc10920b43c1e90d33b465610fa`

Production deployment: `dpl_DGECUFiNbaqcWE1jydNZS3RS13FQ`

## Outcome

Image Studio now provides a direct, optional **Add an image to edit** path. A user no longer has
to infer that the general composer attachment control is also the entry point for an image edit.
After selection, the image appears in the existing private attachment tray and Image Studio changes
to **Reference image ready** with a clear **Continue with reference** action.

The studio also explains the real fidelity boundary: for edits involving a person, users should
describe what changes while Crump asks the image model to preserve identity and appearance. Logos
and readable text are explicitly described as details that can still vary and must be reviewed.
This is guidance and prompt control, not a guarantee of pixel-exact generative output.

No model, provider, prompt-safety policy, moderation threshold, image price, credit amount, plan,
entitlement, upload endpoint, file-storage boundary, analytics event, database object, or customer
record changed.

## User-eye finding

A signed-in production walkthrough confirmed the startup cover blocks interaction until the
workspace is ready and that **Create an image** opens correctly. The actionable gap was one level
deeper: Image Studio promised generation and editing but exposed only aspect ratio, quality, and a
generic continuation button. Editing required discovering a separate composer attachment path.

The corrected contract is:

- one optional single-image picker inside Image Studio;
- JPG, PNG, WebP, HEIC, and HEIF selection, using the existing private upload flow;
- an existing image is recognized as the edit source;
- replacement removes only pending image attachments and leaves non-image attachments alone;
- an invalid replacement is rejected before the existing valid reference is removed;
- the image filename is rendered with `textContent`, not interpolated into HTML;
- the dialog has a name, modal semantics, initial close-button focus, Escape dismissal, and focus
  restoration when its opener remains available;
- aspect and quality choices expose synchronized pressed state; and
- creating without a reference remains a distinct, explicit path.

## Automated and browser verification

- All **724 Python tests** passed.
- All **47 JavaScript validations** passed.
- Python compilation and production build preflight passed.
- The native web bundle built successfully.
- Store metadata and signing-source controls passed; no signing secret was present.
- `scripts/verify-visual-media-browser.cjs` passed at **390×844** using the real studio and upload
  runtime. It proved initial dialog focus, modal labeling, a direct reference picker, private upload
  preview, the reference-ready state, edit-specific composer guidance, and preservation of the
  current valid reference after an invalid replacement, with zero browser errors.
- `git diff --check` passed.

The isolated release worktree does not contain generated Android or iOS platform projects, and the
local shell did not contain RevenueCat public SDK keys. Signed archives, native store billing, and
physical-device behavior are therefore not claimed by this release.

## Production evidence

Vercel marked the exact commit deployment **READY** and assigned all six production aliases.
Canonical production returned HTTP 200 for `/app`, `runtime-body-v1.js`, both exact versioned Image
Studio assets, and `sw.js`. The service worker serves cache revision
`ask-crump-new-body-v1-r188`; the changed JavaScript and CSS serve version
`5.9.76-image-reference-entry-1`.

In the signed-in canonical app, **Create an image** opened an **Image Studio** dialog that exposed:

- **Add an image to edit**;
- **Create without reference**;
- named close and modal semantics; and
- the identity-preservation and logo/text-review guidance.

The studio was closed without selecting a production file, sending a request, creating an image,
or changing durable data. The inspected deployment window contained **10 HTTP 200 responses**, no
4xx/5xx response, no runtime-error cluster, and no warning/error/fatal log.

## Remaining outcome gate

Repeat reference selection, upload, generation, replacement, safety-rejection revision, download,
and relaunch on a physical iPhone and an Android signed candidate. Observe legitimate customer
edits across varied skin tones, ages, lighting, and themes before claiming improved identity
fidelity. Use supplied reference assets for logos, but do not advertise exact mark or text fidelity
until a representative production-quality benchmark supports that claim.
