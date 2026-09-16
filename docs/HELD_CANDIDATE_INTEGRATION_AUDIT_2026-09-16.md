# Held-candidate integration audit — 2026-09-16

Status: conflict audit passed; no combined release created

## Scope

This audit checked the locally held single-output Project-continuity candidate against each later
acquisition candidate while the live `rough-to-useful-v2` Facebook cell remained isolated.

- Exact shared production base: `7833d89e2e5ee419fd27757f82c4fff92beed295`
- Product functional commit: `9ad93c89fa71c48583266a12f164d862f1264cd4`
- Product final evidence/guard HEAD: `b95b4f5d01aef23c010c08804393c17c3b7f4c54`
- Draft-to-clearer evidence HEAD: `f030814440032d09375b6b3a9015e5892e1f0443`
- Resume-you-can-defend evidence HEAD: `ac5a55b339695c2696f290d73ff1d0e966eaed5f`

## Three-way merge evidence

Git's three-way merge engine completed both pairings with exit code zero:

| Pair | Synthetic merged tree | Result |
|---|---|---|
| Final single-output HEAD + draft-to-clearer | `141dcfcf4d16e021db9688c28f6aacfdd8d30ad4` | Clean auto-merge |
| Final single-output HEAD + resume-you-can-defend | `ed7bd1bc26fb19451f50b8fb147beff01bfe7a28` | Clean auto-merge |

The only files changed by both sides were `scripts/check-javascript.mjs` and
`tests/test_button_integrity.py`. Both merged automatically. The customer-facing product fix and
campaign attribution/runtime files do not overlap.

Tree inspection confirmed that both synthetic merges retain:

- the `5.9.76-single-output-continuity-1` UI/runtime asset identifiers;
- service-worker cache `ask-crump-new-body-v1-r249`;
- the matching output-continuity release guard; and
- the fail-closed 38-path candidate verifier; and
- the exact campaign registry/runtime coverage and browser-verifier inventory for the paired
  acquisition candidate.

## Boundary

This proves source-level compatibility, not integrated release readiness. It created no branch,
worktree, deployment, migration, tagged visit, production event, or public change. Before any later
combined deployment, create an explicit release candidate from the then-current production base and
rerun its complete Python, JavaScript, browser, production-build, native-build, credential-boundary,
and diff-integrity gates. Do not combine the two acquisition candidates merely because each is
compatible with the product fix; campaign sequencing remains an evidence decision.
