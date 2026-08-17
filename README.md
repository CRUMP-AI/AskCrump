# Ask Crump 4.3 — Conversation Revamp

This package is a drop-in source update for the current Ask Crump repository.
It intentionally leaves the working FastAPI authentication, Supabase security model, billing, memory, and chat backend alone.

## What changes

### 1. Fixes disappearing Crump replies
`public/chat-sync.js` now mirrors the database conflict rule:

- newer `updatedAt` wins;
- `revision` only breaks an exact timestamp tie;
- an in-flight local turn that is absent from an older server snapshot is protected from being discarded.

This prevents the 60-second pull → push → pull sync loop from replacing a newer local conversation with an older server snapshot simply because the server revision is numerically higher.

### 2. Replaces the tutorial
`public/onboarding.js` and `public/onboarding.css` replace the old 7-step spotlight tour with a calmer five-part product tour:

1. Meet Crump
2. More than chat
3. Continuity
4. Optional check-ins
5. Start chatting

The tutorial API is unchanged (`autoStart`, `restart`, etc.), so `auth-controller.js` does not need to change.
The completion key is bumped to `v4`, so existing users see the new tour once.

### 3. Full interface polish
`public/crump-4.3.css` and `public/crump-4.3.js` remain compatibility layers, now loaded deterministically by the runtime before later product layers. `public/crump-polish-5.6.css` and `.js` are the final-authority store-debut polish layer.

Highlights:
- compact mobile header with the C mark and a quiet status line;
- more usable conversation space;
- open/editorial Crump replies instead of a heavy assistant bubble;
- refined user message bubbles;
- subtle Crump identity marker per assistant turn;
- smaller Copy / Listen actions;
- floating premium composer with a clear active send state;
- proper paperclip attachment icon and upward send arrow;
- Image / Web / Code chips that disappear while composing;
- improved iPhone visual-viewport / keyboard behavior;
- new empty-conversation state with starter prompts;
- conversation sidebar previews show the last message instead of “N messages”;
- cleaner sidebar, settings, modal, and auth presentation;
- password guidance corrected at runtime to match backend validation (10+ characters, at least one letter and one number);
- reduced-motion and 44px-class touch-target considerations retained.

### 4. Service worker + routing persistence
`public/sw.js` moves the shell cache to `ask-crump-shell-v4.3.0` and includes the two new 4.3 assets.
API traffic remains network-only.

`vercel.json` includes the production-critical rewrite:

```json
{
  "source": "/api/(.*)",
  "destination": "/api"
}
```

Do not remove that rewrite. It is the routing fix that made production login work.

## Files in this package

Replace/add these exact paths in the repository:

- `vercel.json` — replace
- `public/chat-sync.js` — replace
- `public/onboarding.js` — replace
- `public/onboarding.css` — replace
- `public/sw.js` — replace
- `public/crump-4.3.css` — add
- `public/crump-4.3.js` — add

Nothing else needs to be deleted.

## Safest GitHub Desktop install

1. Open the local `CRUMP-AI` repository folder from GitHub Desktop.
2. Copy the contents of this package into the repository root.
3. Choose **Replace** when prompted for the five existing files.
4. Confirm GitHub Desktop shows exactly the expected modified/new files above.
5. Commit with a message such as `Ask Crump 4.3 conversation revamp`.
6. Push to `main`.
7. Let Vercel finish the production deployment before refreshing Ask Crump.

## First-load note

Because Ask Crump is a PWA, the previous service worker can serve the old shell for the page that discovers the update. After Vercel is READY, close the Ask Crump tab/PWA once and reopen it. The new `v4.3.0` service worker then owns the shell.

## Acceptance test

1. Sign in normally.
2. Restart the tutorial from Settings and walk through all five cards.
3. Open a chat and send a message.
4. Wait for Crump’s reply.
5. Begin typing the next message and keep the page open for more than 60 seconds.
6. Crump’s previous reply must remain visible.
7. Send the next message; its status should progress normally rather than leaving a user-only tail.
8. Open the sidebar and confirm previews show the latest message text.
9. Test Image / Web / Code, attachment preview, Settings, and the mobile keyboard.

## Rollback

Revert the 4.3 commit in GitHub. The update is intentionally isolated so the backend and database do not need a rollback.
