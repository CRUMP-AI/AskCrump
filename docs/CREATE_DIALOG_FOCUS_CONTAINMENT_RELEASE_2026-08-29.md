# Create dialog focus containment release

Date: 2026-08-29

## Product outcome

The primary Create chooser now behaves as the modal it announces itself to be. While the
chooser is open, keyboard and assistive-technology interaction stays inside its six controls.
Closing it restores the full workspace and returns focus to the exact Create destination that
opened it.

This protects a high-intent activation path: choosing documents, presentations, images,
manuscripts, or video. It does not generate content, consume credits, or alter any private record.

## Reproduced defect

The signed-in production chooser had `role="dialog"` and `aria-modal="true"`, but the workspace
behind it remained in the page focus order. Its chats, navigation, and composer controls could
therefore receive keyboard or screen-reader interaction while the dialog was visibly open.

The issue was reproduced read-only on the live app and then isolated in the existing
credential-free navigation fixture. No prompt, generation, file, conversation, Project, or account
record was created or changed.

## Correction

- Preserve the workspace's prior `inert` and `aria-hidden` state.
- Apply both boundaries while Create is open, leaving the sibling dialog interactive.
- Restrict the focusable query to controls inside the dialog.
- Wrap Shift+Tab from the close control to Video and Tab from Video to the close control.
- Restore the previous workspace state and the original Create trigger on close.
- Version the navigation runtime and workspace loader, and advance the PWA cache to `r138` so
  existing web and installed sessions receive one coherent asset set.
- Mirror the versioned runtime plan in the native web bundle.

## Verification

The credential-free browser fixture executed the exact production navigation layer and proved:

- opening Create set the workspace to `inert` and `aria-hidden="true"`;
- initial focus moved to **Close Create**;
- backward focus wrapped to **Video**;
- forward focus wrapped back to **Close Create**;
- closing removed both background boundaries and returned focus to **Create**; and
- the fixture recorded zero browser errors.

The same non-generating sequence was repeated in the signed-in production workspace after release.
The app runtime was `ready`, the same focus loop passed, and the background state was restored.

Release gates:

- 492 Python regressions passed;
- 45 JavaScript files passed the integration validator;
- the production preflight passed;
- the native web bundle rebuilt successfully;
- Apple and Google metadata source checks passed; and
- `git diff --check` passed.

## Production evidence

- Feature commit: `1589b7b`
- Deployment: `dpl_5ESqFFUemiTWXjXZeLdK8azHdQB4`
- State: `READY`
- Production aliases: all six expected Ask Crump and Clever Crump aliases
- Alias error: none
- Canonical health: HTTP 200, service `Ask Crump`
- Exact live assets: versioned workspace loader, versioned navigation controller, and cache `r138`
- Initial runtime audit: no runtime-error cluster and no warning, error, or fatal deployment log

## Observation boundary

Delivery is verified on web/PWA and included in the regenerated native web bundle. The remaining
store-readiness observation is a physical iPhone PWA keyboard/screen-reader pass and final
accessibility review on the exact signed store candidates. This release does not claim improved
activation or retention until legitimate user outcomes exist.
