# Policy-consent compatibility transition

Status: draft engineering plan only. This source is not live and does not make
legal conclusions.

## Bounded purpose

This is the pre-enforcement phase between the installed legacy client contract
and the exact current policy-bundle contract. It deliberately supports both:

- legacy registration and reacceptance payloads keep their existing behavior
  and may update only the legacy `users.terms_*` mirror;
- the exact bundle `ask-crump-legal-2026-08-01-bc5e6e1d`, accompanied by four
  literal boolean `true` attestations, may call the service-only receipt writer;
- no legacy timestamp, version, truthy value, header, user agent, installation
  identifier, or platform claim can mint or promote an exact current receipt.

The web source now emits the exact payload. Capacitor packages the same public
source, so a compatible native binary can later be built from this reviewed
commit. This change does not build, sign, upload, or publish a native binary.

## No enforcement in this phase

Protected routes and background workers retain the PR #122 behavior. Receipt
absence does not gate product use, provider calls, usage accounting, queue
claims, or durable work. Existing clients therefore remain functional while
exact receipts can begin accumulating through explicit new-contract acceptance.

Do not add client-kind branching. The public web and native clients share the
same endpoints, and `X-Crump-Client`, User-Agent, bearer/cookie selection, and
installation identifiers are spoofable. Receipt provenance records the
server-observed acceptance source and the honest platform value `unknown`.

## Future rollout gates

Before any enforcement change, separately verify a compatible native binary,
choose an adoption/transition threshold, and make a later release decision.
Schema apply, application deploy, native release, and enforcement are all out
of scope for this preparatory pull request.

## Application and schema safety

The additive schema keeps the hardened PR #124 design: immutable manifest and
receipt rows, server timestamps, exact hash guards, empty function search paths,
RLS enabled with no policies, no direct table grants, service-role-only RPCs,
idempotent source-bound writes, and drift refusal rather than silent repair.

If this application source must be rolled back before enforcement, the additive
tables and receipts can remain. Legacy code may continue writing only the
non-authoritative mirror; it cannot fabricate a receipt.

## Explicitly unresolved deletion-cascade decision (P3)

Receipt rows currently follow `users` with `ON DELETE CASCADE`; the non-personal
manifest remains. Whether law, dispute preservation, or another documented
purpose requires a different receipt-retention period is a separate counsel and
company policy decision. This transition intentionally preserves and documents
that PR #124 P3 rather than silently choosing another retention rule.
