# Ask Crump social launch batch

## Status

Four publications are staged: two campaign messages adapted for Facebook and Instagram. Nothing in
this packet authorizes publication. Publish only after the owner says the exact action-time phrase
`Publish the launch batch and send the progress update`.

The links deliberately send cold visitors to a contextual public page before credentials. Facebook
uses an explicit privacy-minimized acquisition label. Instagram uses the profile link, which should
point to the matching contextual URL with `utm_source=instagram` before publication. Ask Crump stores
only the allowlisted source label; Vercel telemetry removes query strings and fragments.

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

## Publication 1 — Facebook — workspace positioning

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

## Publication 2 — Instagram — workspace positioning

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

## Publication 3 — Facebook — presentation outcome

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

## Publication 4 — Instagram — presentation outcome

- Asset: `public/assets/social/ask-crump-presentations-portrait.png` (1080×1350)
- Profile destination: `https://www.askcrump.com/ai-presentation-maker?utm_source=instagram`
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

1. Confirm the Facebook image, caption, CTA, destination, and alt text exactly match this packet.
2. Confirm the Instagram profile link matches the corresponding contextual destination before each
   post; do not point either cold campaign directly to `/app`.
3. Preview crops on phone and desktop. Preserve the full wordmark and the principal headline.
4. Publish the workspace message first on both platforms. Publish the presentation message second.
5. Send one concise progress update to the dedicated ChatGPT conversation after all four
   publications are visibly live.
6. Record publication URLs and timestamps. Observe at least 14 days and 50 combined social-referral
   visitors before making a conversion decision; do not treat verification or owner traffic as
   customer evidence.
