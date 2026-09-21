# Store screenshot capture plan

Capture the exact signed release build with a dedicated demo account and no personal data. Do not
use generated mockups as proof of functionality. Add restrained headlines only after capture, keep
the first three frames focused on real UI, and never include prices, rankings, testimonials, store
badges, or download calls to action.

Required sequence:

1. Ask — useful structured answer and the direct `Keep in a Project` action.
2. Projects — resume prepared continuing work with its instructions, conversations, and references.
3. Create — the unified chooser showing only file, image, and long-form modes enabled in the signed build.
4. Video — the dedicated studio with a reference-ready setup or safely staged active job.
5. Research in Ask — sourced current research and next-step controls inside Ask.
6. Editable work — Document Studio with real document and presentation download controls.
7. Library — prepared manuscripts and books in the dedicated private bookshelf.
8. You — settings, sessions, privacy, and account controls with all personal data removed.

Use the exact destination labels shown in the signed build. The screenshot sequence must agree with
the in-app tutorial and reviewer path before either store packet is approved.

Capture targets:

- Apple: the current native candidate explicitly supports both iPhone and iPad. The release packet
  therefore requires both `iphone/` and `ipad/` directories, with 1–10 screenshots in each. Use a
  current 6.9-inch iPhone size (`1260×2736`, `1290×2796`, or `1320×2868`) and a current 13-inch iPad
  size (`2064×2752` or `2048×2732`), or the corresponding landscape dimensions. The Ask Crump v3
  release packet accepts only validated 24-bit RGB PNG with no alpha/transparency. Do not remove the iPad set unless the signed app is first
  changed, compiled, and verified as iPhone-only.
- Google Play: use 4–8 phone screenshots for recommendation eligibility. Each must be 9:16 portrait
  at a minimum `1080×1920`, or 16:9 landscape at a minimum `1920×1080`; the longest edge cannot
  exceed 3840 pixels. The Ask Crump v3 release packet accepts only validated 24-bit RGB PNG with no
  alpha/transparency, no larger than 8 MB.
- Keep overlay text below 20% of the image and record accessible alt text beside every final asset.

If a device or store tool exports JPEG, convert it to PNG before assembling the v3 packet, inspect
the converted image, and use the converted file's SHA-256 value in the evidence record.

Final image files belong in platform/locale subfolders after physical-device capture. Reviewer
credentials and raw customer content never belong in this directory.
