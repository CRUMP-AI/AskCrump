# Changelog

## 5.8.3 — 2026-08-22

### Fixed

- Rendered Markdown tables as accessible, responsive tables instead of raw pipe-delimited text.
- Rendered quoted copy and numbered steps with designed blockquote and ordered-list presentation.
- Preserved the safe renderer's HTML escaping and URL protections while expanding its presentation support.
- Advanced the service-worker cache to revision 31 so the conversation polish reaches installed customers.

## 5.8.2 — 2026-08-22

### Added

- Added a private, account-level milestone ledger for activation, durable-artifact value, retention, paid-plan intent, and the verified Stripe subscription lifecycle.
- Added server-authoritative activation, durable-artifact, Checkout, billing-portal, and webhook events plus one authenticated workspace-open event per UTC day.
- Added an operating analytics contract that excludes prompts, responses, filenames, emails, payment details, prices, and arbitrary metadata.

### Security

- Locked the product-event table and idempotent recording function to the server service role, enabled row-level security, and separated preview events from production reporting.
- Made analytics writes fail open so an instrumentation outage cannot interrupt account, chat, artifact, or billing flows.

### Changed

- Advanced the application release to 5.8.2 and the service-worker cache to revision 30.

## 5.8.1 — 2026-08-22

### Added

- Preserved a prospect's Professional or Enterprise selection through registration, verification, onboarding, and sign-in, then opened the matching in-app plan for review without starting checkout automatically.
- Added a privacy-conscious `PlanIntentReached` funnel event containing only the selected plan and sanitized acquisition source.

### Fixed

- Made Saved Library cover URLs expire with their private storage signatures instead of remaining cached indefinitely.
- Added one automatic signed-URL refresh when a cover image fails, then restored the designed placeholder if the retry cannot load.
- Advanced the service-worker cache to revision 29 so the reliability and conversion fixes reach installed customers.

## 5.8.0 — 2026-08-22

### Added

- Added a transparent Free, Professional, Enterprise, and Crump Credits pricing section to the Clever Crump acquisition site.
- Added direct signup links from every primary marketing call to action so new prospects land on account creation instead of a returning-user sign-in screen.
- Added privacy-conscious Vercel Web Analytics page views and non-PII funnel events for marketing CTA intent, signup intent, signup submission, and successful account creation.

### Changed

- Reframed the public product copy around a currently available paid product instead of an unfinished product customers may eventually pay for.
- Updated the public release presentation, in-app About signature, package metadata, and backend version to 5.8.0.
- Advanced the service-worker cache to revision 28 so the signup and analytics runtime reaches installed customers promptly.

## 5.7.2 — 2026-08-22

### Fixed

- Restored dependable sidebar access to Settings, Plan & credits, and Projects when late UI hydration replaces destination elements or drops their original listeners.
- Kept each product module's normal click handler as the primary path, with a guarded fallback that opens a destination only when it is still closed.
- Made the navigation bundle boot-critical and network-first so customers receive the repair promptly instead of remaining on a stale service-worker copy.
- Replaced an undefined Library muted-text token with the canonical application theme tokens.
- Added regression coverage for the revenue, account, and Projects navigation paths and advanced the service-worker cache to revision 27.

## 5.6.1 — 2026-08-17

### Fixed

- Allowed authenticated inline video playback from Ask Crump's private Supabase Storage domains through the web Content Security Policy. Saved Library previews remain private and still use short-lived signed URLs.
- Added a release regression guard so future CSP changes cannot silently block private video previews again.

## 5.6.0 — 2026-08-17

### Added

- Added a final store-debut polish layer that normalizes buttons, links, focus states, touch targets, studio hierarchy, billing surfaces, and responsive behavior without replacing the proven 5.x product architecture.
- Added Projects and Video as first-class launchpad actions so important creation workflows are easier to discover from the empty workspace.
- Added a current six-step product tour covering Projects, creation tools, Video Studio, scene continuation, and the Saved Library.
- Added an updated Clever Crump parent-company page that reflects Ask Crump's current Projects, long-form, Saved Library, and multi-engine video capabilities.

### Changed

