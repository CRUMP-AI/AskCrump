# Ask Crump V1 — QA Report

## Automated / static checks
- ✅ master hash crump-mark-master.png
- ✅ master hash crump-wordmark-light-master.png
- ✅ master hash crump-wordmark-dark-master.png
- ✅ master hash crump-horizontal-light-master.png
- ✅ master hash crump-horizontal-dark-master.png
- ✅ transparent display PNG crump-mark.png
- ✅ reasonable display width crump-mark.png
- ✅ transparent display PNG crump-horizontal-light.png
- ✅ reasonable display width crump-horizontal-light.png
- ✅ transparent display PNG crump-horizontal-dark.png
- ✅ reasonable display width crump-horizontal-dark.png
- ✅ transparent display PNG crump-wordmark-light.png
- ✅ reasonable display width crump-wordmark-light.png
- ✅ transparent display PNG crump-wordmark-dark.png
- ✅ reasonable display width crump-wordmark-dark.png
- ✅ node --check crump-v1.js
- ✅ node --check runtime-config-v1.js
- ✅ node --check sw.js
- ✅ node --check build-native.mjs
- ✅ node --check check-javascript.mjs
- ✅ V1 runtime loads canonical shell
- ✅ V1 runtime omits retired branding layer
- ✅ behavior scripts preserve deterministic order
- ✅ styles fetch concurrently
- ✅ V1 CSS reclaims final cascade
- ✅ V1 body class
- ✅ no body-wide branding observer
- ✅ chat-only dynamic observer
- ✅ bounded legacy header recovery
- ✅ new V1 cache namespace
- ✅ non-bricking precache
- ✅ network-first V1 boot
- ✅ old Ask Crump caches retired
- ✅ native writes V1 runtime
- ✅ native loads V1 shell
- ✅ native omits 5.2.4 branding
- ✅ Android mixed content disabled
- ✅ HTTPS Android scheme
- ✅ native keyboard body resize
- ✅ manifest name
- ✅ manifest standalone
- ✅ manifest neutral orientation
- ✅ manifest theme
- ✅ installer contains /runtime-config-v1.js
- ✅ installer contains /crump-v1.css
- ✅ installer contains class=\"crump-v1\"
- ✅ installer contains /assets/brand/crump-horizontal-light.png
- ✅ installer contains Plan & credits
- ✅ installer contains .docx
- ✅ installer removes Google Fonts
- ✅ CI checks app V1 runtime
- ✅ CI checks brand assets
- ✅ CI rejects retired branding runtime
- ✅ safe-area layout
- ✅ reduced motion
- ✅ contrast mode
- ✅ coarse pointer ergonomics
- ✅ no Google Fonts URL in V1 CSS
- ✅ secret scan sk_live_
- ✅ secret scan sk_test_
- ✅ secret scan whsec_
- ✅ secret scan SUPABASE_SERVICE_KEY=

## Visual viewport matrix
- ✅ Auth · 320×700 — No horizontal overflow
- ✅ Auth · 390×844 — No horizontal overflow; logo/card visually inspected
- ✅ Auth · 430×932 — No horizontal overflow
- ✅ Auth · 768×1024 — No horizontal overflow
- ✅ Auth · 1024×768 — No horizontal overflow
- ✅ Auth · 1440×1000 — No horizontal overflow; visually inspected
- ✅ Home/chat · 320×700 — No horizontal overflow
- ✅ Home/chat · 390×844 — No horizontal overflow; visually inspected
- ✅ Home/chat · 430×932 — No horizontal overflow
- ✅ Home/chat · 768×1024 — No horizontal overflow
- ✅ Home/chat · 1024×768 — No horizontal overflow
- ✅ Home/chat · 1440×1000 — No horizontal overflow; visually inspected
- ✅ Conversation · 390×844 — PDF/user/assistant/artifact composition visually inspected
- ✅ Conversation · 1440×1000 — PDF/user/assistant/artifact composition visually inspected
- ✅ Settings / billing · 390×844 — Responsive stack visually inspected
- ✅ Settings / billing · 1440×1100 — Desktop hierarchy visually inspected

## Important release note
This package has been verified as a presentation-layer overlay. A final smoke test
on the live deployed site and real iOS/Android hardware is still required before
store submission. Store approval is ultimately determined by Apple and Google,
not by static code review alone.

The package intentionally does not modify production data, Supabase schema,
Stripe credentials, or billing entitlements.
