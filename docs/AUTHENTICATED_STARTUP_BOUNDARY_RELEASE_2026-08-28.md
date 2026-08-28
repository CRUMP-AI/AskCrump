# Authenticated startup boundary release evidence — 2026-08-28

## Outcome

Ask Crump 5.9.50 no longer starts protected workspace requests on a signed-out page. Projects and
Video, Crump Code, Library, and the credits badge construct their interface without private data,
then hydrate only after the server-confirmed account reaches the workspace.

This removes routine 401 responses from the activation boundary without weakening authentication,
returning private data to anonymous clients, or delaying protected data after successful sign-in.

## Production defect

A fresh signed-out production browser on 5.9.49 made these five requests before authentication:

- `/api/billing/credits/status`
- `/api/projects`
- `/api/features` twice
- `/api/library/books`

All correctly returned 401. The failures did not cause the reported login regression, but they
created unnecessary server work, browser-console noise, and misleading authentication telemetry on
every signed-out visit.

## Released correction

- The auth controller dispatches `crump:authenticated-ready` after account-scoped storage and
  authenticated application initialization.
- The Projects/Video runtime hydrates Projects and feature status from that boundary, with a
  one-start guard.
- Crump Code constructs its hidden shell before authentication but checks availability only after
  confirmation.
- Library installs its interface without requesting books, then hydrates the shelf after
  confirmation.
- The credits surface binds its actions immediately but requests balance only after confirmation.
- Every surface also checks `window.currentUser`, covering a script that finishes loading after the
  auth event already occurred.

## Browser evidence

The complete local application shell was executed twice with all real client modules and
credential-free API interception.

Signed-out scenario:

- API calls: one `/api/auth/check-session`
- protected API calls: zero
- auth screen: visible
- workspace: hidden
- script errors: zero

Server-confirmed scenario:

- workspace: visible
- authenticated account state: present
- protected hydration observed after confirmation: sync pull/push, presence, analytics, Projects,
  feature status for Product and Code, intelligence preferences, Library books/deleted books, and
  credits
- script errors: zero

## Verification

- 362 Python tests passed.
- Ruff passed across `backend` and `tests`.
- Backend byte-compilation passed.
- All 44 public JavaScript files passed syntax and integration-contract validation.
- Production preflight and the generated native web bundle passed.
- Android source verification passed for API 36, version 5.9.50, build 50950.
- Store metadata and mobile signing source controls passed.
- GitHub CI run `33156887623`, Android run `33156887563`, and iOS run `33156887586`
  completed successfully.

Expected owner-account store gates remain unchanged: Android Play Billing requires the RevenueCat
public SDK key and `google-services.json`; signed-archive, physical-device, billing, screenshots,
privacy declarations, reviewer access, and store-console validation remain pending.

## Production proof

- Commit: `ea74f833dab99eccee3462e3fc90f38061f05307`
- Deployment: `dpl_71UWy9RoEESp5WBGKVoT2XMvZAUE`
- Production aliases assigned without error.
- A fresh production browser received HTTP 200, versioned 5.9.50 auth assets, and active service
  worker cache `ask-crump-new-body-v1-r84`.
- Its only API call was `/api/auth/check-session`, which returned 200.
- Protected requests: zero.
- Failed responses: zero.
- Browser script errors: zero.
- Deployment error/fatal log scan: empty.
- Deployment status breakdown in the inspected window: one 200 and no failing status group.

This verifies delivery and observability cleanup. It does not prove higher signup or activation
conversion; that requires legitimate post-release account behavior.
