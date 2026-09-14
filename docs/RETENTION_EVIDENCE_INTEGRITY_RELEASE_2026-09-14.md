# Retention evidence integrity release — 2026-09-14

## Outcome

Ask Crump's weekly growth and combined operating snapshot now fail closed before presenting a D1,
D7, activation, durable-value, or paid-conversion rate from malformed aggregate evidence. The
exporter previously protected sensitive fields and zero denominators, but it still coerced missing,
negative, boolean, or string counts and could calculate a returned-user rate above 100%.

The guard now requires all 25 authoritative cohort counts to be present as nonnegative integers,
validates the three nullable database finance totals, requires every row to share one normalized
cohort boundary, and binds that boundary to the requested half-open reporting window. It then checks
24 subset relationships, including:

- D1 returned cannot exceed D1 eligible;
- D7 returned cannot exceed D7 eligible, and D7 eligible cannot exceed D1 eligible;
- activation reached cannot exceed activation eligible;
- every 24-hour value result remains inside its eligible population;
- account, checkout, plan-intent, payer, and active-paid counts remain inside their authoritative
  denominators.

An empty cohort remains valid and produces unavailable rates. A genuinely eligible cohort with zero
returns still produces a truthful 0% rate. The change does not alter the database function or its
retention semantics; it prevents an operator from accepting impossible output.

## Verification

- focused weekly/operating snapshot suite: **41/41**;
- complete Python suite: **1,120/1,120**;
- JavaScript validation: **54/54** files;
- Ruff: passed;
- whitespace integrity: passed;
- GitHub CI: `34905067263`, Python and JavaScript jobs passed.

Executable fixtures cover valid eligible and not-yet-eligible states, missing D1 denominators,
returned-above-eligible D1, D7 eligibility above D1, activation above its 24-hour denominator,
negative/string/boolean counts, early/mismatched/invalid timestamps, inconsistent multi-row
boundaries, sensitive fields, and valid timezone normalization.

## Release proof

- Commit: `92253749b75f496252e7cb8f70151366a250791d`.
- Production deployment: `dpl_6RgbNiZsJdHccRrU1L4WeEjLsTyj`; Ready on all six aliases with no
  alias error.
- The initial production observation window contained no HTTP 5xx response and no grouped runtime
  error.

## Boundary and next decision

This is reporting-integrity infrastructure, not retention improvement and not a new retention
observation. It performs no database write, adds no customer field, and reads no identity or
customer content. The first comparable account becomes D1-eligible only at
`2026-09-15T00:00:00Z`; refresh the protected aggregate after that boundary and accept the result
only if this guard passes. Continue to keep internal QA and Checkout diagnostics out of users,
payers, retention, and recognized revenue.
