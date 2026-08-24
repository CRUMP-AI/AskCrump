# Ask Crump 4.4 — Intelligence Architecture

Ask Crump 4.4 moves intelligence out of a single model call and into a small
orchestration layer around the model. The UI remains intentionally quiet.

## Request path

1. Authenticate the account and claim the idempotent chat job.
2. Load account intelligence preferences.
3. Classify the request into a route: conversation, analysis, code, document,
   web, weather, or image.
4. Retrieve a small set of relevant durable memories when memory is enabled.
5. Add a concise task strategy. Deep mode may ask the model for a short
   execution checklist; it never requests or stores chain-of-thought.
6. Let the existing AI service use the normal web/weather/image capabilities.
7. In Deep, Strict, code, or higher-stakes situations, optionally run a
   final-answer reviewer. The reviewer returns `OK` or a corrected final answer.
8. Persist the final assistant message server-side before returning it to the
   device.
9. Learn only explicit durable user statements with conservative filters.
10. Write privacy-safe request telemetry containing operational metadata but no
    raw prompt or response text.

## User controls

The sliders button in the chat header opens a hidden intelligence menu.

- **Auto** — recommended. Crump chooses the orchestration needed.
- **Fast** — skips extra planning/review for lower latency.
- **Deep** — adds a planning pass and stronger verification.
- **Memory** — durable context separate from ordinary chat history.
- **Private this conversation** — prevents new long-term memory learning.
- **Automatic tools** — lets Crump decide when web/weather tools are needed.
- **Answer check** — Off, Auto, or Strict.
- **What Crump remembers** — inspect and delete long-term memories.

The existing Image, Web, and Code capabilities remain available. 4.4 does not
remove the 4.3 visual design.

## Keyboard behavior

- Enter: new line
- Ctrl+Enter / Command+Enter: send
- Send arrow: send

## Memory design

`user_memories` stores only durable memory objects. Automatic learning is
deliberately conservative in 4.4: it looks for explicit phrases such as
“remember that,” “I prefer,” “my goal is,” or “I’m working on.”

Sensitive credential and high-risk personal categories are excluded from
automatic memory capture. Users can turn memory off, make a conversation
private, delete one memory, or clear all memories.

This is the safe foundation for a later semantic-memory layer using embeddings,
decay, contradiction resolution, and confidence updates.

## Observability

`ai_request_traces` stores:

- route and intelligence mode
- whether planner/verifier ran
- number of retrieved memories
- tool flags
- model name
- latency
- success/error state

It intentionally does **not** store raw prompts or assistant answers.

## Model orchestration

The routing boundary now maps free-plan chat, creation-intent routing, answer
review, and proactive check-ins to a hard-allowlisted open-weight model through
Vercel AI Gateway. Paid plans and credit-funded manuscript work retain the
configured Anthropic model. Gateway requests disable prompt training and fail
closed instead of silently falling back to a premium provider. Image generation
continues to use the configured OpenAI image model behind paid-plan limits.

## Evaluation direction

The deterministic tests in `tests/test_intelligence_service.py` protect routing
and memory safety rules. The next evaluation layer should add a versioned corpus
covering:

- instruction following
- factuality and citation quality
- memory precision / recall / contradiction handling
- tool-selection accuracy
- code correctness
- refusal and high-stakes behavior
- latency and cost
- cross-device continuity
- regression comparisons between releases
