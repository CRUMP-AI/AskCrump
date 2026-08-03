# ADR 0002: Complete-message delivery with explicit presence states

**Status:** Accepted
**Date:** 2026-07-30

## Context

Token streaming is common in AI products, but Ask Crump uses a messaging metaphor. A complete reply should arrive as one message while the interface still communicates that the request was delivered and is being processed.

## Decision

The client presents four observable states:

1. `Sending` while the request is leaving the device.
2. `Delivered` after the conversation is stored.
3. `Seen` after the server accepts the AI job.
4. An inline activity indicator until the complete response is returned.

Retries use an idempotent message identifier. The server returns a cached completed response or an in-progress status rather than creating a second job.

## Consequences

- The interface preserves a text-message rhythm without simulated token output.
- Users receive honest feedback during provider latency.
- Message identifiers become part of the public client/server contract.
