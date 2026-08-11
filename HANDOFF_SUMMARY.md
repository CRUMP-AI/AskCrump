# Ask Crump Sidebar / Navigation Cleanup

Date: 2026-08-11
Scope: focused release-polish patch; no new features.

## What this fixes

The mobile screenshot made the footer read as multiple navigation controls because the footer buttons used a two-column grid and the live credit badge could wrap onto another line. Separately, the desktop brand rail contained real icon-only Settings and Billing shortcuts that duplicated the labeled sidebar destinations.

This cleanup makes the navigation hierarchy explicit:

- Brand rail: New conversation, Conversation library only.
- Sidebar footer: Settings, Plan & credits, Legal & Privacy, Account sync status.
- Plan & credits retains the live `N C` balance badge inside the same row.
- Settings and Plan & credits close the mobile drawer before opening their destination.

The Settings and Plan icons are fully removed; they are not repurposed. The Legal & Privacy document icon remains because it has no duplicate destination and remains attached directly to its label.


## Compatibility with the production-hardening handoff

This package is intentionally additive to `ask-crump-hardening-release-handoff-2026-08-11.zip` and can be applied either before or after it. The earlier hardening package also edits `public/app.html`, but only around password policy; this navigation cleanup validates its own exact sidebar/rail fragments rather than requiring the entire HTML file to remain byte-identical.

The remaining five shell assets are still protected by exact audited Git-blob checks.

## Files modified by the apply utility

1. `public/app.html`
2. `public/crump-v1-body.js`
3. `public/crump-v1-body.css`
4. `public/app.js`
5. `public/crump-billing-5.1.js`
6. `public/crump-billing-5.1.css`

## File created

- `tests/test_sidebar_navigation.py`

The apply utility also installs `tests/test_sidebar_navigation.py` into the repository after every baseline check passes.

## Apply

From this extracted package:

```powershell
py APPLY_NAV_CLEANUP.py "C:\path\to\CRUMP-AI" --check
py APPLY_NAV_CLEANUP.py "C:\path\to\CRUMP-AI"
```

`--check` performs audited Git-blob validation for the untouched shell assets plus exact structural validation for `app.html`, without writing.
The real apply creates a timestamped `BACKUP-*` directory inside this handoff folder before touching the six source files.

If `--check` reports a blob mismatch, stop. Your local file has moved beyond the audited baseline and should be merged from `PATCHES/sidebar-navigation-cleanup.diff` rather than overwritten.

## Verification

```powershell
cd "C:\path\to\CRUMP-AI"
.\.venv\Scripts\python.exe -m pytest -q tests/test_sidebar_navigation.py
npm test
```

Then on a narrow/mobile viewport verify:

1. Open the conversation drawer.
2. Confirm Settings appears once as a labeled row.
3. Confirm Plan & credits appears once as a labeled row with the live credit badge aligned on its right.
4. Confirm the old standalone-looking Settings and billing icons are gone.
5. Tap Settings: drawer closes, Settings opens.
6. Tap Plan & credits or its balance badge area: drawer closes, billing center opens.
7. Confirm Legal & Privacy still works.
8. Rotate/narrow/widen once to ensure spacing remains stable.

On desktop, confirm the slim rail contains only the brand mark, New conversation, and Conversation library controls; Settings/Billing remain available from the labeled sidebar footer.

## Commit suggestion

**Title:** `Simplify sidebar settings and billing navigation`

**Body:**
- remove duplicate Settings and billing rail shortcuts
- simplify labeled sidebar footer actions
- keep the live credit balance attached to Plan & credits
- close the mobile drawer before opening Settings or billing
- remove stale command handlers and add navigation regression coverage
