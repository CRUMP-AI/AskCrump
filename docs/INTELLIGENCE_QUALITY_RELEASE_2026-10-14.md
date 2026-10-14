# Intelligence quality release — October 14, 2026

## Outcome

This release adds a deterministic intelligence-evaluation contract and hardens
Ask Crump's evidence-backed research path. It does not claim that a checked-in
fixture proves live-model quality. A real synthetic candidate run must be
generated and scored before the benchmark can support a model-quality release
decision.

## Product behavior

- Deliberate Web selection is preserved across retries with the allowlisted
  `requestedTool: web` marker.
- Automatic web and weather lookup obeys the user's durable Automatic tools
  preference. Browser-supplied legacy flags cannot override server policy.
- Research and weather fail closed when current evidence is unavailable; the
  existing chat error path refunds reserved usage.
- Search queries are minimized and bounded before leaving Ask Crump.
- Primary generation and the answer reviewer receive the same bounded set of
  complete evidence records.
- Source URLs accept only sanitized HTTP(S) destinations without credentials;
  source titles cannot inject markup or a second destination.
- Model-authored source tails and invalid citation markers are discarded. Ask
  Crump rebuilds the final Sources list from request-scoped evidence.
- When claim-level review is disabled, unavailable, or safely skipped for a
  long answer, the response states that limitation instead of implying that
  every claim was independently checked.
- Long drafts are never replaced from a truncated reviewer view.

## Evaluation contract

The versioned synthetic suite covers instruction following, grounded current
research, citation integrity, memory boundaries, tool choice, artifact intent,
safety/refusal, and recovery. The evaluator rejects malformed results,
unexpected cases, unsafe metadata, secret-like content, invalid citations,
unapproved tools, and incomplete required categories.

`npm run test:intelligence-contract` validates only the evaluator, manifest,
and checked-in passing fixture. The actual offline release decision requires a
fresh synthetic candidate-results file:

```text
python scripts/evaluate_intelligence_benchmark.py path/to/local-results.json
```

The optional AI Gateway evaluation runner has no default model and requires
three explicit opt-ins, including acknowledgement of spend. No live evaluation
was run for this release.

## Verification evidence

- Complete Python test suite: passed.
- Ruff and Python compilation: passed.
- JavaScript integration contract: 64 files passed.
- Browser control matrix: 56/56 passed.
- Accessibility matrix: 33/33 passed across phone, tablet, and desktop.
- UI visual regression: 54/54 passed across light and dark themes.
- Deterministic evaluator contract: 8/8 cases and 100/100 fixture score.
- Production build, client-secret boundary, store metadata source checks, and
  native privacy source verification: passed.
- Git whitespace validation: passed.

## Boundaries

This release changes no pricing, database schema, credentials, or model-routing
catalog. It makes no live-model quality claim and sends no customer prompts,
responses, filenames, evidence, or URLs to the benchmark reports.

## Next quality gate

Generate fresh synthetic candidate outputs through the current application
path, score them with the versioned evaluator, inspect category failures, and
only then compare or change production model routing. A live Gateway evaluator
run requires explicit action-time spend approval.
