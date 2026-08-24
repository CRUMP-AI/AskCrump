# Changelog

## 5.9.9 — 2026-08-24

### Image reliability
- Made Balanced image quality the default for both conversational requests and Image Studio while preserving Highest as an explicit user choice.
- Added one bounded retry for transient provider and network failures without retrying permanent rejections or long-running timeouts.
- Extended the image-provider deadline from 180 to 240 seconds inside the existing 300-second function budget so near-complete generations are not cancelled prematurely.
- Added privacy-safe image quality and aspect telemetry, and retained the attempted image model on failed traces, without recording prompts or file contents.

### Release
- Advanced the application release to 5.9.9 and the service-worker cache to revision 43 so installed clients receive the reliability defaults immediately.

## 5.9.8 — 2026-08-24

### Activation measurement
- Added a server-authoritative `StarterIntentReached` milestone for the first task category selected from the authenticated launchpad.
- Restricted the milestone to six safe categories and a fixed idempotency key; prompts, filenames, form contents, and arbitrary metadata never enter the analytics record.
- Preserved the server-only product-event table, RLS boundary, revoked browser-role access, and service-role-only recorder path.

### Release
- Advanced the application release to 5.9.8 and the service-worker cache to revision 42 so the next tester cohort can be measured from signup through starter intent, activation, and durable value.

## 5.9.7 — 2026-08-24

### Signup conversion
- Aligned the visible password requirements with the enforced 10-character, letter-and-number policy so prospective users are no longer told that an invalid 8-character password is acceptable.
- Reduced registration to one password field with an accessible Show/Hide control, clarified that signup is free and requires no card, and added privacy-safe validation-reason telemetry without collecting form contents.
- Sent new users directly to the task-oriented workspace launchpad instead of blocking their first useful action with a six-screen passive tour; the full tour remains available on demand.

### Release
- Advanced the application release to 5.9.7 and the service-worker cache to revision 41 so web and installed-app clients receive the corrected signup experience immediately.

## 5.9.6 — 2026-08-23

### Assistant identity
- Made the saved Assistant Name a server-authoritative conversational identity so the model recognizes, answers to, and naturally uses the user-selected name without confusing it with the Ask Crump product name.
- Reflected the selected name throughout the composer and Intelligence controls, including accessible labels and memory copy.

### Intelligence
- Reintroduced Deep mode as the clearer **Think longer** experience: an additional planning pass, high-effort response guidance, and a separate final-answer review for difficult work.
- Reserved Think longer for active Professional and Enterprise subscriptions, with synchronized UI entitlements and server-side enforcement that cannot be bypassed by modifying browser requests.
- Prevented free Auto mode and expired saved preferences from silently invoking the subscriber-only multi-pass workflow.

### Navigation
- Made every conversation selection render the chosen conversation and dismiss the mobile conversation drawer, including the correct expanded-state reset.
- Changed the Legal & Privacy brand return link to reopen the authenticated Ask Crump app instead of the Clever Crump landing page.

### Release
- Advanced the application release to 5.9.6 and the service-worker cache to revision 40 so installed PWAs receive the identity, intelligence, and navigation changes immediately.

## 5.9.5 — 2026-08-23

### Fixed
- Prevented iPhone focus zoom from leaving Video Studio and other Ask Crump surfaces enlarged after editing by enforcing iOS-safe text sizing across every mobile text field, textarea, select, and editable surface.
- Locked the installed app to its intended 1:1 viewport scale and removed the remaining pinch-zoom exception, while preserving ordinary one-finger scrolling.
- Aligned the iPhone Home menu and Intelligence controls to the same safe-area centerline so the two header buttons remain visually level.
- Moved the responsive stability stylesheet to final authority so dynamically loaded Projects & Create, Library, Settings, authentication, and future tool controls inherit the same mobile behavior.

### Release
- Advanced the application release to 5.9.5 and the service-worker cache to revision 39 so installed PWAs receive the viewport correction immediately.

## 5.9.4 — 2026-08-23

### Conversation startup

- Made every cold start or reload open on a clean new-conversation surface instead of restoring the last active conversation.
- Kept every previous conversation safely available in history and preserved deliberate conversation opens from history, notifications, and other in-app navigation.
- Reused an existing pristine starter when possible so repeated reloads do not accumulate empty conversation rows.

### Quality

- Added regression coverage that prevents last-conversation restoration from returning and guards against deleting or clearing conversation history during fresh startup.
- Advanced the application release to 5.9.4 and the service-worker cache to revision 38.

## 5.9.3 — 2026-08-23

### Acquisition measurement

