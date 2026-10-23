\set ON_ERROR_STOP on

create or replace function pg_temp.assert_true(
  condition boolean,
  failure_message text
)
returns void
language plpgsql
as $$
begin
  if condition is not true then
    raise exception 'PostgreSQL migration gate failed: %', failure_message;
  end if;
end;
$$;

select pg_temp.assert_true(
  (
    select account.registration_submitted_at = timestamptz '2026-10-06 00:00:00+00'
      and account.registration_environment = 'production'
    from public.users as account
    where account.id = '10000000-0000-4000-8000-000000000001'
  ),
  'the earliest valid AccountCreated event was not used for backfill'
);

select pg_temp.assert_true(
  (
    select account.registration_submitted_at is null
    from public.users as account
    where account.id = '10000000-0000-4000-8000-000000000002'
  ),
  'a preview-only guest was fabricated into a registration'
);

-- During schema-first rollout, an older application instance will update the
-- guest email without knowing the new marker column. The database must still
-- create the authoritative boundary instead of falling back to guest age.
insert into public.users (
  id, email, is_guest, created_at, registration_environment
) values (
  '10000000-0000-4000-8000-000000000010',
  'guest-10000000-0000-4000-8000-000000000010@guest.askcrump.local',
  true,
  '2020-01-01 00:00:00+00',
  'production'
);

update public.users
   set email = 'rollout-conversion@example.test'
 where id = '10000000-0000-4000-8000-000000000010';

select pg_temp.assert_true(
  (
    select account.registration_submitted_at is not null
      and account.registration_submitted_at > account.created_at
      and account.registration_environment = 'production'
      and account.is_guest is true
    from public.users as account
    where account.id = '10000000-0000-4000-8000-000000000010'
  ),
  'an old application conversion was not assigned a durable cohort boundary'
);

-- During schema-first rollout, an older application instance can also create
-- a fresh registered account without knowing the new marker column. The
-- INSERT trigger must stamp it at the database boundary.
insert into public.users (
  id, email, is_guest, created_at, registration_environment
) values (
  '10000000-0000-4000-8000-000000000012',
  'rollout-fresh@example.test',
  false,
  '2026-10-24 00:00:00+00',
  'production'
);

select pg_temp.assert_true(
  (
    select account.registration_submitted_at is not null
      and account.registration_submitted_at >= account.created_at
      and account.registration_environment = 'production'
      and account.is_guest is false
    from public.users as account
    where account.id = '10000000-0000-4000-8000-000000000012'
  ),
  'an old application fresh registration was not assigned a durable boundary'
);

-- A post-launch preview identity cannot become a non-guest without first
-- receiving the durable registration marker.
insert into public.users (
  id, email, is_guest, created_at, registration_environment
) values (
  '10000000-0000-4000-8000-000000000011',
  'guest-10000000-0000-4000-8000-000000000011@guest.askcrump.local',
  true,
  '2026-10-24 00:00:00+00',
  'production'
);

do $$
begin
  begin
    update public.users
       set is_guest = false
     where id = '10000000-0000-4000-8000-000000000011';
    raise exception 'unmarked post-launch guest verification unexpectedly succeeded';
  exception
    when check_violation then
      null;
  end;
end;
$$;

insert into public.users (
  id, email, is_guest, is_verified, created_at,
  registration_environment, registration_submitted_at,
  deleted_at, internal_tier
) values
  (
    '10000000-0000-4000-8000-000000000003',
    'unverified@example.test', true, false,
    '2026-09-30 00:00:00+00', 'production', '2026-10-03 00:00:00+00',
    null, null
  ),
  (
    '10000000-0000-4000-8000-000000000005',
    'later@example.test', false, false,
    '2026-10-05 00:00:00+00', 'production', '2026-10-11 00:00:00+00',
    null, null
  ),
  (
    '10000000-0000-4000-8000-000000000006',
    'preview@example.test', false, false,
    '2026-10-05 00:00:00+00', 'preview', '2026-10-05 00:01:00+00',
    null, null
  ),
  (
    '10000000-0000-4000-8000-000000000007',
    'deleted@example.test', false, false,
    '2026-10-05 00:00:00+00', 'production', '2026-10-05 00:02:00+00',
    '2026-10-06 00:00:00+00', null
  ),
  (
    '10000000-0000-4000-8000-000000000008',
    'internal@example.test', false, false,
    '2026-10-05 00:00:00+00', 'production', '2026-10-05 00:03:00+00',
    null, 'professional'
  );

-- A resend/retry-style update may change other fields, but it cannot move the
-- first accepted registration boundary or its environment.
update public.users
   set registration_submitted_at = '2026-10-08 00:00:00+00',
       registration_environment = 'preview',
       is_verified = true
 where id = '10000000-0000-4000-8000-000000000003';

select pg_temp.assert_true(
  (
    select account.registration_submitted_at = timestamptz '2026-10-03 00:00:00+00'
      and account.registration_environment = 'production'
      and account.is_verified is true
    from public.users as account
    where account.id = '10000000-0000-4000-8000-000000000003'
  ),
  'retry changed the cohort anchor or blocked an unrelated verification update'
);

