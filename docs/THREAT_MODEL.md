# Threat Model

## Scope

This document covers the public web client, Capacitor mobile clients, FastAPI service, Supabase database, model and search providers, billing providers, email delivery, and push-notification infrastructure.

## Protected assets

- account credentials and session tokens;
- conversation content and attachments;
- service-role and provider credentials;
- subscription and usage state;
- push notification tokens;
- account deletion and recovery workflows.

## Trust boundaries

1. **Client to API:** every client-supplied identifier, timestamp, setting, and message is untrusted.
2. **API to Supabase:** the API uses service-role access and must enforce account ownership before every operation.
3. **API to external providers:** only the minimum required content is transmitted for the requested operation.
4. **Billing webhooks:** provider signatures or shared authorization are required before subscription state changes.
5. **Scheduled check-ins:** the cron endpoint requires a server-held bearer secret.

## Primary threats and controls

| Threat | Control |
|---|---|
| Session theft | HTTP-only, secure, same-site web cookie; native secure storage; hashed server token; revocation and expiration |
| Account enumeration | Uniform recovery response; rate limiting; verification tokens stored as hashes |
| Cross-account data exposure | Server-derived user ID; account filters on every database operation; account-scoped local caches |
| Conversation overwrite or resurrection | Atomic revision comparison; stable chat IDs; deletion tombstones; final synchronization pull |
| Duplicate model responses | Idempotent message job claim keyed by user and message ID |
| Client manipulation of limits or subscription | Server-authoritative usage and billing state |
| Oversized or malformed input | Request-size middleware; Pydantic validation; attachment count, type, and decoded-size limits |
| Cross-site scripting | Escaped message rendering, protocol allowlist for links, no inline event handlers, restrictive script policy |
| Clickjacking | `frame-ancestors 'none'` and `X-Frame-Options: DENY` |
| Credential disclosure | Environment-only secrets, repository ignore rules, server-side provider calls |
| Forged billing events | Stripe signature verification and RevenueCat webhook authorization |
| Push notification leakage after account switch | Installation ownership transfer; token disablement on logout and device revocation |
| Abusive proactive messaging | Explicit opt-in, quiet hours, unanswered-message suppression, category controls, bounded frequency |

## Residual risks

- A compromised end-user device can expose content displayed or cached on that device.
- Model providers can return inaccurate or unsafe output despite system instructions.
- Search summaries can contain misleading source material.
- Availability depends on Supabase, hosting, model, billing, email, and notification providers.
- Legal, privacy, and store-policy compliance requires review against the actual production configuration and jurisdictions served.

## Validation cadence

Review this threat model when adding a provider, changing authentication, changing data retention, introducing a new client platform, or modifying billing, notification, or account-deletion behavior.
