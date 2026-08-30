# Crump Code fixed benchmark

## Status

This is a provider-neutral, offline scoring foundation. It does not enable Crump Code, call a
model, create a production task, spend credits, or establish a quality/parity claim.

The suite pins one public Ask Crump Git revision containing four deliberately small cases: Python
boundary behavior, JavaScript normalization, security-sensitive header handling, and an atomic
concurrency plan. Candidate changes are constrained to explicit implementation paths; acceptance
files are immutable.

## What the evaluator trusts

The evaluator never executes candidate code. It consumes the durable task result and verification
receipts produced inside the deny-all, no-secret Sandbox. Required commands must match the same
verification allowlist used by Crump Code. A result fails if it changes an acceptance file, leaves
its allowed scope, omits a required path or passing receipt, reports a failed verification,
contains a sensitive-token pattern, exceeds its patch/duration/attempt envelope, or drifts from the
pinned source revision.

Reports contain only case IDs, numeric scores, and categorical failure codes. They never echo
summaries, patches, verification output, repository content, identifiers, or secrets.

## Local run artifact

The JSON artifact contains `suite_id`, `source_revision`, and `runs`. Each run contains only
`case_id`, `mode`, `status`, `base_revision`, `result_summary`, `result_patch`, `verification`,
`duration_ms`, and `attempt_count`. Each verification receipt contains the canonical `command`,
integer `returnCode`, `stdout`, and `stderr` returned by the isolated runner. Unsupported fields,
duplicate cases or receipts, extra commands, malformed diffs, and noncanonical commands fail
closed. The evaluator reads these fields to score the run but never copies candidate content into
its report.

## Future live workflow

1. Keep Crump Code disabled until the separate owner-approved Sandbox/OIDC/destruction smoke test
   and rollback controls pass.
2. Run each case against the exact repository URL and revision with the stated mode and objective.
   Do not use a customer repository or production content.
3. Build one local run artifact with only the evaluator fields. Do not commit the artifact.
4. Run: python scripts/evaluate_crump_code_benchmark.py path/to/runs.json
5. Keep an optional report under output/crump-code-benchmark, which is ignored by Git.
6. Reconcile provider token/cost records separately before setting a unit-cost envelope. Product
   credits are not a substitute for provider cost.
7. Record only a reviewed aggregate decision in internal operating evidence. Do not publish raw run
   content or position Crump Code against Codex/Claude Code until repeatable results justify it.

Visible acceptance cases establish the deterministic foundation, not an adversarial holdout. Add
separately injected Sandbox-only holdouts before making a competitive quality claim.
