# Technical Notes — Ask Crump 4.3

## Root cause of disappearing replies

The browser merge previously accepted a server chat when either condition was true:

```js
server.updatedAt > local.updatedAt || server.revision > local.revision
```

The database does **not** use that rule. Its compare-and-apply logic accepts a row when:

```text
server/update timestamp is newer
OR
same timestamp AND higher revision
```

The database also increments its stored revision on accepted writes. Therefore a server snapshot can legitimately have a higher revision while still being older than a newer local turn that has not completed its push. The old browser OR-condition let that older snapshot replace the newer local chat.

`renderMessages()` replaces the entire conversation DOM, so when the stale chat won, the assistant reply vanished visibly.

4.3 corrects the comparator and also protects a newer local message ID that is absent from the candidate server snapshot.

## Why no database migration is included

The `apply_chat_sync` function already has the correct last-write-wins ordering semantics. Changing the database would add risk without fixing the client-side mismatch.

## Why the visual refresh is an override layer

The current app contains working authentication, billing, settings, native/PWA behavior, and conversation logic spread across several established stylesheets. A last-loaded 4.3 layer gives the product a broad visual redesign without rewriting stable structural code. It also makes rollback simple.

`onboarding.js` loads the 4.3 CSS/JS because it is already present on both auth and app surfaces. The service worker pre-caches those assets in 4.3.
