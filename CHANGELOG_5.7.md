# Ask Crump 5.7 — Library

Ask Crump 5.7 turns long-form writing into a first-class Library rather than a project-only manuscript tool.

## Bookshelf

- All manuscripts across Projects appear together in one searchable bookshelf.
- Books created inside Ask Crump and manuscripts imported from outside Ask Crump share the same Library.
- Front-cover and back-cover images can be attached or replaced at any time.
- Imported originals remain preserved as private source files.
- Each book shows its author, status, word count, section count, source origin, and Project.
- Opening a Library book hands off to the existing durable manuscript workspace rather than creating a second editor.

## External manuscript import

Supported source formats:

- DOCX
- PDF
- EPUB
- TXT
- Markdown

Ask Crump extracts readable text, recognizes common chapter/front/back-matter headings, preserves the original upload, and imports the content into the existing manuscript-section model. Import does not automatically rewrite the author's work.

If no Project is chosen, Library creates a dedicated Project for the book so future files, canon, conversations, and edits remain organized together. Existing subscription Project limits still apply; when the limit is reached, the importer asks the user to choose an existing Project.

## Media saving

Generated images and videos are no longer treated as ordinary documents in the native apps.

- Android/iOS native builds use `@capacitor-community/media` 9.1.0 to save images and videos to Photos/Gallery.
- Mobile web/PWA uses the operating-system share/save sheet when file sharing is supported.
- Ordinary documents continue to use normal file downloads.
- A short-lived authenticated signed-media endpoint keeps private Supabase paths and service credentials hidden.

## Store posture

This release does not upload or submit Ask Crump to either app store. It remains a pre-store stabilization release.
