# Ask Crump connected operator: product acceptance contract

Status: local implementation target; source release lock remains false.

This contract defines what “fully built like Muse, Dots, and Codex” means for
Ask Crump. A settings screen or an OAuth demo is not completion. The capability
must work through normal conversation, survive process/deployment failures,
remain owner isolated, and tell the truth about every external effect.

## One-product experience

The final product combines the existing Ask Crump conversation, Projects,
Files, document/image/video creation, code workspace, and the local Autonomous
Crump worker with owner-connected mail and calendars. These are one task system:

- one owner and account boundary;
- one task/turn identity and cancellation state;
- one exact capability and approval model;
- one durable action ledger and activity history;
- one pause/resume/cancel surface;
- one content-free operational receipt model; and
- separate encrypted stores for customer payloads and provider credentials.

No connector, provider response, email, event, attachment, webpage, model
output, or remembered text can grant authority.

## Required user journeys

1. Connect Google or Microsoft from Settings with incremental consent.
2. Return from OAuth to the app without exposing code, state, tokens, account
   identity, or connection IDs in browser history.
3. Ask in ordinary language to search/read mail or inspect availability.
4. See untrusted provider content clearly separated from Ask Crump's
   instructions and authority.
5. Ask to draft, send, reply, create, update, or cancel; review an exact bounded
   preview before any provider mutation. Calendar previews explicitly disclose
   invitations, event updates, or cancellation notices that the provider will
   or may send to affected attendees.
6. Approve or deny once. Approval expires and cannot be reused or substituted
   for a sibling action with equivalent OAuth scopes.
7. Ask for recurring work at an explicit fixed elapsed interval in minutes,
   hours, or numbered days. Weekday, named-day, monthly, and wall-clock
   recurrence are rejected rather than approximated. Read-only schedules may
   run within the exact grant; every scheduled external write requires a fresh
   exact approval for that run.
8. Pause, resume, or cancel schedules and long-running work from the same owner
   workspace.
9. Disconnect an account and prove provider credential revocation/cleanup even
   after response loss or process crash.
10. Delete the Ask Crump account and prove all owner-linked payloads, grants,
    schedules, actions, and credentials are erased or placed in a content-free
    cleanup outbox before the owner row disappears.

The initial released connector contract supports one live connection for each
owner/provider/account-kind/resource tuple (for example, Microsoft personal
mail and Microsoft work/school mail may coexist, while two Microsoft personal
mail authorities may not). Every action and schedule names the exact
connection ID; an ambiguous account-kind selection fails closed. A second
connection cannot silently replace the first: a fresh start is refused while a
current start is live, and a provider grant returned by a losing callback is
placed in the durable cleanup outbox. Expired, never-exchanged pending starts
may be retired and replaced without retaining a provider credential.

## Truthful effect outcomes

Every provider operation ends in exactly one public category:

- **completed**: a typed provider receipt and required authoritative readback
  prove the exact effect;
- **not completed**: dispatch is proven not to have occurred; or
- **uncertain**: an effect may have occurred and Ask Crump will reconcile it
  without blindly repeating it.

“Timed out” never means “safe to retry” after a possible external write.

## Inside implementation gates

- exact OAuth state, PKCE, redirect, tenant/account-kind, client, owner,
  connection-incarnation, action-set, and scope-set bindings;
- encrypted refresh-token custody, no persisted access tokens, key rotation,
  cross-host refresh serialization, and provider-side revocation;
- encrypted payload envelopes with keyed commitments, permanent identity-bound
  deletion tombstones, physical expiry of read payloads, cryptographic erasure
  of expired plan envelopes, retention bounds, and crash-safe response-loss
  readback;
- owner-scoped service-role-only database RPCs; private relations are never a
  PostgREST fallback;
- exact action grants, one-use approvals, database fencing tokens, phase-bound
  one-use credentials, cancellation, deadlines, and idempotency;
- bounded provider transports with no redirects, environment proxy, ambient
  cookies, browser fallback, or raw provider URL execution;
- request-scoped AI planning sends only bounded necessary excerpts, pins the
  reviewed model/provider, requires zero-data-retention and no-training
  routing, and refuses model output unless the gateway returns its matching
  routing audit;
- durable fixed-interval scheduler leases, quiet hours, IANA time-zone labels,
  bounded concurrency/backoff, and invalid-authority pause; no claim is made
  that elapsed intervals preserve a wall-clock time across DST;
- content-free logs, metrics, support records, and error bodies; and
- a composition manifest that keeps public status false unless every required
  component is present and freshly attested.

## Outside/provider and release gates

These require user-controlled provider/platform steps and cannot be fabricated
by local tests:

- production Google and Microsoft app registrations and redirect URIs;
- securely supplied client credentials and encryption-key material;
- Google restricted-scope verification/security assessment where applicable;
- Microsoft consent/tenant validation for personal and work/school accounts;
- version-preserving Supabase migration dry run/application and PostgREST cache
  convergence;
- bounded test accounts proving connect, scope expansion/downgrade, refresh,
  revoke, disconnect, and deletion;
- physical browser/PWA/device connect, return, approval, force-close/reopen,
  offline, owner-switch, and notification flows;
- production observability, cleanup drain, rollback-floor, and incident drills;
  and
- one deliberate same-deployment decision that moves the preview, public-entry,
  and durable multi-step source locks together.

Until both inside and outside gates pass, UI and routes remain hidden/inert and
no “live autonomous email/calendar assistant” claim is allowed.
