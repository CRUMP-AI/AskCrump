# Ask Crump 5.9.57 résumé-purpose delivery release

Date: 2026-08-28

Production version: 5.9.57

Code commit: `de0440fea922e2c373b059d197bf60991b4821d5`

Production deployment: `dpl_6FnNfyGKHFKW4osPxEvLVwDajDDs`

## Outcome

Selecting the public résumé journey or the in-app `RÉSUMÉ · CV` outcome now preserves that exact
purpose through the first message, local synchronization, a queued retry, server-side model
guidance, and final DOCX/PDF packaging. A user can supply only real experience, skills, education,
and a target role without repeating the word “résumé” and still receive the promised ATS-friendly,
fact-grounded résumé structure.

The purpose field accepts only `resume`. It does not contain a prompt, employer, role, skill,
education record, filename, response, account identifier, or token. Invalid or unrelated values
are discarded. Existing authentication, entitlements, usage, credit consumption, pricing,
payments, provider routing, conversation storage, and artifact events remain unchanged.

## Evidence that selected the work

The refreshed 24-hour production Web Analytics view showed 19 visitors, 109 page views, and 42%
bounce. The four capability pages had three to four visitors each, while the visible event table
still contained three `MarketingCTA` visitors/eight events, two `SignupIntent` visitors/14 events,
two `SignupStarted` visitors, and no `CreationIntentContinued`. The protected comparable external
funnel remained zero at every stage, and the artifact report returned no rows. This sample is too
small and may include internal or automated traffic, so it was not treated as a conversion rate.

The deterministic creation audit found a stronger defect. Both the public résumé handoff and the
in-app résumé choice selected only `docx`; their label and placeholder were not part of the sent
request. A fact-only brief such as experience, target role, and skills therefore resolved to the
generic `business` document profile unless the user happened to repeat “résumé” in the message.

## Correction

- The résumé handoff now selects DOCX plus an allowlisted `resume` purpose.
- The in-app `RÉSUMÉ · CV` outcome uses the same purpose, while ordinary Word/PDF choices clear it.
- The composer chip says `Create résumé · DOCX`, keeping the selected outcome visible before send.
- The purpose is copied into the existing request metadata so a failed sync or reply retry retains
  the promised deliverable.
- Cross-device message sanitization keeps only the exact `resume` value and discards arbitrary
  purpose strings.
- The server independently normalizes the value and accepts it only for DOCX/PDF delivery.
- Model-facing creation guidance and deterministic file packaging both receive the normalized
  purpose, preserving the ATS/fact-grounded contract and the résumé layout.
- The application advanced to 5.9.57, native build 50957, and PWA cache revision 91.

## Verification

- The pre-correction reproduction resolved a selected résumé with a fact-only brief to `business`.
- The corrected artifact service resolves the same brief to `resume` only with the allowlisted
  purpose and rejects an arbitrary client value.
- A real DOCX packaging test verified `profile=resume`, résumé metadata, Aptos body typography, and
  compact résumé margins.
- A synchronization test preserved `RESUME` as normalized `resume` and discarded a free-form
  purpose.
- The real navigation/controller fixture selected `{format: docx, purpose: resume}`, emitted one
  `CreationIntentContinued` event, cleared the pending handoff, and recorded zero browser errors.
- 382 Python tests passed.
- Ruff passed for `backend` and `tests`; Python compilation passed for `backend`.
- All 44 JavaScript files passed syntax and integration validation.
- Production preflight, native web-bundle generation, and store metadata checks passed.
- Local Android source configured as 5.9.57/build 50957/API 36. The expected Windows-native gates
  remain the missing local iOS project, RevenueCat public keys, and `google-services.json`.
- GitHub CI run `33189736839` passed.
- Hosted unsigned Android App Bundle run `33189736730` passed.
- Hosted unsigned iOS Release compile run `33189736888` passed.

## Production evidence

- Deployment `dpl_6FnNfyGKHFKW4osPxEvLVwDajDDs` reached `READY` from the exact feature commit.
- Production health returned HTTP 200 and version 5.9.57.
- The live service worker returned `ask-crump-new-body-v1-r91`.
- The live runtime loaded `crump-5.0.js?v=5.9.57`.
- The live studio contained the résumé-purpose state and request contract, and the live navigation
  contained the explicit résumé handoff.
- The exact deployment's observed runtime requests returned 200, and the release-window runtime
  error scan returned no group.
- Supabase remained `ACTIVE_HEALTHY` during the evidence refresh.

No production account, résumé, message, artifact, payment, subscription, credit charge, or
synthetic analytics event was created for verification.

## Rollback

The prior production deployment `dpl_3hTYpXa4Jb4yrjnFyah8LPvtfGii` remains available. This release
requires no database, schema, RLS, environment, authentication, payment, pricing, or provider
migration.

## Remaining evidence

Observe a legitimate résumé page or Create selection through authentication, first send,
`ArtifactRequested`, `ArtifactPackaged`, and first download. Do not infer conversion or quality
lift from the current anonymous sample. A real-user content review is still required before using
generated résumés as advertising proof.
