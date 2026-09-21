# Checkout account-isolation candidate — 2026-09-20

Status: source-only candidate. Not merged or deployed.

## Verified defect and decision

Checkout reauthentication previously hid the app and showed login in the same document. A different account could then sign in while the first account's in-memory chats, file previews, Projects, and in-flight chat synchronization still existed. A delayed first-account sync could merge its conversations into the second account's local cache. The narrow release decision is to replace the whole app document before another login, rather than rely on every feature independently clearing stale state.

The selected plan or credit pack stays in session storage for at most the existing recovery window. The new page forces an explicit login even if an old cookie still exists. After authentication, recovery waits for the enhanced billing panel, focuses the previously selected item, and requires a fresh checkout click. It does not submit a purchase. A stale credit-quote dialog is dismissed immediately when checkout reauthentication begins.

## Evidence

- Local Edge browser checkout fixture: two same-account recovery handoffs, zero automatic checkout requests, both selections focused after login; a separate A-to-B case proved the previous account's private DOM was absent before and after B signed in.
- JavaScript source/release contract: 54 files validated.
- Full browser-control matrix: 48/48 local verifiers passed with installed Edge.
- Returning-PWA cache fixture passed with new versioned auth, billing, and runtime assets.
- Full local Python suite passed excluding two existing Argon2 assertions: this runtime uses the scrypt fallback because the Argon2 dependency is unavailable locally. No new test failures remained.
- `git diff --check` passed.

## Release boundaries

- This fixes the known checkout same-document account-switch path. Other undiscovered in-place account-switch paths are not proven safe by this test.
- Browser fixture uses local fake accounts, not production customer data. Production smoke test and CI remain required before merge/deploy.
- The separate video continuity candidate is not yet integrated. A server-side video-start versus account-deletion concurrency audit remains open.
- No pricing, provider, database, or production state was changed.

## Operating snapshot and next action

At the 2026-09-21 00:38 UTC read-only scan: production health returned HTTP 200; 24-hour Vercel runtime had 1,548 HTTP 200, two HTTP 404, and no 5xx; the seven-day external-signup count was zero. The comparable 30-day external cohort was one account, activated but with no durable Project/artifact or payer milestone. Recognized revenue and variable cost were unavailable, not zero. Marketing/social remain owned by the separate marketing task.

Next: complete independent security review of this candidate, validate CI, then integrate with the reviewed video-client branch. Audit and close the server-side video-start/account-deletion race before treating the combined release as production-ready.
