# Reference and artifact fidelity candidate — 2026-09-24

Status: **draft PR #37, unmerged, undeployed, and migration-free.** The reviewed product commits are
`081a1d3dc596789f458b29476b185cdb797c84a5`,
`c9af9bcca6cf32d175593f8478677becb2798b97`,
`4fb627a3cbea2f57fe49b2c2d98779da3696f194`, and
`653d576076095c3bceab8131b0d88b94f5ec0bfa`. This record is review evidence, not permission to
merge, deploy production, run a migration, spend provider credits, or submit a store build.

## User outcomes

### Reference-led image and video work

- Image Studio accepts a bounded, ordered set of references and asks the user to confirm the role
  of each reference before provider spend. Confirmed image references cannot silently fall back to
  a text-only generation request.
- Every confirmed image reference reaches the edit request in its declared order. Crump restates
  which numbered reference supplies the base/composition, subject/product, logo/wordmark,
  mascot/character, typography/layout, or palette/style direction.
- Video references carry explicit roles and disclose the active provider's real reference limits.
  Unsupported combinations are not presented as exact.
- The response and persisted assistant message retain a bounded, content-free review receipt so a
  later session can see which references were used and which elements still require human review.
- Exact logos and wordmarks have a deterministic **Exact logo / wordmark** path. It composites the
  uploaded pixels locally onto the chosen canvas without asking a generative model to redraw the
  asset, without an AI call, and without a credit charge.
- Generative likeness remains honestly best-effort. Exact brand pixels belong in the deterministic
  overlay path; a newly posed mascot, changed perspective, or generated typography is not claimed
  to be pixel-identical to a reference.

No automated post-generation vision comparison is enabled. Such a check would send the generated
output and the same private references to an AI provider a second time; it remains off until the
founder explicitly approves that additional data-sharing step. Current review receipts are manual
and do not claim automated visual verification.

### Conversational documents and presentations

- A file format typed in natural language is now authoritative when semantic routing notices a
  conflicting topic. For example, **“Create a PowerPoint presentation about our video campaign”**
  produces the requested presentation instead of being diverted into Video Studio.
- The existing intentional-manuscript guard remains intact: asking Crump to write a full novel as
  a Word manuscript continues through the manuscript workflow rather than being flattened into a
  short generic document.
- Generated DOCX, PDF, PPTX, and other supported artifact cards now offer **Open** as well as
  **Download** and **Add to Project**. Open reuses Ask Crump's existing owner-scoped in-app viewer;
  it does not expose a Supabase storage tab or create a popup window.
- Returning PWA clients move from cache `r257` to `r258`. Only the changed runtime plan and composer
  receive the `5.9.76-artifact-card-open-1` token; precision-editor assets retain their prior token
  and lazy-loading boundary.

## Verification

- Complete Python suite with the exact pinned Argon2 dependencies: **1,363/1,363 passed**.
- Focused conversation, artifact, and routing regressions: **70/70 passed**.
- JavaScript integration: **55 files**, plus attribution fixtures **24/24**, **10/10**, and
  **10/10**; store-packet self-test **51/51**.
- Browser-control matrix: **52/52**. It includes mobile and desktop artifact-card Open/Download,
  Files-layer ordering, zero popup windows, owner-scoped download targets, the `r257 → r258`
  returning-client transition, image stability and precision editing, video references, Projects,
  navigation, billing-review controls, and lifecycle recovery.
- Production preflight, native web-bundle generation, client credential scan, store metadata, and
  native privacy source verification passed.
- `git diff --check` and JavaScript syntax checks passed.

## Hosted verification

- [GitHub CI `35964017283`](https://github.com/CRUMP-AI/AskCrump/actions/runs/35964017283)
  passed on behavior commit `653d5760`, including Python 3.12, JavaScript, browser controls,
  accessibility, production bundle, client-secret, and store-evidence checks.
- [PostgreSQL fence verification `35964017124`](https://github.com/CRUMP-AI/AskCrump/actions/runs/35964017124),
  [Android structural verification `35964017134`](https://github.com/CRUMP-AI/AskCrump/actions/runs/35964017134),
  and [iOS structural verification `35964017328`](https://github.com/CRUMP-AI/AskCrump/actions/runs/35964017328)
  all passed. The native runs are unsigned structural proof, not release binaries.
- Vercel preview `dpl_6dSmABiXUUvQWr3iRuFXeJNAJG5g` is **READY**, target `null` (preview),
  for exact commit `653d5760`. An authenticated protected-preview read returned HTTP 200 for
  health, `/app`, the versioned runtime, the versioned composer, and the worker; the served bytes
  contained the artifact-card Open control, reference-plan control, runtime/composer token, and
  `r258` cache marker.

These checks do not change production. The canonical production deployment remains on `main`.

## Remaining boundaries

1. A real authenticated, owned signed-storage check is still required for small and large PDF Open
   and Download under production-equivalent redirect and CSP behavior. The committed browser proof
   uses content-free local owner-route fixtures and does not claim that external journey.
2. Automated visual comparison remains consent-gated as described above. Manual review and the
   deterministic exact-overlay path are the current safe boundary.
3. PR #37 remains subject to its staged SQL, native billing, signing, publisher-account,
   physical-device, reviewer-access, screenshot, and store-console gates. None is bypassed here.
4. No production database, customer content, provider credential, price, checkout, deployment,
   developer account, or public campaign changed while producing this candidate.
