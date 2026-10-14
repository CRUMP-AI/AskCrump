# Intelligence evaluation MVP

## Purpose

This is Ask Crump's first release-grade intelligence quality gate. It turns broad claims such as
"better grounding" or "stronger memory" into repeatable, content-safe checks before provider,
prompt, routing, memory, or tool-policy changes ship.

It does **not** claim parity with OpenAI, Anthropic, or Google. It does not use customer content,
exercise production accounts, create artifacts, call tools, or make network requests in ordinary
test runs.

## Versioned coverage

`benchmarks/intelligence/manifest.v1.json` contains synthetic cases for:

- instruction following and output shape;
- grounded, date-bounded research;
- citation existence, source validity, and claim-level support;
- explicit memory selection without inference;
- current-data tool choice without guessing;
- editable artifact intent;
- privacy-preserving refusal; and
- transparent timeout recovery.

Manifest validation is strict. Unknown fields, unsupported categories, duplicate identifiers,
unsafe token patterns, malformed dates, unallowlisted tools or memories, and citation claims that
do not exist in their cited evidence are rejected before scoring.

Citation syntax matches production Ask Crump: `[1]` points to the first ordered evidence entry,
`[2]` to the second, and so on. The manifest keeps stable internal evidence IDs for authoring the
claim-to-source contract, but symbolic response citations such as `[release-calendar]`, zero,
leading-zero, and out-of-range numeric citations do not satisfy it.

The deterministic citation check is deliberately bounded: it proves that a claim maps to the
correct item in the benchmark's supplied evidence bundle. It does not prove that a public URL is
clickable, that an end user can independently inspect the source, or that an external publisher is
authoritative. Those are separate product and browsing checks.

## Deterministic evaluator contract and release gate

Candidate results use the v1 shape demonstrated by
`benchmarks/intelligence/fixtures/passing_results.v1.json`. Evaluate them with:

```text
npm run test:intelligence-contract
```

That package command runs in the named CI step
`Validate offline intelligence evaluator contract`. It evaluates only the checked-in passing
fixture and uses no credential, network request, model, or paid service. It proves the evaluator,
manifest, and fixture contract remain compatible; it does **not** evaluate a production model or
prove production intelligence quality.

The actual deterministic release gate applies when a complete synthetic candidate-results artifact
from the system under evaluation is supplied:

```text
python scripts/evaluate_intelligence_benchmark.py path/to/local-results.json \
  --report output/crump-code-benchmark/intelligence-quality/report.json
```

That command exits nonzero when the candidate results fall below the manifest thresholds.

The gate requires:

- mean score of at least 90;
- every case to score at least 80;
- every category to meet a 100% case pass rate; and
- perfect scores for grounding, citation integrity, safety/refusal, and recovery.

Forbidden content, leaked credential patterns, unapproved tools or memories, false artifact state,
incorrect refusal/recovery state, and invalid or unsupported citations are hard failures even when
the arithmetic score would otherwise clear the case threshold.
Malformed run fields, response types or lengths, tool lists, artifacts, and metadata are also hard
failures; the quality threshold can never convert an invalid record into a release pass.

The JSON report intentionally excludes prompts, evidence, memories, responses, assertion values,
and secrets. It contains only identifiers, categories, scores, pass/fail state, and categorical
failure codes. The allowed report directory is beneath the repository's already ignored
`output/crump-code-benchmark/` tree.

## Optional live AI Gateway review

The live layer is advisory. The deterministic gate remains the release authority because model
judges are probabilistic. Live review is impossible by accident: there is no default model and the
script requires all three explicit acknowledgements before it reads a credential or reaches the
network.

Choose an evaluation-capable model from the current AI Gateway catalog, understand its current
price, export `AI_GATEWAY_API_KEY` through the repository's secure environment mechanism, and run:

```text
python scripts/run_intelligence_live_evaluation.py path/to/local-results.json \
  --live \
  --model provider/evaluation-model-from-current-catalog \
  --acknowledge-spend \
  --confirm-synthetic-only \
  --report output/crump-code-benchmark/intelligence-quality/live-report.json
```

The live script sends only the fixed synthetic case and its synthetic candidate response to the
AI Gateway `/v1/evaluate` endpoint with zero-data-retention requested. It makes one billable call
per case. It never sends production conversation data. The report retains only numeric/boolean
answers and numeric usage fields; it does not retain model prose.

Do not automate live evaluation in unit tests, pull requests, or routine deployments. A human must
opt in, select an evaluation-capable model returned by the current catalog, and acknowledge spend
for each run. Confirm the request, model, usage, and provider behavior in AI Gateway Logs after an
authorized run.

## Expansion path

1. Add reviewed synthetic cases under a new suite version; never silently mutate past evidence.
2. Add separately held-out cases before using benchmark changes to justify competitive claims.
3. Calibrate release thresholds against repeated runs and real, consented, de-identified failure
   themes without copying customer prompts or outputs into Git.
4. Track latency and provider cost beside quality, but keep those records separate from response
   content.
5. Require an explicit owner decision before this gate can block production deployment.
