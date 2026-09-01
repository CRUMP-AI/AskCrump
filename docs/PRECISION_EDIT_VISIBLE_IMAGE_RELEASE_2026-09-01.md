# Visible Precision Edit image release — 2026-09-01

## Outcome

Precision Edit now keeps the source image visible on desktop and mobile while the manual mask and
editing controls load. The production failure was reproduced before implementation: a valid
1,024-by-1,024 source decoded successfully, but the shrink-to-fit frame, image, and mask rendered at
zero by zero pixels. The editor therefore looked like a black, empty stage even though the image was
available and the controls remained enabled.

The editor now gives the source image its real intrinsic dimensions, waits for the newly mounted
frame to participate in layout, and derives a bounded fit size from the usable stage dimensions.
That deterministic size is applied before the edit canvas is wired. The image and mask therefore
share a nonzero, aligned display size without relying on a circular `fit-content` measurement.

## Product, privacy, and safety boundaries

- The change affects only browser layout and cache delivery for the existing Precision Edit studio.
- Upload, signed-file access, provider generation, local adjustment, overlay, save, ownership,
  storage, Project, billing, credit, and analytics contracts did not change.
- The editor still requires the user to choose the allowed pixels manually. No face, person, race,
  or ethnicity classifier was added, and no change-race control exists.
- Production proof used only the first existing fictional cat-astronaut result. A later private image
  in the conversation was not opened, inspected, edited, uploaded, saved, or sent to a provider.
- The production editor was closed without drawing, saving, generating, writing customer data, or
  consuming Crump Credits.

## Verification

- All **784 Python tests** passed, including all **40 focused visual-media reliability tests**.
- All **48 JavaScript files** passed the repository contract gate.
- Ruff, Python compilation, JavaScript syntax, diff integrity, production preflight, native web
  bundle creation, store metadata, and mobile signing-source controls passed.
- A real-browser desktop/phone fixture proved a visible nonzero source image and mask, at most two
  pixels of subpixel alignment variance, zoom, Move, Brush, Lasso, Invert, Undo/Redo, broad-invert
  rejection, local preview/save shape, exact overlay, focus return, mobile containment, and zero
  browser errors.
- Signed-in production loaded `5.9.76-precision-visible-1` and rendered the fictional 1,024-by-1,024
  cat source at about 279-by-279 pixels. The mask rendered at the same size, the frame was 280-by-280,
  and the stage was no longer loading.
- Six live assets matched the committed files byte-for-byte. `/api/health` returned HTTP 200 with
  version `5.9.76`.
- The exact deployment was `READY` on all six aliases. Its inspected window contained 30 HTTP 200s,
  three ordinary signed-file redirects, no warning/error/fatal log, and no runtime-error cluster.

## Release identity

- Feature commit: `7f8493acb83fa18f183f895727380ea44aece43c`
- Production deployment: `dpl_AAbE5fnY5Gn39EF48zpyE8UvvNBm`
- Status: `READY`
- Build duration: about 36 seconds
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project/main aliases
- Precision Edit script: `5.9.76-precision-visible-1`; SHA-256
  `7E63CE65502F8DD0871BC1C5F6C0FD3A1BE0D2B8CCF3AA09968D3DF3085E9ABD`
- Precision Edit stylesheet: `5.9.76-precision-visible-1`; SHA-256
  `94812C3EE9AD9C9609D275329EB71812529A73FAA7E3CBDBAFBB00F086CE0114`
- Runtime body: SHA-256
  `EF851326FC81147B06EEDF902C332DEC9C243E41BE0BCA659DF4A3DBE49D1B52`
- Runtime configuration: SHA-256
  `30B97D4C399A399506D7FBA52F83C0453A668DF8AAD790463E5280CE991861A2`
- V1 runtime configuration: SHA-256
  `F2DCFFE3C6363917221AB0D9808858FDCC6294A9428EFC0518C5F78B8D745B64`
- Service-worker cache: `ask-crump-new-body-v1-r212`; SHA-256
  `3D5435E0F0C03CAF794713B9335599849E590F7C3CBD8EF339AC6A14832B2FF7`

## Remaining acceptance work

1. Repeat open, brush/lasso, local save, reopen, and download on exact signed iPhone and Android
   candidates using only rights-cleared fixtures.
2. Perform one founder-approved legitimate provider edit and confirm outside-selection restoration,
   stable credit disclosure, recovery, and stored-result continuity.
3. Keep private child/customer images outside engineering proof unless a separately consented,
   rights-cleared fixture and benign test are explicitly authorized.

