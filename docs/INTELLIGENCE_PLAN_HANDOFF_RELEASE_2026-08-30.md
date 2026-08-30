# Intelligence plan handoff release — 2026-08-30

## Outcome

A locked **Think longer**, **Always review**, or **Compare plans** action now opens one real
Professional plan center. It no longer creates a billing dialog and then replaces it with a second
dialog when the plan-intent listener runs.

If the Intelligence control becomes interactive before the billing runtime finishes loading, the
intent waits for the shared workspace-ready signal. Repeated early clicks coalesce into one pending
handoff. A 15-second bound removes the listener, restores retry, and reports truthful failure if the
runtime never becomes ready.

## Evidence behind the change

The production source path had two owners for the same action:

1. Intelligence called the active billing-center function directly.
2. Intelligence dispatched the plan intent.
3. The subscription listener called the billing-center function again.

Both current billing-center implementations return a connected modal. Reusing that connected modal
is therefore the smallest complete repair. The listener still opens a plan center when an intent
arrives from authentication or another source that has not already opened one.

The existing server entitlement remains authoritative. Free accounts still cannot persist
**Think longer** or **Always review**, Professional and Enterprise retain those capabilities, and
opening the plan center does not create a checkout or purchase.

## Verification

- 574 Python regressions passed.
- 45 JavaScript integration files passed validation.
- Production build preflight passed.
- The native web bundle regenerated with the versioned Intelligence and subscription assets.
- Store metadata and non-secret mobile signing-source checks passed.
- The native release verifier retained the known submission gates: owner-controlled iOS project,
  RevenueCat public SDK keys, and Firebase configuration are not present in this Windows checkout.
- A loopback-only real-browser fixture proved the ordinary locked-control path produced exactly one
  billing-center open, one billing-status request, one consumed Professional intent, the correct
  highlighted plan, and zero browser errors.
- The same fixture withheld both billing functions, invoked the locked action twice, then emitted the
  workspace-ready signal. It produced zero opens before readiness and exactly one open, one status
  request, one consumed Professional intent, and zero browser errors afterward.

The fixture contains a fixed local user label, fixed entitlement response, and content-free counters.
It does not contact production, create an account, open checkout, run a model, or spend credits.

## Production delivery

- Feature commit: **6a469c4**
- Production deployment: **dpl_Ccn9bjeDeSpBLaYuVJKDVfZEQqAq**
- State: **READY**
- Aliases: askcrump.com, www.askcrump.com, clevercrump.com, www.clevercrump.com, and both
  Vercel project aliases
- Health: HTTP 200 with no-store
- Exact Intelligence, subscription, runtime-loader, and service-worker assets: HTTP 200 with the
  corrected handoff contract
- Release window: no runtime-error cluster and no warning, error, or fatal runtime log

## Measurement boundary

This release proves reliable delivery into a truthful plan-comparison surface. It does not prove
paid conversion. Observe a legitimate locked Intelligence action → plan intent → deliberate checkout
choice → provider-confirmed entitlement before changing price, entitlements, or the upgrade message.
