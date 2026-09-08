# Explicit button behavior release — 2026-09-08

## Outcome

Every button written in shipped HTML or JavaScript markup now declares whether it is a normal
button, form submitter, or form resetter. The final three implicit controls were the loading
placeholders for credit packs and subscription plans. They were outside a form and worked in the
current layout, but a later composition change could have made the browser treat them as submit
buttons. They now remain normal buttons regardless of where the Plan center is mounted.

The existing action-owner audit also reviewed the 21 dynamically rendered patterns that do not
carry a unique ID or data-action attribute. Each has a direct or delegated click owner; no dead
runtime control was found in that set. A new repository-wide test fails if any future button in
public HTML or JavaScript markup omits an explicit `type`.

## Verification

- All **873 Python tests** were collected: **871 passed** and two environment-dependent tests were
  skipped.
- All **49 JavaScript files** and all six attribution runtime cases passed.
- Ruff, Python compilation, production preflight, native web-bundle generation, and diff integrity
  passed.
- The Plan-center browser fixture passed at 390 by 844 and 1280 by 720. All three credit controls
  hydrated, stayed keyboard reachable, and invoked exactly one checkout boundary. Both runs had
  zero browser errors.
- A repository-wide scan found zero public markup buttons without `type=button`, `type=submit`, or
  `type=reset`.
- The exact production asset returned HTTP 200 with SHA-256
  `C6300911B5E8D791509A2B964047C1C3855958884D4269DE25B078A08102308A`, matching the committed
  file byte-for-byte. `/api/health` and `/app?release_probe=explicit-button-types-1` returned 200.
- The production deployment reached READY on all six aliases with no alias error. The initial
  15-minute runtime-error cluster and deployment-scoped warning/error/fatal queries were empty.

## Release identity

- Feature commit: `8a942f8de51f111786b96edfbad9c9699682e018`
- Production deployment: `dpl_Gtb8hZTG3tDB7j9fu71o8vhadgAC`
- Status: `READY`
- Main CI: `34247798094` — success
- Android verification: `34247798176` — success
- iOS verification: `34247798079` — success
- Aliases: `askcrump.com`, `www.askcrump.com`, `clevercrump.com`,
  `www.clevercrump.com`, and the two Vercel project/main aliases

## Measurement boundary

The service-role, content-free production reports for September 1 through this release still show
zero comparable external accounts, artifact journeys, attribution cohorts, Plan-center journeys,
or checkout journeys. This release prevents a deterministic future button failure; it does not
claim conversion lift. Acquisition volume remains the verified company bottleneck, while product
continues to preserve a clean destination for the first legitimate cohort.

No account, prompt, response, Project, file, event, provider request, credit, subscription, payment,
or customer record was created or changed for verification.
