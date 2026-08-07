# Ask Crump 5.0 — Multimodal Product Architecture

## Product intent

Crump 5 turns attachments and generated media into first-class account objects while preserving the proven 4.4 authentication, memory, billing, and server-authoritative conversation path.

## UI layer

`public/crump-5.0.css` is an additive design-system layer. It restyles the complete product surface — authentication, navigation, conversation, composer, settings, dialogs, generated media, files, and mobile layouts — without moving authentication or synchronization logic into presentation code.

`public/crump-5.0.js` replaces only legacy controls that require new behavior:

- multi-file attachment input
- camera/photo capture
- drag and drop
- clipboard image paste
- upload progress/cancel/retry foundation
- Image Studio and Document Studio controls
- server-authoritative send path using file references
- generated image view/edit/download actions
- generated document cards

Plain Enter remains a newline. Ctrl+Enter / Command+Enter sends.

## Private file transport

1. Browser requests `/api/files/sign-upload`.
2. Python verifies ownership, type, size, and creates a `user_files` row.
3. Python mints a short-lived Supabase signed upload URL using the service role.
4. The browser uploads directly to the private Storage bucket. The service-role key never reaches the browser.
5. `/api/files/{id}/complete` verifies the object exists and marks it ready.
6. Chat messages contain only stable file IDs/metadata, not multi-megabyte base64 payloads.
7. Downloads flow through an authenticated Ask Crump route that redirects to a short-lived signed Storage URL.

## Vision

Images and PDFs are sent to the configured OpenAI vision model through the Responses API using high-detail image input or signed PDF file URLs. Office and text formats are extracted server-side with bounded parsers and added to the existing Crump context path. The existing Anthropic image/PDF path remains a small-file fallback.

Visual analysis is designed to inspect text, layout, objects, spatial relationships, charts, condition, and context while separating observation from inference. No model can guarantee perfect human perception; low-resolution, occluded, ambiguous, or unsupported content can remain uncertain.

## Image generation and editing

GPT Image 2 is used through the Images API. The product supports square, portrait, and landscape output plus quality selection. When an image is used as a reference and the user asks for a transformation, the image-edit endpoint is used instead of merely describing the reference.

Generated images are immediately stored in the private `crump-files` bucket and persisted into the same server-owned conversation record as the text response. This makes them durable and cross-device.

## Document generation

Crump can package polished model output as:

- DOCX (python-docx)
- PDF (ReportLab)
- PPTX (python-pptx)
- XLSX (openpyxl)
- Markdown
- plain text

Generated artifacts are private `user_files` objects and persist across devices.

## Security boundaries

- Bucket is private.
- `user_files` has RLS enabled.
- Browser roles have no direct table privileges.
- File ownership is checked on every API read/write.
- Service-role key stays server-side.
- CSP permits Supabase Storage connections but does not broadly open `connect-src`.
- Attachments are treated as untrusted content by model instructions.
- Generated assistant messages remain server-authoritative through `persist_chat_reply`.

## Release acceptance

A 5.0 release is not considered complete until production verifies:

1. login/session persistence unchanged;
2. phone/laptop text sync unchanged;
3. one image upload and visual Q&A;
4. one multi-file upload;
5. one generated image visible on a second device;
6. one reference-image edit;
7. DOCX, PDF, PPTX, and XLSX generation/download;
8. private file access rejects another account;
9. native build includes the 4.4 + 5.0 runtime loaders;
10. no new production error clusters.
