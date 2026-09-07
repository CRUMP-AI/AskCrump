# Guide current-capture recovery

Date: 2026-09-07
State: local candidate only; no push, merge, deployment, Search Console action, social mutation, or spend

Three 1280×720 frames were recaptured from the existing fictional Savannah Reading Series workflow
in the authenticated production Ask Crump app. The workflow contains no customer identity, customer
file, testimonial, generated person, staged device, reconstructed interface, or fabricated outcome.
The prompt and Project views show the current six-destination navigation: Ask, Projects, Create,
Video, Library, and You. The response view is a natural scroll continuation of the same genuine
conversation. Chats were hidden before the prompt and response recapture so no unrelated founder
conversation title or excerpt appears.

| Asset | SHA-256 |
|---|---|
| `public/assets/guides/rough-idea-prompt.png` | `927E28F77990866218970EFA9E1BA5C4E4B90BDEDD004220FBF402400C870DF5` |
| `public/assets/guides/rough-idea-response.png` | `9D3C78858C63640AA3ACE169F4A93E8F04652519AACA48301D418FB259508224` |
| `public/assets/guides/savannah-project.png` | `557FA9B8A30664EA8C9CB4C038C62814D460C3B26BA703FEC08B92B431EB31D4` |

The two affected guides retain their original August 30 publication date and exact canonical,
destination, CTA, and attribution contracts. Their modified date, visible update date, screenshot
dimensions, and evidence wording now truthfully identify the September 7 recapture.

Product acceptance against September 7 `main` corrected two candidate defects before approval:
the Open Graph metadata now reports the new hero images' actual 1280×720 dimensions instead of the
retired 727×678 values, and the response image's alternative text describes the budget items and
weekly milestones actually visible in that frame. Tests now bind image-header dimensions to both
the rendered image attributes and Open Graph metadata so this cannot silently drift again.

## Verification

- Product review branch: `review/guide-current-product-acceptance-20260907`, based on current
  `origin/main` `c7897899e2e3619a1f3813e913048d5a2584cb2f`; the held marketing source commit is
  `eff15d0bdb35b5a3f07378a0e554d84f1314476e`. Neither branch was pushed or merged.
- Focused guide contract: 6/6 passed.
- Full Python collection: 850 tests; 848 passed and two pre-existing environment-gated tests
  skipped. One dependency deprecation warning did not change the result.
- JavaScript contract: 49 files validated; 6/6 rough-to-useful attribution cases passed.
- Ruff, explicit bundled-Python compilation, production build preflight, native web-bundle
  creation, and diff integrity passed. The preflight's optional local Python guard does not discover
  the bundled runtime, so compilation and the full suite were run independently with that runtime.
- Browser rendering: both guides loaded at 1440×1000 and 390×844 with meaningful content, no
  horizontal overflow at 390px, matching 1280×720 Open Graph metadata, no framework error overlay,
  and every guide image complete with nonzero natural width after its native lazy-load boundary.
  The expected local-only 404s for Vercel analytics scripts were outside the deployed-page
  contract.
- Visual inspection: desktop and mobile layouts remain coherent and readable; all three frames are
  current real-product evidence and sit naturally inside the existing editorial design.
- The historical `verify-marketing-landing-release.mjs` script is not a gate for this candidate: it
  is intentionally hard-coded to the 2026-08-30 marketing-landing base and exact legacy file set.
  Its current-main boundary rejection occurs before page checks and does not describe this patch.

Render evidence was copied outside the product branch to the marketing evidence ledger before the
local verification browser and server were closed.