do $$
begin
  begin
    update public.users
       set registration_submitted_at = '2026-10-03 00:00:00+00',
           registration_environment = null
     where id = '10000000-0000-4000-8000-000000000002';
    raise exception 'invalid first registration marker unexpectedly succeeded';
  exception
    when check_violation then
      null;
  end;
end;
$$;

select pg_temp.assert_true(
  not has_function_privilege(
    'anon',
    'public.enforce_registration_submission_immutability_v1()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated',
    'public.enforce_registration_submission_immutability_v1()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'service_role',
    'public.enforce_registration_submission_immutability_v1()',
    'EXECUTE'
  ),
  'the private registration trigger function is directly executable'
);

do $$
declare
  report_name text;
  report_oid regprocedure;
  report_row record;
begin
  foreach report_oid in array array[
    'public.product_growth_funnel_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure,
    'public.product_weekly_attribution_export(timestamptz,timestamptz,text,boolean)'::regprocedure,
    'public.product_project_continuity_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure
  ]
  loop
    select
      function_row.proname,
      function_row.prosecdef,
      function_row.provolatile,
      function_row.proconfig
    into strict report_row
    from pg_catalog.pg_proc as function_row
    where function_row.oid = report_oid;

    report_name := report_row.proname;
    if report_row.prosecdef
       or report_row.provolatile <> 's'
       or report_row.proconfig <> array['search_path=""']::text[]
       or has_function_privilege('anon', report_oid, 'EXECUTE')
       or has_function_privilege('authenticated', report_oid, 'EXECUTE')
       or not has_function_privilege('service_role', report_oid, 'EXECUTE') then
      raise exception '% security, volatility, search path, or ACL drifted', report_name;
    end if;
  end loop;
end;
$$;

do $$
declare
  overall_accounts bigint;
  weekly_accounts bigint;
  project_accounts bigint;
  overall_with_internal bigint;
  project_with_internal bigint;
  preview_accounts bigint;
  optional_label text;
  finance_is_null boolean;
begin
  select report.accounts
    into overall_accounts
    from public.product_growth_funnel_snapshot(
      '2026-10-01 00:00:00+00', '2026-10-10 00:00:00+00', 'production', false
    ) as report
    where report.metric = 'accounts_created';

  select coalesce(sum(report.accounts_created), 0)
    into weekly_accounts
    from public.product_weekly_attribution_export(
      '2026-10-01 00:00:00+00', '2026-10-10 00:00:00+00', 'production', false
    ) as report;

  select coalesce(sum(report.accounts_created), 0)
    into project_accounts
    from public.product_project_continuity_snapshot(
      '2026-10-01 00:00:00+00', '2026-10-10 00:00:00+00', 'production', false
    ) as report;

  if overall_accounts <> 4 or weekly_accounts <> 4 or project_accounts <> 3 then
    raise exception 'cohort mismatch overall=% weekly=% project=%',
      overall_accounts, weekly_accounts, project_accounts;
  end if;

  select report.accounts
    into overall_with_internal
    from public.product_growth_funnel_snapshot(
      '2026-10-01 00:00:00+00', '2026-10-10 00:00:00+00', 'production', true
    ) as report
    where report.metric = 'accounts_created';

  select coalesce(sum(report.accounts_created), 0)
    into project_with_internal
    from public.product_project_continuity_snapshot(
      '2026-10-01 00:00:00+00', '2026-10-10 00:00:00+00', 'production', true
    ) as report;

  if overall_with_internal <> 5 or project_with_internal <> 4 then
    raise exception 'internal-account boundary drifted overall=% project=%',
      overall_with_internal, project_with_internal;
  end if;

  select report.accounts
    into preview_accounts
    from public.product_growth_funnel_snapshot(
      '2026-10-01 00:00:00+00', '2026-10-10 00:00:00+00', 'preview', false
    ) as report
    where report.metric = 'accounts_created';

  if preview_accounts <> 1 then
    raise exception 'preview environment boundary drifted: %', preview_accounts;
  end if;

  select report.metric
    into optional_label
    from public.product_growth_funnel_snapshot(
      '2026-10-01 00:00:00+00', '2026-10-10 00:00:00+00', 'production', false
    ) as report
    where report.stage_order = 4;

  if optional_label <> 'optional_profile_completed' then
    raise exception 'optional profile metric label regressed: %', optional_label;
  end if;

  select bool_and(
    report.refund_accounts is null
    and report.recognized_revenue_cents is null
    and report.variable_cost_cents is null
  )
    into finance_is_null
    from public.product_weekly_attribution_export(
      '2026-10-01 00:00:00+00', '2026-10-10 00:00:00+00', 'production', false
    ) as report;

  if finance_is_null is not true then
    raise exception 'weekly finance placeholders stopped being null';
  end if;
end;
$$;
