-- Synthetic pre-migration rows that must make the cohort migration refuse to
-- proceed. These cover both ways a post-launch submission can be ambiguous
-- when its best-effort AccountCreated event is absent.

\set ON_ERROR_STOP on

insert into public.users (
  id, email, is_guest, is_verified, created_at, registration_environment
) values
  (
    '10000000-0000-4000-8000-000000000013',
    'submitted-but-unverified@example.test',
    true,
    false,
    '2026-10-24 00:00:00+00',
    'production'
  ),
  (
    '10000000-0000-4000-8000-000000000014',
    'unmarked-non-guest@example.test',
    false,
    true,
    '2026-10-24 00:01:00+00',
    'production'
  );
