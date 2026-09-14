# Project save offer measurement release — 2026-09-14

## Outcome

Ask Crump can now measure whether an account was shown a usable result-to-Project action before it
measures save intent. This closes the missing denominator between activation and durable Project
continuity without changing the user interface.

## Product boundary

- Conversation results emit `ProjectSaveOfferShown` only after the ownership lookup confirms the
  conversation is not already saved.
- Generated document, presentation, image, and other file results emit the same event from the
  visible artifact action.
- The only accepted sources are `conversation_result` and `artifact_result`.
- The browser sends the fixed key `project-save-offer-shown`; the authenticated server replaces it
  with `project-save-offer-shown:<source>:<server UTC day>`.
- Re-rendering a result cannot create more than one database row per account, source, environment,
  and UTC day.
- Existing “Open Project” actions do not emit a new save offer.

## Privacy and reporting boundary

The event cannot carry a plan, artifact type, acquisition tuple, prompt, response, filename, URL,
Project ID, conversation ID, message ID, or arbitrary metadata. Database constraints enforce the
fixed key shape and sources.

`product_project_continuity_snapshot` remains service-role-only and `security invoker`. It adds:

- `offer_measurement_since`;
- `project_save_offer_shown`;
- `project_save_offer_to_intent`;
- `project_save_offer_without_later_intent`;
- `project_save_intent_without_prior_offer`; and
- `offer_to_intent_rate_pct`.

The comparable exposure funnel begins at `2026-09-14 18:34:14+00`. Earlier result-save intent is
preserved in the existing journey fields but is not retroactively paired with an unobserved offer.

## Verification before production

- focused product analytics, Project continuity, and button-integrity tests: passing;
- JavaScript parse checks for every changed browser file: passing;
- fail-closed browser-control matrix: **48/48**;
- conversation result flow: offer → intent → visible success/recovery states verified;
- generated artifact flow: conversation and artifact offers remain independently classified before
  one bounded save intent.

No production event is backfilled, and no interface or pricing claim is changed by this release.

## Production proof

- feature commit: `2995049782f178131d0b4dadcf05185bba1269d8`;
- Supabase migration ledger: `20260914185224 project_save_offer_measurement`;
- protected function: `security invoker`, `anon_execute=false`,
  `authenticated_execute=false`, `service_role_execute=true`;
- GitHub CI: `34883781606` passed;
- Android source/bundle verification: `34883781472` passed;
- iOS source verification: `34883781547` passed;
- Vercel deployment: `dpl_FQAkyt9k9VgQ3nWzKA8kdByRuzMx`, Ready on all six production aliases;
- production analytics route: the new event passes schema/contract validation and reaches the
  expected unauthenticated `401 AUTH_REQUIRED` boundary;
- Vercel one-hour runtime error scan: no grouped errors;
- pre-browser-release production interval (`18:34:14` through `18:56:30.659` UTC): zero offer rows
  and zero save-intent rows, proving the comparable boundary was not contaminated before the new
  client became live.

Exact production asset hashes:

| Asset | SHA-256 | Bytes |
| --- | --- | ---: |
| `runtime-body-v1.js` | `6331c32ce239fadcc1633bc4e0a51d10898f04e161823ac0c40a991da4246a6c` | 8,926 |
| `product-analytics.js` | `936d0c54be92bea512b25b04f4d4540624726f673d20275e227c88240f7c2840` | 1,448 |
| `ui-functions.js` | `6ea8d02dd46ad367cc3be086845082fca3c60426a96d8a10ef7b64a89ef89837` | 48,360 |
| `crump-5.0.js` | `56492505f37e6c0ca6ec6b1a2f82cbd6e6ac6003a6cf482549c8c2ffdf67036e` | 84,633 |
