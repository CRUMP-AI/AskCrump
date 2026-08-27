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
- Every assistant response includes an accessible in-app **Report** action backed by a private, rate-limited moderation queue.
- Android native preparation locks compile/target SDK 36 and validates the release version and generated launcher assets.
- iOS native preparation bundles a base `PrivacyInfo.xcprivacy` and validates its Xcode Resources membership.
- `npm run store:prepare:android` and `npm run store:prepare:ios` rebuild generated native projects from reviewed source.
- `npm run store:verify:metadata` enforces current field limits and alignment between the structured
  en-US submission source and the reviewed listing draft.
- The reviewed lockfile supports a clean Node 22 `npm ci`; store preparation fails closed if the
  lockfile is ever removed.
- Android native preparation disables cleartext traffic and local app backup, then verifies the
  permanent package ID before any signing step.

## Release-time checklist outside this package

- Verify account deletion end-to-end against production data and third-party processors.
- Complete App Store privacy disclosures and Google Play Data safety declarations.
- Configure and approve Apple / Google consumable products and subscriptions.
- Exercise purchase, restore, refund, interrupted-purchase, and cross-device entitlement cases in sandbox/test environments.
- Complete age-rating questionnaires and review generative-AI/content disclosures as applicable.
- Provide reviewer access / demo credentials where required.
- Test on representative physical iPhone, iPad, and Android devices.
- Reconcile the production privacy policy with the actual data collection/retention behavior at launch.
- Apply `migrations/014_ai_content_reports.sql` before testing AI reports in production, then run Supabase security/performance advisors.
- Follow `docs/STORE_LAUNCH_RUNBOOK.md` for publisher identity, signing, native preparation, testing, and submission order.
- Review and adapt `docs/STORE_LISTING_COPY.md` against the exact signed release build.
- Follow `store/screenshots/README.md` and capture real UI from the signed build; do not use mockups
  as functionality evidence.
- Review `docs/STORE_READINESS_AUDIT_2026-08-27.md` for the current proved state and blockers.
