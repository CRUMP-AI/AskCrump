# Ask Crump 5.2

This release closes the largest seams found during live multimodal and billing testing.

- Durable uploaded file metadata now survives server synchronization, including private file IDs, size, kind, status, and safe metadata.
- Attachment-only conversation turns no longer disappear during synchronization.
- Generated image/file references survive synchronization through authenticated relative file URLs.
- User-uploaded images render inline in the conversation; documents render as durable file cards.
- Legacy 5.0/5.1 file bubbles can recover private file references by conversation when possible.
- Current document context is promoted ahead of memory so a large DOCX cannot be silently truncated out of the model prompt.
- Large nonvisual documents use broader bounded extraction with distributed excerpts across oversized files.
- Document revision intent can infer downloadable artifact output from recent document context.
- PDF/visual document revision prompts are told to write the complete revised artifact content rather than advice-only prose.
- The + attachment experience is re-owned by 5.2. Crump’s source sheet closes before Safari/iOS invokes its required OS picker.
- The billing center no longer shares a global loading lock; credit packs render immediately and hydrate independently.
- Live subscription choices remain intentionally disabled pending pricing/unit-economics work.
- The legacy Stripe subscription webhook now ignores non-subscription Checkout sessions and validates mode/tier before granting entitlement.
- Crump receives a stronger conversational persona: decisive opinions and preferences without false claims of consciousness or human experience.
- Service-worker cache/version and native build loader advance to 5.2.
