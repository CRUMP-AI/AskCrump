# Ask Crump V1 — New Body Architecture

## What changed

This package is a structural frontend rebuild. It does not restyle the legacy `app.html`; it replaces that page body with a new workspace architecture while preserving the proven application controllers and backend contracts.

### New application structure

**Desktop**
1. Brand rail — global actions and compact identity.
2. Conversation library — synchronized conversation navigation and account surfaces.
3. Workspace — contextual header, launchpad or conversation, and a dedicated command dock/composer row.

**Mobile / tablet**
1. Native-feeling safe-area-aware header.
2. Conversation library as a drawer.
3. Full-width workspace.
4. Composer/task dock in its own structural row, never floating over short conversations or generated artifacts.

**Authentication**
- Desktop uses a split-screen product story + authentication stage.
- Mobile collapses to a centered branded authentication card.
- Existing login, registration, verification, reset-password, terms, and onboarding controller IDs are preserved.

**Settings**
- Rebuilt as a two-pane workspace with Profile, Behavior, Account, and About sections.
- Existing settings input IDs remain intact for compatibility.
- Account deletion remains a first-class in-app action and exposes the external deletion resource.

## Brain/body separation

The new body deliberately preserves the current functional layers underneath:
- 4.4 intelligence and memory controls
- 5.0 multimodal upload, image, file, and artifact behavior
- 5.1 credit wallet / billing behavior
- 5.2 durable multimodal / artifact rendering
- 5.2.2 stable scrolling and checkout behavior

The retired 5.2.4 branding layer is **not loaded** by `runtime-body-v1.js`.

## Brand ownership

The five user-supplied transparent PNG masters are stored byte-for-byte in `public/assets/brand/`.
Optimized transparent derivatives are used for UI display so the application does not decode multi-megapixel assets for small interface placements.

- Horizontal white/gold wordmark: dark application surfaces
- Standalone C mark: compact global identity and Crump identity moments
- Black/gold variants: preserved for future light surfaces

## Legacy compatibility strategy

The V1 body exposes every DOM ID currently required by `auth-controller.js`, `app.js`, settings, billing, uploads, and account flows.

The 5.0 multimodal module still performs a delayed header rewrite. V1 protects only the two brand containers with narrow, idempotent `MutationObserver` guards. A legacy rewrite causes one corrective mutation; the second observer callback sees the correct single child and stops. There is no whole-document observer and no self-triggering mutation loop.

## Scroll/composer architecture

The composer occupies its own grid row instead of floating above the conversation. This removes a class of overlap and auto-scroll problems from the previous shell. `chatContainer` is the sole scrolling conversation surface, and 5.2.2 remains responsible for reply anchoring / manual-reading stability.

## Runtime ownership

`app.html` directly loads `crump-v1-body.css` to avoid a legacy-layout flash.
`runtime-body-v1.js` then loads the preserved feature layers and re-appends the V1 stylesheet last, giving the new body final cascade authority.

Boot-critical files use a fresh service-worker namespace and network-first strategy.
