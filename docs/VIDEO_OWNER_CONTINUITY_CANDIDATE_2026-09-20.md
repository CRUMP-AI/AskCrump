# Video owner continuity candidate — 2026-09-20

Status: **draft; not committed, pushed, or deployed.** Production is unchanged. Hold release until independent review and the separate app-wide checkout-reauth isolation issue are resolved.

## Defect and bounded change

The Video Studio previously saved pending job and idempotency handles in browser-wide keys. In one browser, account B could inherit account A's pending video ID, poll A's owner-protected endpoint, and clear the handle after a 404. A then lost the convenient way to resume a paid job.

This candidate scopes video job and request handles to the authenticated account. It only migrates an old unscoped job after a protected GET confirms that the current account owns it; another account's 404 preserves that old handle. The unscoped request key is never reused. Owner/session checks fence delayed POST, poll, continuation, Project, Files, and reference-upload work from the next account's interface. A successful delayed POST can still save A's returned handle under A, but cannot populate B's UI. Credit-confirmation retries cannot reissue A's paid request as B. Ordinary logout retains the owner's pending handle; successful account deletion removes only that owner's handles and prevents a late response from recreating them.

The touched shared composers clear private transient attachments/previews on a changed account, while same-owner authentication refresh preserves them. The global credit quote closes as soon as checkout reauthentication is required, before another account signs in. No provider generation, database migration, payment, or production request was made by these tests.

## Verification performed

- New executable two-account browser verifier: **13 scenarios passed**, zero page errors. It covers A→B→A, independent jobs, B legacy 404 then A verified 200, same-owner idempotency, delayed A POST/poll, ABA paid-submit timing, Files/continuation isolation, real credit quote and checkout reauth dismissal, deleted-account late POST, and held image normalization before upload.
- Existing video-reference browser verifier: passed against this worktree on a dedicated localhost fixture port; no unscoped request persisted and no image data leaked into request/recovery storage. Port 8765 was serving another checkout, so the verifier now accepts `ASKCRUMP_FIXTURE_BASE_URL` while retaining its previous default.
- Focused Python contracts: **132 passed** (one third-party deprecation warning).
- JavaScript contract: **54 files validated**; returning-load service-worker browser check passed; client credential-boundary scan passed for the available copied client assets; `git diff --check` passed.
- Native bundle build remains **unverified**: this isolated machine's existing local `esbuild` package lacks the `@esbuild/win32-x64` optional binary, and no package-manager executable was available. The incomplete generated `dist` was removed. Run the complete locked build in CI/a provisioned environment before release; the credential scan does not substitute for a complete native build.

## Release hold and next action

Separate, preexisting app-wide checkout reauthentication can still leave or merge account A's chats into B's workspace through in-place `chat-sync.js` and shell state. That is outside this bounded Video Studio patch and is a **privacy release blocker**. Keep this candidate draft, complete and test the separate auth isolation change, then run the full browser matrix, complete native build, and release review together before any commit, push, or deployment.
