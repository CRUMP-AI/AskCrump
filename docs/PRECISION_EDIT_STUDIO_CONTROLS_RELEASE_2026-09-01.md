# Precision Edit Studio controls release — 2026-09-01

## Outcome

Ask Crump's generated-image action now says **Edit area** and opens the existing pixel-protected
Precision Edit Studio. The studio can enlarge the working image from fit view through 400 percent,
switch between Brush, Erase, and Move, and preserve the user's normalized mask coordinates while
zoomed. This makes small details practical on both desktop and phone instead of forcing a user to
paint against the fit-to-screen image.

The editor also offers optional, editable guidance for natural retouching, warmer or cooler visible
tone, and slightly deeper or lighter visible tone. A selected suggestion becomes ordinary reviewable
composer text before Send. It is not a hidden instruction and does not generate immediately. The
updated workspace guide teaches **Edit area → zoom → brush → review → send**.

## Product and safety boundaries

- The user still selects pixels manually. This release adds no face, person, race, ethnicity, age,
  or identity classifier.
- The product does not present race as a visual slider. It explicitly distinguishes a visible tone
  adjustment from race or ethnicity.
- Guided text requires the selected region to preserve natural texture, facial features, lighting,
  age, and identity. The existing server contract continues to restore every unselected source pixel
  after the provider edit.
- A guided suggestion is reviewable text, not a claimed live preview. Deterministic local preview
  controls remain future work.
- The transient mask remains excluded from browser storage, conversation synchronization, traces,
  analytics, and saved file metadata.
- No image was generated during verification, so no provider request, saved result, credit charge,
  Project write, or customer-content access occurred.

## Verification

- All **753 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Changed-file Ruff checks, production preflight, native web-bundle creation, store metadata checks,
  mobile signing-source controls, and diff integrity passed. A broad repository Ruff run separately
  reported one pre-existing unused test variable in `tests/test_destination_tool_hierarchy.py`; that
  unrelated line was not changed by this release.
- Desktop browser proof verified 100-to-150-percent enlargement, Move-mode activation, guided-text
  handoff, mask dimensions, focus return, and no horizontal overflow.
- A 390-by-844 browser proof verified the stacked studio layout, accessible Close action, Escape,
  and no horizontal overflow.
- The surrounding Image Studio browser proof preserved reference entry, invalid-replacement
  recovery, preview stability, focus containment, and focus return.
- Signed-in production loaded the new workspace, editor, stylesheet, and tutorial cache keys; opened
  Image Studio; displayed **Edit one exact area** and **Zoom in and brush over only the pixels Crump
  may change**; and closed without an error overlay. No file was selected and no generation ran.
- Both canonical health endpoints returned HTTP 200 and version 5.9.76.
- The final deployment's inspected window contained 21 HTTP 200 requests, no 4xx or 5xx request,
  and no warning, error, or fatal log.

## Release identity

- Feature commit: `ec0b60751c80ac17341a6b245f69c7d4d4a796f8`
- Atomic cache correction: `ad566541b4510ec9f4e570c8ced1ae99fe5d922e`
- Final production deployment: `dpl_GtRSoVQxF7u4NJwXkKpf3rt5K2zW`
- Status: `READY`
- Build duration: about 37 seconds
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`, `www.clevercrump.com`, and the two
  Vercel project/main aliases
- Workspace asset: `5.9.76-precision-edit-handoff-2`; SHA-256
  `3A8A0F263EBA0283D46B75587AE621A0C14FE01C35D424B1425D4B353051C74D`
- Precision Edit script: `5.9.76-precision-edit-studio-2`; SHA-256
  `964680048B8689D9BAD473FC0DBEA5FF836875BDC92372E56E7F3F0CB4384B50`
- Precision Edit stylesheet: `5.9.76-precision-edit-studio-2`; SHA-256
  `C5FD5221D5DD68ABF1CE1CBEFEDD10022A68DE02F4CB97E652D35654D81D708D`
- Workspace guide: `5.9.76-precision-edit-guide-2`; SHA-256
  `26B0CD1CC83E1E62A8C860B91457208F60554202E1E3724C66787F4226B1A59B`
- Runtime loader content: SHA-256
  `3A6506C2039EC52EECA73F196A7ECF7EF96A76BCA4A978C994D0EB6CD01B7CF4`

## Remaining acceptance work

1. Repeat zoom, Move, very small brush strokes, software-keyboard behavior, and touch panning on exact
   signed iPhone and Android candidates.
2. Run one controlled, rights-cleared legitimate edit and inspect identity stability, edge quality,
   saved-version behavior, charge/refund semantics, and Project continuity before making a public
   precision or identity-preservation claim.
3. Add optional on-device subject/region segmentation only after privacy, bundle-size, battery,
   accessibility, and false-selection tests pass. It must select pixels without identifying a person
   or inferring sensitive traits.
4. Add deterministic local warmth, exposure, and saturation previews inside the user's manual mask,
   with an explicit reset and before/after view. Do not imply that a local preview guarantees the
   provider-generated result.
5. Keep exact logos and readable text on the separate deterministic overlay path rather than asking a
   generative model to redraw them.

