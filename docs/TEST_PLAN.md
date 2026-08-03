# Release Test Plan

## Automated gate

```bash
python -m compileall -q app.py backend
pytest -q
npm run test:js
git diff --check
```

## Authentication and sync

Verify registration/email/reset, persistent web/native sign-in after force close/restart, sliding expiration, per-device revocation, all-device logout, and rate limits. Test iPhone+laptop and Android+desktop chat creation, replies, concurrent changes, deletion while offline, reconnect, reinstall, and account switching without cache leakage.

## Messaging presence

- Confirm `Sending` appears immediately.
- Confirm `Delivered` only after synchronized persistence succeeds.
- Confirm `Seen` after `/api/chat/ack` accepts the message.
- Confirm reading/searching/creating/thinking labels match operation type.
- Confirm the dots become a label only after the delay and transform cleanly into the completed reply.
- Retry the same message repeatedly and confirm one canonical reply job/result.
- Simulate provider failure after delivery and confirm `Seen · Reply failed` with retry.
- Go offline before sending; confirm queued state, reconnect sync, and no duplicate message.
- Verify no fixed loading banner, splash animation, hover lift, or unexpected scroll jump.

## Crump Check-ins

- Default is disabled for new accounts.
- Enable each frequency/category combination and verify server persistence across devices.
- Verify quiet hours across midnight and multiple timezones.
- Verify no meaningless message is sent when the AI returns `SKIP`.
- Verify no second check-in while one remains unanswered.
- Verify ignored check-ins increase cooldown.
- Reply to a check-in and verify its event becomes responded.
- Verify the message is saved before push delivery.
- Verify disabled notifications still place the check-in in the synchronized conversation.
- Verify notification tap opens the correct chat.

## Native and accessibility

Test small/large phones, tablet, keyboard avoidance, safe areas, offline pill, reconnect, light haptics, haptics disabled, push permission denial, stale push token, foreground/background/terminated push, VoiceOver/TalkBack labels, keyboard/focus, contrast, Dynamic Type/zoom, and Reduce Motion.

## AI, billing, deletion, and rollback

Exercise long history, attachments, image generation, search/weather context, provider timeout/refund, simultaneous usage limits, web Stripe, native RevenueCat purchase/restore/lifecycle, wrong deletion credentials, atomic successful deletion, public deletion page, and database/deployment rollback from a verified backup.