- Preserved a prospect's privacy-safe first-touch acquisition channel from the public homepage through account creation and initial onboarding.
- Reduced known social referrers to channel names and unknown external referrers to `referral`; full URLs, campaign content, search terms, and user identifiers are never recorded.
- Kept CTA location separate from acquisition source so the business can distinguish which channel brought a customer from which page action converted them.

### Quality

- Added regression coverage for UTM/referrer handling, CTA propagation, registration intake, and server-authoritative account-event attribution.
- Advanced the application release to 5.9.3 and the service-worker cache to revision 37.

## 5.9.2 — 2026-08-23

### Acquisition and discovery

- Restored the public Ask Crump marketing homepage instead of redirecting every first-time visitor directly into the application sign-in screen.
- Preserved source and plan attribution across every first-party signup path and added a distinct returning-user sign-in route.
- Added canonical, Open Graph, social-card, structured-application, robots, and sitemap metadata so the product has a truthful indexable surface.
- Kept the authenticated application out of search results while preserving `/app` as the installed PWA and returning-user destination.

### Quality

- Added regression coverage that prevents the public homepage redirect from returning and verifies the marketing/app indexing boundary.
- Verified the restored funnel visually at desktop and mobile breakpoints with no browser warnings or errors.
- Advanced the application release to 5.9.2 and the service-worker cache to revision 36.

## 5.9.1 — 2026-08-23

### Professional formatting

- Rebuilt Word and PDF output around format-native academic, résumé, and business conventions instead of a shared branded template.
- Enforced exact academic typography, spacing, margins, heading hierarchy, list treatment, and reference hanging indents while keeping citations source-grounded.
- Refined résumés into restrained, single-column ATS-ready documents with stronger hierarchy and no visible product chrome.
- Reworked presentations into varied editorial layouts with readable typography, content-aware tables, and neutral slide furniture.
- Simplified spreadsheets into professional working models with compact workbook indexes, restrained formatting, typed data, and selective visual analysis.
- Polished manuscript title pages and book typography across Word and PDF while preserving editable, publication-oriented structure.

### Quality

- Removed visible Ask Crump branding from default user deliverables while retaining internal provenance metadata.
- Added regression checks for exact Word font slots, reference indentation, neutral page furniture, and professional-format conventions.
- Advanced the application release to 5.9.1 and the service-worker cache to revision 35.

## 5.9.0 — 2026-08-23

### Added

- Added outcome-first Document Studio paths for essays and reports, résumés and CVs, presentations, spreadsheets, and manuscripts.
- Added format-aware, editable Word, PDF, PowerPoint, and Excel finishing with academic, résumé, presentation, spreadsheet, and business profiles.
- Added source-aware research routing and automatic final verification for downloadable artifact requests.
- Added a checksum-locked app-identity pipeline that derives versioned web-install icons, the native icon source, and the native splash source from the permanent Ask Crump C-and-magnifying-glass mark.
- Added representative artifact fixtures and structural tests covering page setup, metadata, editability, spreadsheet types and formulas, presentation dimensions, and extractable PDF text.

### Quality and safety

- Prevented the document system from inventing citations, quotations, credentials, employment history, dates, metrics, research results, or financial inputs.
- Added spreadsheet formula-injection guards, explicit print areas, stable pagination, inferred business number formats, filters, frozen headings, and editable native tables.
- Replaced a fragile manuscript scene-break glyph with a cross-platform typographic break for consistent Word, PDF, and EPUB output.

### Changed

- Advanced the application release to 5.9.0 and the service-worker cache to revision 34 so installed customers receive the document-quality and identity updates.

## 5.8.5 — 2026-08-23

### Added

- Added a privacy-safe `ActivationReached` milestone when an account receives its first successful Ask Crump response.
- Added an account-scoped local guard so the activation event is attempted once, while the server remains the idempotent source of truth.

### Privacy

- Kept activation measurement limited to a fixed milestone key; prompts, responses, filenames, and arbitrary metadata are never sent to product analytics.

### Changed

- Advanced the service-worker cache to revision 33 so activation measurement reaches installed customers.

## 5.8.4 — 2026-08-23

### Added

- Added a deliberate Share action to every Ask Crump response, using the native share sheet on supported devices and a branded clipboard fallback elsewhere.
- Added a privacy-safe `ResponseShared` milestone so the response-sharing loop can be measured without storing prompts, response text, filenames, or personal data.

### Changed

- Limited shared responses to a practical excerpt and attached the canonical AskCrump.com destination for a clear recipient experience.
- Advanced the service-worker cache to revision 32 so the sharing feature reaches installed customers.

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
