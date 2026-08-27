# Data Safety and Privacy Mapping

Use this engineering inventory to complete Apple App Privacy and Google Play Data Safety declarations. Reconcile it against the exact production SDKs, logging, contracts, and provider retention settings before submission.

| Data category | Collected | Purpose | Linked to account | Storage / recipient |
|---|---:|---|---:|---|
| Name and email | Yes | account, verification, recovery | Yes | Supabase; Resend for email delivery |
| Password | No plaintext | authentication | Yes | only a password hash in Supabase |
| Conversations and titles | Yes | AI service, history, cross-device sync | Yes | Supabase; free-plan generation may use Vercel AI Gateway and its hard-allowlisted provider; premium or credit-funded generation uses the configured premium AI/context provider |
| Attachment content | When submitted | requested analysis | Yes during request | configured AI provider; synchronized history retains limited file metadata |
| Video prompts and generation settings | When video is requested | generate or continue AI video | Yes | Google Gemini/Veo or Runway, depending on the selected engine; job metadata in Supabase |
| Generated video files | When generation succeeds | private playback, download, continuation, and cross-device library | Yes | copied from the generation provider into private Supabase Storage; provider output URLs are not used as permanent user assets |
| Message delivery/seen metadata | Yes | reliable messaging experience | Yes | Supabase |
| Check-in preferences/events | Optional | user-requested proactive follow-up | Yes | Supabase; free-plan check-ins may use Vercel AI Gateway and its selected provider; premium check-ins may use the configured premium AI provider |
| Crump Code task objective and public repository reference | Only when the disabled feature is later enabled and requested | plan or implement repository work | Yes | Supabase task history; Anthropic for coding-agent reasoning; short-lived no-secret Vercel Sandbox for repository analysis and verification |
| Crump Code result summary, patch, verification, and audit metadata | Only when the disabled feature is later enabled and requested | review, continuity, cost control, and safety audit | Yes | Supabase; audit events are content-free and public responses omit internal sandbox and usage identifiers |
| Response text for premium voice | Only when the disabled feature is later enabled and the user selects Read aloud | generate temporary spoken audio | Yes during request | ElevenLabs; Ask Crump returns a private non-cacheable MP3 and does not store text or audio for this flow |
| Native push token | Optional | deliver enabled check-ins | Yes/device linked | Supabase; APNs or FCM |
| Device/session information | Yes | persistent login, security, revocation | Yes | Supabase |
| Approximate IP/network information | Yes | security, rate limiting, abuse prevention | Yes | application/database logs and session records |
| Usage events | Yes | limits, cost control, abuse prevention | Yes | Supabase |
| AI response safety reports | When a user taps Report | moderation, policy enforcement, safeguard improvement | Yes | Supabase; reviewed by authorized Clever Crump staff |
| Subscription status | Yes | entitlement | Yes | Stripe or Apple/Google/RevenueCat; status mirrored in Supabase |
| Full card number | No | — | — | handled by Stripe or the platform store |
| Precise location | No | — | — | geolocation permission disabled |
| Contacts | No | — | — | no contacts integration |
| Advertising data | No in this build | — | — | no advertising SDK |

## User controls

- Check-ins are off by default.
- Notifications require an explicit native permission decision and can be disabled independently.
- Frequency, quiet hours, categories, and haptics are user-controlled.
- Users can delete chats, export history, revoke sessions, clear history, and permanently delete the account in-app.
- Every AI response has an in-app Report control. Reports contain the selected reason, optional comment, reported output, and limited preceding prompt context; they are deleted with the owning account.
- Crump Voice is explicit-action only and falls back to device speech when unavailable; its provider path remains disabled until disclosure and production configuration are approved.
- Crump Code accepts only public GitHub repositories in its initial disabled foundation; it does not receive private repository credentials or push source changes.

## Security controls

HTTPS; HTTP-only web cookies; native secure credential storage; hashed session/reset/verification credentials; password hashing; account ownership filters; request/auth rate limits; account-isolated cache keys; per-device revocation; idempotent reply jobs; protected cron endpoint; and atomic account deletion.

## Retention and submission review

Account/conversation/settings/presence data persists while the account is active unless deleted sooner. Provider, infrastructure backup, security, billing, fraud-prevention, and legally required records may follow separate schedules. Confirm production logs do not capture full credentials, prompts, attachment bodies, push private keys, or provider secrets. Video provider references used for native Veo continuation are server-only and short-lived; they are never exposed as permanent public media URLs. Runway-generated results are copied into private Supabase Storage before user access. Update declarations whenever an SDK, connector, analytics tool, notification provider, AI/video provider, or data type changes.

Crump Code task history, result summaries, patches, and verification receipts remain account-linked
until the owning project/account is deleted under the application's deletion workflow. Confirm the
new tables participate in production deletion tests before enabling the feature. Premium voice
text and audio are transient in Ask Crump, but ElevenLabs processing and retention must be checked
against the production account terms and reflected in public disclosures before activation.
