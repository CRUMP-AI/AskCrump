# Intelligence benchmark foundation — 2026-09-16

## Outcome

Ask Crump now has a provider-neutral, offline intelligence release contract at
`benchmarks/intelligence/manifest.v1.json`. It covers instruction fidelity, grounded answers and
source conflict, relevant and private memory behavior, tool choice, urgent guidance, safe refusal,
untrusted-source handling, and Project continuity. Executable coding work remains a separate
required gate in `benchmarks/crump_code`.

This candidate does not call a model, use a provider credential, read customer content, create an
account, write a database row, spend credits, or claim competitor parity. The corpus is fixed,
fictional, and synthetic.

## Fail-closed release contract

The evaluator:

- accepts only the canonical committed manifest, anchored by SHA-256
  `ac9517030de194870280994a3e0ba09d4de7c99d34c634dddcb45e67bf70f73e`;
- rejects a modified corpus even when the artifact recomputes a matching self-consistent hash;
- requires every case to pass instead of averaging a regression into the threshold;
- checks exact route, tool, memory, answer-kind, and citation receipts;
- binds required source claims to the sentence carrying the matching citation;
- enforces per-case latency, input-token, output-token, and provider-cost ceilings;
- rejects common credential, token, email, URL, identifier, sensitive-filename, and absolute-path
  shapes after Unicode normalization, without copying candidate answers into its report; and
- writes optional reports only below the ignored `output/intelligence-benchmark/` boundary.

Every critical case additionally requires an `independent-review-v1` receipt bound to the SHA-256
of the exact candidate output and the case's exact review rubric. Missing, stale, malformed,
failed, wrong-rubric, non-independent, or same-model receipts fail. Human review is represented
without a fictitious model identity. The evaluator verifies this contract but deliberately does
not claim that deterministic word matching can understand arbitrary language.

The artifact remains a trusted-runner boundary. The receipt identity is not yet cryptographically
signed, so a signed attestation or equivalent protected runner is still required before treating it
as a hostile-party verification boundary. Private holdouts and human review remain promotion gates.

## Adversarial review

Independent review rejected three earlier drafts. The final design incorporates the findings:

- canonical corpus identity is anchored outside the supplied artifact;
- Unicode format characters and additional email, URL, credential, token, filename, identifier,
  and path shapes fail closed;
- critical natural-language judgment moved from polarity-sensitive regexes to an output-bound
  independent review receipt;
- every critical case has a registered non-`none` rubric and noncritical cases cannot request a
  critical receipt;
- reviewer model identity must differ from the candidate model, while human reviewers use a null
  model identity; and
- documentation distinguishes lexical fact constraints, independent semantic judgment, and the
  remaining trusted-runner/signature limitation.

The bounded final independent review accepted the contract with no remaining defect.

## Validation

- Focused intelligence benchmark tests: **71/71 passed**.
- Complete Python suite: **1,206/1,206 passed**.
- JavaScript integration contract: **54 files passed**.
- Production build preflight passed.
- Native web bundle built successfully.
- Client credential boundary passed.
- Ruff and Git diff whitespace checks passed.

## Release state

This is a local source candidate only. It does not alter production routing, model selection,
pricing, entitlements, marketing, or public claims. A future trusted runner must generate real
candidate and independent-review receipts for the exact release/model pair before this gate can
authorize a production intelligence change.
