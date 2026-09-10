# Rough-to-useful organic-feed attribution release

Date: 2026-09-10

## Outcome

Ask Crump now recognizes the current rough-to-useful feed creative from Facebook and
Instagram without widening the already approved paid Facebook path. The accepted set is
exactly:

1. `facebook / organic-social / rough-to-useful-v2 / rough-to-useful-current-feed / projects`
2. `instagram / organic-social / rough-to-useful-v2 / rough-to-useful-current-feed / projects`
3. `paid-social / facebook-paid / rough-to-useful-v2 / rough-to-useful-current-feed / projects`

Facebook and Instagram Story/Reel labels, profile-link variants, paid/organic cross-products,
unknown labels, and blank or null creative labels fail closed. A previously captured unexpired
first-touch tuple remains immutable.

The compact browser registry is:

`'rough-to-useful-v2':{intent:'projects',acquisitions:newSet(['facebook','instagram','paid-social']),placements:newSet(['organic-social','facebook-paid']),creatives:newSet(['rough-to-useful-current-feed']),touchpoints:newSet(['facebook|organic-social|rough-to-useful-current-feed','instagram|organic-social|rough-to-useful-current-feed','paid-social|facebook-paid|rough-to-useful-current-feed',]),},`

## Database boundary

Remote migration `20260910165757 release_rough_to_useful_organic_feed_attribution` is present in
the authoritative Supabase ledger. A rollback-only production transaction proved all three valid
tuples, exact-repeat idempotence, rejection of Story, Reel, profile-link, paid/organic cross-product,
and null-creative inputs, direct constraint enforcement, and zero residue. The account-creation
writer remains security invoker, has an empty search path, and grants execute only to `service_role`;
`public`, `anon`, and `authenticated` remain revoked.

Post-migration Supabase advisors reported no warning or error. The existing informational notices
are 61 RLS-enabled tables without client policies—consistent with service-role-only tables—and 59
unused indexes, which are not evidence that an index should be removed before representative load.
References: [RLS enabled without policy](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)
and [unused index](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index).

## Verification

- Product commit: `c0d4e93aef6e5311ec47a291fcca85a49f51e124`
- Automated suite: 989/989 collected tests passed
- JavaScript contract: 49/49 files; 22/22 rough-to-useful, 10/10 Word/PDF, and 10/10 résumé cases
- Browser-control matrix: 38/38, including image editing/stability, files/viewers, video,
  mobile navigation, Projects, account entry, checkout recovery, and attribution destinations
- Ruff, Python compilation, production preflight, and diff integrity passed
- GitHub CI `34506313230`, Android verification `34506313344`, and iOS verification
  `34506313239` passed
- Production deployment `dpl_5wTHTFDdsqzsb1UVc78hqhAdWjCS` is READY on all six aliases
- Canonical homepage and `/app` returned HTTP 200 and reference
  `5.9.76-organic-feed-attribution-1`
- Live `landing.js` SHA-256:
  `c43bcdc290fb3505f43d41e50e63a690acfe08ef179e98ecaebcca3c30794a4a`
- Live `auth-controller.js` SHA-256:
  `d3562b29b156e5c9c205b7efca7f2573cf9a2b789f0e6f3c4e8473d55c5455fd`
- Initial deployment-scoped warning/error/fatal log scan and project runtime-error scan were empty
- Marketing's exact-set live verifier passed both production assets and its full non-synthetic
  action-time preflight passed with tagged URL unrequested, publication false, and spend `$0`

## Authority boundary

No tagged campaign URL was opened, no synthetic account or product event was created, no social
post was published, and no advertising spend or offer change occurred. Publication remains a
separate immediate representational decision owned by the founder and marketing operator.