- Renamed the creation workspace to “Projects & Create” and simplified video status, Founder Lab, Library, and action copy.
- Standardized video result actions so links and buttons share one visual system and the Download video action no longer renders as a raw underlined link.
- Moved the legacy 4.3 runtime dependency into the deterministic runtime loader instead of loading it as an onboarding side effect.
- Improved Studio tab keyboard semantics, settings access to the product tour, mobile spacing, text sizing, and responsive touch targets.
- Updated PWA product metadata and store-facing copy to reflect Projects, manuscripts, saved creations, Runway Cinematic video, and native scene continuation.
- Advanced the service-worker cache to revision 12.

## 5.5.0 — 2026-08-17

### Added

- Added a provider-agnostic Crump Video Engine with Quick, Extendable, and Cinematic generation paths.
- Added native Veo 3.1 Fast scene continuation with durable job lineage, provider-reference expiry, and private-storage size safeguards.
- Added an optional server-only Runway Gen-4.5 provider with plan-aware 5/10 second generation, attribution, and provider-cost circuit breakers.
- Added continuation controls to completed compatible videos and Saved Library items.

### Changed

- Preserved Veo 3.1 Lite as the existing Quick video path and made expensive video compute explicitly credit-metered behind Professional/Enterprise access.
- Made video failure accounting provider-aware so billable moderation rejections are not automatically treated like infrastructure failures.
- Reduced the default generated-video safety ceiling to 45 MB for compatibility with the current storage tier; it can be raised deliberately when storage capacity is upgraded.
- Fixed Windows JavaScript syntax validation by converting file URLs to native filesystem paths before invoking Node.
- Advanced the application to 5.5.0 and service-worker cache revision 11.

## 5.4.1 — 2026-08-15

### Added

- Added leased, resumable full-manuscript jobs with pause, resume, cancellation, progress, automatic export, and a protected minute worker.
- Added founder/staff lab access that bypasses Ask Crump message, feature, credit, and Project limits without changing customer billing records.
- Added actionable, sanitized OpenAI image and Gemini video provider diagnostics and exposed the configured non-secret model names.

### Changed

- Made book-scale chat requests persist their workspace before any model call, eliminating the 90-second request-timeout failure mode.
- Enabled video generation by default when a Gemini key is configured while preserving the explicit emergency-disable flag.
- Advanced the service-worker cache to revision 8.

## 5.4.0 — 2026-08-15

### Added

- Introduced a durable long-form workflow that turns book-scale chat requests into persistent Project and Manuscript workspaces instead of truncating them into a single response.
- Added AI manuscript blueprints, chapter-purpose continuity, target-word progress, one-click next-chapter drafting, and chat-to-workspace handoff cards.
- Added visible Document and Manuscript composer modes and natural-language detection for Word, PDF, presentation, spreadsheet, Markdown, and text deliverables.
- Added a server-managed internal entitlement for founder, staff, and QA access that remains separate from customer billing records.

### Changed

- Opened manuscript creation and KDP-aware DOCX, PDF, and EPUB export to every tier; Free accounts can use Crump Credits for AI planning and drafting.
- Made the system capability contract explicit so the assistant no longer falsely claims that Ask Crump cannot create or export files.
- Restored Projects, Manuscripts, navigation, stability, and subscription layers to native builds for web/mobile feature parity.
- Advanced the application and service-worker release to 5.4.0 / cache revision 7.

## 4.2.0 — 2026-08-01

### Changed

- Decomposed the API entry point into domain routers and a dedicated application factory.
- Reworked repository documentation around product architecture, operational boundaries, and reviewable engineering decisions.
- Updated the default OpenAI image model to `gpt-image-2`.
- Removed promotional and implementation-history language from user-facing and repository-facing copy.
- Standardized client logging, attachment previews, legal copy, and version metadata.
- Corrected password-recovery layering, account-dialog focus handling, notification rendering, and destructive-action confirmation.
- Hardened the database migration to remove legacy raw session credentials and fail on incomplete data conversion.
- Consolidated conversation, attachment, account, and native-shell styling into defined design tokens.

### Added

- GitHub Actions quality checks for Python and JavaScript.
- Security policy, contribution guide, pull-request template, editor configuration, and project metadata.
- Architecture decision records for synchronization, message presence, and proactive check-ins.

## 4.1.0 — 2026-07-30

- Introduced the FastAPI backend, persistent opaque sessions, synchronized conversations, message delivery states, proactive check-ins, native push support, and web/native billing separation.
