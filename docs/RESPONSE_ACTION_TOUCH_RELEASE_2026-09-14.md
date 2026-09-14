# Ask Crump response-action touch release — 2026-09-14

## Decision

Make every action attached to a completed response comfortably visible and operable on phones and
touch devices without changing what any action does. This is a narrow usability correction to the
existing result-to-Project and feedback system, not a new retention feature.

## Evidence

The first complete 24-hour comparable account reached activation and completed four chat jobs with
no failure, but recorded no explicit useful/not-yet feedback, Project-save intent, Project, or file.
That one-account absence is directional only and does not diagnose a failed button.

A separate signed-in production user-eye inspection did identify a deterministic defect. On the
current mobile workspace, the newest response's **Yes** and **Not yet** controls were only 30 pixels
tall with approximately 11.5-pixel text. Copy, Share, Listen, and Report were 34 pixels tall with
10-pixel text and low visual emphasis. The existing saved-work action was 38 pixels tall in the
inspected touch-width shell. All handlers worked, but these targets were materially easier to miss
or mistap than the product's 44-pixel persistent-control standard.

The inspected conversation was a fixed fictional quality-assurance example. No customer content,
account identifier, prompt, response, Project name, file, analytics event, share, feedback, or
provider action was created or changed during the review.

## Change

On phone-width or coarse-pointer devices:

- Copy, Share, Listen, and Report are at least 44 pixels tall with 12-pixel labels and stronger
  restrained contrast;
- Yes, Not yet, Project, referral, and issue-detail actions are at least 44 pixels tall;
- the feedback group uses a readable 0.8rem base size; and
- the action row remains compact, wraps naturally, and preserves the existing charcoal-and-gold
  hierarchy.

Desktop sizing and behavior remain unchanged. Save destination, Project ownership, retry semantics,
feedback meaning, sharing, speech, reporting, analytics, credits, and provider behavior are
unchanged. Service-worker cache `r241` and asset URL `5.9.76-response-touch-1` ensure existing PWAs
receive the corrected stylesheet.

## Verification

The real-browser phone fixture measures both feedback controls at 44 pixels, all four response
actions at 44 pixels with 12-pixel labels, the full-width Project action at 44 pixels, and zero
horizontal overflow. It also repeats stalled-save recovery, successful save, exact Project target,
analytics, and Open Project behavior. The desktop case retains its compact hierarchy.

Local verification passed:

- response Project/touch browser fixture: passed;
- browser-control matrix: **47/47**;
- focused Project/runtime/revenue/button contracts: **83/83**;
- complete backend suite: **1,063/1,063**;
- JavaScript validation: **54/54**; and
- Ruff and diff integrity.

Commit `7ec8fc5` passed GitHub CI `34866386480`, Android store-bundle verification
`34866386579`, and iOS source verification `34866386419`. Production deployment
`dpl_8SnBtnTo5aKfAQvGqgzTdkwYohRL` reached Ready on all six aliases. The canonical stylesheet is
byte-for-byte identical to the committed 82,294-byte file at SHA-256
`8dd5ea34c049e4bbd8ea92f9373eb415a605c413cc97800e41615c5cc682a2f7`; both the live app and
service worker reference `5.9.76-response-touch-1`, and the live worker identifies cache `r241`.

A signed-in production reload exposed that exact stylesheet and rendered the existing response
actions with their accessible names and enabled states; the browser console/log view was empty. The
initial exact-deployment window contained 23 HTTP 200 responses, no grouped runtime error, and no
warning, error, or fatal log. The production browser's 727-pixel desktop-pointer panel correctly
retained compact desktop sizing; the deterministic 390-pixel/coarse-pointer fixture supplies the
phone measurement without changing a real account or publishing test-only fixture routes.

## Outcome gate

The production asset, PWA delivery, signed-in rendering, and phone measurement gates are complete.
Observe real feedback and Project-save intent across the remaining consented cohort. Do not claim
improved activation, durable value, or retention from control delivery alone.
