# Continuous workflow and button-integrity proof — 2026-09-08

## Outcome

Ask Crump's complete generated-work handoff now has a reproducible phone-width proof:

1. enter a rough request;
2. receive a useful response and an editable PowerPoint artifact;
3. choose **Keep in a Project**;
4. observe the completed **Open Project** state;
5. open the exact named Project; and
6. open the PowerPoint in Ask Crump's foreground viewer.

The proof uses the production interface owners from `ui-functions.js`, `crump-5.0.js`,
`crump-product-5.3.js`, and `crump-product-5.3.1.js`. It runs at 390×844, records one continuous
WebM, and captures a final PNG. The completed run reported zero browser errors, zero fixture errors,
zero unexpected requests, and zero horizontal overflow.

The output Project button regression was also strengthened. Desktop and phone now each prove both
an existing-Project and new-Project path through **Saving…** → **Open Project** → the correct named
workspace. All four cases passed with the correct accessible dialog name and heading.

## Broader control sweep

- Repository-wide static button ownership/type guard: **15 passed**.
- Credential-free browser verifiers: **34 passed**, zero failed.
- Complete Python suite: **910 collected**, **908 passed**, two environment-dependent skips.
- JavaScript integration contract: **49 files** and **6/6** attribution runtime cases passed.
- Ruff, Python compilation, production preflight, native web build, and diff integrity passed.
- The browser matrix covers primary destinations, every Create handoff, mobile Chats/destinations,
  Projects, generated-output save/open, Files, image and PowerPoint viewers, precision image editing,
  image stability, Video and reference images, Library, Settings, plans/credits, public account-entry
  actions, lifecycle prompts, authentication recovery, and close/back/retry states.

Destructive, account, billing, checkout, download, and provider-backed generation actions remain
covered with isolated recovery fixtures instead of being executed against production data.

## Generated evidence

The generated files are intentionally ignored by Git and remain local:

- `artifacts/marketing-workflow-proof/ask-crump-continuity-proof.webm`
  - 323,008 bytes
  - SHA-256 `AEBBA9E6AEFF42893F2B986F0B091292169B9A3AA112E6DED2AFB53EB25C4F2E`
- `artifacts/marketing-workflow-proof/ask-crump-continuity-proof-final.png`
  - 82,436 bytes
  - SHA-256 `235703141333C7B8537BBA40573D0FFCFB1B072F95CC8AA8E6FBC61261F4D305`

Reproduce after starting a repository-root local server on port 8765:

```powershell
$env:NODE_PATH='C:\Users\gcrum\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
$env:ASKCRUMP_BROWSER_EXECUTABLE='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
& 'C:\Users\gcrum\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' scripts/record-marketing-workflow-proof.cjs http://127.0.0.1:8765
```

## Truth and privacy boundary

This is a deterministic interface-continuity demonstration, not a live-model quality receipt. It
contains generic fictional content, no customer data, no credentials, no production endpoint, and
no provider request. It may demonstrate the product's interface and continuity behavior, but must
not be represented as proof that a live model generated the sample response or PowerPoint.

This work is product evidence only. It does not authorize social publication, paid acquisition, or
an unsupported performance or conversion claim. A human-owned sanitized demo account remains the
right path for recording authentic provider output.

## Release identity

- Evidence and regression commit: `cea422229eed3cba5da3cc6dbe5ce05f40a43cd8`.
- Main CI: `34284434266` — success.
- Automatic production deployment: `dpl_Bogw4VNvYydfhoBLAE3kvfLCBVaH` — READY on all six aliases,
  with no alias error.
- Initial one-hour runtime-error aggregate: empty.
- Deployment-scoped 5xx query: empty.

The committed release changes only tests, credential-free fixtures, the recording harness, and
documentation. Customer-facing production assets and behavior are unchanged.
