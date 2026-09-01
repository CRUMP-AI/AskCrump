# Local Precision Photo Studio release — 2026-09-01

## Outcome

Ask Crump's Precision Edit Studio now turns a manual pixel selection into a real, private image
version without sending the image to an AI provider. After brushing the exact area allowed to
change, a user can preview bounded warmth, exposure, and saturation adjustments, compare the edit
with the untouched original, reset it, and save the result to Files. The saved PNG is a normal
owner-scoped generated image that can be reopened, downloaded, or kept with the user's work.

The generative workflow remains a separate, explicit **Continue with AI edit** action. Local edits
use no provider and no Crump Credits.

## Product, privacy, and safety boundaries

- Selection remains manual. This release adds no face, person, race, ethnicity, age, or identity
  classifier and does not present race as a live-edit control.
- The appearance controls alter visible pixels only. They are labeled as visible-tone adjustments,
  not as claims about a person's race or ethnicity.
- Local changes are composited only inside the manual selection. Every pixel outside the selection
  remains byte-for-byte identical to the decoded source image.
- The source file is owner-checked before download and save. The mask must exactly match the source
  dimensions, adjustment values are finite and bounded to plus or minus 30, source images are
  bounded to 16,777,216 pixels, and the existing private-file download limit remains in force.
- The selection mask and preview are transient. They do not enter browser storage, conversation
  synchronization, analytics, traces, or saved-file metadata.
- The saved metadata contains only the source file ID, image dimensions, bounded adjustment values,
  and fixed edit-category flags. It contains no prompt, face/identity label, inferred trait, mask,
  or provider response.
- Retrying the same owner/source/mask/value tuple resolves to the same deterministic file identity,
  preventing accidental duplicate versions.
- This release required no Supabase schema, policy, function, or migration change. A read-only
  production schema inspection confirmed the existing `user_files` record supports the bounded
  owner-scoped file and metadata contract.

## Verification

- All **762 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Changed-file Ruff, Python compilation, production preflight, native web-bundle creation, store
  metadata, mobile signing-source controls, and diff integrity passed.
- Service tests proved exact outside-selection preservation, bounded channel changes inside the
  selection, invalid/mismatched masks, non-image rejection, empty/out-of-range adjustment rejection,
  owner-scoped storage, safe metadata, and retry-stable file identity.
- Route tests proved authentication, normalized file and optional conversation IDs, no-provider and
  zero-credit receipts, and the existing safe error boundary.
- Desktop and 390-by-844 browser proofs verified Brush/Erase/Move, 100-to-150-percent zoom, Undo and
  Redo, local warmth preview, original/edit comparison, exact mask alpha, the save request contract,
  the provider-free confirmation, focus return, scrollable mobile controls, and no horizontal
  overflow. Both runs reported zero page or console errors.
- Signed-in production opened an existing synthetic generated image and the real **Edit area**
  studio. It displayed **LOCAL ADJUSTMENTS · NO AI OR CREDITS**, warmth/exposure/saturation,
  **Show original**, **Reset**, **Save local edit**, and **Continue with AI edit**. With no selection,
  **Save local edit** correctly remained disabled. The studio was closed without painting, saving,
  generating, or spending credits.
- The production script, stylesheet, workspace guide, loader, and service worker matched the shipped
  commit byte-for-byte. Both canonical health endpoints returned HTTP 200 and version 5.9.76.
- The exact deployment was `READY` on all six aliases. Its inspected 30-minute window contained no
  warning, error, or fatal log and no runtime-error cluster.

## Release identity

- Feature commit: `d32eba0a5acb85bd5889d8c1c2ec8111f9df79cd`
- Production deployment: `dpl_8mu3DF3w7hF5NVXet18oA1k7prD8`
- Status: `READY`
- Build duration: about 41 seconds
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`, `www.clevercrump.com`, and the two
  Vercel project/main aliases
- Precision Edit script: `5.9.76-local-photo-studio-1`; SHA-256
  `80856D7338C229459050C73DF6609D794F5F78727449C552BE890B0C3D64621F`
- Precision Edit stylesheet: `5.9.76-local-photo-studio-1`; SHA-256
  `ED8F780A24F3C77F98789D6A69783DF9A8F4AB63C9C0D9788D7C23CF18BB9D63`
- Workspace guide: `5.9.76-local-photo-studio-guide-1`; SHA-256
  `64726439D424FEA832A217BCBC230735D78F495FCF41AEE25530656733AA59C5`
- Runtime loader: `5.9.76-local-photo-studio-loader-1`; SHA-256
  `0136B24EEC84F167E59D9E14B6E772EF4C774D7143CD01402DF46E62BD5E5F6F`
- Service worker cache: `ask-crump-new-body-v1-r203`; SHA-256
  `A2691EC2E89F685ECB135823DE747793B2C4F8121D22E43A57150D71B4FF83A6`

## Remaining acceptance work

1. Run one founder-approved, rights-cleared production save and verify the saved version can be
   reopened, downloaded, added to a Project, and compared with the original.
2. Repeat small-brush, touch-pan, software-keyboard, save, reopen, and download behavior on the exact
   signed iPhone and Android release candidates before making a public precision claim.
3. Observe legitimate, consented edits across varied skin tones and lighting before tuning defaults;
   do not infer or store sensitive traits as part of that evaluation.
4. Consider lasso, invert-selection, feathering, crop/rotate, and non-destructive version history only
   after the shipped path has clear user demand and performance evidence.
5. Keep exact logos and readable text on a separate deterministic overlay path rather than asking a
   generative model to redraw them.
