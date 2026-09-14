# Facebook embedded signup handoff gate — 2026-09-14

## Decision

Preserve the current registration experience and add a permanent production-script browser gate
for the social mobile handoff. Do not claim that Facebook traffic converts poorly from the current
product, because the available 30-day client-analytics window crosses several superseded account-
entry releases and the current seven-day period does not contain a comparable Facebook acquisition
cohort.

## Privacy-safe acquisition evidence

The production-only Vercel Web Analytics 30-day view reported 197 visitors, 1,191 page views, and a
44% bounce rate at observation. It reported 36 visitors with 60 `SignupIntent` events, four visitors
with four `SignupStarted` events, two visitors with two `SignupSubmitted` events, and two visitors
with two client-side `AccountCreated` events. These are browser aggregates, not the authoritative
server cohort, and may include internal, automated, pre-fix, and duplicate activity.

Within the `SignupIntent` filter, 12 visitors had an `m.facebook.com` referrer and ten had a
`facebook.com` referrer. The fixed source labels accounted for nine `facebook-pinned`, seven
`facebook`, and six `facebook-organic` visitors. None of the four `SignupStarted` visitors had a
Facebook referrer: the start cohort was two `clevercrump` acquisition visitors and two `direct`
visitors, split across three desktop and one mobile visitor. This is a useful historical signal to
protect, but it is not a current conversion rate.

The same dashboard's current seven-day overview reported 24 visitors, 151 page views, and a 4%
bounce rate. Its visible referrer set contained one Ask Crump self-referral and one Clever Crump
referral rather than a fresh Facebook cohort. The service-role database report remains authoritative:
one comparable `clevercrump` account exists through activation, while no comparable Facebook account
or current Facebook signup denominator exists.

No account identifier, email, credential, prompt, response, Project, filename, URL path containing
customer data, or payment detail was read or retained. The fixed test email below exists only inside
a loopback browser fixture and is never submitted.

## Released regression boundary

`scripts/verify-public-account-entry-buttons.cjs` now runs the real registration controller inside a
390-by-844 touch context with a Facebook embedded-browser user agent and an
`https://m.facebook.com/` referrer. It opens the exact allowlisted continuity campaign URL and
requires all of the following before the general browser matrix can pass:

- the registration surface is visible without waiting for a user gesture;
- the headline promises the private Projects workspace rather than a generic account;
- keyboard focus lands on the email field;
- the referrer survives the browser handoff;
- typing a local fixture email and valid password records exactly one `SignupIntent`, one
  `SignupStarted`, and one `SignupCredentialsReady` event;
- every milestone retains only the allowlisted `facebook` / `organic-social` /
  `real-product-continuity` / `continuity-feed` / `projects` tuple;
- the initial signup location remains `deep-link`; and
- the embedded-mobile context produces no browser error.

The fixture intercepts analytics and the session check locally. It never submits the registration
form, contacts the production account endpoint, creates an account, sends email, changes attribution,
or writes a production event.

## Verification

- Focused auth and registration contracts: 24/24 passed.
- Full Python suite: 1,060/1,060 passed.
- JavaScript validation: 54/54 files passed.
- Browser control matrix: 47/47 passed, including the expanded public account-entry verifier.
- Python lint, JavaScript syntax, and diff integrity passed.

## Next evidence gate

Keep the current auth copy and behavior stable. Re-evaluate after at least one current-release
Facebook visitor reaches `SignupIntent`, or after a fresh bounded cohort supplies a reproducible
embedded-browser failure. Compare `SignupIntent` → `SignupStarted` only within the same release
boundary and acquisition tuple; do not combine this historical 30-day aggregate with the current
server cohort or scale spend from it.
