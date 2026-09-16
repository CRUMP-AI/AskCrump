# Live signed-in button walkthrough

Observed: 2026-09-16 15:20–15:24 EDT

Production source: `7833d89e2e5ee419fd27757f82c4fff92beed295`

Application version: `5.9.76`

Scope: read-only and reversible control verification during the isolated Facebook acquisition cell

## Result

A non-destructive walkthrough of the owner-authenticated production workspace completed without a
visible control failure, browser warning, or browser error. The walkthrough used the actual live
interface; it did not rely on a fixture or preview deployment.

Verified paths:

- Ask launchpad and composer loaded with the empty Send action truthfully disabled.
- Projects opened the owner-scoped Project index.
- Files opened in the foreground, completed its private inventory load, opened an image in the
  foreground preview, and returned to Files through **Done**.
- Create opened its outcome chooser, and **Documents** opened Document Studio without generating.
- Video opened Video Studio with the active Project destination, provider choices, optional reference
  image control, disclosure, and generation action visible.
- Library opened independently from Files and loaded the private books-only shelf.
- You opened Profile, Behavior, Plan & credits, Account, and About.
- Plan & credits completed its live balance, allowance, credit-pack, subscription-review, and ledger
  load; no checkout was started.
- Signed-in devices completed its current/other-session inventory load; no session was revoked.
- Replay workspace guide opened and returned through **Open Ask and close the guide**.
- Intelligence opened, durable-memory review completed its private item load, and the Back/Close
  controls returned correctly; no preference was changed and no memory was deleted.
- Chats opened the synchronized conversation list; an exact conversation options menu opened and
  Escape closed only that menu while preserving the Chats drawer; Close returned to Ask.

## Safety boundary

No purchase, checkout, generation, upload, download, settings save, sign-out, session revocation,
conversation creation/rename/delete, Project creation, manuscript action, account deletion, provider
call, credit use, or production-data write was performed. Private names, content, filenames, memory
text, and session identifiers are intentionally excluded from this evidence.

## Interpretation

This is strong live evidence for the exercised navigation, overlay, loading, and return controls. It
does not substitute for legitimate completion evidence for destructive actions, commerce,
provider-backed generation, uploads/downloads, permissions, or physical-device outcomes. Those stay
behind their existing action-time and regression gates.

The separate held single-output Project-continuity candidate remains unpushed and undeployed through
the Facebook isolation boundary at 2026-09-17 13:28 EDT.
