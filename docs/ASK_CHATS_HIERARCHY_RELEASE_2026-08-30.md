# Ask and Chats hierarchy release

Date: 2026-08-30
Production version: `5.9.76`

## Outcome

Ask Crump's desktop rail now presents the promised five product destinations without making
Chats look like a competing sixth destination. Chats remains permanently visible and one click
away, but it is visually and programmatically treated as Ask's conversation drawer.

This resolves a deterministic hierarchy mismatch found during the first-visit-to-first-work
audit: Ask and Chats could both appear active at the same time even though Ask is the current
destination and Chats only controls the adjacent conversation panel.

## Product contract

- Ask is the sole current destination while the main conversational workspace is visible.
- Chats is a subordinate utility immediately beneath Ask and remains discoverable on desktop.
- An open conversation drawer uses the quiet `is-open` state, never the destination
  `is-active` state.
- The control exposes `Hide Chats` while open and `Show Chats` while closed.
- Collapsing the drawer sets the conversation panel to hidden and inert; reopening restores it.
- Projects, Create, Library, and You retain their existing destination behavior.
- The mobile five-destination navigation is unchanged.

No authentication, registration, conversation, Project, Library, generation, billing,
entitlement, pricing, private-data, or backend behavior changed.

## Verification

- All 522 Python tests passed.
- All 45 JavaScript files passed the repository integration validator.
- Production preflight and the native web-bundle build passed.
- Diff integrity passed.
- A local real-runtime fixture recorded zero browser errors and proved the exact open, collapsed,
  and reopened drawer states.
- The signed-in production workspace proved Ask retained `aria-current="page"` while Chats used
  `is-open` without `is-active`.
- The production interaction check collapsed and reopened Chats, verified the panel's hidden and
  inert state, and restored the original open state.
- The versioned runtime loader, navigation stylesheet, navigation controller, and service worker
  returned HTTP 200 with the expected hierarchy contract.

## Production release

- Feature commit: `10130ad`
- Deployment: `dpl_3LhJ5MMVqrxGz2aiaEBHzEG3mZrR`
- Deployment state: `READY`
- Alias state: six production aliases, no alias error
- Service-worker cache: `ask-crump-new-body-v1-r147`
- Navigation asset boundary: `5.9.76-chats-hierarchy-1`
- Framework: other / Vercel Functions

The deployment-scoped production observation contained 18 successful HTTP 200 responses and two
informational runtime entries, with no warning, error, or fatal entry observed.

No production account, message, conversation, Project, file, manuscript, generation, checkout,
payment, subscription, or synthetic funnel event was created for verification.

## Next operating decision

The remaining growth constraint is evidence, not another navigation surface. Keep the five
destinations stable, acquire the first comparable external users, and observe whether legitimate
first visits progress through registration, first useful work, durable Project or download value,
and return use before making another structural change.
