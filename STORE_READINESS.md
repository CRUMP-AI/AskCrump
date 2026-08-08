# Ask Crump V1 — Store Readiness Foundation

This frontend rebuild is designed to preserve the existing store-sensitive architecture. It is not a guarantee of App Store or Google Play approval; final submission still requires live-device testing, store metadata, privacy/data-safety declarations, approved commerce products, and successful review.

## Preserved in the new body

- Clear in-app **Delete account** action under Settings → Account.
- External `/delete-account.html` deletion resource remains discoverable from Account settings.
- Legal & Privacy is available from both the conversation library and Settings.
- Native shell remains HTTPS-only with Android mixed content disabled.
- iPhone/iPad safe-area insets are respected.
- Primary coarse-pointer controls use large touch targets.
- Keyboard focus-visible states are provided.
- Reduced-motion and increased-contrast preferences are supported.
- No new tracking, advertising, analytics, or social-login SDK is introduced by this package.
- The web Stripe path is not substituted for the existing native purchase architecture.
- RevenueCat / Apple / Google native product hooks remain unchanged.
- Purchased-credit expiration semantics are not altered.

## Release-time checklist outside this package

- Verify account deletion end-to-end against production data and third-party processors.
- Complete App Store privacy disclosures and Google Play Data safety declarations.
- Configure and approve Apple / Google consumable products and subscriptions.
- Exercise purchase, restore, refund, interrupted-purchase, and cross-device entitlement cases in sandbox/test environments.
- Complete age-rating questionnaires and review generative-AI/content disclosures as applicable.
- Provide reviewer access / demo credentials where required.
- Test on representative physical iPhone, iPad, and Android devices.
- Reconcile the production privacy policy with the actual data collection/retention behavior at launch.
