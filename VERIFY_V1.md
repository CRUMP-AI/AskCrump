# Ask Crump V1 Verification Matrix

## Boot / auth
- New Safari tab loads without freezing.
- Login renders with full horizontal wordmark at readable size.
- Existing login still succeeds.
- Register / reset screens remain usable at 320px+ viewport widths.
- No Google Fonts request is required for the application shell.

## Main shell
- Header wordmark is centered and not recreated with generic text.
- Menu and Crump controls remain 48px touch targets.
- Sidebar opens/closes without horizontal page movement.
- Desktop and mobile do not horizontally overflow.

## Conversation
- Empty state mark is clean and unboxed.
- Suggestions are 2-column on desktop and 1-column on mobile.
- Existing chats render.
- New assistant replies retain 5.2.2 top-anchor scrolling.
- Manual reading does not jump.
- Scroll-to-newest button remains visible and functional.

## Composer / multimodal
- Plus menu opens.
- Photos / Camera / Files still work.
- Attachment tray stays above composer.
- Image previews remain durable.
- DOCX/PDF attachments remain durable.
- Artifact cards still open generated documents.
- Image tool / document tool sheets remain usable.

## Billing
- Plan & credits opens.
- 50 / 150 / 400 packs render.
- Web checkout still reaches Stripe.
- Native build continues to use store billing / RevenueCat paths.

## Account / settings
- Settings opens and scrolls.
- Delete account remains discoverable.
- Legal & Privacy remains accessible.
- Signed-in devices still opens.

## Accessibility / native
- Focus-visible ring appears with keyboard navigation.
- Primary coarse-pointer controls are >=48px.
- prefers-reduced-motion disables ornamental motion.
- safe-area insets are respected.
- 320px, 390px, 430px, 768px, 1024px, and 1440px widths are visually checked.
