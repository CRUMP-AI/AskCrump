# Project-save activation release — 2026-09-01

## Outcome

The one-click Project action beneath a useful response now tells the user exactly what is happening.
While the private save is in flight, the action reads **Saving…** and the adjacent explanation says
the conversation is being saved privately. A timeout or other recoverable failure restores the
available **Start a Project** or selected-Project action and confirms that the conversation is still
present. A successful save reads **Open Project** and names the private destination.

The click also records one idempotent, content-free `StarterIntentReached` milestone with the fixed
key `project-save-intent` and a bounded `new_project` or `existing_project` source. The existing
server-authoritative Project creation/attachment path continues to record completed durable value.
Together, those signals can distinguish no observed save intent from intent that did not reach a
completed Project without inspecting conversation content.

## Product and privacy boundaries

- The save request, Project ownership checks, Project creation/attachment behavior, and 15-second
  client timeout are unchanged.
- A failed save never removes the response or conversation and does not create a fake success state.
- The new analytics signal contains only the fixed event name, fixed event key, and bounded source.
  It contains no prompt, response, Project name, conversation ID, filename, user-entered text, URL,
  referrer, or customer content.
- No database, Storage, billing, credit, entitlement, model, provider, price, plan, or separate API
  repository contract changed.
- This release proves delivery and observability, not an activation or retention lift. Legitimate
  post-release behavior is required before making that claim.

## Verification

- All **770 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Changed-file Ruff checks, explicit Python compilation, production preflight, native web-bundle
  creation, store metadata, mobile signing-source controls, and diff integrity passed.
- A credential-free 390-by-844 browser proof exercised the real Project-save code. The stalled path
  displayed **Saving…**, recovered to **Start a Project**, preserved the conversation, emitted one
  bounded intent milestone, and made one save request. The success path displayed **Open Project**
  and named **Launch plan** as private. There were no unexpected requests or console errors.
- Both canonical health endpoints returned HTTP 200 and version 5.9.76.
- The live `ui-functions.js`, authenticated runtime loader, and service worker matched the exact local
  SHA-256 bytes after deployment.
- The deployment-specific observation window contained five successful HTTP 200 responses,
  no 4xx or 5xx response, no warning/error/fatal log, and no runtime-error cluster.
- Verification created no production Project, account, message, analytics event, payment, credit
  charge, file, provider request, or customer-data mutation.

## Release identity

- Feature commit: `a46313797bb411cbee78f8d342c32ecc547b9081`
- Production deployment: `dpl_A6u3Uz3xY79aFdHFrNL7dtwV9H24`
- Status: `READY`
- Build duration: about 37 seconds
- Canonical aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and both Vercel production aliases

## Remaining acceptance work

1. Observe legitimate `project-save-intent` users against server-authoritative Project completion;
   investigate intent without completion before changing acquisition.
2. Follow completed saves through later Project resume and eligible D1/D7 return. Do not treat the
   click milestone itself as activation or retention.
3. Repeat save, timeout recovery, Project open, and later resume on exact signed iPhone and Android
   candidates before store screenshots or physical-device reliability claims.
