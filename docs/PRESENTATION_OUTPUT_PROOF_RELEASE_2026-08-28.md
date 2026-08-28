# Ask Crump 5.9.62 presentation-output proof release

Date: 2026-08-28
Production version: 5.9.62
Feature commit: `84eddec0540167f9939d35191b03b8eda700b5d5`
Production deployment: `dpl_J49gDvXouaQXjiWpobM4kSowkby7`

## Outcome

The AI presentation maker page previously described editable PowerPoint quality without letting a
visitor inspect representative output. Production 5.9.62 adds a three-slide gallery rendered from a
synthetic internal quality brief through Ask Crump's current PowerPoint exporter. The gallery shows
the actual dark-and-light visual rhythm, editorial hierarchy, asymmetric story treatment, and native
chart styling before a visitor starts creating.

The page identifies the gallery as representative synthetic output, says that request and source
material affect the result, and explicitly states that no customer content or testimonial is shown.

## Scope and safety

- The exporter, generation prompts, providers, entitlements, credits, pricing, authentication,
  storage, schema, RLS, analytics events, and payment behavior did not change.
- The source brief and all slide content are synthetic. No customer file, prompt, identity, account,
  testimonial, logo, private metric, or production generation was used.
- The three published images are static 1,600-by-900 PNG renders. The page does not claim that every
  request produces the same composition or that generated facts are automatically verified.
- Existing presentation delivery remains an editable `.pptx`; the gallery is visual proof, not a
  replacement for the downloadable artifact.

## Verification

### Local contracts

- All 393 Python tests passed.
- Ruff passed across the backend and tests; backend compilation passed.
- All 44 JavaScript source and integration validations passed.
- Production preflight, native web bundle, store metadata, and signing-source checks passed.
- The expected Windows iOS-project gap and existing RevenueCat/Firebase submission warnings remain
  release-time gates; the hosted Android and iOS source gates passed.
- Each published image passed PNG, RGBA/RGB, and exact 1,600-by-900 dimension checks.

### Browser verification

- At a 1,280-by-720 desktop viewport, the gallery rendered one representative-output region with
  three complete 1,600-by-900 source images, no horizontal overflow, and no browser warning or error.
- At a 390-by-844 mobile viewport, copy and gallery collapsed to one column, all three slides retained
  their 16:9 aspect ratio, the page had no horizontal overflow, and no browser warning or error was
  reported.
- Full-size review confirmed readable slide hierarchy, restrained gold accents, the light editorial
  story composition, and the native chart example without visible clipping.

### Hosted gates

- CI: [run 33202997095](https://github.com/CRUMP-AI/AskCrump/actions/runs/33202997095) — passed.
- Android store bundle: [run 33202997026](https://github.com/CRUMP-AI/AskCrump/actions/runs/33202997026) — passed.
- iOS store source: [run 33202997094](https://github.com/CRUMP-AI/AskCrump/actions/runs/33202997094) — passed.

### Production

- Git deployment `dpl_J49gDvXouaQXjiWpobM4kSowkby7` reached READY on production and serves commit
  `84eddec`.
- `https://www.askcrump.com/api/health` returned HTTP 200 and version 5.9.62.
- The live presentation page returned HTTP 200 with one named proof region, three images, and the
  5.9.62 stylesheet marker.
- All three live example images returned HTTP 200 as `image/png` with byte sizes matching the
  committed assets.
- The live service worker returned HTTP 200 with cache `ask-crump-new-body-v1-r96` and 5.9.62 assets.
- No Vercel runtime error cluster was reported in the inspected 30-minute release window.

## Outcome still to prove

The release verifies truthful visual proof and delivery. It does not yet prove that the gallery
improves presentation-intent continuation, successful artifact delivery, first download, paid
conversion, or return use. Those outcomes require legitimate external behavior in the content-free
funnel and artifact-journey aggregates.
