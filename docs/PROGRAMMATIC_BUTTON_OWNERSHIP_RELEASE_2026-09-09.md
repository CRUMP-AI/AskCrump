# Programmatic button ownership release — 2026-09-09

## Outcome

The complete button-prevention boundary now includes controls built with
**document.createElement('button')**, not only static HTML and JavaScript template markup.
The earlier exhaustive release locked and owner-checked **181** markup-rendered buttons, but a
separate source audit found **92** programmatically constructed buttons across 16 JavaScript
owners. Those controls already had working owners, but their creation sites were outside the
fail-closed inventory.

The corrected contract:

- locks all 92 programmatic creation sites by file, alongside the existing 181-button markup
  inventory, for **273 reviewed button construction sites**;
- requires every programmatic button to declare button, submit, or reset behavior explicitly;
- bounds a direct click owner to that created control's declaration lifetime instead of accepting
  an unrelated use of the same variable name elsewhere;
- records exact executable evidence for the 11 intentional indirect owners: two viewer-close
  helpers, one generated-output Project helper, one billing delegation, five Crump Code
  delegations, one conversation-menu delegation, and one form submission;
- requires the indirect-owner evidence set to remain exact, so a stale exception cannot survive
  after ownership changes; and
- includes a negative fixture proving that a typed, visible-looking programmatic button without an
  owner is rejected.

No customer-facing JavaScript, API, database, billing, provider, or interface behavior changed.
This is a prevention and proof correction: a future dynamic dead button now fails CI instead of
shipping outside the inventory.

## Verification

- Complete button integrity module: **20/20** checks passed.
- Reviewed inventory: **181** markup-rendered plus **92** programmatic button sites, **273 total**.
- Programmatic ownership: **81** direct click owners plus **11** exact indirect/form owners.
- Complete Python suite: **922 collected**, **920 passed**, two environment-dependent skips.
- JavaScript integration contract: **49 files** and **6/6** attribution runtime cases passed.
- Ruff, Python compilation, production preflight, and diff integrity passed.
- Feature commit: **fa2cc57ebd92963b196ea9eb52ad5d91646796b0**.
- Main CI **34364271065** passed.

## Production boundary

The automatic six-alias production build is
**dpl_897k5ybTj3s1mcLmtRtPVyJLAnx3**, READY on all six aliases with no alias error. Because the
feature changes test coverage only, the prior customer runtime remains byte-for-byte unchanged.
All four Ask Crump/Clever Crump custom-domain health endpoints returned HTTP 200 at version
5.9.76. The first 30-minute production runtime-error aggregate was empty, and the exact deployment
contained no warning, error, or fatal log.

This contract proves explicit ownership at every reviewed button construction site and preserves
the existing credential-free browser workflow matrix. It does not claim that an external provider,
permission, network, store, or customer-data dependency can never fail; those actions retain
visible recovery states and require legitimate-use or signed-device evidence for their respective
outcome gates.
