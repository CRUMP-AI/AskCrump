# Public accessibility and control gate — 2026-09-13

## Outcome

Ask Crump now has a required, reproducible accessibility check covering its public product,
capability, account-entry, recovery, and company pages at both phone and desktop widths. The new
gate complements the existing fail-closed button inventory and real-browser control matrix: a
button must still have an explicit owner, its representative interaction flow must still execute,
and the public surface must now also pass the automated WCAG A/AA rules selected by the release
check.

The first full run found one genuine defect on the desktop Ask Crump product page. The inactive
destination labels used `#697178` against `#090d12`, a contrast ratio of about 3.93:1. They now use
`#858d94`, about 5.78:1, without changing the active destination, layout, navigation, or click
behavior. The local fixture also incorrectly served no page at `/`; it now maps that route to the
same Ask Crump landing document used by production instead of reporting false missing-title and
missing-language failures.

All public pages now request one exact `5.9.76-accessibility-1` stylesheet URL. Service-worker cache
revision `r239` replaces the old cache so returning web and PWA sessions receive the corrected
contrast rather than retaining the previous stylesheet.

## Automated evidence

- The new axe-core 4.13.0 check passed **22/22** scenarios: 11 routes at 390×844 and 1440×900.
- Covered routes include the Ask Crump home and product pages; Projects, document, presentation,
  résumé, and video capability pages; sign in; account creation; password recovery; and Clever
  Crump.
- The fail-closed source inventory still covers **182 rendered + 94 programmatic = 276** reviewed
  button construction sites.
- The complete real-browser control matrix passed **45/45** flows, including primary navigation,
  mobile drawer destinations, Projects, Files/viewers, Project save/output actions, Library,
  Video and reference-image paths, image stability and Precision Edit, account entry and recovery,
  Settings, plans/credits, checkout recovery, lifecycle prompts, and close/back/retry states.
- The complete Python suite passed **1,049/1,049**; JavaScript validation passed **54/54**.
- Ruff, production preflight, native-web bundling, client-secret scanning, and diff integrity passed.
- The exact Python requirements and npm lockfile each reported no known dependency vulnerability.

## Continuous release boundary

CI now installs the pinned browser runtime and runs the accessibility matrix after the complete
interactive-control matrix. Adding a public route, changing account-entry state, introducing an
accessibility violation, adding an unowned control, or breaking a covered interaction blocks the
release rather than relying on a later manual report.

Automated checks cannot prove every assistive-technology combination or safely complete actions
that spend money, consume credits, delete data, contact a provider, request native permissions, or
depend on a signed physical device. Those actions retain their existing confirmation and
legitimate-user evidence boundaries. The release proves deterministic wiring and safe outcomes for
every reviewed control construction point, full execution of 45 representative browser flows, and
the 22-scenario public accessibility boundary; it does not claim that irreversible external actions
were performed merely to test their buttons.

## Production evidence

Pending the exact commit, hosted CI run, production deployment, live asset parity, health checks,
and initial runtime-error review.
