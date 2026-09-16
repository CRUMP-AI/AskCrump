# Provider-cost observability source audit

Status: source review complete; provider-cost receipt remains **HOLD**

Reviewed against production source base
`7833d89e2e5ee419fd27757f82c4fff92beed295`. No provider call, database write,
deployment, campaign action, spend, or production mutation was performed.

## Decision

The current application cannot produce the complete, privacy-safe provider-cost receipt required
to authorize even the bounded paid learning cell. Provider cost remains **unavailable**, never
zero. Runtime health, Vercel infrastructure cost, free credits, a catalog price, or a successful
chat cannot substitute for per-attempt provider evidence.

## Verified source gaps

- `_gateway_completion` returns response text, a reported model, the literal provider label
  `vercel-ai-gateway`, opaque usage, and finish reason. It discards the generation identifier,
  actual routed provider, cost metadata, response headers, and per-call latency.
- `gateway_text` then reduces helper calls to text. Creation-intent classification, answer
  verification, proactive check-ins, and the latent planner lose their own usage, cost, provider,
  latency, generation identifier, and failure evidence. Helper errors may be intentionally absorbed
  by the caller, so a successful overall chat does not prove every outbound call succeeded.
- Primary raw usage survives only when the whole result is retained in `chat_jobs.response_data`
  for a request carrying `message_id`. That row still lacks actual provider, cost, purpose,
  generation identifier, and call-level latency.
- `ai_request_traces` is a top-level route trace, not one row per Gateway call, and has no provider,
  purpose, token, cost, or generation fields.
- The creation classifier uses `creation-router`; the accepted receipt vocabulary requires
  `creation-intent`.
- Reporting tags are currently top-level request fields. Current Vercel guidance places Gateway
  tags under `providerOptions.gateway.tags`.
- API-key authentication precedes OIDC. Until the key or Gateway project is proven exclusive to
  Ask Crump, a project export cannot honestly claim Ask-Crump-only allocation.

## Smallest safe closure after the protected observation

1. First prove whether the active API key or Gateway project is exclusive to Ask Crump. Keep the
   existing authentication lane unchanged during this proof.
2. Correct tag placement and use a fixed allowlist such as `app:ask-crump`, environment,
   `tier:free`, and the exact feature purpose. Rename `creation-router` to `creation-intent`.
3. Retain the opaque generation identifier when returned.
4. If exclusive project/key attribution plus a fully loaded Gateway Logs export can prove every
   attempt, reconcile that export to immutable deployment metadata and Custom Reporting. A
   completed-generation lookup alone cannot cover failed calls.
5. Otherwise emit exactly one content-free observation inside `_gateway_completion` for every
   outbound POST outcome. Allow only timestamp, purpose, environment, project/deployment/SHA,
   requested and actual provider/model, authentication lane (never its credential), outcome/error
   class, normalized token counts, separately named market cost and Gateway debit/surcharge,
   call-level latency, and optional opaque generation identifier.
6. Never record user identity, prompt, answer, message, filename, URL, request or response body,
   headers, error body, or credential.

`market_cost` should mean gross provider list-price cost. Gateway debit, fees, or surcharge must
remain separate rather than being silently combined.

## Required implementation proof

- One observation each for success, 402, 429, other 4xx, 5xx, timeout, network error, invalid JSON,
  and empty response; none for a rejection before an outbound POST.
- Primary chat, creation intent, verifier, and check-in calls retain their own content-free facts,
  including when a helper failure is absorbed by its caller. The planner is either covered or
  proven unreachable for Free traffic.
- Nested tags, exact purpose vocabulary, cached-token normalization, actual-provider extraction,
  authentication lane, deployment/SHA, cost-field meaning, and one-row-per-attempt behavior have
  executable coverage.
- The aggregate uses a declared UTC half-open window, deduplicates safely, defines percentile basis
  and sample count, reconciles row sums to the authoritative export, and fails closed on missing
  metadata.
- The receipt verifier recursively rejects prohibited or extra privacy fields, requires immutable
  non-duplicate evidence references, ties required tags to exported rows, and calculates “other
  provider errors” without double-counting classified 429/402 failures.

## Post-isolation decision gate

Do not implement or deploy this boundary before `2026-09-17T17:28:00Z`. After that time, open a
new release-bound observation window only after the exact deployment is READY. The window must stay
inside one deployment, contain at least one natural completion, wait for Gateway log ingestion,
and close before a receipt is evaluated. No synthetic production request may be created to fill it.

Current reference behavior:

- <https://vercel.com/docs/ai-gateway/observability-and-spend/logs>
- <https://vercel.com/docs/ai-gateway/observability-and-spend/custom-reporting>
- <https://vercel.com/docs/ai-gateway/sdks-and-apis/rest-api>

