# Architecture

## System overview

Ask Crump is a web-first application with native iOS and Android shells. A single FastAPI application exposes authentication, synchronization, chat, presence, notification, account, and billing endpoints. Static web assets are served from `public/`.

## Backend boundaries

```text
app.py
└── backend/application.py
    ├── HTTP middleware and exception mapping
    ├── backend/routes/auth.py
    ├── backend/routes/account.py
    ├── backend/routes/sync.py
    ├── backend/routes/chat.py
    ├── backend/routes/presence.py
    ├── backend/routes/billing.py
    └── backend/routes/health.py
```

Route modules validate transport input and coordinate services. Business behavior lives in service modules:

- `auth_service.py` — session creation, request authentication, public user projection
- `sync_service.py` — conversation and settings reconciliation
- `ai_service.py` — provider orchestration, search/weather context, image generation
- `checkin_service.py` — proactive-message eligibility and scheduling
- `usage_service.py` — account-tier limits and refunds
- `push_service.py` — APNs and FCM delivery
- `email_service.py` — verification and password recovery email
- `rate_limit.py` — persistent abuse controls

`runtime.py` owns process-scoped clients. Vercel may reuse these objects across warm invocations, reducing repeated client setup without introducing mutable user state.

## Data ownership

Supabase Postgres is authoritative for:

- users and account preferences;
- opaque sessions and device metadata;
- conversations, revisions, and deletion tombstones;
- usage events and rate-limit counters;
- message receipts and idempotent chat jobs;
- proactive check-in preferences and events;
- push tokens and subscription state.

The client stores only account-scoped cached conversations and interface preferences. Cache keys include the authenticated user identifier. A sign-out clears the active account state and disables the installation's push token.

## Authentication

Web authentication uses a random opaque credential stored in an HTTP-only cookie. Native clients receive the same credential in the authenticated response and place it in platform secure storage. Only a SHA-256 hash is persisted in the session table.

Normal activity extends the session expiration. Users can revoke individual devices or all sessions. Password resets revoke active sessions after the password changes.

## Conversation synchronization

Every conversation has:

- a stable UUID;
- an integer revision;
- creation and update timestamps;
- an optional deletion timestamp;
- a JSON message payload.

The `apply_chat_sync` database function compares incoming and stored revisions atomically. A client performs pull, merge, push, then final pull. This prevents a stale device from silently overwriting a newer server revision.

See [ADR 0001](decisions/0001-server-authoritative-sync.md).

## Message processing

The client saves the outgoing message before invoking the AI route. `/api/chat/ack` records delivery and processing acceptance. `/api/chat` claims an idempotent job keyed by account, conversation, and message identifier.

A repeated request receives one of three outcomes:

- the previously completed response;
- an in-progress response with a retry delay;
- a new job claim.

Usage is refunded when the provider request fails before a response is returned.

See [ADR 0002](decisions/0002-message-presence.md).

## Proactive check-ins

An hourly authenticated scheduler evaluates a bounded batch of eligible accounts. Check-ins are disabled by default. Eligibility considers quiet hours, timezone, selected categories, recent activity, unanswered check-ins, and ignored-message cooldown.

The message is written to the conversation before push delivery. Push is optional; synchronized history remains the source of truth.

See [ADR 0003](decisions/0003-proactive-checkins.md).

## Billing

Web subscriptions use Stripe Checkout and the Stripe customer portal. Native applications never open web checkout for digital subscriptions; they use platform billing through RevenueCat.

Webhooks and explicit native reconciliation update the same server-side subscription fields. Client-supplied tier values are not trusted as proof of entitlement.

## Deployment model

Vercel detects `app.py` as the FastAPI entry point and serves `public/` through its static asset layer. The FastAPI application remains a single serverless function. Supabase provides durable persistence and atomic database functions.

Production provider credentials are environment variables. Native signing files, APNs keys, Firebase service-account data, and store credentials are not part of the repository.
