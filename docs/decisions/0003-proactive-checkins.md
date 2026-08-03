# ADR 0003: Server-scheduled, opt-in proactive check-ins

**Status:** Accepted
**Date:** 2026-07-30

## Context

A browser timer cannot reliably initiate a message after the app is closed and can duplicate work across devices. Proactive communication also requires explicit user control to avoid becoming intrusive.

## Decision

Check-ins are evaluated by an authenticated server schedule. Preferences are stored per account and include enabled state, frequency, quiet hours, timezone, notification permission, and allowed categories.

A check-in is skipped when there is no meaningful conversational reason, during quiet hours, or while a previous check-in remains unanswered. Ignored check-ins increase the next delay. Generated messages are written to the relevant conversation before push delivery.

## Consequences

- Every device observes the same proactive message history.
- Delivery can occur while the app is closed.
- Notification permission is optional and independent from core chat functionality.
- Scheduler monitoring and abuse-volume controls are operational requirements.
