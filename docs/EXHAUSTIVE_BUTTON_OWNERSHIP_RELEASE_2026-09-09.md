# Exhaustive button ownership release — 2026-09-09

## Outcome

Ask Crump now has a fail-closed inventory and runtime-owner guard for every button rendered by
the web/PWA source. The previous guard exhaustively reviewed the 47 buttons in public HTML, while
the 134 buttons emitted from JavaScript templates were only covered by the separate explicit-type
check and the broader browser workflow matrix. A new dynamic button could therefore have carried
an ID in its own markup and looked referenced without proving any independent runtime owner.

The corrected contract:

- locks the current per-file inventory at **181 rendered buttons** across 13 source owners;
- parses both public HTML and JavaScript-rendered button markup;
- removes rendered button tags before searching executable JavaScript, so a markup ID cannot
  satisfy its own ownership test;
- requires every non-submit button to resolve through an independently referenced ID, data
  attribute, class owner, or explicit inline action; and
- includes a negative fixture proving an ID that exists only in dead markup is rejected.

Four dynamic controls that previously relied on anonymous `querySelector('button')` lookups now
use explicit, scoped owners without changing their visible behavior:

- desktop Project-context exit;
- mobile Project-context exit;
- **Open Workshop** for a manuscript handoff; and
- **Open Video Studio** for a video handoff.

The affected product script is cache-addressed as
`5.9.76-button-ownership-1`, and service-worker cache revision `r225` carries the same script into
web, installed PWA, Android, and iOS source bundles.

## Verification

- Button integrity: **17/17** focused checks.
- Rendered inventory: **181/181** buttons have a form or independent runtime owner.
- Browser control matrix: **34/34** credential-free verifiers passed. Twenty-seven used the
  repository-root server directly; seven fixed-port verifiers were rerun against their required
  repository/public roots after their initial connection-refused infrastructure results.
- Complete Python suite: **912 collected**, **910 passed**, two environment-dependent skips.
- JavaScript integration contract: **49 files** and **6/6** attribution runtime cases passed.
- Ruff, Python compilation, production preflight, native web bundle, and diff integrity passed.
- Main CI: **34354925097** — success.
- Android store-source workflow: **34354925047** — success.
- iOS store-source workflow: **34354925051** — success, including unsigned Release compilation
  and compiled privacy-manifest inventory verification.

The browser sweep covers primary destinations, Create handoffs, Chats, Projects, generated-output
save/open, Files, image and PowerPoint viewers, precision editing, image stability, Video and
reference images, Library, Settings, plans/credits, public account entry, lifecycle prompts,
authentication recovery, and close/back/retry states. Destructive, account, checkout, download,
and provider-backed generation actions remain isolated in safe recovery fixtures.

## Production evidence

- Feature commit: `fd2da132f272178137aba1eb637b45858c7664bf`.
- Automatic production deployment: `dpl_3yxvjGggLpZtwdenQ1BDqFGTdhAj` — READY on all six aliases
  with no alias error.
- `www.askcrump.com`, `askcrump.com`, `www.clevercrump.com`, and `clevercrump.com` health returned
  HTTP 200 at version 5.9.76.
- Live service-worker, runtime-loader, and product-script responses returned HTTP 200 and exposed
  exact cache `r225`, product version, and the three new scoped selector markers.
- The initial 30-minute runtime-error aggregate and deployment-scoped 5xx query were empty.

This release changes ownership precision and prevention coverage. It does not claim every future
provider, device, permission, network, or customer-data state can never fail. Those paths retain
their explicit recovery behavior and require signed physical-device and legitimate external-use
evidence before broader claims.
