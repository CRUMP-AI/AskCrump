# Facebook Reel attribution live-parity release — 2026-09-17

## Outcome

Production now recognizes exactly this future Facebook Public Reel first-touch tuple:

`facebook / organic-social / rough-to-useful-v2 / rough-to-useful-current-reel / projects`

This release establishes product-side measurement readiness only. It does not authorize or perform a tagged visit, customer event, social publication, advertisement, billing action, purchase, or spend. Marketing action-time authority remains false.

## Released source

- Production source commit: `231e5c8cde4800a3b66b456da299b5fb5af6b0e7`
- Feature implementation commit: `14e5f869e6af07bd8ceac820b866c5410fa9a7d8`
- Production deployment: `dpl_36abLQyMKtnkh4hFy1rTRXYsQJYB`
- Final preview deployment: `dpl_8snsDsG4GJnQNiXv3TJT1G96N72r`
- Applied Supabase migration: `20260917225143 release_rough_to_useful_facebook_reel_attribution`

## Exact parity and rejection behavior

The exact campaign registry mapping is present in:

- `public/landing.js`
- `public/auth-controller.js`
- `backend/product_analytics.py`
- `migrations/20260917225143_release_rough_to_useful_facebook_reel_attribution.sql`
- the service-role-only `public.record_account_created_event` database function

The release accepts the Facebook organic Reel tuple while retaining the existing Facebook organic Feed tuple as a separate creative. Instagram Reel, paid Reel, profile-link Reel, mismatched intent, and other invalid cross-products remain rejected. Stored, unexpired first-touch attribution remains immutable when a second campaign is opened in the same tab.

## Verification

- Full Python test suite: passed.
- Focused attribution suite: 33 passed after final migration-ledger alignment.
- JavaScript validation: passed across 54 files.
- Rough-to-useful runtime matrix: 24/24 passed.
- Browser attribution fixture: 6 valid cases and 21 rejection cases passed; no credentials were entered, no AccountCreated request was sent, and no analytics event was sent.
- Production build preflight and native web bundle credential-boundary check: passed.
- Database constraints: present, validated, and contain the Reel creative.
- AccountCreated writer: contains the Reel mapping; `SECURITY INVOKER`; empty `search_path`; executable by `service_role`; not executable by `anon` or `authenticated`.
- Production health: HTTP 200, Ask Crump `5.9.76`.
- Vercel runtime errors after deployment: none in the checked 30-minute window.
- Production aggregate export for `rough-to-useful-v2`: no rows, as expected before any authorized tagged traffic. No fixture/customer event was created to manufacture proof.

## Live asset identity

The fetched production assets byte-match the committed release files:

- `public/landing.js`: `5a30cf03655d648741b1fe49125bd4bfa8544334ffc527283df4900545506e75`
- `public/auth-controller.js`: `c300c48c354d49e280dca212c28e78d8c94c4c3048e92723b641db206217a172`
- `public/sw.js`: `e04b1bb99469aa8f547fe1b1b73e22413ecceeba1ef5233400b2fd08b17d8452`

Database verification fingerprints:

- `product_events_campaign_registry_check`: `1bb533b0c69c7593bf56deef707cf4e6`
- `product_events_creative_check`: `e77ba3d1ceb6e57125826134b3ab4589`
- `record_account_created_event`: `f4d0dea85d06f35edf3ea86799a8453c`

## Preserved boundaries

- The tagged campaign URL was not opened.
- The previously reviewed untagged-guide browser context was not reused for tagged proof.
- No live guide or Marketing repository file was changed.
- No social account was edited and nothing was published.
- No ad, checkout, billing, purchase, or spend action occurred.
- Future live proof requires a newly isolated clean browser context and must remain excluded from customer outcome counts.
