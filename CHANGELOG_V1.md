# Ask Crump V1 — Interface Revamp

## Canonical shell
- One final visual layer now owns the application presentation.
- Retains proven feature modules underneath instead of rewriting backend behavior.
- Removes the 5.2.4 branding layer from the V1 runtime path.
- Adds a new runtime entrypoint: `runtime-config-v1.js`.

## Brand system
- Preserves all five supplied PNG masters byte-for-byte.
- Adds optimized transparent display derivatives for UI performance.
- Uses the horizontal white/gold wordmark on the dark header, auth, onboarding, and sidebar.
- Uses the standalone mark for assistant identity, billing identity, and the empty state.
- Keeps black/gold variants available for future light surfaces.

## Core UI
- Rebuilt auth presentation.
- Rebuilt navigation/sidebar.
- Rebuilt conversation typography and message hierarchy.
- Rebuilt empty state.
- Rebuilt floating composer.
- Refined durable file, image, and generated artifact presentation.
- Refined attachment/tool sheets.
- Refined Crump intelligence controls.
- Refined Settings.
- Refined Plan & credits.
- Refined toast and account-dialog presentation.

## Responsive / accessibility
- Safe-area-aware iPhone/iPad layout.
- Phone, tablet, laptop, and desktop breakpoints.
- 48px primary coarse-pointer controls.
- Keyboard focus-visible treatment.
- Reduced-motion support.
- Increased-contrast support.
- No external web-font dependency in the core shell.

## Reliability
- Boot-critical service-worker requests are network-first.
- Previous Ask Crump caches are retired on V1 activation.
- Cache installation uses `Promise.allSettled` so a single optional asset does not brick installation.
- V1 CSS is preloaded to prevent legacy flash, then re-appended after feature styles to own the final cascade.
- V1 branding recovery is bounded around the two known 5.0 delayed shell passes; there is no global self-triggering branding observer.
- GitHub JavaScript CI now validates the V1 integration contract.

## Not changed
- Python backend
- Supabase schema
- server-authoritative chat persistence
- authentication/session architecture
- Stripe web credit checkout
- RevenueCat/native billing architecture
- credit ledger semantics
- multimodal upload APIs
- document / image generation APIs
