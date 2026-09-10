# Precision Edit lazy-load and control audit release — 2026-09-10

## Decision

Keep every shipped control behind a deterministic owner and keep Precision Edit available from its
existing **Edit area** actions, while removing the full editor from ordinary authenticated startup.

This is a responsiveness and regression-prevention release. It does not claim that every external
provider, permission, purchase, download, destructive confirmation, or signed physical-device
outcome was exercised in production.

## Released behavior

The authenticated workspace previously loaded the complete Precision Edit script and stylesheet
before a user chose to edit an image:

- `crump-precision-image-edit.js`: 78,537 raw bytes; and
- `crump-precision-image-edit.css`: 17,650 raw bytes.

Commit `1345449` replaces those 96,187 boot-time bytes with the 3,379-byte
`crump-precision-image-edit-loader.js`. The ordinary plan now avoids **92,808 raw bytes** and loads
19 styles instead of 20. Script count remains 33 because the loader replaces the full editor.

When **Edit area** is chosen, the control now:

1. displays an explicit opening state and becomes temporarily unavailable;
2. loads the editor script and stylesheet together and only once;
3. opens the existing pixel-selection studio after both assets are ready;
4. restores the control after success or failure; and
5. removes only incomplete lazy assets so a later attempt can recover without losing the original.

The web, PWA, legacy runtime manifests, and native web plan share the same boundary. The service
worker pre-caches the small loader, not the unused editor.

## Control proof

The source inventory still requires every rendered and programmatic button to declare its behavior
type and have a bounded direct or explicitly reviewed delegated owner. The complete real-browser
matrix passed **42/42** flows, covering account entry, chats, composer state, Projects, project/file
handoffs, Create, Image Studio, Precision Edit, Video, Library, Settings, Intelligence, plans and
credits, referral recovery, lifecycle prompts, public guides, service-worker return, and focus and
containment behavior.

The new 42nd verifier proves all of the lazy editor states in an isolated real browser:

| Case | Full editor JS | Full editor CSS | Result |
| --- | ---: | ---: | --- |
| Startup | 0 requests | 0 requests | editor absent; Edit area remains actionable |
| First explicit open | 1 request | 1 request | one shared load, ready, busy state cleared |
| Repeated open | still 1 | still 1 | no duplicate assets |
| Temporary stylesheet failure | 1 request | 2 requests | first attempt releases the button; retry succeeds |

Sensitive outcomes were stopped at safe deterministic boundaries: no purchase, generation, credit
charge, upload, destructive confirmation, sign-out, permission grant, or external message was
performed for this audit.

## Validation

- complete Python suite: **998/998 passed** with repository-pinned FastAPI 0.116.1;
- JavaScript inventory and integration contract: **51 files passed**;
- real-browser control matrix: **42/42 passed**;
- production preflight, native web bundle, and client-credential boundary: passed;
- Python compilation, Ruff, and diff integrity: passed;
- GitHub CI `34524784618`: passed;
- Android store-bundle verification `34524784562`: passed; and
- iOS source verification `34524784402`: passed.

## Production acceptance

Production deployment `dpl_5EG2rm1YxGXR9tfNXHLf5ioTq9XA` reached `READY` on all six expected
aliases. The committed app shell, workspace runtime, Precision Edit loader, image composer, and
service worker matched the canonical production bytes exactly.

A signed-in canonical reload activated cache revision `r230`, remained stable after the update,
and showed only the 3,379-byte Precision Edit loader: the 78,537-byte editor script, 17,650-byte
stylesheet, and editor modal were absent. Safe live clicks moved through Projects, Create, Video,
Library, You, and back to Ask, with the active destination changing on every click. The exact
deployment had no grouped runtime error, HTTP 5xx log, or warning/error/fatal log in the release
window.

## Remaining boundary

This proves deterministic control ownership, browser behavior, deployment parity, and reduced
startup work. It does not prove field-performance lift, conversion lift, provider quality, or every
signed-device/external dependency outcome. Investigate another control only from a reproducible
user report or a failing regression gate; preserve paid and irreversible action-time boundaries.
