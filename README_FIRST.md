# Ask Crump — Direct Sidebar Replacement

This package is intentionally different from the previous handoff.

## IMPORTANT

There is NO apply script and NO patch command.

Copy the `public` folder from this ZIP into the root of your CRUMP-AI repository
and choose **Replace** when Windows asks about `public/runtime-body-v1.js`.

Two files are new:
- `public/crump-navigation-5.2.5.js`
- `public/crump-navigation-5.2.5.css`

One file is replaced:
- `public/runtime-body-v1.js`

Optional regression test:
- `tests/test_sidebar_navigation_runtime.py`

## Result

Runtime navigation becomes:

Desktop rail:
- New conversation
- Conversation library

Sidebar footer:
- Settings
- Plan & credits + live credit balance
- Legal & Privacy
- Account sync

The duplicate icon-only Settings and Billing rail destinations are removed from
the rendered DOM. The decorative Settings and Plan icons are removed from the
footer rows. The live credit badge remains attached to Plan & credits.

Tapping Settings or Plan & credits closes the mobile drawer before the existing
destination handler opens its screen.

## Why this package is direct-replacement safe

The existing Ask Crump frontend already uses versioned runtime layers loaded by
`public/runtime-body-v1.js`. This package adds one narrowly scoped final layer
instead of requiring a patch tool or overwriting several large application files.

## Commit title

Clean up redundant sidebar navigation on mobile

## Commit summary

Simplify Ask Crump navigation by removing duplicate Settings and billing
destinations, keeping the live credit balance attached to the primary Plan &
credits row, and closing the mobile drawer cleanly before opening Settings or
billing. Adds a final versioned navigation layer and regression coverage without
changing core product behavior.

## Commit body

- Remove duplicate icon-only Settings and billing rail destinations
- Keep Settings as the single explicit settings destination
- Keep Plan & credits as the single explicit billing destination
- Preserve the live credit balance within the Plan & credits row
- Remove decorative footer icons that visually read as duplicate controls
- Close the mobile drawer before Settings or billing opens
- Tighten footer spacing and alignment
- Add regression coverage for navigation de-duplication
