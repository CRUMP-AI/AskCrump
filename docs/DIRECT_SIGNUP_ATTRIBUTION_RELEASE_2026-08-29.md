# Direct signup attribution release

Date: 2026-08-29

Status: verified in production

## Decision

Preserve the existing registration experience while the predeclared observation window matures.
Repair the deterministic attribution gap that labeled direct-to-app social visitors as `direct`
before using the next cohort to choose an acquisition or activation intervention.

This is a measurement-quality release. It does not change signup requirements, verification,
pricing, entitlements, prompts, customer data, or social publication.

## Evidence before the change

The Vercel Web Analytics trailing-seven-day view (Aug 22, 04:00 through Aug 29, 04:59 in the
dashboard) reported:

- 108 visitors, 391 page views, and 58% aggregate bounce;
- 29 `SignupIntent` visitors producing 46 events;
- two `SignupStarted` visitors;
- one `SignupSubmitted` visitor;
- one directional browser-side `AccountCreated` event;
- 22 of the 29 signup-intent visitors carrying Facebook referrers
  (`m.facebook.com` 12 and `facebook.com` 10);
- 55% mobile and 45% desktop signup-intent visitors;
- 48% Android, 38% Windows, 7% macOS, and 7% iOS signup-intent visitors; and
- 28 deep-link signup-intent visitors versus one explicit auth-link visitor.

The signup-intent event's acquisition property nevertheless showed 18 visitors as `direct`, one
as `facebook-pinned`, and one as `organic`. Direct `/app?signup=1` links did not execute the
marketing landing page's privacy-minimized referrer reducer, so known Facebook referrals could be
recorded as direct acquisition.

The service-role, production-only `product_growth_funnel_snapshot` for the comparable measurement
window beginning `2026-08-23 09:10:55.602863+00`, with internal accounts excluded, returned zero
accounts at every stage. The artifact-journey snapshot returned no rows. Existing production
product events belonged to one account created before the comparable window and therefore are not
evidence of new-user conversion.

These aggregates do not justify a signup conversion rate or a downstream activation rate. The
cohort has not reached the existing decision boundary of 14 days and 50 signup-intent visitors, and
there is no eligible non-internal account denominator.

## Change

`auth-controller.js` now applies the same privacy-minimized first-touch rules on direct app entry:

- explicit `acquisition` or `utm_source` remains authoritative;
- allowlisted legacy social source parameters remain supported;
- a valid first-touch value already stored for the tab remains authoritative;
- Ask Crump-to-Ask Crump navigation remains `direct`;
- known search hosts reduce to `organic`;
- known social hosts reduce to their channel name;
- Clever Crump reduces to `clevercrump`;
- other external hosts reduce to `referral`; and
- malformed or absent referrers reduce to `direct`.

No URL, page path, search term, campaign content, email, credential, account identifier, or customer
content is stored. The derived value remains a lowercase allowlisted category no longer than 32
characters. Cache revision 115 distributes the updated controller and landing reducer to existing
installed PWAs.

## Verification

- Executable JavaScript coverage runs the production reducer against same-site, Ask Crump apex,
  Facebook, Instagram, Google, unknown external, absent, and malformed referrers.
- Static coverage preserves explicit-parameter and stored first-touch precedence.
- All 432 Python regressions passed.
- All 44 JavaScript files and the new reducer contract passed validation.
- Explicit Python compilation, production preflight, native web-bundle build, and store metadata
  checks passed.
- Commit `aba3f3d` deployed as `dpl_BKbNy1DM7pyGfQ5Xohqkggkeg3Aw`.
- All six production aliases point to the release.
- Production serves the new Facebook reducer and cache revision 115.
- The clean signed-out release retained nine scripts, four styles, focused login, a deferred
  workspace runtime, and zero horizontal overflow.
- The existing authenticated canonical session retained the complete 38-script/21-style
  runtime-ready workspace with zero browser log.
- Canonical health returned 200/version 5.9.75.
- The release window contained no runtime error cluster or warning/error/fatal deployment log.

## Next decision boundary

Continue observing the protected `SignupIntent` → `SignupStarted` boundary until at least 14 days
and 50 signup-intent visitors have accrued, or inspect the first legitimate non-internal account
and its content-free account → workspace → intent → activation journey sooner. Do not change signup
policy or scale acquisition spend from the current small anonymous sample.
