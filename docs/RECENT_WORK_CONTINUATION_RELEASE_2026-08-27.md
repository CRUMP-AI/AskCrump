# Named recent-work continuation release — 2026-08-27

## Outcome

Ask Crump 5.9.28 makes the home resume action identify the private conversation it will open. The
previous generic `Continue recent work` card required mobile users to resume without knowing which
work was selected; the new card shows the actual conversation name and `Continue where you left
off.`

The name is whitespace-normalized, limited to 72 characters, inserted with `textContent`, and
visually ellipsized on narrow screens. Generic fallback copy remains for untitled conversations.
The button's accessible name identifies its destination.

## Privacy and measurement boundary

The conversation name appears only inside the signed-in workspace, where the same name is already
shown in the private conversation library. The `RecentWorkResumed` analytics event still sends only
its allowlisted event key and `launchpad` source. It does not send a conversation ID, title, message,
or other content.

## Verification

- Commit: `6161778`
- Production deployment: `dpl_EJmVH3eLTbfQdPzLCpyLZ6H22RUj`
- 295 backend tests and backend lint passed.
- 40 JavaScript validations, production preflight, and native web bundle passed.
- Android 5.9.28/build 50928 source, metadata, and signing-source controls passed locally.
- CI [33126950108](https://github.com/CRUMP-AI/AskCrump/actions/runs/33126950108), Android
  [33126950133](https://github.com/CRUMP-AI/AskCrump/actions/runs/33126950133), and iOS
  [33126950091](https://github.com/CRUMP-AI/AskCrump/actions/runs/33126950091) completed successfully.
- Production health returned 5.9.28.
- Desktop and 390-by-844 mobile browser checks showed the bounded named card, and activating it
  opened the intended conversation.
- The deployment window contained no runtime error cluster and no warning/error/fatal/5xx response.

The comparable external growth cohort still contains zero accounts, and the artifact journey still
contains zero rows. This release proves delivery quality, not a retention improvement. The outcome
gate remains a legitimate external conversation-to-Project transition followed by a later return.
