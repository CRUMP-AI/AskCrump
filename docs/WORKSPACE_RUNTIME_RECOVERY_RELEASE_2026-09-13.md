# Workspace runtime recovery release — 2026-09-13

## Decision

Do not let the authenticated app declare the workspace ready when a required
stylesheet or JavaScript module failed to load. Retry a temporary asset failure
once, fail closed with a useful recovery message after a second failure, and
allow a later user-controlled reload or retry to complete without signing the
person out.

This is a control-reliability release. It does not claim that every future
network, provider, or device failure is eliminated.

## Released behavior

- Every deferred workspace stylesheet and script rejects a real browser load
  error instead of silently resolving it.
- A failed asset is removed and retried exactly once. Successful assets stay in
  place and are reused.
- The runtime reaches `ready` and dispatches its ready event only after all 17
  styles and all 34 ordered scripts have loaded.
- A second failure changes the runtime state to `failed`, does not start the
  partial workspace, and shows a bounded message that the sign-in is safe and a
  reload can retry.
- The failed runtime promise is cleared, so a later attempt can recover. The
  background runtime request path handles rejection without creating an
  unhandled browser promise.
- The web and native loaders both clone an already active stylesheet for final
  cascade position instead of detaching and moving it, preventing a transient
  unstyled frame.
- The app shell, sign-in controller, runtime loader, and service worker use a
  fresh atomic cache address: `workspace-runtime-recovery-1` and cache revision
  `ask-crump-new-body-v1-r237`.

## Executable proof

The credential-free browser fixture proves four states:

1. normal loading requests 17 styles concurrently, preloads 34 scripts, then
   executes all 34 scripts in the established order;
2. a one-time stylesheet failure makes exactly one extra stylesheet request and
   still reaches ready;
3. a one-time script failure makes exactly one extra script execution attempt
   and still reaches ready; and
4. a persistent stylesheet failure makes two attempts, executes no workspace
   script, dispatches no ready event, and exposes the safe recovery message. A
   later allowed attempt loads only the missing stylesheet, executes the full
   script plan, and dispatches one ready event.

All four cases completed with zero browser or unhandled-promise errors. The
complete fail-closed browser inventory remains 45 exact verifiers and includes
the button-state, chat-action, file, image, Project, Create, Video, Library,
account, Intelligence, mobile-drawer, and returning-service-worker journeys.

## Validation

- Python: 1,003/1,003 passed
- JavaScript: 54/54 validated
- attribution runtime fixtures: 22/22 rough-to-useful, 10/10 Word/PDF, and
  10/10 résumé-audit cases passed
- browser controls: 45/45 passed
- deterministic normal/retry/fail/recover runtime browser proof: passed
- production build preflight and native web bundle: passed
- public/native client-credential boundary: passed
- Ruff, Python compilation, store metadata, native privacy source, mobile
  signing-source controls, and diff integrity: passed

## Release evidence

- product commit: `8595a44`
- production deployment: `dpl_GNSqduDXjmh8LsnhWoPxHPQTauNr`
- CI: `34772071740`
- Android source/bundle verification: `34772071737`
- iOS source verification: `34772071742`
- production `/api/health`: HTTP 200, product version `5.9.76`
- the live app shell, workspace runtime, sign-in controller, and service worker
  match the committed files byte for byte by SHA-256
- signed-in production replay reached runtime state `ready`; opened Chats,
  Projects, Files, a file preview above Files, Video Studio, Library, Create,
  account Settings, and Intelligence; and closed each tested layer through its
  visible control

## Boundaries retained

No account, conversation, Project, file, image, video, manuscript, database,
provider, credit, plan, checkout, price, entitlement, credential, campaign, or
customer-content state changed. No generation, upload, download, purchase,
deletion, permission grant, external message, social publication, or store
submission occurred.

The automated inventory and production replay substantially raise confidence in
the shipped control surface; destructive, billable, provider-backed, permission,
download, and physical-device outcomes retain their separate action-time gates.
