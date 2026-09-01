# Deterministic exact overlay release — 2026-09-01

## Outcome

Ask Crump's Precision Edit Studio can now place a rights-cleared logo, image, or exact text on an
existing image without asking a generative model to redraw it. The user adds the overlay, selects
**Place**, drags it into position, and adjusts size, opacity, and text color against the real source
image. **Save local edit** creates a normal private PNG in Files. This path uses no AI provider and
no Crump Credits.

The manual Brush/Erase boundary and the separate **Continue with AI edit** action remain unchanged.
The workspace guide now explains that exact marks and readable text can be placed without an AI
redraw.

## Product, privacy, and safety boundaries

- The overlay is browser-rasterized at the exact source-image dimensions and alpha-composited by
  Ask Crump's server. The model does not see, reinterpret, or recreate the logo or text.
- A local save may contain bounded manual tone adjustments, deterministic overlays, or both. An
  overlay-only save requires no brush mask and sends zero warmth, exposure, and saturation values.
- The source image is owner-checked. The server accepts only a single-frame alpha PNG overlay with
  the exact source dimensions, a visible alpha channel, at most 2 MiB of decoded PNG data, and no
  more than 16,777,216 pixels. The browser also limits uploaded overlay sources to PNG/JPG/WebP,
  8 MiB, 16,777,216 pixels, and 12 overlay items per edit.
- Retry identity is calculated incrementally from length-delimited owner/source/mask/value/overlay
  inputs. The same save retry resolves to the same private file identity without retaining the
  overlay payload in metadata.
- Saved metadata contains fixed edit flags, the source file ID, image dimensions, and bounded local
  adjustment values. It contains no overlay pixels, text, filename, prompt, inferred trait, mask,
  provider response, or customer-content analytics.
- The editor adds no face, person, race, ethnicity, age, or identity classifier. Visible tone
  remains a manually selected pixel adjustment, not a race label or a **change race** control.
- Users are told to use rights-cleared artwork. The separate overlay source is transient and is not
  saved as another Ask Crump file; only the user-approved flattened result is saved.

## Verification

- All **766 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Changed-file Ruff, JavaScript syntax, Python compilation, production preflight, native web-bundle
  creation, store metadata, mobile signing-source controls, and diff integrity passed.
- Service tests proved overlay-only composition, exact outside-artwork preservation, alpha and
  dimension rejection, no-provider/zero-credit receipts, safe metadata, and retry-stable identity.
- Desktop and 390-by-844 real-browser proofs covered exact image and text placement, drag, size,
  opacity, overlay pixels, overlay-only request shape, local save receipt, Brush/Erase/Move, zoom,
  Undo/Redo, local preview, original comparison, focus return, scrollable controls, and zero
  horizontal overflow or browser errors.
- Signed-in production opened an existing generated cat image, launched the exact editor, and
  displayed **Place**, **EXACT OVERLAY · NO AI OR CREDITS**, **Add logo or image**, exact text/color,
  size, opacity, and disabled no-change save. The editor was closed without upload, painting, save,
  generation, Project write, credit use, or customer-data mutation.
- The production script, stylesheet, workspace guide, runtime loader, and service worker matched the
  shipped commit byte-for-byte. Both canonical health endpoints returned HTTP 200 and version
  5.9.76.
- The exact deployment was `READY` on all six aliases. The inspected release window had 45 HTTP
  200s and three normal redirects, no 4xx/5xx, no warning/error/fatal log, and no runtime-error
  cluster.

## Release identity

- Feature commit: `b0ed801fbbc979de221b46e1b3d1b63831086afd`
- Production deployment: `dpl_D57wGLABDKwqoFt6yEYrM2PASVNu`
- Status: `READY`
- Build duration: about 51 seconds
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project/main aliases
- Precision Edit script: `5.9.76-exact-overlay-1`; SHA-256
  `7F7A7FBECBC7284FB7F9D6B1FE912B592F8DCCD93A207BD1269AB9C9F80AC864`
- Precision Edit stylesheet: `5.9.76-exact-overlay-1`; SHA-256
  `9BFA4A7C01E09A664E3ABEA639E30335951F232266FBDC5923734C1D3FE696FE`
- Workspace guide: `5.9.76-local-photo-studio-guide-1`; SHA-256
  `EC4C11E6A0102381EB76F972E1C86298BFE39E98857DE3ADB2A19434D9434B21`
- Runtime loader: `5.9.76-local-photo-studio-loader-1`; SHA-256
  `8314EDB5EFA79FB13227732875E8F9AE853DDB2AFA7EC8013161F3F841C7B918`
- Service worker cache: `ask-crump-new-body-v1-r204`; SHA-256
  `2561E421A319EEB23D96EB898850B82392906F9436522F734B09A01D80ED26C8`

## Remaining acceptance work

1. Run one founder-approved, rights-cleared production overlay save and verify reopen, download,
   Project attachment, and visual comparison with the source.
2. Repeat touch placement, software-keyboard text entry, save, reopen, and download on exact signed
   iPhone and Android candidates before advertising exact-logo fidelity.
3. Add lasso, invert selection, feathering, crop/rotate, and an explicit version-history browser only
   after legitimate usage shows which controls materially improve kept work.
4. Keep automatic subject recognition and any sensitive-attribute inference out of this workflow.
5. The native web bundle includes this release, but Android/iOS shell preparation and RevenueCat
   public keys remain separate store-release gates; no signed store candidate is claimed here.
