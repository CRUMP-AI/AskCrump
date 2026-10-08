# Protected operating refresh — 2026-10-08

## Outcome

Ask Crump's first post-September protected refresh now contains an observed durable-value milestone,
Project creation, and server-confirmed Project save. That supersedes the earlier zero-Project
baseline. It does not yet prove continuing work because no later Project reopen or resume is
observed.

Both read-only external-production snapshots passed the shipped ten-section
`ask-crump.operating-snapshot.v1` validator at `2026-10-08T01:23:56.891233Z`:

- current closed week: `[2026-10-01T00:00:00Z, 2026-10-08T00:00:00Z)`;
- comparable cohort to date: `[2026-08-23T09:10:55.602863Z, 2026-10-08T00:00:00Z)`.

The validator required every protected section, exact growth-funnel schema and order, exact artifact
and navigation contracts, Project-continuity boundaries, and agreement between shared growth and
weekly-attribution facts. The source was commit `c1a3ab7b9b17739f853508cbfe03f19d264bcb10`,
which merged the hardened exporter from `2ef70464df25f459a3a83ff7fe469bf750f1c2b1`.

## Current closed week

The current-week cohort contains one direct account and one matching `AccountCreated` event. Before
the window closed, the cohort contained:

- zero verified accounts, workspace opens, activations, durable-value milestones, plan intents,
  Checkout opens, Checkout completions, or active paid accounts;
- zero Project-save offers, intents, completions, or resumes;
- no artifact-journey, outcome-issue, or lifecycle row;
- zero D1-eligible and zero D7-eligible activated accounts.

This is a pre-verification stop in a one-account cohort. A follow-up content-free delivery audit
isolated the account to the 2026-10-06 10:00 UTC hour: account creation and the matching
`AccountCreated` event completed, one verification message was accepted by Resend, and Resend
classified that message as one transient bounce less than one second later. The same hour contains
one login attempt, zero resend-verification attempt, zero permanent bounce, zero failed or suppressed
message, and no authentication-route runtime error. The verification token later expired.

The sending domain remains verified and enabled, and the two preceding listed verification messages
were delivered. Resend exposes no configured webhook for this application, while individual message
logs had already passed the connected runtime's one-day retention boundary. The strongest supported
classification is therefore a downstream recipient-server delivery failure plus a deterministic
recovery and observability gap—not a registration, session, PWA, or general email-domain regression.

## Comparable cohort to date

The instrumentation-bounded cohort contains three accounts:

- three account-creation events;
- two verified accounts, two workspace opens, and two activations;
- one durable-value milestone, one Project creation, and one Project-save completion;
- one D1 return among two eligible activated accounts;
- zero D7 returns among two eligible activated accounts;
- zero later Project resumes, response shares, plan intents, Checkout opens, Checkout completions,
  distinct payers, or active paid accounts;
- no observed artifact-journey row;
- one fixed-category external `safety` outcome record;
- two `continuity-assist` exposures and zero recorded actions;
- one `starter-assist` exposure with its target completed within 24 hours, despite no recorded card
  action;
- sanitized demo proof remains false across all seven boolean checks.

The Project-save aggregate records one observed offer, later intent, and paired completion in the
organic acquisition row. Offer-to-intent and intent-to-completion are both `1/1`; completion-to-
later-resume is `0/1`. These are exact small-sample counts, not stable conversion rates or evidence
of causal lift.

The aggregate has no authoritative recognized-revenue, refund, variable-cost, landing-visitor, or
ad-spend input. Those fields remain unavailable. Checkout and payer counts must not be converted
into a revenue claim.

## Production-health companion check

At the observation boundary:

- GitHub `main` was `c1a3ab7b9b17739f853508cbfe03f19d264bcb10`;
- GitHub Actions run `37711365419` passed its Python and JavaScript checks;
- Vercel deployment `dpl_Gy4XifhUh1YC4tTXT4WGM6NdGkb3` was Ready for the same commit;
- the canonical `/app` route and direct deployment both returned HTTP 200;
- Vercel reported no grouped production runtime error in the trailing seven days;
- the latest five production deployments were Ready.

No current runtime failure explains the current-week pre-verification stop. Repository governance
still reports unprotected `main` with no required-check enforcement; changing that is a separate
sensitive-control decision, not part of this read-only refresh.

## Decision and next action

Preserve the shipped Project-save experience. The first observed completion closes the first-use
portion of the continuity evidence gap, but no later reopen or resume exists, so an end-to-end
continuing-work journey remains unproven. Keep paid-acquisition, D7, payer, artifact, recognized-
revenue, and demo-proof gates closed.

Ship the narrow local recovery already justified by this incident: the durable verification-pending
screen must let a person return to registration with the prior address selected for correction, the
password cleared, and no automatic resend or second registration request. Preserve the existing
explicit resend and sign-in actions. The next larger reliability item is signed, idempotent,
content-free Resend delivery-event ingestion with bounded transient-bounce recovery; do not configure
that production webhook or silently resend mail until signature verification, attempt limits,
suppression behavior, privacy fields, and operator rollback are proven.

After the recovery action is verified, the next highest-value product evidence remains three
consented current-release observations of:

`account creation → verification → useful result → Project save → named Project reopen`

Schedule the existing D1 and D7 checks for those cohorts. Do not insert synthetic production events
or infer failure from an unattempted action.

## Verification-email correction candidate

The recovery candidate adds **Use a different email** to the persistent verification-pending
screen without removing **Already verified? Sign in** or **Resend verification email**. The action
returns locally to registration, retains and selects the address for correction, clears the prior
password and its visible/validation state, announces that the password must be entered again, and
makes no network request. Submitting the unchanged address is rejected locally and still makes no
request; a genuinely corrected address requires one deliberate registration submission.

The server continues to preserve the password of any already-pending target account. A repeated
registration response now states that the person must use the password already set for that account
or use Forgot password, preventing the UI from implying that a discarded replacement password was
saved. This avoids turning an email-correction convenience into an unverified-account takeover path.

Verification completed locally with the full Python regression suite, all 54 JavaScript source
checks, the complete 53/53 browser-control matrix, the focused real 390×844 account-entry flow,
33/33 public accessibility scenarios, the production build preflight, and diff-integrity checks.
No production account, email, token, database row, provider configuration, webhook, or customer
content was changed by these tests.

## Privacy and mutation boundary

The refresh used service-role-only aggregate functions and excluded internal accounts. It did not
read or retain account identifiers, email addresses, prompts, responses, filenames, URLs,
referrers, payment objects, storage paths, or customer content. It performed no database, account,
Project, payment, entitlement, pricing, campaign, or customer-content write. Raw snapshot JSON was
not committed.
