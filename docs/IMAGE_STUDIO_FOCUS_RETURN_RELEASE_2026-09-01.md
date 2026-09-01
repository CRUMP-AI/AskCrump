# Image Studio focus-return release

Date: 2026-09-01

## Product outcome

Closing Image Studio now returns a keyboard or assistive-technology user to a usable visible
control. If the control that opened Image Studio still exists and is visible, focus returns to that
exact control. If the opener belonged to a transient chooser that was removed or hidden, focus
moves to **Message Crump** instead of falling onto the document body.

This is a creation-path navigation correction. Image setup, references, uploads, model selection,
generation, safety, credits, Projects, Files, and billing behavior are unchanged.

## Reproduced defect

A read-only signed-in production walkthrough opened **Create → Images** and then closed Image
Studio without selecting a file or generating anything. The Create chooser had already been hidden,
but Image Studio still tried to return focus to its now-hidden Images card. Browsers cannot focus a
hidden control, so the active element became the page body. The visual workspace returned to Ask,
while keyboard and screen-reader users lost their place and had to navigate from the beginning.

The same failure was possible when Image Studio opened from the temporary composer attachment
menu because that menu removes its own action before the studio opens.

## Correction

The shared Image Studio dismiss path now:

- retains the exact opener only when it is connected, enabled, not inside a hidden, inert, or
  assistive-technology-hidden surface, and has a rendered box;
- restores that valid opener on the next animation frame;
- otherwise focuses the existing `userInput` composer without scrolling; and
- uses the same behavior for the Close control and Escape.

The PWA cache advances to `ask-crump-new-body-v1-r190`. The exact released script is
`/crump-5.0.js?v=5.9.76-image-studio-focus-return-1`; the unchanged stylesheet keeps its prior
version.

## Automated verification

The real Image Studio browser fixture now proves both return paths:

- a durable visible opener regains focus after Close;
- a connected but hidden transient opener is rejected and the composer gains focus;
- Image Studio still opens as a modal and focuses its labeled Close action;
- reference selection, valid-preview stability, invalid-replacement preservation, edit-mode
  handoff, identity-preservation guidance, and Escape remain intact; and
- the browser console contains zero errors.

Adjacent browser proofs remained green for image scroll stability, image rejection recovery, and
desktop/mobile Create destination handoff. All **727 Python tests**, **47 JavaScript validations**,
Python compilation, production preflight, native web bundling, store metadata, signing-source
controls, and diff integrity passed.

## Production evidence

- Feature commit: `9ca479ab0ba2fe0e46662ad18cbc340750565d2b`
- Deployment: `dpl_8NwjGSHohcjBYfnWm6SRHM1UVbL7`
- State: `READY`
- Aliases: all six Ask Crump and Clever Crump production aliases
- Alias error: none
- `/api/health`, the runtime loader, exact Image Studio script, and `sw.js`: HTTP 200
- Exact cache/script markers: present in the canonical responses
- Signed-in production flow: **Create → Images** opened once, focused **Close Image Studio**, and
  closed to `userInput` with Ask active, the studio removed, the composer visible, and no horizontal
  overflow
- Release-window runtime errors: none
- Release-deployment 4xx/5xx logs: none
- Release-deployment warning/error/fatal logs: none

The production walkthrough did not upload a file, send a message, generate media, spend credits,
change a Project, open checkout, alter billing, or mutate account or customer data.

## Observation boundary

This proves deterministic web/PWA delivery and inclusion in the native web bundle. Repeat the exact
Create → Images → Close and Escape paths on signed physical iPhone and Android candidates with
VoiceOver and TalkBack before store screenshots. Legitimate image creation, completion, return, or
conversion outcomes remain unproven and must not be inferred from internal verification.
