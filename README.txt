Ask Crump 4.3.1 Sync Hotfix

Replace exactly these two files in the CRUMP-AI repository:
- public/chat-sync.js
- public/sw.js

Why:
- Preserves assistant replies across devices with message-level merging.
- Prevents one whole-device snapshot from erasing unique turns from another device.
- Forces explicit chat saves through pull -> merge -> push -> verify.
- Queues a second sync if another sync is already running.
- Reduces auto-sync interval from 60 seconds to 20 seconds.
- Bumps the PWA cache to ask-crump-shell-v4.3.1.

No backend, authentication, Supabase schema, billing, or Vercel routing files are changed.

Install:
1. Copy the contents of this folder into the root of the CRUMP-AI repository.
2. Choose Replace when prompted.
3. In GitHub Desktop, confirm only public/chat-sync.js and public/sw.js changed.
4. Commit: Fix cross-device assistant reply sync
5. Push origin.
6. Wait for Vercel to become READY.
7. Close Ask Crump on BOTH phone and laptop once, then reopen both.
