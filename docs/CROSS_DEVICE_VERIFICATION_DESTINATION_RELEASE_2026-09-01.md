# Cross-device verification destination release — 2026-09-01

## Outcome

Ask Crump now keeps the product destination promised before account creation when the verification
email opens in a different browser or on a different device. Document, presentation, résumé,
Video, and Projects entry links carry their allowlisted destination through registration, the
initial verification email, resend, the successful verification redirect, and the first
authenticated workspace frame. Professional or Enterprise review intent follows the same path
without starting checkout.

The prior same-device path relied on local browser storage and worked. The verification email itself
contained only the token, so a different device had no way to know which workspace the registration
screen promised. The new server-generated link carries only the bounded tool and optional plan
labels. The authenticated client consumes each once and removes the query string.

## Boundaries

- Allowed creation destinations are exactly `document`, `presentation`, `resume`, `video`, and
  `projects`; allowed plan-review destinations are exactly `professional` and `enterprise`.
- Unknown values, arbitrary text, and a `free` plan label are discarded before they enter an email
  or successful redirect.
- The handoff contains no prompt, response, message, filename, Project/conversation/file identifier,
  email address, referrer, raw campaign URL, or customer content.
- A plan label opens the existing review surface only. It does not grant an entitlement, create a
  checkout, charge a payment method, or change pricing, quotas, credits, or subscription state.
- Verification token lifetime, scanner-safe replay, password policy, cookie/session policy,
  attribution semantics, and server-authoritative account creation remain unchanged.
- No Supabase schema, migration, policy, function, shared table, provider, or API dependency changed.
- Verification did not create a production account or send a real email during release proof.

## Verification

- All **784 Python tests** passed.
- All **48 JavaScript files** passed the repository contract gate.
- Ruff, explicit Python compilation, production preflight, native web-bundle creation, store
  metadata, mobile signing-source controls, and diff integrity passed.
- Focused server tests prove allowlist normalization, URL encoding, invalid-value rejection,
  registration forwarding, resend forwarding, scanner-safe replay, successful redirect behavior,
  and no-session behavior for invalid tokens.
- A 390×844 real-browser fixture began with empty device storage and a successful verification URL.
  It opened the PowerPoint creation workspace and Professional review exactly once, consumed both
  intents, removed both storage records and the URL query, and produced zero page, console, or HTTP
  errors.
- Production deployment `dpl_CWJycAeXUM3VroFaFUfpfAGvZ5tm` is `READY` on all six aliases and points
  to commit `816f5fd210d91ad413cdd2f629e2ccba438da9b2`.
- The live workspace HTML, authentication controller, and service worker matched the committed
  SHA-256 bytes exactly. `/api/health` returned HTTP 200 and version 5.9.76.
- The settled deployment had two observed HTTP 200 requests, no severe log, and no runtime-error
  cluster.

## Release identity

- Feature commit: `816f5fd210d91ad413cdd2f629e2ccba438da9b2`
- Production deployment: `dpl_CWJycAeXUM3VroFaFUfpfAGvZ5tm`
- Status: `READY`
- Build duration: about 50 seconds
- Canonical aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and both Vercel production aliases
- Auth controller: `5.9.76-verification-handoff-1`; SHA-256
  `2288EEE274DF059AA6522EBE4D4A5C04333CED26A76F69C66080F1DBE9B7B412`
- Workspace HTML SHA-256:
  `A48FEC313E51275389036FFB4EBE970F115C691D6FF03DEDF3F632ED0B55AC4B`
- Service worker cache: `ask-crump-new-body-v1-r211`; SHA-256
  `DA85759CD188BAD6613B57C9C5D19600911AE347B99A4AE372D72BB7297A66F8`

## Remaining acceptance work

1. Observe a legitimate, naturally occurring capability entry through account creation,
   verification, destination continuation, useful work, Project save, artifact, and eligible return.
2. Repeat one rights-cleared cross-device verification on exact signed iPhone and Android candidates
   before final store screenshots; do not manufacture a production account for measurement.
3. Keep paid acquisition held until source-segmented activation, retention, payer, recognized
   revenue, refund, and variable-cost evidence meets the existing decision rules.
