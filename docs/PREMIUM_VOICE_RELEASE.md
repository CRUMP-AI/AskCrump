# Premium voice release plan

Last reviewed: 2026-08-27

## User experience

Crump Voice is a staged Professional feature for explicit “Read aloud” requests. When the
feature is unavailable, disabled, the response is too long, the account is not entitled, or the
provider fails, Ask Crump uses the device's built-in speech capability. Automatic narration and
background voice generation are out of scope.

## Data flow and privacy boundary

1. A signed-in user explicitly selects Read aloud on one response.
2. The browser asks the server whether premium voice is configured and entitled.
3. The server removes code blocks, raw links, HTML, and noisy Markdown, then enforces the
   configured character limit.
4. The server sends that prepared response text to ElevenLabs using a server-held API key.
5. The returned MP3 is streamed as a private, non-cacheable response and played from a temporary
   browser object URL, which is revoked after playback.

Ask Crump does not store the request text or audio for this flow. Usage metadata contains only
character count and the configured model identifier. Application code must not log request text,
audio, API keys, or provider response bodies. ElevenLabs remains an external data recipient and
its own processing/retention terms must be reconciled before activation.

## Cost and entitlement controls

- The feature is disabled unless the kill switch, API key, approved voice ID, and approved model
  are all present.
- Professional includes 10 premium reads per day; Enterprise includes 30. Overflow costs two
  Crump Credits per read. Free accounts use device speech.
- The route permits at most 30 requests per account per hour.
- Invalid or over-limit text is rejected before charging. Provider and unexpected failures refund
  the usage receipt.
- Audio is limited to 15 MB and must have an audio content type.

These initial quotas are operating limits, not a public pricing promise. Review actual character,
latency, success, fallback, refund, and provider-cost data before changing them.

## Required approvals before activation

1. Approve the exact customer-facing privacy/help disclosure that response text is sent to
   ElevenLabs only after the user selects Read aloud.
2. Confirm the production ElevenLabs account, API key, voice rights, and voice ID.
3. Confirm the chosen model and current commercial terms.
4. Add production environment values server-side and keep the feature flag off until smoke tests
   pass.
5. Test entitled, unentitled, over-limit, provider-failure, refund, browser fallback, stop, replay,
   mobile, and accessibility behavior.
6. Enable gradually, monitor cost and failure rate, and retain the kill switch.

## Proposed disclosure for owner/legal review

> When you choose Read aloud with Crump Voice, Ask Crump sends the text of that response to
> ElevenLabs to generate temporary audio. Ask Crump does not save that audio through this
> feature. If Crump Voice is unavailable, your device's built-in speech service may be used.

This is draft operational copy, not published legal language. It must be reconciled with the
actual production configuration and provider terms before public activation.
