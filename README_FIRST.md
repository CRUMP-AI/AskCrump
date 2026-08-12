# Ask Crump — Phase 4 CI / Production Health Fix

## Scope
This package fixes only the exact CI blockers found on current `main`. It does not change UI/UX or product behavior.

## Why there is an apply utility
Two affected Python runtime files are large and actively maintained. To avoid replacing whole files merely to delete one unused import, this package uses a guarded exact edit. It aborts if the audited snippets are not present.

## Apply
Extract this ZIP outside the repository. From PowerShell:

```powershell
py APPLY_PHASE4_CI_FIX.py "C:\path\to\CRUMP-AI" --check
py APPLY_PHASE4_CI_FIX.py "C:\path\to\CRUMP-AI"
```

Then review the three-file diff in GitHub Desktop.

## Expected changed files
- `backend/crump52_patches.py` — removes unused `json` import only.
- `backend/intelligence_service.py` — removes unused `json` import only.
- `scripts/check-javascript.mjs` — recognizes the already-deployed `crump-navigation-5.2.5.js` and `crump-v1-stability.js` runtime files.

## Verification
From repo root, if your local environment is available:

```powershell
.\.venv\Scripts\python.exe -m ruff check app.py backend tests
.\.venv\Scripts\python.exe -m compileall -q app.py backend
.\.venv\Scripts\python.exe -m pytest -q
npm test
```

GitHub Actions is the authoritative verification after push.

## Commit title
`Restore CI alignment for production runtime`

## Commit summary
Remove two stale Python imports that block Ruff and update the JavaScript runtime contract to recognize the navigation and stability layers already deployed in production. No UI/UX or application behavior changes.

## Commit body
- remove two unused Python imports reported by Ruff
- register crump-navigation-5.2.5.js in the JS runtime contract
- register crump-v1-stability.js in the JS runtime contract
- preserve current production UI/UX and runtime behavior
- restore CI coverage so pytest and full JS validation can execute
