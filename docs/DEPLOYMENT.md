# Deployment Guide

## 1. Prepare a staging environment

Create a verified Supabase backup and run the migration in a staging project before production. Keep production and staging provider credentials separate.

Never commit:

- populated `.env` files;
- Supabase service-role keys;
- APNs `.p8` keys;
- Firebase service-account JSON;
- Stripe, RevenueCat, Anthropic, or OpenAI secrets;
- native signing certificates or keystores.

## 2. Apply the database migration

Run `migrations/001_python_backend.sql` from the Supabase SQL editor or an approved migration workflow.

Verify the core records:

```sql
select count(*) from public.users;
select count(*) from public.user_chats;
select count(*) from public.sessions;
select count(*) from public.check_in_preferences;
select email, count(*)
from public.users
group by email
having count(*) > 1;
```

Inspect representative conversations, account settings, and deletion tombstones. Do not remove legacy tables until the new deployment has completed cross-device and rollback validation.

## 3. Configure Vercel

Required production variables:

```text
APP_ENV=production
APP_URL=https://www.askcrump.com
COOKIE_SECURE=true
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
ANTHROPIC_API_KEY=...
CRON_SECRET=...
```

Use `.env.example` for optional integrations. Leave `COOKIE_DOMAIN` unset unless a tested cross-subdomain requirement exists.

The default text model is `claude-sonnet-5`. The default image model is `gpt-image-2`. Confirm access in the production provider accounts before deployment.

## 4. Deploy the web application and API

Connect the GitHub repository to Vercel and deploy a preview environment first. Validate:

- `/api/health`;
- registration and email verification;
- login and session restoration;
- conversation pull/push;
- message acknowledgement and reply jobs;
- account deletion;
- provider error handling;
- static asset caching.

Promote the preview deployment only after the staging migration and smoke tests pass.

## 5. Configure the check-in scheduler

`vercel.json` calls `/api/cron/check-ins` hourly. Vercel sends the configured `CRON_SECRET` as a bearer credential. Keep check-ins disabled for general users until internal accounts have completed volume and content review.

For another host, schedule an hourly authenticated `GET` request to the same endpoint.

## 6. Configure transactional email

Verify the sending domain, SPF, DKIM, and return-path settings. Test:

- verification emails;
- resend-verification behavior;
- password reset links;
- expired and reused tokens;
- provider outage behavior.

## 7. Configure billing

### Web

Create Stripe recurring prices and configure `/api/stripe/webhook`. Test checkout, customer portal access, renewals, cancellation, expiration, and webhook replay behavior.

### Native

Create Apple and Google subscription products, then configure RevenueCat products, offerings, entitlements, webhook authentication, and the secret API key. Test purchase, restore, product change, cancellation, billing issue, transfer, and expiration behavior.

## 8. Generate native projects

Install locked dependencies, then prepare only the platform being built:

```bash
npm ci
npm run store:prepare:android
```

On macOS for iOS:

```bash
npm ci
npm run store:prepare:ios
```

These commands create a missing platform, sync Capacitor, generate branded assets, configure the release version and platform requirements, and run platform-specific validation. The generated `ios/` and `android/` directories are ignored; reviewed source and scripts reconstruct them. Use `STORE_BUILD_NUMBER` for a strictly increasing upload build number. See `docs/STORE_LAUNCH_RUNBOOK.md` for signing and store submission.

## 9. Configure push notifications

### iOS

- Enable the Push Notifications capability.
- Configure the required entitlements and provisioning profile.
- Set APNs key, team, bundle, private-key, and environment variables.
- Test foreground, background, terminated, stale-token, and notification-tap flows on a physical signed device.

### Android

- Register the Android application in Firebase.
- Add `android/app/google-services.json` locally according to the project's secret-handling policy.
- Configure `FCM_PROJECT_ID` and `GOOGLE_SERVICE_ACCOUNT_JSON` on the server.
- Test permission, channel, icon, foreground/background, and deep-link behavior.

## 10. Release and monitor

Run the full test plan, then release through TestFlight and Google Play internal testing. Use staged production rollouts.

Monitor:

- authentication and session renewal failures;
- sync conflicts and duplicate-job responses;
- provider latency and errors;
- check-in volume and notification delivery;
- billing reconciliation;
- account-deletion failures;
- Vercel function duration and error logs.
