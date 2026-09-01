# Precision lasso and invert-selection release — 2026-09-01

## Outcome

Ask Crump's Precision Edit Studio now lets a user draw a freehand **Lasso** around the exact part of
an image that may change. The outline is visible while it is being drawn and becomes an ordinary
gold selection when it closes. **Invert** switches the selection to everything outside the current
area, and both actions participate in the existing Undo/Redo/Clear history.

This is a manual editing control, not automatic subject recognition. It works with the existing
local warmth/exposure/saturation adjustments and the separate reviewed AI-edit handoff. No provider
request, upload, save, generation, or Crump Credit is used merely to draw or invert a selection.

## Product, privacy, and safety boundaries

- Lasso points are normalized to the source image and rasterized into the same transient alpha mask
  already used by Brush and Erase. At most 4,096 points are retained per outline, and a degenerate
  outline is rejected before it becomes a selection.
- The live trace uses a lightweight SVG guide. The full-resolution source canvas is filled only when
  the user finishes the outline, avoiding repeated image-scale redraws while the pointer moves.
- Invert is an explicit, undoable history action. It calculates current alpha-weighted coverage only
  when pressed and refuses an inverted result covering more than 90 percent of the image, matching
  the existing server-side maximum-mask boundary.
- The mask remains transient. Lasso coordinates, mask pixels, and selection coverage are not stored
  in Files, conversations, Projects, analytics, metadata, or traces.
- Unselected pixels remain protected by the existing server-side restoration after a generative
  edit. Local adjustments continue to be deterministic and no-credit.
- The release adds no face/person detector and no race or ethnicity classifier. It does not offer a
  **detect race** or **change race** control. Visible warmth and tone remain user-directed pixel
  adjustments inside a manually chosen area.
- Images of minors receive no special inference or automated selection. Any legitimate validation
  with a child image still requires a rights-cleared, consented fixture and a benign edit.

## Verification

- All **766 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Changed-file Ruff, JavaScript syntax, Python compilation, production preflight, native web-bundle
  creation, store metadata, mobile signing-source controls, and diff integrity passed.
- Desktop and 390-by-844 real-browser proofs covered the visible lasso guide; closed-polygon fill;
  exact selected/unselected alpha; invert; Undo/Redo; Clear; rejection of an over-broad inversion
  without changing the mask; Brush, Move, zoom, local preview/save request shape, exact overlays,
  focus return, scrollable controls, and zero horizontal overflow or browser errors.
- Signed-in production opened the existing synthetic cat conversation, launched Precision Edit on
  the first generated cat image, and displayed **Lasso**, **Invert**, the updated manual-selection
  guidance, and the complete existing studio. Invert was correctly disabled before a selection.
  The editor was closed without drawing, uploading, saving, generating, writing to a Project, or
  using credits. A separate private image in the conversation was not opened or edited.
- The production script, stylesheet, workspace guide, runtime loader, and service worker matched the
  shipped commit byte-for-byte. Both canonical health endpoints returned HTTP 200.
- The exact deployment was `READY` on all six aliases. The inspected release window had no 4xx/5xx,
  no warning/error/fatal log, and no runtime-error cluster.

## Release identity

- Feature commit: `de31f84409b34108d772d0b94cb82ed86858b543`
- Production deployment: `dpl_8nyVbmAGnFUQU5UxCMDAuD7VZ4s6`
- Status: `READY`
- Build duration: about 43 seconds
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project/main aliases
- Precision Edit script: `5.9.76-lasso-invert-1`; SHA-256
  `A172CF64E35CE6DA287703815D7B0AA3379B4F993ABC7BDEB779F1A353F4EEDB`
- Precision Edit stylesheet: `5.9.76-lasso-invert-1`; SHA-256
  `94812C3EE9AD9C9609D275329EB71812529A73FAA7E3CBDBAFBB00F086CE0114`
- Workspace guide: `5.9.76-local-photo-studio-guide-1`; SHA-256
  `495ABC01FBD79303D1FAAA53E45008BE5E2F77B1BA7F26E30D6631C06A5D0711`
- Runtime loader: `5.9.76-local-photo-studio-loader-1`; SHA-256
  `F2E1394421BDC9AA8DC20CDA449A82992E5658D20DA2F58D5E59241C10A9E16F`
- Service worker cache: `ask-crump-new-body-v1-r205`; SHA-256
  `8D6D56D36E3530B1311149483FE1F22D553DE464BA6193096C80B371989CB307`

## Remaining acceptance work

1. Repeat lasso, invert, Undo/Redo, local save, reopen, and download on exact signed iPhone and
   Android candidates using only rights-cleared fixtures.
2. Perform one founder-approved legitimate provider edit and confirm exact outside-selection pixel
   restoration, stable credit disclosure, recovery, and stored-result continuity.
3. Add feathering, crop/rotate, and an explicit immutable source/version-history browser only when
   legitimate usage establishes their priority and the same privacy/recovery gates are satisfied.
4. Keep automatic subject recognition and sensitive-attribute inference out of the workflow.
5. The native web bundle includes this release, but Android/iOS shell preparation and RevenueCat
   public keys remain separate store-release gates; no signed store candidate is claimed here.
