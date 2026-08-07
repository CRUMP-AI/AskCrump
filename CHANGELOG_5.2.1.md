# Ask Crump 5.2.1 — Document & Checkout Hotfix

This hotfix addresses two issues confirmed during live 5.2 testing.

## Large DOCX handoff
- Keeps a concise current-attachment cue adjacent to the current user turn.
- Recursively detects current uploaded-file context even if orchestration nests it.
- Preserves the large-document sampled context while preventing Crump from claiming a successfully resolved attachment is missing.
- Especially improves emoji-only / short follow-up turns with an attached manuscript.

## Crump Credits checkout
- Replaces per-button-only checkout binding with a single delegated capture-phase handler.
- Makes the entire credit pack card actionable, while retaining the explicit Add credits button.
- Survives billing card hydration/re-rendering and improves iOS Safari tap reliability.
- Uses same-tab Stripe navigation after the server returns the Checkout URL.

## Version
- Backend/app version: 5.2.1
- PWA shell cache: ask-crump-shell-v5.2.1
