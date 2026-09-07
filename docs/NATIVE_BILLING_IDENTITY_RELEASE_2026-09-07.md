# Native billing identity isolation release — 2026-09-07

## Outcome

Ask Crump's native RevenueCat client now binds every product read, purchase, restore, and
subscription-management action to the currently signed-in Ask Crump account. Opening the Plan
center can no longer race two SDK configuration calls, and changing accounts without killing the
app can no longer leave later commerce attached to the prior account identity.

This is a source/readiness correction, not proof that App Store or Google Play billing is live.
RevenueCat public SDK keys, store products, signed candidates, sandbox purchases, and physical-device
commerce tests remain release-time gates.

## Risk corrected

`getProducts()` and `getCreditProducts()` are intentionally loaded in parallel. The former billing
manager guarded configuration with a Boolean set only after the asynchronous provider call, so both
reads could enter `Purchases.configure()` during the same Plan-center open. The same Boolean also
made every later call return early, even if account A signed out and account B signed in within the
same native process. A provider login failure was swallowed.

The corrected manager now:

- shares one in-flight SDK configuration across concurrent callers;
- records the Ask Crump account represented by the configured provider identity;
- shares one in-flight identity change across concurrent callers;
- adopts an already-configured native SDK and its current identity after a WebView reload instead of
  attempting a second native configuration;
- logs into the new account or logs out to an anonymous provider identity when the Ask Crump session
  changes;
- disconnects the provider identity after local Ask Crump auth is cleared during sign-out;
- rechecks identity if the account changes during an in-flight transition; and
- fails closed with a content-free recovery message before products or purchases proceed when the
  provider cannot confirm the active identity.

No account identifier is written to analytics, logs, local storage, or source. No product ID,
price, allowance, credit charge, entitlement, webhook, or server reconciliation rule changed.

## Executable proof

The browser-JavaScript release contract executes the real `billing-manager.js` against an isolated
RevenueCat fixture. It proves:

1. simultaneous subscription and credit reads configure the SDK exactly once for account A;
2. simultaneous reads after switching to account B perform exactly one provider login;
3. repeated reads for account B do not churn provider identity;
4. sign-out performs exactly one provider logout;
5. account C is aligned before its product read;
6. a WebView reload adopts an already-configured native identity without configuring again; and
7. an identity failure is shared by concurrent callers and exposes no post-failure offering read.

All **837 Python tests**, all **49 JavaScript files/contracts**, Ruff, production preflight, native
web bundling, store metadata validation, signing-source controls, and diff integrity passed.

## Release evidence

- Source commits: **a3ce883** (`Keep native billing identity account-scoped`), **f878e16**
  (`Harden native billing across WebView reloads`), and **0b0fa7c**
  (`Verify every native-facing release change`)
- Production deployment: **dpl_Fp5JZkcFSnpkajDTt2ZsHgEvnS8x** (`READY`)
- Main CI: [34156623388](https://github.com/CRUMP-AI/AskCrump/actions/runs/34156623388) — passed
- Android source/bundle verification:
  [34156623389](https://github.com/CRUMP-AI/AskCrump/actions/runs/34156623389) — passed
- iOS source/unsigned Release verification:
  [34156623394](https://github.com/CRUMP-AI/AskCrump/actions/runs/34156623394) — passed

Production health returned version **5.9.76**. All four public domains reached the canonical app with
HTTP 200 after redirects where appropriate. The deployed runtime and service worker named
`5.9.76-native-billing-identity-1`; the live billing and sign-out assets contained the single-flight,
persisted-SDK adoption, account alignment, disconnect, and fail-closed guards. The exact deployment
exposed all six intended aliases, had no
alias error, and its inspected release window had no runtime-error cluster or warning/error/fatal
log. No account, store identity, product, purchase, restore, credit, subscription, or customer data
was created or changed for verification.

Both mobile source workflows now trigger on the complete `public/**` native web payload, the
authoritative RevenueCat catalog, store packet, listing draft, and their build/release verifiers.
This prevents a native-facing source change from inheriting an obsolete green mobile result.

## Remaining store gate

Configure owner-controlled RevenueCat keys and exact Apple/Google products only inside the signed
candidate process, then repeat the account A → sign out → account B test with sandbox purchases and
server reconciliation on physical iPhone and Android devices. Do not submit either store build until
purchase, restore, refund/cancellation, entitlement sync, reviewer access, privacy declarations, and
the rest of `docs/STORE_LAUNCH_RUNBOOK.md` pass on that exact signed build.
