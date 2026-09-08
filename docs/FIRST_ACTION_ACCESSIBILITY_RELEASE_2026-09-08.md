# First-action accessibility — 2026-09-08

## Outcome

The six authenticated launchpad choices now expose one clean action name and a separate helpful
description to assistive technology. Decorative icons and arrows no longer become part of the
button name:

- Think with Crump
- Research something
- Analyze a file
- Create an image
- Start or open a Project
- Create a video

The visible design, order, copy, destinations, analytics event, pricing, generation behavior, and
account flow are unchanged.

## Evidence and decision boundary

A signed-in production accessibility-tree inspection showed names such as **✦ Think with Crump …
↗** because decorative text participated in the accessible button name. The same audit confirmed
that the actions themselves worked. Ask Crump now binds each button to its visible title with
`aria-labelledby`, binds its supporting sentence with `aria-describedby`, and hides decorative
glyphs from accessibility APIs.

The content-free seven-day product-event review contained no recent external first-session cohort
and no new `StarterIntentReached` event after 2026-08-31. That absence is not evidence of a broken
button or conversion impact. It is why this release stays limited to the deterministic semantics
defect and makes no activation claim.

## Browser acceptance

A new credential-free 390×844 browser proof executes all six real first-action paths:

- Think focuses the empty composer.
- Research focuses the composer and primes exactly one research scaffold, including on reselection.
- Analyze a file reaches the file picker.
- Create an image reaches Image Studio.
- Projects and Video expose visible busy state while their shared runtime loads.
- If the user changes from Projects to Video during that load, only the latest choice opens.
- Every action retains the existing content-free `StarterIntentReached` event key and source.

The existing cross-device verification fixture also passed, preserving presentation and
Professional intent through verification with zero HTTP or browser errors. Production inspection
then confirmed all six exact clean names in the live accessibility tree. No customer content or
credential is present in either fixture.

## Automated and release verification

- Full Python suite: **898 collected**, **896 passed**, two environment-dependent tests skipped.
- Focused first-action/composer/activation/button suite: **30 passed**.
- JavaScript integration contract: **49 files** and **6/6** attribution runtime cases passed.
- New first-action browser proof and existing cross-device verification proof passed.
- Ruff, explicit Python compilation, production preflight, native web build, and diff integrity
  passed.
- Main CI `34269902834`: success.
- Android Store Bundle Verification `34269902711`: success.
- iOS Store Source Verification `34269902882`: success.
- Production deployment `dpl_G9SCKv2pPnhfeQd3dSZPMpTkQoTb`: READY on all six aliases with no
  alias error.
- Canonical `/api/health`: HTTP 200, Ask Crump `5.9.76`.
- Deployment-scoped runtime-error, error/fatal, and HTTP 5xx queries: empty.

## Release identity and exact bytes

- Feature commit: `2e1d5b20eb4541f86f47ff59dd2098dec184d0e3`
- `public/app.html` live/local SHA-256:
  `A22B3A0ECD27DB713173563A6CB340822C8E275A62707F1B91BED31B6C22B889`

## Boundary and next evidence

No account, signup, message, response, file, Project, generation, checkout, payment, publication,
social action, synthetic product event, or customer-data operation was created for this release.
The fixture and live accessibility tree prove behavior and semantics, not improved activation.

Observe a legitimate registration → first choice → useful result journey, including assistive-
technology feedback when available, before claiming activation impact or changing the launchpad's
information architecture.
