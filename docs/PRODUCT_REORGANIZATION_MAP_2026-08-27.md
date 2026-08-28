# Ask Crump product reorganization map

Date: 2026-08-27

Release candidate: 5.9.30

Positioning: **An AI workspace for work that continues.**

## Decision

Organize the signed-in product around five user destinations: **Ask, Projects, Create, Library,
and You**. This is an information-architecture change over the existing product, not a backend
rewrite. Accounts, conversations, Projects, files, generated artifacts, entitlements, APIs, and
stable public links remain unchanged.

## Evidence from the previous shell

The prior product exposed capability through five competing control areas:

- an icon-only desktop rail for new conversation, conversation history, and Projects;
- a conversation drawer that also contained Projects, Settings, Plan & credits, and Legal;
- six launch cards mixing conversation modes, file intake, Projects, image, and video creation;
- a compact composer tool menu containing seven tools;
- a separate Projects & Create dialog containing Projects, manuscripts, video, and saved files.

Every important capability existed, but the user had to learn where each one happened to live.
Mobile reduced the rail to a conversation menu and left the product hierarchy implicit.

## Destination and capability map

| Destination | User job | Existing surface reused | Preserved behavior |
| --- | --- | --- | --- |
| Ask | Think, decide, research, work from files, or continue a conversation | Main conversation workspace, launchpad, composer tools, research mode | Conversations, sync, memory, file intake, current chat state, and model orchestration |
| Projects | Keep ongoing work, instructions, canon, files, manuscripts, and conversations together | Existing owner-scoped Projects panel | Project APIs, ownership checks, limits, Project-to-chat associations, and saved context |
| Create | Choose an output before entering its focused setup | New non-generating hub handing off to existing document, PowerPoint, image, manuscript, and video tools | Existing feature gates, credit costs, provider selection, generation flows, and private file storage |
| Library | Find and reuse saved files and creations | Existing private saved-library panel | Owner-scoped file listing, playback, download, reuse, filters, and deletion behavior |
| You | Manage profile, behavior, account, privacy, and device settings | Existing Settings dialog | Authentication, device sessions, profile persistence, sign-out, and account-deletion path |

Research stays inside Ask because it changes how a conversation reasons; it is not a separate
place where work lives. Documents, presentations, images, manuscripts, and video sit under Create
because they begin with an output choice. Plan & credits remains available in the conversation
drawer during this first slice so no monetization or entitlement affordance is removed.

## First staged slice

Release 5.9.30 adds:

- a labeled five-destination desktop rail;
- the same five destinations in a mobile safe-area tab bar;
- active-destination state synchronized with Projects, Create, Library, Settings, conversations,
  and the existing creation dialogs;
- a restrained Create dialog that does not generate or charge until the user enters the existing
  tool flow and sends a request;
- direct PowerPoint and image-studio handoffs that reuse the current composer state;
- a device-local rollback switch: set `askcrump.navigation.mode` to `legacy` and reload.

The old conversation drawer remains the owner of conversation history and secondary account/legal
actions. No data migration, route migration, schema migration, pricing change, or entitlement
change is part of this release.

## Verification and release gates

- Automated contracts must prove all five destinations exist in web and native runtimes, both new
  assets are pre-cached and network-first, the Create hub makes no network request, and the legacy
  switch bypasses the layer.
- The full backend and browser-script suites, Python lint/compile checks, production preflight,
  native web bundle, store metadata, and mobile signing-source checks must pass.
- Desktop and mobile visual review must verify readable labels, composer clearance, safe areas,
  dialog fit, focus entry, escape/close behavior, and no clipped destinations.
- Production must return release 5.9.30, serve the new assets, preserve authenticated workspace
  entry, and show no deployment-scoped error cluster or warning/error/fatal/5xx regression.
- Store screenshots remain blocked until the exact signed Android and iOS candidates pass their
  separate release gates and receive owner approval.

## Rollback

The preferred release rollback is the previous verified deployment. For a device-scoped diagnostic,
set local storage key `askcrump.navigation.mode` to `legacy` and reload; the new runtime records
legacy mode and leaves the prior rail/drawer behavior intact. Removing the key restores the five-
destination layer. Neither path changes server data.
