# Data Safety and Privacy Mapping

Use this engineering inventory to complete Apple App Privacy and Google Play Data Safety declarations. Reconcile it against the exact production SDKs, logging, contracts, and provider retention settings before submission.

| Data category | Collected | Purpose | Linked to account | Storage / recipient |
|---|---:|---|---:|---|
| Name and email | Yes | account, verification, recovery | Yes | Supabase; Resend for email delivery |
| Password | No plaintext | authentication | Yes | only a password hash in Supabase |
| Conversations and titles | Yes | AI service, history, cross-device sync | Yes | Supabase; relevant content sent to configured AI/context providers |
| Attachment content | When submitted | requested analysis | Yes during request | configured AI provider; synchronized history retains limited file metadata |
| Message delivery/seen metadata | Yes | reliable messaging experience | Yes | Supabase |
| Check-in preferences/events | Optional | user-requested proactive follow-up | Yes | Supabase; conversation content may be evaluated by the AI provider |
| Native push token | Optional | deliver enabled check-ins | Yes/device linked | Supabase; APNs or FCM |
| Device/session information | Yes | persistent login, security, revocation | Yes | Supabase |
| Approximate IP/network information | Yes | security, rate limiting, abuse prevention | Yes | application/database logs and session records |
| Usage events | Yes | limits, cost control, abuse prevention | Yes | Supabase |
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

## Security controls

HTTPS; HTTP-only web cookies; native secure credential storage; hashed session/reset/verification credentials; password hashing; account ownership filters; request/auth rate limits; account-isolated cache keys; per-device revocation; idempotent reply jobs; protected cron endpoint; and atomic account deletion.

## Retention and submission review

Account/conversation/settings/presence data persists while the account is active unless deleted sooner. Provider, infrastructure backup, security, billing, fraud-prevention, and legally required records may follow separate schedules. Confirm production logs do not capture full credentials, prompts, attachment bodies, push private keys, or provider secrets. Update declarations whenever an SDK, connector, analytics tool, notification provider, or data type changes.
