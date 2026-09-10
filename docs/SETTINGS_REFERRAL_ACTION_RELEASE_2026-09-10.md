# Settings referral action release — 2026-09-10

## Outcome

Ask Crump now gives a signed-in user a permanent **Invite someone to Ask Crump** action in
**Settings → About**. The action shares only the fixed public Ask Crump invitation and its
content-free referral URL. It does not include a conversation, prompt, response, Project, file,
customer identifier, or raw referrer.

The same reviewed sharing helper remains the sole delivery path:

- a completed native share records one `ResponseShared` event after delivery;
- a native-share cancellation is quiet and records nothing;
- if native delivery is unavailable, a successful clipboard fallback records only after copy;
- if both delivery methods fail, the interface says that nothing was posted or sent; and
- the Settings action disables only while its own delivery attempt is in progress, preventing a
  duplicate action without blocking the rest of the workspace.

## Verification

- Repository button inventory: **182 rendered + 94 programmatic = 276** construction sites,
  every one with explicit behavior and a bounded click owner.
- Focused Python contracts: **31/31** passed.
- Browser referral fixture: native cancel, true failure, and clipboard success passed from both
  the lifecycle prompt and the permanent Settings action.
- Complete browser control matrix: **37/37** passed.
- Complete Python suite: **978/978** passed.
- JavaScript contract: **49 files**, **21/21** rough-to-useful attribution cases, and **10/10**
  Word/PDF attribution cases passed.
- Production preflight and native web-bundle build passed. Local signed native verification
  remains correctly blocked because the Android/iOS projects and RevenueCat public keys are not
  present in this checkout; no store-readiness claim is made from that local check.
- Product commit: `710553d5e6b8233f3fd7d0576766911032601e0b`.
- GitHub CI `34494255055`, Android source verification `34494255313`, and iOS source
  verification `34494255215` passed.
- Vercel production deployment `dpl_Fozgp9TwMypt3TL8C1rTTrfXDaqF` is READY on all six aliases.
- Canonical health returned HTTP 200 at version `5.9.76`.
- Exact production/local SHA-256 matches:
  - `app.html`: `11ac4a3e67271a48837fac2ea540a79e743450898defeeafd9370f0ec63c498c`
  - `lifecycle-share.js`: `bd39ab4ad3a813bcc8f50cb43788c47f05ca275f8695dff636c3f82d3fe99385`
  - `runtime-body-v1.js`: `5d414f32fdce7321060bb7224a182c18b5b3e0600c6a44aedb7b3e5f34648742`
  - `sw.js`: `45a6d4b77ce8388119f0937912b03c34e651072637c95c001ed72f3a84c5cc4e`
- Initial production scans found no grouped runtime error, no error/fatal log, and no 5xx request
  on the deployment.

## Claim boundary

This release proves that the persistent referral control behaves safely and that the broader
credential-free button matrix remains intact. It does not prove recipient acquisition or
activation, and it does not authorize social publication, messages to contacts, paid promotion,
or referral-performance claims. Observe a legitimate share → recipient visit → registration →
activation journey before changing the invitation or claiming lift.
