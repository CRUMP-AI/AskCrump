# Engineering Case Study

## Problem

Ask Crump began as a browser-first assistant with several independent implementations of authentication, conversation storage, and synchronization. That architecture created three user-visible failures:

1. conversation history did not reliably follow the account across devices;
2. sessions did not survive normal app restarts consistently;
3. client-side timers and local storage were being asked to perform work that required server authority.

The product also needed a path to iOS and Android without mixing web checkout with native digital-subscription flows.

## Constraints

- Preserve the existing messaging-oriented product experience.
- Keep JavaScript in the interface where browser and native bridge behavior requires it.
- Move identity, synchronization, usage enforcement, provider access, and proactive messaging to Python.
- Support an incremental database migration without silently duplicating or discarding conversations.
- Avoid introducing a second source of truth during offline operation.

## Architecture decisions

### Server-authoritative identity and history

The browser keeps an account-scoped offline cache, but Supabase is authoritative for sessions, conversations, settings, usage, and subscription state. Opaque session credentials are hashed before storage and can be revoked per device.

See [ADR 0001](decisions/0001-server-authoritative-sync.md).

### Conflict-aware synchronization

Each conversation carries a stable UUID, revision, update timestamp, and deletion tombstone. A database function applies writes atomically and rejects older competing revisions. The client completes a pull, merge, push, and final pull cycle so it converges on server state.

### Idempotent message jobs

Every user message receives a stable message ID. The backend claims a job for that ID before calling the model provider. Retries can return the completed job, wait on an active job, or reclaim an abandoned job without creating duplicate assistant messages.

### Honest conversational presence

The interface maps visible states to real events:

- `Sending` — the request has not yet been stored;
- `Delivered` — the conversation write succeeded;
- `Seen` — the server accepted the AI job;
- retry states — delivery or generation failed.

The activity indicator reports the operation category selected by the server rather than displaying arbitrary progress.

See [ADR 0002](decisions/0002-message-presence.md).

### Proactive messaging as a server feature

Crump Check-ins are opt-in and evaluated on the server. Eligibility considers quiet hours, frequency, unanswered messages, recent engagement, and the originating conversation. A generated message must be grounded in an unfinished task or useful continuation; otherwise the model returns `SKIP`.

See [ADR 0003](decisions/0003-proactive-checkins.md).

### Billing boundary

Stripe is used only for web checkout. Native purchases and restoration are delegated to Apple or Google through RevenueCat. The backend reconciles provider events into one account subscription state.

## Reliability and security controls

- request-size limits and centralized exception mapping;
- database-backed authentication and usage rate limits;
- HTTP-only web cookies and native secure storage;
- account-isolated browser cache keys;
- no-store API responses and restrictive browser security headers;
- row-level security with service-role-only direct database access;
- atomic account deletion;
- push-token ownership transfer and revocation during account changes;
- CI checks for Python compilation, API behavior, static assets, CSS variables, HTML structure, and JavaScript syntax.

## Verification

The automated suite covers authentication authority, route contracts, synchronization conflicts, tombstones, message presence, check-in eligibility, request protections, account deletion, static asset integrity, and browser structure. The repository also includes a manual real-device and store-release test plan because signed-device behavior cannot be proven by unit tests alone.

## Remaining production work

The repository does not claim that unsigned source code is a shipped mobile product. Production release still requires owner-controlled credentials, a staging migration, provider webhooks, signed native builds, TestFlight and Play internal testing, privacy declarations, and operational monitoring.
