# Registration exploration measurement release — 2026-08-29

Status: verified delivery; legitimate visitor outcome pending

## Decision

Measure the first meaningful choice after a cold visitor reaches registration: beginning account
creation or selecting the restrained route to evaluate Ask Crump first. Do not change authentication
policy, add form friction, or claim a conversion problem from the small anonymous cohort alone.

## Evidence before the change

- The trailing-seven-day Vercel dashboard showed 116 visitors, 435 page views, and a directional
  57% bounce rate across all environments.
- Content-free events showed 30 visitors and 47 total `SignupIntent` events, but only two visitors
  and two total `SignupStarted` events.
- The newly shipped registration exploration link had no event, so abandonment and intentional
  product evaluation were indistinguishable.
- The internal-excluded Supabase production funnel from the comparable lower bound still returned
  zero accounts at all 18 stages. The artifact-journey snapshot returned no rows. The current
  controllable uncertainty is therefore before account creation, not inside artifact generation or
  monetization.
- These anonymous dashboard totals may include internal, automated, repeated, or preview traffic.
  They are directional evidence only and cannot support a signup-rate claim.

## Change

- Selecting the registration exploration link now records `RegistrationExplore` through the
  existing Vercel Web Analytics boundary.
- The event contains only the existing allowlisted `source`, `acquisition`, `plan`, and `intent`
  categories plus one allowlisted `destination` category:
  - `overview`;
  - `document`;
  - `presentation`;
  - `resume`; or
  - `video`.
- The listener does not delay, prevent, or replace navigation.
- Invalid or modified destination values fail closed to `overview`.
- No email, account ID, URL, referrer URL, content, credential, file, conversation, artifact,
  payment detail, or free-form value is collected.
- Authentication, verification, session handling, pricing, entitlements, providers, database
  schema, and customer data did not change.

## Executable proof

- The credential-free cold-entry fixture uses the real authentication controller and blocks its
  exploration navigation locally, allowing the queued analytics payload to remain visible without
  contacting production or creating an account.
- A local browser opened a presentation-intent registration handoff and selected “See presentation
  examples first.” It recorded exactly the expected progression:
  - `SignupIntent` with `location=deep-link`; then
  - `RegistrationExplore` with `destination=presentation`.
- The event retained only `source=hero`, `acquisition=facebook`, `plan=unspecified`,
  `intent=presentation`, and the destination category. The fixture contained no production URL and
  made no production write.

## Verification

- Feature commit: `a094348` (`Measure registration exploration choices`).
- Production deployment: `dpl_J6MZSx7Z77u9Wi2c2V52WsxPjghh`, `READY`.
- The exact production authentication asset returned HTTP 200 and contained the destination
  allowlist, event name, listener, and initialization call.
- All 441 automated tests passed.
- All 45 JavaScript files validated.
- Production preflight, native web-bundle creation, and store-metadata checks passed.
- The inspected deployment window contained eight HTTP 200 responses, no warning/error/fatal log,
  and no runtime error cluster.
- Production verification did not click the link and created no analytics event, account,
  conversation, message, artifact, Project, payment, social publication, or Search Console change.

## Decision boundary

Evaluate the new fork after the first of:

- 50 additional legitimate `SignupIntent` visitors after this deployment; or
- 14 full days of post-deployment traffic.

Segment `RegistrationExplore` and `SignupStarted` by allowlisted acquisition, device, intent, and
destination before changing authentication. Do not scale acquisition until at least one legitimate
external account reaches activation. A high exploration share would prioritize stronger public
proof and capability continuity; a low exploration share with persistently low signup interaction
would prioritize traffic-quality and registration-friction diagnosis. No threshold outcome is
claimed before the boundary is reached.
