# Public entry experience audit — 2026-09-10

## Decision

Preserve the current public landing and first authenticated-entry experience. The live phone and
desktop review found no product-owned defect that justifies a conversion redesign before qualified
traffic exists.

## Live evidence

The audit used the canonical production host and a separate background browser tab.

- At **390 × 844**, the opening viewport showed the canonical Ask Crump lockup, the complete
  **AI should help you finish things** value statement, one prominent **Start free** action, one
  **See a real workflow** action, and the no-card boundary without horizontal overflow.
- At **1440 × 900**, the same promise and actions remained prominent; the full navigation added
  product, pricing, principles, sign-in, and Free-start destinations without crowding the hero.
- All loaded images reported valid rendered dimensions. The live page exposed one H1 and descriptive
  links rather than unlabeled controls.
- The hero Free-start destination preserved the exact direct-safe tuple
  `/app?signup=1&source=hero&plan=free&acquisition=direct`.
- Because the inspection browser already held a valid Ask Crump session, that destination opened the
  authenticated workspace rather than a duplicate account-entry form. The workspace rendered Ask,
  Projects, Create, Video, Library, and You; it did not create a conversation, send a message, start a
  provider job, consume credits, or change account state.
- **See a real workflow** opened the canonical rough-idea guide. Its live hero, authentic product
  evidence, human-review boundary, Project continuity explanation, and direct-safe Free-start action
  rendered without a warning or browser error.
- The browser warning/error log was empty across the landing and guide inspection.

## Measurement boundary

The one live hero CTA click can emit the existing anonymous Vercel `MarketingCTA` event with direct
acquisition and hero placement. It is internal QA traffic, not evidence of customer demand, account
creation, activation, or conversion. The inspection created no Supabase account or product-event row.
Do not use this click to infer a funnel rate.

The in-app inspection scope did not expose trustworthy Navigation Timing or transfer-size entries,
so this audit makes no performance claim. Route-level field performance remains governed by the
existing production evidence in the operating backlog.

## Next action

Keep the landing message and Free-start routing stable while the comparable external cohort is empty.
The next acquisition decision should follow legitimate profile/search traffic or a consented
sanitized-demo journey, not another internal visual redesign.

