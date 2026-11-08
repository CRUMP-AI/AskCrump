# Ask Crump connected operator UI contract

Status: local review packet for Muse and Codex; source and production release locks remain false.

This is the shared product contract for the Muse-owned visual direction and the
Codex-owned connected control plane. It turns connected mail, calendars,
approvals, schedules, receipts, and bounded multi-step work into one truthful
Ask Crump experience without presenting an unreleased capability as live.

## Product promise

The interface uses one simple loop:

1. Ask in the normal conversation.
2. Review one exact external change when required.
3. Follow durable progress, results, and effect evidence.

Provider content is untrusted data. It may be displayed only as text inside the
bounded result viewer or exact approval preview. It never becomes an
instruction, an approval, or a capability grant.

Every calendar write preview includes an `Attendee effect` row derived only
from the bound provider, action, and attendee payload. It names invitations,
event updates, or cancellation notices before approval, including the case
where removing all attendees can notify the people removed.

## Information architecture

Connections remains a hidden Settings destination until authenticated runtime
readiness reports the exact provider/capability manifest. Once ready, it has:

- a restrained premium overview explaining Ask → Review → Proof;
- Accounts for Google and Microsoft mail/calendar with separate read and
  management grants;
- Reviews for exact, expiring, one-use external-write approvals;
- Tasks for content-free progress across the eight-step durable loop;
- Schedules for pause/resume/cancel controls;
- Activity for content-free action receipts; and
- an explicit result viewer that loads untrusted mail/calendar content only
  after a user click.

Conversation cards provide the shortest truthful next action:

| State | Copy/behavior | Destination |
| --- | --- | --- |
| `needs_connection` | Account permission is required | Accounts |
| `pending_approval` | Nothing was sent or changed | Reviews |
| `schedule_created` | Schedule exists and can be controlled | Schedules |
| `clarification` | The request will not continue itself | Composer |
| task stop/terminal states | Show the exact stop meaning | Tasks |
| completed read | Result opens only on an explicit click | Result viewer |

Cards are hidden and inert whenever readiness is false, unavailable, stale, or
owner authentication changes. Returning to ready may reveal only the current
owner's already-rendered content-free controls.

## Durable task states

The UI accepts only these states:

- `active`: work is proceeding inside granted capability;
- `waiting_approval`: one exact action is waiting and nothing continues;
- `clarification`: terminal for that loop; a reply starts safely revised work;
- `completed`: all planned steps finished;
- `failed`: stopped after failure;
- `cancelled`: user cancellation won;
- `expired`: the bounded lifetime ended;
- `effect_unknown`: an external effect may have occurred and is never blindly
  repeated; and
- `limit_reached`: stopped at the eight-step safety limit.

The public task surface is deliberately content-free. It shows steps used,
state, update time, and safe controls. When the authenticated in-memory chat
store already contains the exact `chatId`, the UI may show that local title via
`textContent` only after strict length/control-character checks; otherwise it
uses “Connected task.” The task API itself never returns a title. It never returns the
instruction, provider payload, customer content, turn claim, session binding,
or model observation.

## Expected authenticated API contract

Every request uses the current authenticated account ID in
`X-Ask-Crump-Expected-Owner`, same-origin credentials, no-store, redirect
refusal, a bounded response, and an owner-generation abort signal.

### List tasks

`GET /api/connected-apps/tasks`

```json
{
  "success": true,
  "tasks": [{
    "loopId": "uuid",
    "chatId": "uuid",
    "turnId": "uuid",
    "status": "active",
    "currentStep": 2,
    "maxSteps": 8,
    "taskStateRevision": 4,
    "pendingApprovalId": null,
    "lastResultReferenceId": "uuid-or-null",
    "expiresAt": "RFC3339 timestamp",
    "updatedAt": "RFC3339 timestamp"
  }]
}
```

No extra or missing fields are accepted.

### Cancel task

`POST /api/connected-apps/tasks/{loopId}/cancel`

```json
{
  "taskStateRevision": 4,
  "confirmed": true
}
```

The server resolves all secret/session/turn authority from the authenticated
owner-bound private record. The browser never receives or sends a claim token.
Cancellation is available only for `active` and `waiting_approval`. A revision
race fails closed and asks the user to refresh.

## Accessibility and responsive behavior

- All interactive targets are at least 44 CSS pixels.
- The 1440 × 900 layout keeps provider grants side by side and the operator
  flow compact.
- At 390 × 844, providers and approvals become one column, the section rail is
  horizontally scrollable, task controls stack, and safe-area padding is kept.
- Every dialog supports Escape, explicit close, initial focus, and opener focus
  restoration.
- Section jumps move keyboard focus as well as scroll position.
- Owner switch removes private results and approvals, aborts in-flight work,
  hides connected controls, and resets counts.
- Reduced-motion preferences remove smooth transitions.

## Truth and release boundary

The UI does not claim attachment handling, general browser control, voice-driven
connected actions, automatic background writes, or live provider availability.
Before OAuth begins, it discloses that limited connected mail/calendar excerpts
needed for a request may be processed through the configured AI gateway and
selected model provider. Connected-content model calls require
zero-data-retention and no-training routing and fail closed when no eligible
provider is available; the UI also preserves the separate security,
abuse-prevention, and legally required processing boundary.
The source remains local, uncommitted, unpushed, undeployed, and hidden behind
false release locks until provider registrations, production secrets, exact
schema application, authenticated provider smoke, device/PWA tests, and a
deliberate release decision all pass.
