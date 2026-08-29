# Addressable Project workspaces release evidence

Date: 2026-08-29

## Outcome

Selecting a named Project now opens that Project's dedicated workspace through a real,
addressable app link. The selected workspace survives refresh, browser Back returns to the
Projects index, and an unavailable Project produces a visible fallback instead of an inert row.

## Delivered boundary

- Each Project row is an anchor to `/app?project=<owned-project-id>` with an instant in-place
  navigation path for ordinary clicks and native browser fallback for modified or restored links.
- Route restoration resolves the requested identifier only against the signed-in account's
  already-authorized Project list before revealing the workspace.
- Project URLs are rebuilt from the app path and Project identifier only. Signup, campaign,
  verification, and arbitrary query parameters are not copied into the durable link.
- Browser history and the visible Back to Projects action keep the Project index and dedicated
  workspace as distinct navigation states.
- Browser/PWA/native delivery moved to `5.9.76-project-routes-4`; the service-worker cache moved
  to `ask-crump-new-body-v1-r127`.

## Verification

- Behavior commit: `f98008d` (`Make project workspaces addressable`).
- Production deployment: `dpl_Anv4zcbudezZeMSg9sN9gp3wV7ok`, `READY` with no alias error on
  all six production aliases.
- All 479 Python regression tests passed. The focused Projects/navigation/PWA/mobile suite and
  validation of all 45 JavaScript files also passed.
- Production build preflight and generated native web bundle passed; store metadata source checks
  passed. Native submission still has the existing external gates: missing local iOS project,
  RevenueCat public keys, and Android `google-services.json`.
- A credential-free real-runtime browser fixture proved ordinary Project selection, a clean
  Project-only URL, refresh restoration, Back navigation, a 390-by-844 workspace, and zero
  JavaScript errors. A deliberately supplied signup/source/verification query was removed from
  the resulting Project URL.
- The signed-in production app exposed real Project anchors, opened an owner Project as a named
  dedicated workspace, restored it after refresh, returned to the eight-Project index through
  Back, and reported zero browser errors. No Project, file, conversation, or account data changed.
- The exact public Project runtime, runtime loader, and service worker contained the shipped link,
  route-restoration, canonicalization, asset-version, and cache-revision markers.
- The release deployment's inspected window contained 124 HTTP 200 responses, no 4xx or 5xx
  response, no warning/error/fatal log, and no runtime error cluster.

## Safety and data handling

No synthetic account, Project, event, conversation, artifact, payment, or checkout was created.
Production verification used read-only navigation against existing owner data. The Project route
contains only the opaque Project identifier; authorization remains enforced by the existing
account-scoped Project APIs.

## Remaining outcome boundary

Delivery and production behavior are verified. The next outcome check is the owner's physical
iPhone/PWA confirmation after the updated service worker activates, followed by legitimate
external Project open, durable-value, and return events when such traffic exists.
