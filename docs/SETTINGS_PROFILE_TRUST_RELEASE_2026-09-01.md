# Settings profile trust release — 2026-09-01

## Outcome

The You → Settings profile surface now tells the truth from first paint through late session recovery.
Signed-in users see the account identity available to the session; guest users see the explicit
read-only state **Sign in to view account email**. Whitespace-only or stale cached identity cannot
masquerade as a valid account value.

**Save changes** begins disabled, enables only after an editable preference actually changes, and
returns to disabled when the change is reverted or the save completes. Repeated saves are guarded
while a request is in progress. The account-email field remains read-only and is never included in
the profile-preference save path.

The workspace script is now boot-critical and network-first. The service worker requests it with
`no-store`, Vercel serves it with `no-cache, no-store, must-revalidate`, and a late presentation
repair reconciles guest or signed-in identity after cached-session transitions. This prevents an
older PWA shell from silently retaining the earlier Settings behavior.

## Release evidence

- Feature commits: `50fa044`, `a63a390`, `97b846e`, `3d2fb62`, `13cd844`, `3df03d3`,
  `94d68c1`, `9009634`, and `b2ba213`.
- Production feature deployment: `dpl_AX18UZtboPZkSa8dsuLsyztRMxA5`, `READY` with no alias error
  on `askcrump.com`, `www.askcrump.com`, `clevercrump.com`, `www.clevercrump.com`, and both Vercel
  production aliases.
- Exact public asset: `5.9.76-settings-profile-trust-8`; service-worker cache:
  `ask-crump-new-body-v1-r198`.
- The canonical app, service worker, and exact versioned workspace script returned HTTP 200. The
  workspace script returned `no-store, must-revalidate, no-cache` and contained the late identity
  repair.
- A real-runtime browser fixture covered signed-in desktop at 1280×760, signed-in phone at 390×844,
  and guest phone. It proved the read-only identity boundary, disabled initial save, edit/revert
  transitions, a second editable section, deliberate late stale-value corruption, guest recovery,
  zero horizontal overflow, and zero browser errors.
- Production loaded the exact release asset with a read-only account field, disabled unchanged Save
  action, canonical guest first-paint copy, and no horizontal overflow. The browser privacy layer
  masks account-field contents, so the deterministic signed-in fixture—not a production identity
  string—is the authoritative field-value proof.
- All **738 Python tests**, **47 JavaScript validations**, Python compilation, production preflight,
  native web-bundle generation, store metadata, mobile signing-source controls, and diff integrity
  passed.
- The final release window contained 35 successful HTTP 200 runtime requests, no 4xx or 5xx log,
  no runtime-error cluster, and no warning/error/fatal log.

No Settings save, account update, session change, customer-content access, Project/file change,
generation, credit, checkout, payment, analytics event, email, or support message occurred during
verification.

## Remaining gate

Repeat the unchanged/edit/revert/save states on the exact signed physical iPhone and Android release
candidates with VoiceOver/TalkBack before store screenshots. Observe a legitimate user preference
save and cross-device refresh before claiming a retention improvement.
