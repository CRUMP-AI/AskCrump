# Ask Crump V1 — Revamp Blueprint

## Design thesis
Ask Crump should feel like a premium working environment, not a chat page with features bolted onto it.

V1 uses:
- deep graphite / near-black surfaces
- warm metallic gold only for hierarchy, status, and intentional action
- the real Ask Crump PNG wordmarks rather than recreated text
- system typography for reliability and platform-native rendering
- one spacing, radius, shadow, and motion language across web and native shells
- responsive behavior designed for iPhone, Android, tablet, laptop, and desktop

## Ownership model
V1 is the canonical shell owner.

Preserved behavior layers:
- 4.3 conversation enhancement
- 4.4 intelligence and memory controls
- 5.0 multimodal upload / image / artifact behavior
- 5.1 credit wallet and billing surfaces
- 5.2 durable attachment surfaces
- 5.2.2 checkout and stable reply scrolling

Deliberately not loaded:
- 5.2.4 branding layer

That prevents the latest branding/cache conflict from competing with the V1 shell.

## V1 visual ownership
- authentication
- onboarding
- app header
- navigation/sidebar
- empty state
- chat typography
- user messages
- assistant metadata
- composer
- file / image / artifact presentation
- attachment/tool sheets
- settings
- intelligence panel
- billing
- toasts
- account dialogs
- responsive breakpoints
- reduced-motion and high-contrast behavior

## Brand mapping
- dark app header: horizontal white/gold Ask Crump
- dark sidebar: horizontal white/gold Ask Crump
- auth/onboarding: horizontal white/gold Ask Crump
- assistant avatar / empty state / billing mark: standalone C mark
- black/gold variants remain preserved for future light surfaces

## Versioning note
“V1” in this package means the first canonical interface architecture. It does **not**
reset the public App Store / Google Play version number yet. The public product can
be reset to 1.0 when the complete native release is actually store-ready.
