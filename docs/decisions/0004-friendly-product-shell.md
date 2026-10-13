# 0004: Friendly product shell and destination ownership

**Status:** Accepted

## Context

Ask Crump accumulated multiple ways to reach the same work. Desktop and mobile exposed different labels, Video was hidden inside Studios, Files was confused with Library, and experimental presentation views could appear to own settings or project actions that were only stored in the browser. The result was visually dense and made a capable product feel less predictable.

## Decision

The application presents one product-first navigation system:

- Desktop: Ask, Projects, Files, Library, Video, Autonomous (Beta), with Profile at the bottom.
- Mobile: Ask, Projects, Library, Video, and More. More contains Files, Autonomous (Beta), and Profile.
- Ask remains the default surface and retains the real conversation history and composer.
- Library is exclusively for books and manuscripts.
- Files delegates to the existing Files surface.
- Video, Autonomous, and Profile delegate to their existing production owners.
- The former Home, Studios, and presentation-only You views do not own production destinations.
- Existing internal route identifiers remain stable for compatibility and analytics. User-facing `Autonomous` maps to the existing `code` owner; `Profile` maps to `you`; Files temporarily reports through the existing Projects analytics vocabulary until a dedicated server dimension is introduced.

The visual system uses warm graphite surfaces, system typography, restrained gold accents, accessible contrast, comfortable spacing, and one clear action hierarchy. The redesign changes presentation and routing only; it does not change authentication, billing, chat synchronization, file storage, media generation, or server contracts.

## Consequences

- Users see fewer competing entry points and can reach Video directly.
- Mobile navigation stays legible at narrow widths while secondary destinations remain discoverable.
- Experimental local-only controls cannot masquerade as synced account behavior.
- Cache references and the service-worker revision must be updated whenever the shell assets change.
- Tutorial and store-facing navigation copy must follow this destination contract.
