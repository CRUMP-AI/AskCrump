# Store review URL readiness — 2026-08-28

## Outcome

The Apple App Store and Google Play metadata packet now points directly to Ask Crump's canonical
`www` support, marketing, privacy, privacy-choice, and account-deletion routes. The previous apex
URLs returned HTTP 307 before reaching the working pages. No store form, listing, build, upload, or
submission was changed.

## Production evidence

- `https://www.askcrump.com/legal` returned HTTP 200 and contained the promised `contact` and
  `privacy` anchors.
- `https://www.askcrump.com/delete-account` returned HTTP 200 and contained the permanent
  account-deletion instructions.
- `https://www.askcrump.com/` returned HTTP 200 and exposed the canonical Ask Crump marketing page.
- Production health returned HTTP 200 for Ask Crump 5.9.71.

The URL fragments remain in the metadata where the store should open a specific legal section;
fragments are browser-local and do not change the verified HTTP destination.

## Regression boundary

The store metadata verifier now requires the exact direct-200 canonical URLs and rejects the apex
host or legacy `.html` forms. The source suite also protects every final field value. Reviewer
credentials, signed builds, physical-device checks, screenshots, console declarations, and final
per-platform submission remain owner-controlled gates.

## Verification

- Source commit: `87110a8`.
- CI run `33228342115` passed the complete 415-test suite, production bundle, JavaScript checks,
  and store metadata verifier.
- Android run `33228342176` regenerated 5.9.71/build 50971 and compiled a non-empty unsigned
  Release App Bundle with no signing or upload credential.
- iOS run `33228342063` regenerated 5.9.71/build 50971 and compiled the unsigned Release
  configuration on hosted macOS with no signing or upload credential.
- Production deployment `dpl_B6YpWHbTJxFKABnYfahd4NnzXEBL` reached `READY`; the post-deploy
  runtime-error scan was empty and `/api/health` returned HTTP 200 for 5.9.71.
