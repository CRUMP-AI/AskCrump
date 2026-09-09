# Button owner context guard release — 2026-09-09

## Outcome

The exhaustive Ask Crump button inventory can no longer treat a JavaScript token match as proof
that a rendered button works. Each non-submit rendered button must now have its strongest available
identifier—ID first, then data attribute, then a non-generic class—inside a bounded JavaScript
context that contains a click owner. Sources are checked independently so a handler in one file
cannot rescue an unrelated button in another.

The 94 programmatically created buttons retain their existing stricter rule: each must declare its
behavior type and have either a direct click owner or an exact reviewed delegated-owner contract.

## Evidence that selected the work

The preceding broad sweep proved 275 inventoried button construction sites, 36 browser flows, and a
safe signed-in production interaction boundary. A follow-up review found that the rendered-button
guard itself accepted an ID, data attribute, or class merely because it appeared anywhere in the
combined JavaScript corpus. A future dead button could therefore pass if code only looked it up, or
if an unrelated file happened to contain the same generic class.

Production evidence did not justify a signup, pricing, or feature redesign: the privacy-safe
September external growth, attribution, Project-continuity, plan-conversion, and feedback aggregates
remain empty; the demo proof remains unconfigured; and the seven-day runtime review contains no
runtime-error group. Strengthening release prevention was therefore the highest-leverage safe
product action supported by current evidence.

## Fail-closed contract

- Button markup is removed before executable owner analysis, so a button cannot own itself.
- Exact IDs take precedence when executable code references them.
- Referenced `data-*` attributes are used when no executable ID reference exists.
- Only non-generic classes are eligible as the final anchor; shared tokens such as `btn`,
  `is-primary`, and `is-danger` cannot establish ownership.
- The anchor and click owner must occur within a 2,500-character bounded context in the same
  JavaScript file.
- A lookup-only fixture fails.
- A distant unrelated click handler fails.
- An exact click binding passes.
- Inventory drift remains fail-closed at 181 rendered plus 94 programmatic sites.

## Validation and delivery

- Commit `df2a134e0460ae693b71d449c7f9acb9fd556b25`.
- Button integrity: 22/22 tests passed.
- Complete Python suite: 946 collected, 944 passed, two environment-dependent skips.
- JavaScript validation: 49 files and all six rough-to-useful attribution cases passed.
- Browser control matrix: 36/36 verifiers passed.
- Ruff, Python compilation, production preflight, native web bundle, and diff integrity passed.
- GitHub Actions CI `34403512783` passed.
- Production deployment `dpl_Ho7hBE3NpGUW53fSeefxD2bXuv5J` is READY on all six aliases with
  no alias error.
- Production health returned HTTP 200 on Ask Crump v5.9.76; the initial 30-minute runtime-error
  query and one-hour 5xx query were empty.

This release changes the prevention test only. It creates no account, Project, file, prompt,
generation, checkout, charge, database row, campaign, post, or customer-facing runtime behavior.

## Decision boundary

The inventory now provides stronger evidence that every reviewed control has a real click owner;
it does not claim that every destructive, paid, permission, provider, or signed physical-device
outcome has been executed. Those outcomes retain their separate legitimate-user and action-time
gates.
