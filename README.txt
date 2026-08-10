ASK CRUMP — UI Stability Fix

This patch is built against the current GitHub main branch inspected on August 10, 2026.

Replace/add these files in the repository:
- public/runtime-body-v1.js  (replace)
- public/sw.js               (replace)
- public/crump-v1-stability.css (new)
- public/crump-v1-stability.js  (new)

Fixes:
1. iPhone + attachment sheet no longer shifts half off-screen.
2. Short desktop/laptop viewports compact the home launchpad so the Crump mark,
   greeting, headline, four launch cards, mode strip, and composer can fit
   without the top of the mark being clipped.
3. Replaces the visually overcomplicated Settings gear with a clean,
   consistent 21px settings glyph.
4. Crump Controls stays open while changing response mode, memory,
   automatic tools, answer checking, and Web/Image/Code controls. It closes
   only from its close button, Escape, an intentional product-tour action,
   or a true outside click.
5. Service-worker cache bumped to r3 so mobile/PWA clients pick up the fix.

Suggested GitHub Desktop commit summary:
Fix responsive UI and Crump Controls behavior
