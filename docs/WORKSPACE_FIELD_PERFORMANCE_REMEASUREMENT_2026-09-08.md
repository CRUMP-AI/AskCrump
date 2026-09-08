# Workspace field-performance remeasurement — 2026-09-08

## Outcome

The planned real-user remeasurement gate for the authenticated workspace has matured. In Vercel
Speed Insights' production-only desktop view for September 1 through September 8, `/app` reached a
Real Experience Score of **91** across **400** field-performance events. The pre-release baseline
was **79** across 317 desktop events. The new route score is above Vercel's displayed **Great**
threshold of 90 and satisfies both operating-plan gates: at least seven full post-release days and
at least 300 post-release desktop events.

The same dashboard reported an overall desktop score of **93** across **477** events. Measured
public routes remained at 100: `/` across 27 events, the rough-idea workflow guide across 19,
`/clever-crump` across 12, and `/ai-project-workspace` across 11. These route-specific counts and
scores were read without changing project configuration or application state.

## Decision

The production field result closes the loader release's planned desktop observation gate. Do not
start another workspace-loader rewrite from the old score. Preserve the parallel asset-fetch and
ordered-execution boundary, and investigate performance again only if route-level field evidence
regresses or a specific Core Web Vital becomes available and identifies a new constraint.

Mobile Speed Insights still reported **no data** for the same production seven-day selection.
Desktop evidence must not be relabeled as mobile performance. The exact signed iPhone and Android
candidates still need physical-device interaction and performance review before store submission.

## Evidence boundary

This is observational field evidence, not a controlled causal experiment. The score improvement is
consistent with the released loader repair, but the population and traffic mix may differ from the
earlier window. It proves that current desktop `/app` performance cleared the predetermined
production gate; it does not prove a signup, activation, retention, or revenue lift. No synthetic
visit, account, product event, checkout, customer record, or application mutation was created.
