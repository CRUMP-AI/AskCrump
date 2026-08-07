# Ask Crump 5.2.2

## Stability fixes
- Credit-pack taps now use a document-level capture path and always reach the server for known packs.
- Removed the silent client-side disabled-card failure mode; the backend now returns the real Stripe configuration error if one exists.
- One scroll controller owns the conversation reading position.
- New assistant replies anchor once at the top of the reply instead of forcing the conversation to the bottom.
- Legacy post-reply bottom-scroll calls are suppressed during the new-reply reading window.
- Manual history reading is respected; Crump will not yank the page while the user is actively reviewing older content.
- The scroll-to-newest button now has a high-contrast gold surface and dark arrow.
- Service worker and native loaders include the 5.2.2 layer.

No database migration and no environment-variable changes are included.
