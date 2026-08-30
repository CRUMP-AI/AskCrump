# Ask Crump social launch batch

## Status

The workspace-positioning message is already live on Facebook and Instagram. Do not publish those
two messages again. The remaining launch batch is the presentation outcome adapted once for
Facebook and once for Instagram. Nothing in this packet authorizes the remaining actions. Proceed
only after the owner says the exact action-time phrase
`Apply the tracked profile links, submit the Ask Crump sitemap, publish the presentation batch, and send the progress update.`

The external acquisition handoff is not complete: Facebook's public profile links are untagged,
Instagram's public profile currently shows no clickable external link, and the verified Search
Console property has no submitted sitemap. Nothing in this packet authorizes those edits or the two
remaining publications.

The links deliberately send cold visitors to a contextual public page before credentials. Facebook
uses an explicit privacy-minimized acquisition label. During the presentation campaign, Instagram's
clickable profile link should point to
`https://www.askcrump.com/ai-presentation-maker?acquisition=instagram&source=profile-link`.
Facebook's profile link should use
`https://www.askcrump.com/?acquisition=facebook&source=profile-link`.
Ask Crump stores only the allowlisted source and placement labels; Vercel telemetry removes query
strings and fragments.

## Verification

- Feature commit: `6546b1c` (`Stage contextual social launch batch`).
- Production deployment: `dpl_CcWeAy5rJwaEn7xnYHBA618fBDCs`, `READY` on all six Ask Crump and
  Clever Crump aliases with no alias error.
- All 436 regression tests, 45 JavaScript validations, production preflight, and store-metadata
  checks passed.
- A live browser loaded both portrait assets from `www.askcrump.com` at exactly 1080×1350 with no
  browser error log.
- The release window contained no Vercel runtime error cluster and no warning, error, or fatal log
  for the deployment.
- No post, profile link, social-account setting, Search Console setting, production account, or
  customer data was created or changed during verification.

## Live reference 1 — Facebook — workspace positioning

Status: already live; retain as a historical campaign reference and do not republish.

- Asset: `public/assets/social/ask-crump-workspace.png` (1200×630)
- Destination: `https://www.askcrump.com/?utm_source=facebook`
- CTA: Learn more
- Alt text: Black-and-gold Ask Crump campaign card reading “Work that continues,” with the Ask Crump
  magnifying-glass mark and a short description of persistent conversations, Projects, files, and
  finished work.

Caption:

> Good work rarely ends with one prompt.
>
> Ask Crump is an AI workspace for work that continues—conversations, Projects, research, files,
> and finished work together in one place.
>
> Explore the workspace: https://www.askcrump.com/?utm_source=facebook

## Live reference 2 — Instagram — workspace positioning

Status: already live; retain as a historical campaign reference and do not republish.

- Asset: `public/assets/social/ask-crump-workspace-portrait.png` (1080×1350)
- Profile destination: `https://www.askcrump.com/?utm_source=instagram`
- Alt text: Vertical black-and-gold Ask Crump campaign card reading “Work that continues,” with a
  restrained geometric gold motif and the Ask Crump wordmark.

Caption:

> Good work rarely ends with one prompt.
>
> Keep conversations, Projects, research, files, and finished work together—and return when the
> work moves again.
>
> Explore Ask Crump at the link in bio.
>
> #AskCrump #AIWorkspace #FutureOfWork

## Remaining publication 1 — Facebook — presentation outcome

- Asset: `public/assets/social/ask-crump-presentations.png` (1200×630)
- Destination: `https://www.askcrump.com/ai-presentation-maker?utm_source=facebook`
- CTA: Learn more
- Alt text: Black-and-gold Ask Crump campaign card describing an AI presentation maker that creates
  an editable PowerPoint draft.

Caption:

> A presentation should start with a clear story, not an empty slide.
>
> Ask Crump turns a brief into a structured, editable PowerPoint draft you can download, revise, and
> keep moving inside the same workspace.
>
> See how it works: https://www.askcrump.com/ai-presentation-maker?utm_source=facebook

## Remaining publication 2 — Instagram — presentation outcome

- Asset: `public/assets/social/ask-crump-presentations-portrait.png` (1080×1350)
- Profile destination: `https://www.askcrump.com/ai-presentation-maker?acquisition=instagram&source=profile-link`
- Alt text: Vertical black-and-gold Ask Crump campaign card reading “From an idea to an editable
  PowerPoint,” with the Ask Crump wordmark and restrained gold geometry.

Caption:

> Start with a brief. Leave with an editable PowerPoint draft.
>
> Build the structure, download the .pptx, revise it, and keep the work moving in Ask Crump.
>
> See the presentation workflow at the link in bio.
>
> #AskCrump #AIPresentation #PowerPoint

## Action-time checklist

1. Apply the exact tracked Facebook and Instagram profile links above; do not expose credentials or
   account data in either URL.
2. Submit `https://www.askcrump.com/sitemap.xml` to the verified `askcrump.com` Search Console
   property.
3. Confirm the remaining Facebook image, caption, CTA, destination, and alt text exactly match this
   packet.
4. Confirm the Instagram profile link points to the presentation page before publication; do not
   point either cold campaign directly to `/app`.
5. Preview both presentation assets on phone and desktop. Preserve the full wordmark and principal
   headline.
6. Publish only the two remaining presentation messages, one per platform.
7. Send one concise progress update to the dedicated ChatGPT conversation after the profile links,
   sitemap, and two publications are visibly confirmed.
8. Record publication URLs and timestamps. Observe at least 14 days and 50 combined social-referral
   visitors before making a conversion decision; do not treat verification or owner traffic as
   customer evidence.
