# In-app product support release — 2026-09-01

## Outcome

You → About now gives signed-in users a direct **Product support** path instead of requiring them to
leave the app, search a legal page, or find an old email. The destination uses
`support@askcrump.com`, the same configured address already included in Ask Crump transactional email,
and pre-fills only the generic subject **Ask Crump support**.

Legal, privacy, security, and abuse contacts remain separate and unchanged. The link does not send
mail itself; it hands off to the user's configured email application only after deliberate activation.

## Release evidence

- Code commit: `321fe6b`.
- Production deployment: `dpl_4rQFpWX5hsp8xu4WYLj6zRtg3CwU`, `READY` on all six aliases.
- Production service-worker cache: `ask-crump-new-body-v1-r181`.
- 711 Python tests passed.
- 47 JavaScript files passed the integration contract.
- Python compilation, production preflight, native web-bundle generation, store metadata, mobile
  signing-source controls, and diff integrity passed.
- Static acceptance binds the in-app address to the configured transactional-email support contract.
- The signed-in production app displayed **Product support**, displayed the established address, and
  exposed the exact `mailto:` destination. Verification inspected the destination without activating
  it.
- The canonical app and service worker returned HTTP 200 with the exact support and cache markers.
- The release deployment showed no runtime-error cluster and no warning/error/fatal log.

No email client was opened. No message, support request, account, session, content, Project, artifact,
checkout, payment, subscription, entitlement, or credit state changed during verification.

## Remaining gate

A founder-controlled support-address delivery and response test should confirm that legitimate inbound
mail is received and triaged before public support-response expectations are advertised. Native store
readiness separately still requires generated platform projects, RevenueCat public SDK keys,
signed-device proof, screenshots, reviewer credentials, and store-console completion.
