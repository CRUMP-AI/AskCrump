# Pixel-protected Precision Edit release — 2026-09-01

## Outcome

Ask Crump's generated-image **Edit** action now opens a focused Precision Edit Studio. A user
manually paints the smallest area that may change, can switch between Brush and Erase, adjust the
brush size, undo, clear, cancel, or hand the selection back to the composer. The editor explains
that Ask Crump does not identify or label race or ethnicity and that skin tone is not a race label.

When a masked edit is submitted, the server validates and normalizes the source and mask, sends the
mask to the image-edit provider, and then restores the original source pixels everywhere outside the
selected region. This deterministic final compositing step is the protection boundary; provider
mask adherence alone is not treated as sufficient.

## Safety and privacy boundaries

- Selection is manual. The release adds no face, person, race, or ethnicity detection.
- A user may describe an explicit visible appearance change inside the selected region, while the
  server prompt requires identity, age, facial structure, and all unselected details to remain stable.
- Rights-cleared images of minors remain limited to benign transformations.
- The transient mask is removed before intelligence preparation, conversation synchronization,
  traces, and analytics. It is not stored in browser local or session storage.
- The decoded mask is capped at 2 MB. Empty selections, masks covering more than 90 percent of the
  canvas, dimension mismatches, and invalid inputs fail closed before provider work.
- Exact logos and readable text remain a future deterministic overlay workflow; the product does not
  claim that a generative redraw is exact.

## Verification

- All 749 Python tests passed.
- All 48 JavaScript files passed the repository contract gate.
- Python compilation, production preflight, native web-bundle creation, store metadata checks,
  mobile signing-source controls, and diff integrity passed.
- Focused server coverage proves mask normalization/inversion, empty/broad/mismatched rejection,
  transient-data exclusion, the provider multipart request, and exact restoration of protected
  pixels after a mocked provider result.
- Desktop and 390-by-844 browser proofs covered Brush, Erase, brush size, Undo, Clear, focus
  containment, Escape, focus return, selection handoff, and zero horizontal overflow.
- Signed-in production opened an existing generated image, displayed **Choose exactly what may
  change**, verified the outside-selection explanation, and closed cleanly with zero browser errors.
- The production asset check returned HTTP 200 and byte-for-byte matches for the runtime loader,
  main workspace script, Precision Edit script, and Precision Edit stylesheet.
- Vercel reported no runtime-error cluster in the inspected 30-minute production window.
- No live image request was submitted during release verification, so no provider credit was spent.

## Release identity

- Feature commit: `d1772c447c1acf93a1bf6a8e1484f97dc019b770`
- Production deployment: `dpl_56GihGcjQ4WVQp22xPooRxKbLFgA`
- Status: `READY`
- Build duration: about 40 seconds
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`, `www.clevercrump.com`, and the two
  Vercel project/main aliases
- Main asset: `5.9.76-precision-edit-handoff-1`
- Precision Edit assets: `5.9.76-precision-edit-studio-1`
- Runtime loader: `5.9.76-precision-edit-loader-1`

## Remaining acceptance work

1. Repeat the workflow with touch, zoom, software keyboard, VoiceOver, and TalkBack on exact signed
   iPhone and Android candidates.
2. Run a controlled, rights-cleared legitimate edit and inspect identity stability, the protected
   boundary, result usability, charging, retry, and saved-version behavior before making a public
   precision or identity-preservation claim.
3. Add local, non-generative warmth/exposure/saturation controls for an actual live preview inside the
   user's manual selection. Do not add a race control or sensitive-attribute classifier.
4. Add a deterministic asset/text overlay layer for rights-cleared logos and readable typography.

