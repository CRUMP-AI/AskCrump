# Project return measurement release

Date: 2026-08-29

Status: verified in production; legitimate Project-return outcome pending

## Decision

Project conversation returns must be observable before Ask Crump can determine whether Projects
improve continuing-work retention. This release corrects a deterministic measurement failure
without adding a new event, database object, customer-content field, or production test event.

## Evidence before the correction

The Project workspace client already sent the existing content-free
`RecentWorkResumed` milestone with:

- event key `recent-work-resumed`;
- source `project`;
- no Project ID, chat ID, title, prompt, response, filename, URL, or arbitrary metadata.

The authenticated intake allowed only source `launchpad`, so the legitimate Project value was
rejected with HTTP 422 before authentication or recording. The executable client contract required
`source: 'project'`, while the server contract required
`RECENT_WORK_SOURCES == frozenset({"launchpad"})`.

A read-only production aggregate before release contained two `RecentWorkResumed` rows with
source `launchpad` and zero with source `project`. That baseline is consistent with the
validation mismatch, but it is not a retention-rate claim.

## Correction

- The server accepts exactly `launchpad` and `project` for `RecentWorkResumed`.
- The historical launchpad idempotency key remains
  `recent-work-resumed:<server UTC date>`.
- Project returns use
  `recent-work-resumed:project:<server UTC date>`.
- Repeated clicks therefore record at most one milestone per account, approved source, production
  environment, and UTC day.
- Existing aggregate growth reports count accounts reaching `RecentWorkResumed`; no schema or
  report change is required.

The intake remains authenticated and rate-limited. The service-role-only event recorder,
private table, ownership-linked deletion, and fail-open product behavior are unchanged.

## Verification

- The focused analytics and Project-continuity suite passed 53 tests.
- The complete suite passed 468 tests.
- All 45 JavaScript files passed the integration validator.
- Explicit Python compilation, production preflight, native web-bundle generation, and store
  metadata checks passed.
- A read-only Supabase query confirmed the pre-release aggregate baseline without exposing account
  or content data.
- A credential-free production probe using the approved `project` source returned HTTP 401
  `Authentication required`. This proves the event passed source/key validation and stopped at
  authentication; it created no event.
- A matched probe using source `invented` returned HTTP 422
  `Invalid recent work event`.
- Canonical production health returned HTTP 200 for Ask Crump 5.9.76.
- The exact production deployment reported no runtime error cluster, 5xx response, or
  warning/error/fatal log. Its observed 401 and 422 were the two intentional non-writing probes.

## Release

- Code commit: `3fa6f34d0b8f9332513277d920d2c1eb5b90c3ed`
- Production deployment: `dpl_GeCzd3eiXby5DUf1qruiGRfHwZFB`
- Build duration: approximately 41.5 seconds
- Alias error: none

## Outcome boundary

Do not create a synthetic Project resume or interpret the internal owner baseline as retention.
Observe the first legitimate `RecentWorkResumed` event with source `project`, reconcile it to an
activated account that already kept work in that Project, and then evaluate later return behavior
with an explicit cohort window and denominator.

