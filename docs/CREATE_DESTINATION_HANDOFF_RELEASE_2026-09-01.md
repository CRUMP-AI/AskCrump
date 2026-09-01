# Create destination handoff release

Date: 2026-09-01  
Feature commit: `d2f19adb0c5d6cc5ab22ca6a285013130c0bcce0`  
Production deployment: `dpl_7fWJuQYhTiHp2aXYWgsytLBMByrK`

## User problem

The user-eye production audit found a deterministic inconsistency in the persistent navigation.
Projects, Video, Library, and You allowed a person to move directly to another visible destination.
Create deliberately left the desktop rail and phone destination bar visible, but marked the entire
`appContainer` inert and assistive-technology-hidden. The visible destination controls therefore
could not act until Create was dismissed first.

This was a navigation and accessibility defect, not an account, content, generation, or analytics
problem. The current anonymous registration sample remains too small and too exposed to owner/QA
traffic to justify an authentication rewrite.

## Shipped behavior

- Create is a non-modal destination surface, matching the existing Projects, Video, Library, and You
  navigation contract.
- Only the covered Chats/sidebar and workspace canvas become inert and assistive-technology-hidden.
- The desktop rail and safe-area-aware mobile destination bar remain visible, focusable, and
  actionable.
- One destination activation closes Create and opens the selected existing surface.
- Opening Create still focuses its explicit close control; Escape still closes it and restores the
  originating control.
- Nothing generates until the user chooses an outcome, reviews that surface, and sends a request.
- No API, database, migration, Supabase object, account, conversation, Project, file, generation,
  provider, credit, entitlement, price, checkout, payment, subscription, or customer data changed.

## Automated and local proof

- All **713 Python tests** passed.
- All **47 JavaScript validations** passed.
- Python backend compilation, production preflight, native web bundling, store-metadata source
  checks, mobile signing-source controls, and diff integrity passed.
- The local native release verifier continued to report the existing release-time blockers: no
  generated Android/iOS projects in this web release worktree and no RevenueCat public keys loaded
  in the shell. No store submission or signed-build claim is made.
- `scripts/verify-create-destination-handoff.cjs` exercised the production navigation runtime at
  **1280×720** and **390×844**.
- Desktop: Create overlay left and rail right both measured **94px**.
- Mobile: Create overlay bottom and destination-bar top both measured **776px**; the destination bar
  measured **68px** high.
- In both viewports the app container remained operable, the covered workspace/sidebar were inert,
  and the visible Video destination was outside every inert ancestor.
- One Video activation closed Create, opened the existing Video section, marked Video active, and
  focused `crump53WorkspaceTitle`. One Ask activation closed the studio and removed workspace inert
  state. Browser error count was zero.

## Production proof

The GitHub-connected production deployment reached `READY` on all six aliases with no alias error.
Signed-in inspection at `https://www.askcrump.com/app` loaded the exact
`5.9.76-create-destination-handoff-1` navigation asset.

The live desktop geometry matched the contract: Create overlay left and rail right were both
**94px**. `appContainer` was not inert, while the covered workspace and Chats/sidebar were inert.
The visible Video destination had no inert ancestor. One deliberate Video click closed Create,
opened `crump53Sheet[data-crump53-section="video"]`, marked Video active, and moved focus to the
workspace title. One Ask click closed the studio, removed workspace inert state, and returned focus
to the composer without changing the URL or starting generation.

Vercel reported no runtime-error cluster, no 4xx or 5xx request log, and no
warning/error/fatal log for the release deployment during verification. The observed request group
contained 13 successful HTTP 200 responses.

## Rollback and remaining gate

Rollback is the single feature commit above; the prior Create card actions and every underlying
destination remain unchanged. Before native store screenshots, repeat the Create-to-destination
handoff on a physical iPhone with safe areas, VoiceOver, and the software keyboard. Legitimate
activation and retention outcomes remain observation gates; this release proves delivery, not lift.
