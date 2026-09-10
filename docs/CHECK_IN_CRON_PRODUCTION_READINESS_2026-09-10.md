# Protected check-in scheduler production readiness

Date: 2026-09-10

## Outcome

The production check-in scheduler is configured and reaching Ask Crump through its protected
hourly route. This closes the source-and-runtime portion of the App Store and Google Play
check-in scheduler gate. It does not enable check-ins for any user, prove push delivery, or replace
the signed-device notification tests that remain before store submission.

## Evidence

A read-only Vercel production aggregation for the trailing 24 hours reported exactly **24**
requests to `/api/cron/check-ins`, matching the committed `0 * * * *` schedule. The only 4xx
routes in the same complete window were unrelated `/api/features` and `/api/version` requests;
there was no 5xx response or grouped runtime error. Therefore all 24 scheduled check-in calls
completed outside the 4xx/5xx error boundary.

The production handler fails closed whenever `CRON_SECRET` is absent or the bearer credential
does not match. Its successful hourly execution therefore verifies that the Vercel scheduler and
protected credential path are configured together. Existing automated coverage separately proves
that a missing or incorrect credential returns HTTP 401.

No endpoint was invoked manually for this review. No account, prompt, response, conversation,
Project, file, push token, notification, check-in, product event, or customer identifier was read,
created, or changed.

## Remaining store boundary

- Check-ins remain optional and disabled by default.
- Signed iPhone and Android candidates still need foreground, background, terminated-state,
  permission, quiet-hours, cooldown, and deep-link testing with owner-controlled APNs/FCM setup.
- Store products, RevenueCat public keys, signing credentials, reviewer access, screenshots,
  console declarations, and final owner approval remain separate unresolved gates.
