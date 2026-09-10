# Ask Crump client credential boundary release

Date: 2026-09-10  
Release commit: `f265e99`  
Production deployment: `dpl_4BQMZJoQuoy8pCg2yLR5LCgQENvS`

## Outcome

Every production and native-web build now fails before release if privileged provider credential
material appears in the public web source or the generated `dist` bundle. This protects the growing
web/PWA/native client surface from accidentally shipping a backend key while new AI, billing,
storage, voice, video, or infrastructure providers are integrated.

The guard scans text-bearing HTML, JavaScript, CSS, JSON, SVG, XML, manifest, and text files under
both required client roots. A missing client root is itself a failure. Symlinks and non-text media
are not followed or decoded.

## Protected credential classes

The fixed signatures cover:

- OpenAI and Anthropic secret keys;
- Stripe live secret/restricted keys and webhook signing secrets;
- Supabase backend-secret keys and decoded service-role JWT claims;
- Replicate, GitHub, SendGrid, and AWS secret-token signatures;
- private-key material; and
- hard-coded literals assigned to reviewed server-only configuration names, including ElevenLabs,
  Runway, Vercel, APNs, Stripe, Supabase, OpenAI, Anthropic, Replicate, and GitHub credentials.

The failure report contains only the credential class and repository-relative file path. It never
prints the matched value. Intentional client configuration such as Stripe publishable keys,
Supabase publishable keys, RevenueCat public SDK keys, domains, and ordinary Ask Crump product text
does not fail the gate.

## Verification

- The scanner's mandatory self-test detected synthetic OpenAI, Stripe, Supabase-secret, and
  Supabase service-role JWT samples and accepted the reviewed public-key examples.
- The current `public` and generated `dist` artifacts passed with no privileged signature.
- The production/native build completed through the new mandatory gate.
- The full Python suite passed 996/996; the JavaScript release contract validated 49 files,
  22/22 rough-to-useful attribution cases, 10/10 Word/PDF cases, 10/10 résumé cases, and the 14/14
  store-packet self-test.
- GitHub CI `34515071687`, Android source verification `34515071775`, and iOS source verification
  `34515071674` passed for the exact release commit.
- Vercel deployment `dpl_4BQMZJoQuoy8pCg2yLR5LCgQENvS` is READY. Its authoritative
  deploy log records the credential boundary passing immediately after the generated bundle and
  before deployment completion.

## Boundary

This is a deterministic client-artifact prevention gate, not a claim that backend secret storage,
provider dashboards, account permissions, key rotation, or runtime authorization have been fully
audited. Those controls retain their own server, provider, and owner-account gates. No credential,
provider setting, customer data, account, payment, generation, or production database row was read
or changed for this release.
