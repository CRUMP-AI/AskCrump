# Ask Crump intelligence quality benchmark

This fixed v1 corpus is synthetic, content-safe, provider-neutral, and suitable for deterministic
release checks. It covers instruction following, evidence-grounded current research, citation
integrity, bounded memory use, tool choice, artifact intent, safety refusal, and recovery.

The committed passing fixture proves the evaluator contract; it is not evidence that a production
model passes the suite. Real candidate responses belong in local ignored output and must never be
copied from customer conversations.

Validate the deterministic evaluator contract:

```text
npm run test:intelligence-contract
```

CI runs this same offline command as `Validate offline intelligence evaluator contract`. It has no
network, credential, model, or paid-provider dependency. The checked-in passing fixture proves the
evaluator and manifest remain compatible; it does not evaluate a production model or establish
production intelligence quality.

Apply the actual release gate to a complete, separately produced synthetic candidate-results file:

```text
python scripts/evaluate_intelligence_benchmark.py path/to/local-results.json \
  --report output/crump-code-benchmark/intelligence-quality/report.json
```

That candidate-results command exits nonzero below the manifest's release gate. Keep candidate
responses local and use `--report` only for ignored diagnostic output.

Reports contain only suite metadata, aggregate scores, case IDs, categories, and categorical
failure codes. Prompts, evidence, memories, responses, and assertion values are never echoed.
Responses cite the ordered evidence list with production-style numeric markers: `[1]` is the first
evidence entry, `[2]` is the second, and so on. Internal evidence IDs remain stable manifest keys
for assertion authoring but are never accepted as response citation syntax.
This validates claim-to-evidence integrity against the benchmark's supplied evidence bundle. It
does not claim that citations are public, clickable, or independently verifiable by an end user.

The optional AI Gateway semantic review is documented in
`docs/INTELLIGENCE_EVALUATION_MVP.md`. It is disabled by default, never participates in ordinary
tests, has no default model, and requires explicit spend and synthetic-content acknowledgements.
