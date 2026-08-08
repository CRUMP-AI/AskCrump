# Ask Crump V1 New Body — QA Report

## Structural verification
- New `app.html` is a full replacement body, not a style patch.
- 92 DOM IDs detected; no duplicates.
- Every ID required by the current auth/app/settings/upload controllers is present.
- Account deletion is present both as an in-app control and an external web resource.
- No Google Fonts dependency in the application body.

## JavaScript / runtime
- `node --check` passes for the new shell, runtime, service worker, native builder, and CI checker.
- Active runtime preserves 4.4, 5.0, billing 5.1, 5.2, and 5.2.2 behavior layers.
- Active runtime does not load retired 5.2.4 branding.
- V1 CSS is given final cascade authority after preserved feature styles.
- No whole-document branding MutationObserver exists.

## Legacy 5.0 compatibility
Tested with the real `crump-5.0.js` from the existing 5.0 package underneath the new shell.

After more than four seconds:
- canonical header wordmark remained restored
- canonical library wordmark remained restored
- attachment control was successfully upgraded to `crump50-plus`
- send control was successfully upgraded to `crump50-send`
- zero browser page errors

## Interaction smoke test
- Research command forwards to the existing web-search action.
- Settings command forwards to the existing Settings controller.
- Task mode updates the composer prompt.
- Composer `has-content` state updates from real textarea input.
- No browser page errors.

## Visual QA
Rendered and inspected at representative phone and desktop sizes for:
- home / launchpad
- active conversation with file + generated artifact
- authentication
- Settings

Additional compatibility render included the existing 4.4 / 5.0 / billing 5.1 / 5.2 / 5.2.2 feature CSS underneath the new V1 body stylesheet.
- 390×844: no horizontal overflow
- 1440×1000: no horizontal overflow

## Asset verification
- All five user-supplied canon PNG masters remain byte-for-byte preserved.
- UI derivatives retain transparency and aspect ratio and are downscaled only for runtime efficiency.

## Security/static scan
- No Stripe live/test secret-key patterns packaged.
- No Stripe webhook signing-secret pattern packaged.
- No environment-variable values added.

## Required post-deployment validation
A local/static test cannot substitute for production and physical-device testing. Before store submission, repeat the functional matrix on the deployed web app and native TestFlight/Play test builds, including billing sandbox flows and real keyboard/safe-area behavior.
