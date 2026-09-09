# Sanitized demo recording workflow proof release — 2026-09-09

## Outcome

Ask Crump now has a service-role-only, content-free proof gate for the exact live-product journey
marketing needs to record honestly. The proof is separate from the existing clean-state reset and
does not expose or copy customer material.

The protected `demo@askcrump.com` identity passes only when production data proves all of the
following:

1. exactly one active Project exists;
2. a complete user-and-assistant exchange is linked to that Project;
3. the same account later records a production `RecentWorkResumed` event with `source=project`;
4. a ready, editable Word or PowerPoint artifact exists; and
5. that artifact was created and attached to the same Project after the resume.

The database evaluates the relationships privately. The operator receives seven fixed booleans,
not an account ID, Project name, prompt, response, filename, Storage path, URL, or arbitrary
metadata.

## Privacy and authority boundary

- Migration `20260909190741_demo_recording_proof_snapshot.sql` installs a stable,
  service-role-only function.
- `PUBLIC`, `anon`, and `authenticated` have no execute permission; `service_role` is the sole
  executable role.
- The function is not `SECURITY DEFINER` and uses an empty `search_path`.
- `scripts/manage_demo_account.py --require-proof` is read-only and mutually exclusive with the
  account replacement and clean-state receipt modes.
- The fixed demo account remains excluded from customer growth/lifecycle reporting through its
  preview registration environment and internal entitlement contract.

The implementation was rebuilt against the current repository and migration ledger instead of
copying an older isolated candidate. The remote migration was applied only after reconciling the
API team's latest Supabase migration identity.

## Verification

- Demo workflow tests passed **19/19**.
- Migration-contract tests passed **3/3**.
- The complete Python suite collected **942 tests**: **940 passed** and two environment-dependent
  tests skipped.
- The browser control matrix passed **36/36**.
- **49 JavaScript files** and six attribution cases validated.
- Production preflight, native web bundle construction, compilation, and diff integrity passed.
- Feature CI run **34393146504** and migration-ledger correction CI run **34393335531** completed
  successfully.
- Feature deployment **dpl_9AGxNLa9g1kagGucHeeNxnrW6Y4e** and final deployment
  **dpl_CXKZirExcakXDdWhNGfBz3q7h1Sa** are READY.

Remote function metadata and grants matched the intended boundary. Its initial production snapshot
returned all seven proof booleans as `false`, which is the correct fail-closed baseline because no
sanitized demo identity and completed recording journey currently exist.

## Remaining operator gate

No demo identity was created or reset, no credential was selected, no customer/founder account was
used, and no recording was made. An authorized operator must still:

1. provision or reset the fixed demo account locally with a hidden password and preserve the
   content-free clean-state receipt;
2. perform and continuously record the real request → response → Project save → later Project
   resume → editable DOCX/PPTX journey; and
3. run `python scripts/manage_demo_account.py --require-proof` and retain the fixed pass/fail result
   with capture QA evidence.

Until that gate passes, there is no approved product-proof capture. This release does not authorize
publication, profile changes, paid spend, or performance claims.
