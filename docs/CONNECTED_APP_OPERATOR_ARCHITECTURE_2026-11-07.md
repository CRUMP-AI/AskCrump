# Connected App Operator Architecture

Status: local design contract; not connected, deployed, or released.

This document defines the boundary for turning Ask Crump into an owner-controlled
operator that can work with mail and calendars. It is intentionally independent
from the browser-control stack. Mail and calendar actions use provider APIs with
delegated user consent; browser automation is never the fallback for a missing
scope or failed provider call.

## Product boundary

Ask Crump may eventually:

- search and read mail the owner explicitly connected;
- prepare drafts and suggested replies;
- send an owner-reviewed message;
- read calendars and calculate availability;
- prepare, create, update, or cancel an owner-reviewed event;
- run a durable fixed-elapsed-interval schedule that invokes only capabilities
  already granted to that exact owner, connection, task, and action class.
  Weekday, monthly, and wall-clock recurrence are not represented and must be
  clarified rather than approximated.

Ask Crump must never:

- accept an access token, refresh token, password, recovery code, or OTP through
  model context;
- treat email, calendar text, an attachment, a webpage, or tool output as
  authorization;
- silently expand OAuth scopes or connect a persistent account;
- replay an external write after a response-loss or timeout when the first write
  might have succeeded;
- use personal `gregory.d.crump@gmail.com` as a business-support fallback;
- claim an action completed without a provider receipt or authoritative readback.

## Trust separation

The model proposes a typed action. A deterministic control plane decides whether
the action is allowed, requires approval, or is denied. Provider credentials stay
behind a broker and are represented everywhere else by an opaque handle. The
provider adapter receives the handle only after owner, task, turn, connection,
exact granted action (not merely a scope-equivalent sibling action), parameters,
resource version, deadline, and approval bindings have all been checked.

Inbound content is always untrusted data. A message that says "send this," "book
this," "ignore prior instructions," or contains tool-shaped text has no greater
authority than any other string.

## Initial action classes

| Action | Default decision | Required evidence |
| --- | --- | --- |
| Search/read mail | Allow only inside an already consented task capability | Exact owner, connection, task, turn, and read scope |
| List events/free-busy | Allow only inside an already consented task capability | Exact owner, connection, task, turn, and read scope |
| Prepare local draft/event | Allow only inside task capability | Content stays local; no provider mutation |
| Create provider draft | Approval required | Reversible external-write approval bound to exact content digest |
| Send/reply | Approval required | External-communication approval bound to recipients and content digest |
| Create/update/cancel event | Approval required | Calendar-write approval bound to attendees, times, time zone, and version |
| Connect account/expand scope/start watch | User takeover | OAuth consent and persistent-permission confirmation outside model context |

Forwarding and archive/move/trash/delete mail are intentionally outside the
initial implementation. They must not be advertised or inferred from a broad
provider scope; adding any of them requires a separately reviewed action kind,
provider contract, exact preview, approval class, and reconciliation proof.

Approvals expire, are one-use, and cannot cross owners, accounts, connections,
tasks, turns, actions, parameter digests, or resource versions.

## Least-privilege provider scope plan

Google scopes are requested incrementally. Every Google plan also requests
`openid` and `email` so the callback can derive the stable OIDC subject used in
the content-free external-account binding. Read-only Gmail access uses
`gmail.readonly`; sending uses `gmail.send`; draft management uses
`gmail.compose`. Ask Crump never requests `https://mail.google.com/`, because it
also permits permanent deletion. Google documents Gmail read/compose/modify as
restricted scopes, so public use requires OAuth verification and may require a
security assessment when restricted-scope data is stored or transmitted.

Calendar availability begins with `calendar.events.freebusy`. Reading owned
events uses `calendar.events.owned.readonly`; writing owned events uses
`calendar.events.owned`. Wider calendar scopes are not the default.

Microsoft access is delegated, never tenant-wide application access for the
consumer product. Start with `Mail.Read`, `Mail.Send`, `Calendars.Read`, and
`Calendars.ReadWrite` only as the corresponding feature is enabled. Microsoft
documents that `Mail.ReadWrite` does not include send authority, which is kept as
a separate permission. Every Microsoft plan also requests `User.Read` for the
least-privileged `/me` identity binding and `offline_access`;
without it the v2 authorization-code flow does not issue the refresh token that
owner-approved background schedules require.

Primary references:

- https://developers.google.com/workspace/gmail/api/auth/scopes
- https://developers.google.com/workspace/calendar/api/auth
- https://learn.microsoft.com/en-us/graph/permissions-reference
- https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc#the-offline_access-scope

## Durable execution protocol

1. Resolve the owner-scoped connection and granted scopes.
2. Normalize the request into a content-free action identity and a separate
   encrypted/untrusted payload reference.
3. Bind an immutable provider resource version or ETag for any update.
4. Run deterministic policy and, when required, obtain one exact approval.
5. Claim one idempotency key in the durable ledger.
6. Atomically consume the phase-specific credential nonce, then execute at most
   once through the provider adapter.
7. On a definite rejection, close the action as failed.
8. On a definite receipt, re-read authoritative state and settle the action.
   For create/send requests that cannot name the new object before execution,
   the provider adapter itself must reconcile authoritatively before it may
   return the proof-capable receipt.
9. On timeout or lost response after a possible effect, mark the action
   ambiguous. Reconcile by provider idempotency key or readback; never blind
   retry.
10. Store a content-free audit receipt and show the user the truthful outcome.

## Release gates

The preview, public-entry, and durable multi-step source locks remain false
until all of these are proven. They move together in one same-deployment
release candidate; a staged single-step public release is not permitted:

- OAuth state/PKCE, callback-origin, account-link, revocation, and scope-downgrade
  tests;
- encrypted credential broker with key rotation and no token exposure in logs,
  database APIs, model context, browser storage, or error bodies;
- owner isolation, stale-version, one-use approval, idempotency, response-loss,
  cancellation, and deletion tests;
- Gmail, Google Calendar, Outlook Mail, and Outlook Calendar provider contract
  suites against bounded test accounts;
- timezone/DST, recurrence, attendee, reply-all, alias, attachment, and draft
  preservation matrices;
- authenticated physical-click flows for connect, disconnect, approve, deny,
  revoke, send, schedule, cancel, and force-close/reopen;
- privacy deletion, support, observability, rollback, and incident runbooks;
- provider verification/consent-screen approval and a deliberate release
  decision.

Until those gates pass, only pure local contracts and fake-provider tests are
allowed. No provider traffic, schema application, credential creation, account
connection, public claim, or production release is implied by this work.
