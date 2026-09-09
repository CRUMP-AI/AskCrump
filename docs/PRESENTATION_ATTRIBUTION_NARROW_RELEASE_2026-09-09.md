# Presentation attribution narrowing release — 2026-09-09

## Outcome

Ask Crump now accepts exactly four first-touch tuples for the held Presentation proof
campaign:

| Acquisition | Placement | Creative | Intent |
| --- | --- | --- | --- |
| `facebook` | `profile-link` | none | `presentation` |
| `instagram` | `profile-link` | none | `presentation` |
| `facebook` | `organic-social` | `fb-static` | `presentation` |
| `instagram` | `organic-social` | `ig-story` | `presentation` |

The retired `ig-feed` identifier and every missing, cross-channel, or mismatched creative are
discarded. This release makes the measurement destination ready; it does not authorize campaign
publication, paid spend, or a performance claim.

## Corrections made during review

The frozen marketing candidate supplied the correct four-route product requirement, but two SQL
edge cases would have weakened it if released unchanged:

1. an omitted creative was normalized to an empty string while the profile-link routes tested for
   SQL `NULL`, which rejected both valid profile paths; and
2. PostgreSQL three-valued logic allowed a blank organic-social creative to escape the intended
   rejection because `CHECK` constraints accept `UNKNOWN` and `IF NOT (NULL)` does not run.

The released functions normalize blank creatives to `NULL` and require a non-null creative on both
creative-bearing routes. The same exact mapping is locked across landing JavaScript, authentication
JavaScript, Python normalization, SQL constraints/RPC validation, executable browser fixtures, and
parity tests. The review also repaired a pre-existing standalone constraint mismatch so the already
registered `rough-to-useful-v2` campaign and `rough-to-useful-current-feed` creative remain valid.

## Database and privacy boundary

- Migration `20260909200726 narrow_presentation_attribution_touchpoints` installs the narrowed
  registry and standalone allowlists.
- Migration `20260909201749 reject_blank_presentation_creative` closes the SQL null-logic edge case.
- The affected writer remains `SECURITY INVOKER`, volatile, and configured with an empty search
  path.
- Execute remains revoked from PUBLIC, `anon`, and `authenticated`; only `service_role` can call it.
- No referrer URL, prompt, response, filename, email, account label, or arbitrary metadata is added.
- The production table contained zero Presentation-campaign rows, zero retired `ig-feed` rows, and
  zero `rough-to-useful-v2` rows before the migration, so no customer-row repair was needed.

A production transaction proved all four valid tuples and nine invalid variants, then rolled back.
The retained fixture-row count was zero. Live schema inspection confirmed the exact route check,
retired creative removal, blank normalization, explicit non-null guards, and service-role-only ACL.
The post-DDL security advisor reported only the existing informational RLS-with-no-policy notices
for service-role/private tables; it introduced no warning or error.

## Verification and delivery

- Product commits:
  - `04735ce9f2d4d20357625d99b2adb3948bf29406` — exact client/server attribution contract
  - `0af232bac5759c035319ea76e6f69a0039f3ac63` — explicit blank-creative rejection
  - `dad6532821c99760c47d8f92dc7d6c5e673d51c1` — local migration names matched to the remote ledger
- Complete Python suite: 945 collected, 943 passed, two environment-dependent skips.
- JavaScript contract: 49 files and all six rough-to-useful cases passed.
- Browser control matrix: 36/36 verifiers passed, including the expanded Presentation attribution
  browser proof.
- Ruff, Python compilation, production preflight, native web bundle, and diff integrity passed.
- GitHub Actions:
  - CI `34401350155` — success
  - Android Store Bundle Verification `34401350124` — success
  - iOS Store Source Verification `34401350174` — success
- Production deployment `dpl_3FCh424jNVC1LgiwfszmXGqj2Eow` is READY on the Ask Crump aliases.
- Production health returned HTTP 200 on Ask Crump v5.9.76. The served landing and authentication
  assets contain `fb-static` and `ig-story` and omit `ig-feed`. The initial 30-minute runtime-error
  query and one-hour 5xx query were empty.

## Decision boundary

The technical attribution gate for the four approved Presentation touchpoints is complete. Marketing
may treat those labels as server-authoritative only when it uses these exact tuples. The campaign
remains held until the founder gives action-time publication approval and the remaining launch-proof
requirements are satisfied.
