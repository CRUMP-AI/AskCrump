# Conversation action accessibility release — 2026-09-10

## Outcome

Ask Crump's conversation controls now identify the conversation they affect and keep
their keyboard behavior scoped to that conversation. This closes the last ambiguity
found during the whole-product control review without changing conversation content,
storage, or destructive-action behavior.

## Product behavior

- Every rendered conversation row is named `Open conversation: <title>`.
- Every three-dot trigger is named `Conversation options for <title>` and exposes its
  collapsed or expanded state.
- The opened menu is named `Conversation actions for <title>` and identifies its
  Rename and Delete actions with the same title.
- Focus moves to Rename when the menu opens.
- Escape closes only that menu, returns focus to the originating options button, and
  leaves the Chats panel open.
- If a visible conversation title changes, the row, trigger, menu, and action names
  update without creating a second options button.

## Automated evidence

Product commits `5939014` and `6d76a2c` add the specific names and then scope Escape
so it cannot bubble into the broader Chats-panel handler. The fail-closed control
inventory remains **182 rendered + 94 programmatic = 276** button construction sites.

A dedicated real-browser verifier covers row and options naming, menu role and state,
focus placement, non-navigation when the options button is chosen, Escape restoration,
sidebar persistence, dynamic title changes, and ordinary conversation opening. It is
now part of the required **44/44** browser matrix.

The complete release gate passed:

- **999/999** Python tests;
- **53/53** JavaScript file validations;
- **44/44** real-browser control flows;
- production preflight, native web build, client-credential boundary, compilation,
  Ruff, and diff integrity;
- GitHub CI **34530272347**, Android **34530272376**, and iOS source verification
  **34530272346**.

## Production evidence

Production deployment `dpl_Fa9KwgWHh75T27maHNJoWKRRgfiV` is Ready for commit
`6d76a2c`. The deployed app shell, runtime body, conversation controller, and service
worker matched the committed bytes exactly.

A signed-in production replay showed ten specifically named conversation rows and ten
specifically named options buttons. Opening the first action menu produced the matching
menu, Rename, and Delete names, marked the trigger expanded, and focused Rename.
Pressing Escape removed the menu, marked the trigger collapsed, restored focus to it,
and kept the Chats panel visible. The release log contained visible GET/POST traffic
with HTTP 200 responses and **0 Warning / 0 Error / 0 Fatal** entries.

## Safety boundary

No conversation was renamed, deleted, created, or opened for content inspection during
production acceptance. No customer content, prompt, response, email, filename, or
identifier was read or recorded. Purchases, destructive confirmations, provider work,
permissions, uploads, downloads, and physical-device outcomes retain their existing
action-time gates.
