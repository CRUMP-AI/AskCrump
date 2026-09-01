# Files preview layer release

Date: 2026-09-01

## Outcome

Opening a saved PowerPoint, document, or image from Projects → Files now keeps the preview above the workspace window. Closing the preview returns the user to the same Files context and restores focus to the file action that opened it.

## Root cause

Signed-in production inspection proved the workspace overlay used z-index 10,000 while the document and image viewers used z-index 120. The preview was created correctly but appeared behind the current Files or Project panel, which looked like a failed open or a blank external-storage handoff.

## Product behavior

- Shared preview mounting places document and image viewers at z-index 120,100.
- Document and image viewers use dialog semantics and support Escape.
- Closing restores focus to the originating control.
- Saved-file open/download no longer falls through to a direct private Supabase Storage navigation.
- If an in-app viewer is unavailable, the user receives an in-app recovery message.
- The Files list no longer exposes the undefined `toolIcon` placeholder or code-fence-only titles.
- Accessible Open and Download labels remain specific to the saved item.

## Verification

- A production-matched browser fixture proved document and image previews above Files, in-app document download behavior, Escape/Done dismissal, and focus restoration.
- Signed-in production proved z-index 120,100 above the Files overlay at 10,000 for both document and image viewers.
- All 65 saved items rendered in the inspected owner account; no `toolIcon` leak appeared.
- The URL remained `/app`, each close returned to Files, and the browser console stayed free of errors.
- Full Python, JavaScript, production-preflight, and native web-bundle gates passed.
- Commit: `1fe8e9a2406c804703dc1bcf08cb5502c16118fb`.
- Deployment: `dpl_4Wr7VoFbmtvJPX8XzUg7xSQUkRR9`, READY with all six aliases and no alias error.

## Remaining evidence gate

Observe legitimate users opening, downloading, and reopening editable artifacts before claiming an artifact-retention effect. This release does not publish customer content or change file ownership, storage access, or analytics privacy.
