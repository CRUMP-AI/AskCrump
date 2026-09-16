# Ask Crump intelligence benchmark

## Status

This is a provider-neutral, offline release gate. It does not call a model, use a
provider credential, spend credits, create an account, read customer content, or
claim that Ask Crump outperforms another product.

The versioned corpus measures behaviors that should remain stable across model
and orchestration changes:

- instruction fidelity;
- grounded factuality and citation discipline;
- durable-memory precision and private-turn boundaries;
- tool selection;
- high-stakes guidance and safe refusal;
- Project continuity; and
- latency, token, and provider-cost envelopes.

Code correctness remains a separate executable gate in
`benchmarks/crump_code`. A release is not intelligence-ready unless both suites
pass. Keeping executable code work separate prevents a text rubric from being
mistaken for code-quality evidence.

## Artifact contract

The evaluator accepts one local JSON artifact. Each case records only the fixed
case ID, completion status, candidate answer, selected route/tools/memories,
declared citations, answer kind, and numeric latency/token/cost metadata. The
candidate answer is inspected locally and is never copied into the report.
The artifact must declare `fixed-synthetic-corpus` and match the canonical
manifest SHA-256 anchored in the evaluator; a self-consistent replacement or
drifted corpus still fails closed.

Every critical case also requires an `independent-review-v1` receipt. The
receipt binds an independent model or human reviewer, the case rubric, and the
SHA-256 of the exact candidate output. The candidate model cannot review its
own output. Missing, failed, stale, malformed, or same-model receipts fail the
release. The evaluator validates the receipt contract; it does not pretend that
word matching can replace semantic judgment. As with latency and cost, the
trusted runner is responsible for the truth of the reviewer identity and
independence claim. A signed attestation is still required before this becomes
a hostile-party verification boundary.

The committed corpus contains fictional, non-customer prompts and context. Do
not place production prompts, responses, filenames, account identifiers, URLs,
or secrets in a benchmark artifact. The evaluator rejects common email, URL,
UUID, absolute-path, filename, credential-assignment, and secret-token shapes,
but a trusted runner remains responsible for enforcing the synthetic-only input
boundary before it writes the artifact.

Run locally:

```text
python scripts/evaluate_intelligence_benchmark.py path/to/local-runs.json
```

Optional reports may be written only below
`output/intelligence-benchmark/`, which is ignored by Git and excluded from the
deployed function bundle.

## Promotion rule

The report passes only when every fixed case passes, its category-balanced score
meets the manifest threshold, and every critical privacy/safety case passes. A
passing report proves only the fixed corpus at the named release and model. It
does not establish general intelligence, competitor parity, or production
quality on unseen work.

Critical natural-language behavior is decided by the bound independent review.
The evaluator also retains a few fixed lexical contract checks—for example, a
required fact or forbidden memory marker—and those remain release-blocking, but
they are not treated as semantic judgment. The other deterministic checks cover
route, tool, memory, citation, privacy-shape, efficiency, and corpus-integrity
regressions. Private holdouts and human review remain mandatory for promotion.

Before a model or orchestration change reaches production:

1. run this suite with the exact release candidate;
2. run the executable Crump Code benchmark;
3. compare category, latency, token, and cost results with the current release;
4. investigate every regression instead of averaging it away; and
5. retain only aggregate, content-free evidence in operating records.

Add private, separately injected holdouts before making any public competitive
claim. Never tune the product directly against the visible corpus alone.
