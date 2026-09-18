# Autonomous Crump brand identity release — 2026-09-17

## Decision

The customer-facing name of Ask Crump's gated software-engineering agent is
**Autonomous Crump**. The earlier **Crump Code** name is retired from current
customer-facing copy. **Nova** is not used.

Stable implementation identifiers remain unchanged: `crump_code`, the `/api/code`
routes, database objects, JavaScript globals, CSS selectors, filenames, feature keys,
telemetry names, and error codes continue to use their existing machine-readable
values. This prevents a brand-only change from breaking stored tasks, permissions,
analytics, caches, or operational tooling.

Historical release receipts continue to describe the name that was true when those
releases were recorded. Current living documentation uses Autonomous Crump and calls
out the internal `crump_code` identifier where operators need it.

## Customer surfaces

- The private-preview workspace, accessible names, task states, and notices say
  **Autonomous Crump**.
- The gated navigation destination says **Autonomous Crump**.
- The feature catalog and overflow-rate disclosure use the same name.
- Backend validation and task-state errors shown to a customer use the same name.
- The lazy-loaded workspace script has a new cache key so an entitled browser cannot
  retain the retired wording.

## Preserved boundaries

This release does not enable the coding agent, change entitlement or pricing, call a
model, start a Sandbox, create a task, spend credits, publish a parity claim, or weaken
the existing public-release lock. Autonomous Crump remains disabled and unadvertised
until its live Sandbox/OIDC, cancellation, destruction, refund, monitoring, rollback,
quality, latency, and actual-cost gates are complete.

## Acceptance

- Customer-visible runtime and server messages contain Autonomous Crump.
- Stable implementation identifiers remain present and unchanged.
- The disabled, locked, and entitled browser fixtures preserve their existing access
  behavior while exposing the new accessible name.
- JavaScript validation, focused Python coverage, the browser control matrix, the full
  Python suite, lint, build, and diff integrity must pass before release.
