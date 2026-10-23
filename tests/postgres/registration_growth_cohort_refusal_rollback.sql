-- Run only after the migration is expected to fail with SQLSTATE 55000.
-- Prove its transaction rolled back completely, then remove the synthetic
-- refusal fixtures so the normal success path can run in the same database.

\set ON_ERROR_STOP on

do $$
declare
  v_fixture_count bigint;
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'users'
      and column_name = 'registration_submitted_at'
  ) then
    raise exception 'failed cohort migration left its new column behind';
  end if;

  if to_regclass('public.users_registration_submission_cohort_idx') is not null then
    raise exception 'failed cohort migration left its new index behind';
  end if;

  select pg_catalog.count(*)
    into v_fixture_count
    from public.users
   where id in (
     '10000000-0000-4000-8000-000000000013'::uuid,
     '10000000-0000-4000-8000-000000000014'::uuid
   );

  if v_fixture_count <> 2 then
    raise exception 'refusal fixtures changed unexpectedly: %', v_fixture_count;
  end if;
end;
$$;

delete from public.users
 where id in (
   '10000000-0000-4000-8000-000000000013'::uuid,
   '10000000-0000-4000-8000-000000000014'::uuid
 );
