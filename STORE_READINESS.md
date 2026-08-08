# Store-readiness guardrails preserved in V1

This revamp is a presentation-layer rebuild. It does not weaken the existing security or purchase architecture.

Preserved:
- in-app Delete account entry in Settings
- external /delete-account.html route
- in-app Legal & Privacy access
- HTTPS-only native configuration
- Android mixed-content disabled
- native credit/subscription billing hooks remain RevenueCat / store based
- web Stripe remains web-only
- account data and chat synchronization remain server-authoritative
- accessible labels already present in the HTML are retained
- safe-area handling for iPhone / iPad
- reduced-motion support
- high-contrast support
- 48px primary touch targets for coarse pointers
- no new tracking SDKs
- no new analytics SDKs
- no third-party social login introduced

Release-time work still required outside this ZIP:
- App Store privacy disclosures
- Google Play Data safety form
- final App Store / Play product configuration
- IAP / Play Billing product approval
- age-rating questionnaires
- store screenshots / metadata
- final device accessibility testing
- privacy-policy review against production data practices

## Compliance posture
V1 is designed to preserve the existing store-sensitive architecture and make
review-critical controls discoverable. It should be treated as a store-readiness
foundation, not a guarantee of approval. Final review still requires store
metadata, privacy/data-safety declarations, approved in-app products, and
on-device testing.
