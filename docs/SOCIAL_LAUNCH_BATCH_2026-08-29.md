# Ask Crump social launch batch

## Status

**Superseded — do not use this packet to publish the presentation pair.**

The workspace-positioning message is already live on Facebook and Instagram. Do not publish those
two messages again. The presentation assets originally staged in this repository are retired from
campaign use because the Instagram portrait still carries the obsolete `AI VIRTUAL ASSISTANT`
descriptor. The original action-time approval phrase in this file is therefore void.

The current presentation creative is owned by the marketing workspace at
`ask-crump-marketing/campaigns/presentation-proof-current/final`, with its governing handoff at
`ask-crump-marketing/handoffs/PRESENTATION_BATCH_REPLACEMENT.md`. Marketing must review that package
and obtain the appropriate action-time approval before any publication. This product-repository
record neither copies the marketing assets nor authorizes publishing them.

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

## Retired reference — Facebook — presentation outcome

- Invalid campaign asset: `public/assets/social/ask-crump-presentations.png` (1200×630)
- Status: do not publish; use the current marketing-owned replacement package after review.
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

## Retired reference — Instagram — presentation outcome

- Invalid campaign asset: `public/assets/social/ask-crump-presentations-portrait.png` (1080×1350)
- Status: do not publish; this asset visibly carries the retired descriptor.
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

1. Do not publish either product-repository presentation asset or reuse the original approval phrase.
2. Review `ask-crump-marketing/handoffs/PRESENTATION_BATCH_REPLACEMENT.md` and the current final
   creative package in the marketing workspace.
3. Keep profile-link, Search Console, publication, and campaign-spend actions under the marketing
   task's explicit approval boundary.
4. Preserve the full current workspace lockup and verify that no retired descriptor appears in any
   final preview.
5. Use one canonical tracked destination per platform so acquisition attribution is not split.
6. Record any eventual publication URLs and timestamps in the marketing system of record. Observe
   legitimate acquisition, activation, retention, payer, recognized-revenue, refund, and variable-
   cost evidence before making a scale decision; do not treat verification or owner traffic as
   customer evidence.
