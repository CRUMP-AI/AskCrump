# Intelligence Clarity Release — 2026-08-30

## Outcome

Ask Crump's Intelligence panel now presents only controls that change how the assistant works:

- **Thinking** — Adaptive, Fast, and paid Think longer modes.
- **Memory & privacy** — saved memory, explicit learning, per-conversation privacy, and memory review.
- **Current information** — one automatic routing control for supported live information.
- **Answer review** — Off, Automatic, and paid Always review modes.

The redundant Web, Image, and Code launchers were removed from Intelligence, along with internal system diagnostics, duplicate tutorial navigation, and keyboard help. Crump Code remains a separate, hidden surface while its isolated runtime is disabled; it is not presented as a working feature until the complete execution path is ready.

## Paid-feature enforcement

Think longer and Always review use the existing Professional entitlement. Enforcement now exists at every relevant boundary:

- Free accounts see both controls as locked and receive a direct plan comparison path.
- The preferences API rejects attempts to save either paid mode.
- The chat API rejects direct attempts to request either paid mode.
- Expired paid preferences safely downgrade to Adaptive thinking and Automatic review.

## Usability details

- The panel subtitle and section names describe the real function of each control.
- A new conversation disables its privacy switch until the first message creates the conversation, avoiding a silent no-op.
- Free plans receive a restrained Advanced intelligence card; entitled plans receive an active-state confirmation.
- The PWA cache revision moved to `r157` so installed clients receive the new assets.

## Verification

- 563 Python tests passed.
- 45 JavaScript files passed the integration validation.
- Production build preflight and native web bundle completed.
- Free desktop browser check: five intended sections, two paid locks, zero preference writes after selecting a locked control, and zero browser errors.
- Professional mobile browser check: paid controls unlocked, Always review persisted, no horizontal overflow, and zero browser errors.
- Production deployment `dpl_CdVY31m9Qw8akJo5iEBUvRCEWDyz` reached READY on all six aliases.
- Live asset inspection confirmed the new labels and styles, removal of all three obsolete launchers, and PWA cache `r157`.
- Vercel reported no runtime error clusters in the first post-deployment hour window.

## Source

- Feature commit: `e62c4db528c45bd8c9af16f9f62635b66c567195`
