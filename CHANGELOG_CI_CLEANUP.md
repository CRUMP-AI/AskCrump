# Ask Crump 5.2.4 — CI Cleanup

- Removes the Ruff-confirmed unused `json` imports from:
  - `backend/intelligence_service.py`
  - `backend/crump52_patches.py`
- Registers `crump-5.2.4.js` in the strict browser JavaScript allowlist.
- Restores Capacitor, RevenueCat, esbuild, and native platform dependencies in `package.json`.
- Does not change the 5.2.4 login/session behavior or branding behavior.
