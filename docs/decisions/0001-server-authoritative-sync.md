# ADR 0001: Server-authoritative conversation synchronization

**Status:** Accepted
**Date:** 2026-07-30

## Context

A conversation may be edited from multiple browsers or mobile devices. Treating local storage as the primary record causes missing history, duplicate conversations, and account-boundary risk.

## Decision

Supabase Postgres is the authoritative record for conversations. Each conversation carries a stable identifier, revision, update timestamp, and optional deletion timestamp. Client storage is an account-scoped cache used for immediate rendering and offline continuity.

The synchronization RPC compares revisions and timestamps atomically. Deletions are represented by tombstones long enough to propagate to other devices.

## Consequences

- Users see the same history after signing in on another device.
- Offline work can be reconciled instead of silently replacing server data.
- Sync behavior is testable at the database boundary.
- Conflict policy and tombstone retention must remain backward compatible.
