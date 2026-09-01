# Ask Crump 5.9.76 credit-pack accessibility release

Date: 2026-09-01

Feature commit: `c07cde96875fbd3be122eb8da2fec991509e2148`

Production deployment: `dpl_6L6wqoDSHxQEvZTS6z4LV58tay1v`

## Outcome

Each available Crump Credit pack now exposes one unambiguous purchase control. The visual card
remains a forgiving pointer and touch target, while its actual **Add credits** button exclusively
owns keyboard and assistive-technology semantics. The button's accessible name includes the exact
pack amount and displayed price, for example **Add 50 Crump Credits for $4.99**.

No price, catalog item, credit balance, allowance, subscription, entitlement, provider, checkout
endpoint, analytics event, payment behavior, or customer record changed.

## User-eye finding

A signed-in production walkthrough opened **You → Plan & credits** without purchasing anything.
Before this release, each hydrated pack was announced as a button-like card containing a second
button. The three inner controls were all named only **Add credits**. That nested interaction model
could create duplicate focus stops, unclear screen-reader choices, and double or unpredictable
activation around a revenue-critical action.

The corrected contract is:

- the pack `article` has no `role="button"` and no `tabindex`;
- each pack contains exactly one real button;
- the three live button names include `50 / $4.99`, `150 / $9.99`, and `400 / $19.99`;
- Enter and Space are owned only by the real purchase button;
- pointer and touch activation across the pack still produces one checkout attempt;
- an opening state is announced, and a failed or interrupted opening restores the exact original
  accessible name;
- focus styling follows the contained button through `:focus-within`.

## Automated and browser verification

- All **722 Python tests** passed.
- All **47 JavaScript validations** passed.
- Production build preflight passed.
- The native web bundle built successfully.
- Store metadata and signing-source controls passed; no signing secret was present.
- `scripts/verify-credit-pack-accessibility.cjs` passed at **390×844** and **1280×720**. Each run
  proved three packs, zero nested interactive cards, three unique buttons, keyboard focus on the
  first pack action, exactly one blocked fixture checkout from a full-card pointer activation,
  restored labeling, and zero browser errors.
- The adjacent image-scroll browser contract remained green.
- The adjacent paid-plan-intent browser contract remained green for Professional and Enterprise on
  phone and desktop.
- `git diff --check` passed.

The isolated release worktree does not contain generated Android or iOS platform projects, and its
shell did not contain RevenueCat public SDK keys. Signed archives, store billing, and physical-device
behavior are therefore not claimed by this release.

## Production evidence

Vercel marked the exact commit deployment **READY**. Canonical production returned HTTP 200 for
`/app`, both versioned billing contracts, and `sw.js`. The service worker serves cache revision
`ask-crump-new-body-v1-r187`; both changed runtime assets serve version
`5.9.76-credit-pack-accessibility-1`.

In the signed-in canonical app, all three live pack cards had:

- one contained button;
- `role = null` on the card;
- `tabindex = null` on the card; and
- exactly one matching accessible button name for its amount and price.

No production credit or plan control was activated. The inspected release window contained **19
HTTP 200 responses**, no 4xx/5xx response, no runtime-error cluster, and no warning/error/fatal log.

## Remaining outcome gate

Repeat the Plan & credits journey on a physical iPhone with VoiceOver and on a keyboard/screen-reader
desktop candidate. Observe a legitimate customer checkout and successful credit reconciliation
before claiming any conversion lift. A safe accessibility correction is shipped; revenue impact is
not yet proven.
