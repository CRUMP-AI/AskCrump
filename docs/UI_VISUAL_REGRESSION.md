# Ask Crump UI visual regression gate

This gate renders representative Ask Crump states with the production CSS cascade and fails closed when release-critical UI contracts regress. It does not sign in, call production APIs, mutate customer data, or require a running app server.

## Run it

From the repository root on Windows, macOS, or Linux:

```powershell
npm run test:ui-regression
```

The script resolves a Playwright Chromium installation (including the normal Windows user-profile browser cache), renders the fixture entirely offline, and exits non-zero if any scenario fails.

Screenshots and `summary.json` are written beneath the ignored `artifacts/ui-regression/<timestamp>/` directory. The screenshots are review evidence, not committed pixel baselines; deterministic computed-style and geometry checks are the automated gate.

## Coverage

Every state is exercised in light and dark appearance at these exact viewports:

- Phone: 390 × 844
- Tablet: 1024 × 1366
- Desktop: 1440 × 900

The fixture covers:

- Home
- Conversation response, intelligence receipt, response actions, outcome feedback, Project continuity, Keepsake artifact, attachment tray, and composer
- Files
- Video Studio
- Intelligence
- Settings
- Plan and credits
- Add to Crump
- Background Activity Center, including queued, running, ready, and failed work

The gate rejects:

- rendered text below a 4.5:1 contrast ratio;
- mobile interactive targets smaller than 44 × 44 CSS pixels;
- document or primary-surface horizontal overflow;
- fixed composer controls obscuring outcome or artifact content;
- attachment cards overlapping the composer;
- animations, transitions, or smooth scrolling that remain active when `prefers-reduced-motion: reduce` is enabled;
- browser console errors, page errors, incomplete scenario coverage, or missing fixture styles.

## Exemptions

Exemptions must be explicit in the fixture and carry a short reason as their attribute value:

- `data-ui-contrast-exempt="reason"`
- `data-ui-target-exempt="reason"`
- `data-ui-overflow-exempt="reason"`
- `data-ui-motion-exempt="reason"`

Use exemptions only for genuinely non-semantic decoration or an independently verified platform exception. Never exempt ordinary labels, metadata, status text, buttons, links, or controls to make the suite green. The current fixture exempts only the decorative billing monogram and an intentionally disabled save control from text-contrast evaluation.

## Release workflow

1. Run the gate after any CSS, layout, theme, composer, sheet, or motion change.
2. Open the generated screenshots for all changed states in both themes.
3. Fix every programmatic violation or document a legitimate, narrowly scoped exemption.
4. Re-run until all scenarios pass.
5. Keep the most recent `summary.json` as local release evidence; do not commit generated images.

This fixture intentionally uses production class names and imports `crump-activity-center-1.0.css`, `crump-ui-guardrails.css`, and then `crump-motion-system.css` as the final release layers. When a component's production structure changes, update the fixture in the same change so the gate cannot silently test retired markup.
