# Changelog

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
