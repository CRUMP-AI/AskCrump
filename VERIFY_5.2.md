# Ask Crump 5.2 verification

## Multimodal continuity
- Upload a new image and send it with a short message. The image should remain visibly embedded in the user message after the reply and after a refresh.
- Upload a DOCX/PDF. A durable file card should remain in the conversation and open through the authenticated private-file route.
- Reopen one of the 5.0/5.1 test conversations. 5.2 attempts to recover old file IDs from the private files stored for that chat.

## Large documents
- Upload the EDEN DOCX again and ask, “Can you read this?” Crump should acknowledge the actual document instead of claiming no attachment arrived.
- For large documents, Crump receives bounded excerpts distributed across the file rather than silently losing the attachment behind memory context.

## Artifacts
- Upload a resume and ask, “Improve this resume and tailor it for this role.” Crump should return a downloadable document artifact, not only advice.
- Ask for a specific output format (DOCX, PDF, PPTX, XLSX, Markdown, TXT) to exercise the existing artifact packager.

## Upload picker
- Tap + once. Only the Crump source sheet should appear first.
- Tap Photos, Files, or Camera. The Crump sheet should dismiss before iOS presents its required system picker.

## Billing
- Open Plan & credits. The 50 / 150 / 400 credit cards should render immediately instead of remaining skeletons.
- Subscription cards intentionally remain disabled (“Coming soon”) until subscription economics and live subscription webhooks are finalized.
- Tap 50 Credits. Stripe Checkout should open at $4.99. Do not complete a real payment unless intentionally testing a live purchase.

## Image generation
- Replace the invalid OPENAI_API_KEY in Vercel first, then redeploy.
- Ask Crump to create an image. The generated image should persist as a private conversation artifact.

## Personality
- Ask Crump for a subjective favorite or ranking. He should make a clear pick and defend it naturally instead of leading with “I don’t have personal preferences.”
- He should still avoid falsely claiming consciousness, a body, or human sensory experiences.
