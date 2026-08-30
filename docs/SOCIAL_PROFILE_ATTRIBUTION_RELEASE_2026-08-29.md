# Social profile attribution handoff

Date: 2026-08-29

Behavior commit: `d3d458a`

Production deployment: `dpl_H1Ru89SL6aVweTfbcMADZwvid8Va`

## Accountable outcome

Ask Crump can now preserve a fixed, categorical `profile-link` placement from a public landing
page into signup or sign-in while retaining the separately allowlisted acquisition channel. This
allows future Facebook and Instagram profile links to distinguish a profile visit from a pinned
post, response share, generic direct visit, or onsite CTA without collecting a profile identity,
referrer URL, email, prompt, response, or other customer content.

The prepared destinations are:

- Facebook: `https://www.askcrump.com/?acquisition=facebook&source=profile-link`
- Instagram: `https://www.askcrump.com/?acquisition=instagram&source=profile-link`

The social profiles were not edited in this release. Search Console was inspected read-only and
its sitemap was not submitted.

## Evidence that selected the work

Read-only channel and product-path review found that social profile visits could reach the public
site without a stable categorical placement. The app already preserved `response-share`, but a
profile-originated visit could otherwise become indistinguishable from generic direct or onsite
traffic before signup or sign-in. The review did not inspect customer content, prompts, responses,
files, or raw identities.

The current registration surface was visually inspected at desktop, 390-by-844, and 390-by-667.
Its value promise, email/password fields, consent, primary free-account action, verification
assurance, learn-first path, and existing-account sign-in all remained visible without horizontal
overflow. No deterministic form or layout defect justified another authentication rewrite.

Read-only profile inspection confirmed that the two channels did not share one canonical,
measurable profile-link contract. Search Console was also inspected without changing its state.
Detailed audience, funnel, account, and search measurements remain in the private operating review
and are intentionally excluded from this public repository.

## Corrected contract

- Only `response-share` and `profile-link` are accepted as persistent acquisition placements.
- A recognized placement survives the public page and is forwarded to both signup and sign-in.
- The acquisition channel remains a separate allowlisted category such as `facebook` or
  `instagram`.
- An invented placement is discarded; the ordinary onsite CTA location remains intact.
- No raw referrer URL, social identity, profile name, email, customer content, or free-form field is
  collected.
- Existing referral attribution, creation intent, plan intent, authentication, payments,
  entitlements, and pricing are unchanged.

## Verification

- A credential-free real-browser fixture proved:
  - Facebook + `profile-link` reached signup and sign-in exactly;
  - the two content-free marketing events retained acquisition `facebook`;
  - Instagram remained acquisition `instagram`;
  - an invented placement was omitted and did not replace the onsite CTA location;
  - zero browser errors and no production request or event.
- All 485 Python tests passed.
- All 45 JavaScript files passed the repository validation contract.
- Production preflight passed.
- The native web bundle regenerated successfully.
- Store metadata source checks passed.
- Deployment `dpl_H1Ru89SL6aVweTfbcMADZwvid8Va` reached `READY` on all six aliases.
- Canonical health, the homepage, the versioned landing runtime, and service worker returned HTTP
  200 with the exact `profile-link` and cache `r129` markers.
- The initial release window contained one observed HTTP 200 runtime response, no 4xx or 5xx, and
  no runtime error cluster.

## Observation and action boundary

Do not compare historical labels as if they were one consistent cohort. After the tracked profile
links are applied, use a predeclared observation window and minimum legitimate sample before
judging signup-intent reach. Reconcile account creation and activation against the
internal-excluded cohort; do not optimize for social visits alone.

The highest-leverage next actions are external and remain owner-gated: apply the prepared Facebook
and Instagram links, publish the approved launch batch, and submit the canonical Search Console
sitemap. No paid traffic should scale before a legitimate account reaches useful work and a durable
Project or artifact.
