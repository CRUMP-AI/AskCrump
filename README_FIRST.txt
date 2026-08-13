ASK CRUMP — PHASE 4 FINAL CI ALIGNMENT

WHY
The real source fixes are already on main. The latest CI run exposed two stale
test/validation contracts:

1. tests/test_sidebar_navigation.py still expects duplicate rail controls to be
   absent from static app.html, but Ask Crump 5.2.5 intentionally removes them in
   the final runtime navigation layer and hides them with CSS before cleanup.
2. scripts/check-javascript.mjs still expects service-worker cache r2, while the
   approved UI stability deployment intentionally bumped public/sw.js to r3.

WHAT THIS PACKAGE CHANGES
ONLY:
- tests/test_sidebar_navigation.py
- scripts/check-javascript.mjs

It does NOT modify app.html, navigation runtime, CSS, billing runtime, service
worker, auth, backend, Supabase, Stripe, or production UI behavior.

HOW
1. Extract this ZIP to Downloads/Desktop, outside the CRUMP-AI repo.
2. Double-click RUN_PHASE4_FINAL_CI_ALIGNMENT.bat.
3. When it says SUCCESS, open GitHub Desktop.
4. Confirm ONLY the two files above are modified.
5. Commit: Align Phase 4 regression contracts
6. Push origin.
7. Tell Echo: Phase 4 final CI alignment pushed.
