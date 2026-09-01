# In-app product support release — 2026-09-01

## Outcome

You → About gives users a direct **Product support** path instead of requiring them to leave the app,
search a legal page, or find an old email. The current destination uses the monitored
`askcrump@gmail.com` inbox and pre-fills only the generic subject **Ask Crump support**.

The earlier domain-mailbox claim in this receipt was superseded on 2026-09-01 after independent DNS
validation found that mailbox was not provisioned. Product defaults now fail over the retired value
to the monitored inbox so a stale deployment environment cannot silently publish an unreachable
support destination.

Legal, privacy, security, and abuse contacts remain separate and unchanged. The link does not send
mail itself; it hands off to the user's configured email application only after deliberate activation.

## Release evidence

- Original support-surface commit: `321fe6b`; monitored-inbox correction: `5c3673a`.
- Production correction deployment: `dpl_AX18UZtboPZkSa8dsuLsyztRMxA5`, `READY` with no alias error
  on all six production aliases.
- Production service-worker cache: `ask-crump-new-body-v1-r198`.
- 738 Python tests passed.
- 47 JavaScript files passed the integration contract.
- Python compilation, production preflight, native web-bundle generation, store metadata, mobile
  signing-source controls, and diff integrity passed.
- Public markup, the documented environment default, and backend configuration now use
  `askcrump@gmail.com`. A stale explicit `support@askcrump.com` runtime value is mapped to the
  monitored inbox; a different deliberate operator address remains configurable.
- The production app displayed **Product support** and exposed the exact
  `mailto:askcrump@gmail.com?subject=Ask%20Crump%20support` destination. Verification inspected the
  destination without activating it and found no retired public support address.
- The canonical app and service worker returned HTTP 200 with the exact support and cache markers.
- The final release window contained 35 successful HTTP 200 runtime requests, no 4xx or 5xx log,
  no runtime-error cluster, and no warning/error/fatal log.

No DNS record, mailbox, provider configuration, deployment secret, or environment variable was
changed. No email client was opened and no message was sent. No support request, account, session,
content, Project, artifact, checkout, payment, subscription, entitlement, or credit state changed
during verification.

## Remaining gate

No support-response time is advertised. Native store readiness separately still requires generated
platform projects, RevenueCat public SDK keys, signed-device proof, screenshots, reviewer credentials,
and store-console completion.
