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
  exists (
    select 1
    from information_schema.columns as column_row
    where column_row.table_schema = 'public'
      and column_row.table_name = 'users'
      and column_row.column_name = 'email_verified_at'
      and column_row.data_type = 'timestamp with time zone'
      and column_row.is_nullable = 'YES'
  ),
  'email_verified_at is missing or has the wrong type'
);

select pg_temp.assert_true(
  (
    select account.is_verified is true
      and account.email_verified_at is null
    from public.users as account
    where account.id = '10000000-0000-4000-8000-000000000004'
  ),
  'legacy verified timing was fabricated during migration'
);

select pg_temp.assert_true(
  exists (
    select 1
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid = 'public.users'::regclass
      and constraint_row.conname = 'users_email_verified_at_boundary_check'
      and constraint_row.convalidated
  ),
  'email verification boundary constraint is missing or unvalidated'
);

select pg_temp.assert_true(
  (
    select function_row.prosecdef is false
      and function_row.provolatile = 'v'
      and function_row.proconfig = array['search_path=""']::text[]
    from pg_catalog.pg_proc as function_row
    where function_row.oid =
      'public.enforce_email_verification_timestamp_v1()'::regprocedure
  )
  and not has_function_privilege(
    'anon',
    'public.enforce_email_verification_timestamp_v1()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'authenticated',
    'public.enforce_email_verification_timestamp_v1()',
    'EXECUTE'
  )
  and not has_function_privilege(
    'service_role',
    'public.enforce_email_verification_timestamp_v1()',
    'EXECUTE'
  ),
  'private verification trigger function security or ACL drifted'
);

insert into public.users (
  id, email, is_guest, is_verified, created_at,
  registration_environment, registration_submitted_at,
  subscription_tier, subscription_status, subscription_provider
) values (
  '20000000-0000-4000-8000-000000000001',
  'ordered-journey@example.test',
  false,
  false,
  pg_catalog.statement_timestamp() - interval '2 hours',
  'production',
  pg_catalog.statement_timestamp() - interval '2 hours',
  'professional',
  'active',
  'stripe'
);

insert into public.product_events (
  user_id, environment, event_name, event_key, source, created_at
)
select
  account.id,
  'production',
  'AccountCreated',
  'measurement-account-created',
  'verification-test',
  account.registration_submitted_at + interval '1 minute'
from public.users as account
where account.id = '20000000-0000-4000-8000-000000000001';

insert into public.chat_jobs (user_id, status, updated_at)
select
  account.id,
  'completed',
  account.registration_submitted_at + interval '30 minutes'
from public.users as account
where account.id = '20000000-0000-4000-8000-000000000001';

insert into public.product_events (
  user_id, environment, event_name, event_key, source, created_at
)
select
  account.id,
  'production',
  'ActivationReached',
  'measurement-preverification-activation',
  'verification-test',
  account.registration_submitted_at + interval '40 minutes'
from public.users as account
where account.id = '20000000-0000-4000-8000-000000000001';

do $$
declare
  v_since timestamptz;
  v_until timestamptz;
  v_activation bigint;
  v_active_paid bigint;
  v_weekly_payers bigint;
  v_weekly_active_paid bigint;
  v_project_activation bigint;
begin
  select
    account.registration_submitted_at - interval '1 minute',
    pg_catalog.statement_timestamp() + interval '1 minute'
    into strict v_since, v_until
  from public.users as account
  where account.id = '20000000-0000-4000-8000-000000000001';

  select
    max(report.accounts) filter (where report.metric = 'activation_reached'),
    max(report.accounts) filter (where report.metric = 'active_paid_now')
    into strict v_activation, v_active_paid
  from public.product_growth_funnel_snapshot(
    v_since, v_until, 'production', false
  ) as report;

  select
    coalesce(sum(report.distinct_payers), 0),
    coalesce(sum(report.active_paid_now), 0)
    into v_weekly_payers, v_weekly_active_paid
  from public.product_weekly_attribution_export(
    v_since, v_until, 'production', false
  ) as report;

  select coalesce(sum(report.activation_reached), 0)
    into v_project_activation
  from public.product_project_continuity_snapshot(
    v_since, v_until, 'production', false
  ) as report;

  if v_activation <> 0
     or v_active_paid <> 0
     or v_weekly_payers <> 0
     or v_weekly_active_paid <> 0
     or v_project_activation <> 0 then
    raise exception
      'pre-verification state leaked into metrics: activation=% paid=% weekly_payers=% weekly_active_paid=% project=%',
      v_activation,
      v_active_paid,
      v_weekly_payers,
      v_weekly_active_paid,
      v_project_activation;
  end if;
end;
$$;

update public.users
   set email_verified_at = timestamptz '2000-01-01 00:00:00+00'
 where id = '20000000-0000-4000-8000-000000000001';

select pg_temp.assert_true(
  (
    select account.email_verified_at is null
    from public.users as account
    where account.id = '20000000-0000-4000-8000-000000000001'
  ),
  'caller supplied verification time was accepted without verification'
);

update public.users
   set is_verified = true,
       email_verified_at = timestamptz '2000-01-01 00:00:00+00'
 where id = '20000000-0000-4000-8000-000000000001';

create temporary table verification_test_clock as
select
  account.id as user_id,
  account.registration_submitted_at,
  account.email_verified_at
from public.users as account
where account.id = '20000000-0000-4000-8000-000000000001';

select pg_temp.assert_true(
  (
    select clock.email_verified_at is not null
      and clock.email_verified_at <> timestamptz '2000-01-01 00:00:00+00'
      and clock.email_verified_at >= clock.registration_submitted_at
    from verification_test_clock as clock
  ),
  'verification transition did not receive a database timestamp'
);

update public.users
   set email_verified_at = email_verified_at + interval '1 day'
 where id = '20000000-0000-4000-8000-000000000001';

select pg_temp.assert_true(
  (
    select account.email_verified_at = clock.email_verified_at
    from public.users as account
    join verification_test_clock as clock
      on clock.user_id = account.id
  ),
  'verification timestamp was not immutable'
);

-- A pre-verification job cannot become a verified activation merely because a
-- later reconciler moves its completion time past the verification boundary.
update public.chat_jobs as job
   set updated_at = clock.email_verified_at + interval '30 seconds'
  from verification_test_clock as clock
 where job.user_id = clock.user_id
   and job.created_at < clock.email_verified_at;

do $$
declare
  v_since timestamptz;
  v_until timestamptz;
  v_activation bigint;
begin
  select
    clock.registration_submitted_at - interval '1 minute',
    clock.email_verified_at + interval '1 minute'
    into strict v_since, v_until
  from verification_test_clock as clock;

  select report.accounts
    into strict v_activation
  from public.product_growth_funnel_snapshot(
    v_since, v_until, 'production', false
  ) as report
  where report.metric = 'activation_reached';

  if v_activation <> 0 then
    raise exception 'pre-verification completed answer activated after verification: %',
      v_activation;
  end if;
end;
$$;

insert into public.chat_jobs (user_id, status, created_at, updated_at)
select
  clock.user_id,
  'completed',
  clock.email_verified_at + interval '4 minutes',
  clock.email_verified_at + interval '5 minutes'
from verification_test_clock as clock;

insert into public.projects (id, user_id, archived_at, created_at)
select
  '20000000-0000-4000-8000-000000000101',
  clock.user_id,
  null,
  clock.email_verified_at + interval '6 minutes'
from verification_test_clock as clock;

insert into public.project_chats (user_id, project_id, created_at)
select
  clock.user_id,
  '20000000-0000-4000-8000-000000000101',
  clock.email_verified_at + interval '7 minutes'
from verification_test_clock as clock;

insert into public.user_files (
  id, user_id, kind, status, size_bytes, deleted_at, created_at
)
select
  '20000000-0000-4000-8000-000000000201',
  clock.user_id,
  'generated_document',
  'ready',
  128,
  null,
  clock.email_verified_at + interval '8 minutes'
from verification_test_clock as clock;

insert into public.project_files (user_id, project_id, file_id, created_at)
select
  clock.user_id,
  '20000000-0000-4000-8000-000000000101',
  '20000000-0000-4000-8000-000000000201',
  clock.email_verified_at + interval '9 minutes'
from verification_test_clock as clock;

insert into public.product_events (
  user_id, environment, event_name, event_key, source, created_at
)
select clock.user_id, 'production', event_row.event_name,
       event_row.event_key, event_row.source, event_row.created_at
from verification_test_clock as clock
cross join lateral (
  values
    (
      'ActivationReached'::text,
      'measurement-postverification-activation'::text,
      'verification-test'::text,
      clock.email_verified_at + interval '5 minutes'
    ),
    (
      'ProjectSaveOfferShown'::text,
      'project-save-offer-shown:conversation_result:2026-10-24'::text,
      'conversation_result'::text,
      clock.email_verified_at + interval '6 minutes'
    ),
    (
      'ProjectSaveIntentReached'::text,
      'project-save-intent'::text,
      'new_project'::text,
      clock.email_verified_at + interval '7 minutes'
    ),
    (
      'ProjectSaveCompleted'::text,
      'result-action-save'::text,
      'new_project'::text,
      clock.email_verified_at + interval '8 minutes'
    ),
    (
      'RecentWorkResumed'::text,
      'measurement-project-resumed'::text,
      'project'::text,
      clock.email_verified_at + interval '9 minutes'
    ),
    (
      'WorkspaceOpened'::text,
      'measurement-d1-workspace'::text,
      'verification-test'::text,
      (
        pg_catalog.date_trunc('day', clock.email_verified_at at time zone 'UTC')
        + interval '1 day 12 hours'
      ) at time zone 'UTC'
    ),
    (
      'WorkspaceOpened'::text,
      'measurement-d7-workspace'::text,
      'verification-test'::text,
      (
        pg_catalog.date_trunc('day', clock.email_verified_at at time zone 'UTC')
        + interval '7 days 12 hours'
      ) at time zone 'UTC'
    )
) as event_row(event_name, event_key, source, created_at);

do $$
declare
  v_since timestamptz;
  v_until timestamptz;
  v_verified bigint;
  v_activation bigint;
  v_durable bigint;
  v_active_paid bigint;
  v_d1 bigint;
  v_d7 bigint;
  v_weekly_activation bigint;
  v_weekly_durable bigint;
  v_weekly_project bigint;
  v_weekly_file bigint;
  v_weekly_payers bigint;
  v_weekly_active_paid bigint;
  v_project_activation bigint;
  v_project_completion bigint;
  v_project_resume bigint;
begin
  select
    clock.registration_submitted_at - interval '1 minute',
    (
      pg_catalog.date_trunc('day', clock.email_verified_at at time zone 'UTC')
      + interval '9 days'
    ) at time zone 'UTC'
    into strict v_since, v_until
  from verification_test_clock as clock;

  select
    max(report.accounts) filter (where report.metric = 'verified_now'),
    max(report.accounts) filter (where report.metric = 'activation_reached'),
    max(report.accounts) filter (where report.metric = 'durable_value_reached'),
    max(report.accounts) filter (where report.metric = 'active_paid_now'),
    max(report.accounts) filter (where report.metric = 'd1_returned'),
    max(report.accounts) filter (where report.metric = 'd7_returned')
    into v_verified, v_activation, v_durable, v_active_paid, v_d1, v_d7
  from public.product_growth_funnel_snapshot(
    v_since, v_until, 'production', false
  ) as report;

  select
    coalesce(sum(report.activation_reached_24h), 0),
    coalesce(sum(report.durable_value_reached_24h), 0),
    coalesce(sum(report.project_created_reached_24h), 0),
    coalesce(sum(report.project_file_reached_24h), 0),
    coalesce(sum(report.distinct_payers), 0),
    coalesce(sum(report.active_paid_now), 0)
    into v_weekly_activation, v_weekly_durable, v_weekly_project, v_weekly_file,
         v_weekly_payers, v_weekly_active_paid
  from public.product_weekly_attribution_export(
    v_since, v_until, 'production', false
  ) as report;

  select
    coalesce(sum(report.activation_reached), 0),
    coalesce(sum(report.project_save_completed), 0),
    coalesce(sum(report.project_resumed_after_save), 0)
    into v_project_activation, v_project_completion, v_project_resume
  from public.product_project_continuity_snapshot(
    v_since, v_until, 'production', false
  ) as report;

  if v_verified <> 1
     or v_activation <> 1
     or v_durable <> 1
     or v_active_paid <> 1
     or v_d1 <> 1
     or v_d7 <> 1
     or v_weekly_activation <> 1
     or v_weekly_durable <> 1
     or v_weekly_project <> 1
     or v_weekly_file <> 1
     or v_weekly_payers <> 1
     or v_weekly_active_paid <> 1
     or v_project_activation <> 1
     or v_project_completion <> 1
     or v_project_resume <> 1 then
    raise exception
      'ordered journey mismatch verified=% activation=% durable=% paid=% d1=% d7=% weekly_activation=% weekly_durable=% weekly_project=% weekly_file=% weekly_payers=% weekly_active_paid=% project_activation=% project_completion=% project_resume=%',
      v_verified,
      v_activation,
      v_durable,
      v_active_paid,
      v_d1,
      v_d7,
      v_weekly_activation,
      v_weekly_durable,
      v_weekly_project,
      v_weekly_file,
      v_weekly_payers,
      v_weekly_active_paid,
      v_project_activation,
      v_project_completion,
      v_project_resume;
  end if;
end;
$$;

insert into public.users (
  id, email, is_guest, is_verified, created_at,
  registration_environment, registration_submitted_at
) values (
  '20000000-0000-4000-8000-000000000002',
  'window-stability@example.test',
  false,
  false,
  pg_catalog.statement_timestamp() - interval '1 hour',
  'development',
  pg_catalog.statement_timestamp() - interval '1 hour'
);

update public.users
   set is_verified = true
 where id = '20000000-0000-4000-8000-000000000002';

do $$
declare
  v_registration_at timestamptz;
  v_verified_at timestamptz;
  v_before bigint;
  v_after bigint;
begin
  select account.registration_submitted_at, account.email_verified_at
    into strict v_registration_at, v_verified_at
  from public.users as account
  where account.id = '20000000-0000-4000-8000-000000000002';

  select report.accounts
    into strict v_before
  from public.product_growth_funnel_snapshot(
    v_registration_at - interval '1 minute',
    v_verified_at - interval '1 microsecond',
    'development',
    false
  ) as report
  where report.metric = 'verified_now';

  select report.accounts
    into strict v_after
  from public.product_growth_funnel_snapshot(
    v_registration_at - interval '1 minute',
    v_verified_at + interval '1 second',
    'development',
    false
  ) as report
  where report.metric = 'verified_now';

  if v_before <> 0 or v_after <> 1 then
    raise exception 'verification window rewrote history: before=% after=%',
      v_before,
      v_after;
  end if;
end;
$$;

do $$
declare
  v_accounts bigint;
  v_verified bigint;
begin
  select
    max(report.accounts) filter (where report.metric = 'accounts_created'),
    max(report.accounts) filter (where report.metric = 'verified_now')
    into v_accounts, v_verified
  from public.product_growth_funnel_snapshot(
    '2026-10-04 00:00:00+00',
    '2026-10-05 00:00:00+00',
    'production',
    false
  ) as report;

  if v_accounts <> 1 or v_verified <> 0 then
    raise exception 'legacy unknown verification timing was fabricated: accounts=% verified=%',
      v_accounts,
      v_verified;
  end if;
end;
$$;

insert into public.users (
  id, email, is_guest, is_verified, created_at,
  registration_environment, registration_submitted_at, internal_tier
) values (
  '20000000-0000-4000-8000-000000000003',
  'born-verified-internal@example.test',
  false,
  true,
  pg_catalog.statement_timestamp() - interval '1 minute',
  'development',
  pg_catalog.statement_timestamp() - interval '1 minute',
  'professional'
);

select pg_temp.assert_true(
  (
    select account.email_verified_at is not null
      and account.email_verified_at >= account.created_at
    from public.users as account
    where account.id = '20000000-0000-4000-8000-000000000003'
  ),
  'a row inserted verified did not receive a database timestamp'
);

do $$
declare
  report_oid regprocedure;
  report_row record;
  report_definition text;
begin
  foreach report_oid in array array[
    'public.product_growth_funnel_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure,
    'public.product_weekly_attribution_export(timestamptz,timestamptz,text,boolean)'::regprocedure,
    'public.product_project_continuity_snapshot(timestamptz,timestamptz,text,boolean)'::regprocedure
  ]
  loop
    select
      function_row.prosecdef,
      function_row.provolatile,
      function_row.proconfig,
      pg_catalog.pg_get_functiondef(function_row.oid)
      into strict report_row
    from pg_catalog.pg_proc as function_row
    where function_row.oid = report_oid;

    report_definition := report_row.pg_get_functiondef;
    if report_row.prosecdef
       or report_row.provolatile <> 's'
       or report_row.proconfig <> array['search_path=""']::text[]
       or has_function_privilege('anon', report_oid, 'EXECUTE')
       or has_function_privilege('authenticated', report_oid, 'EXECUTE')
       or not has_function_privilege('service_role', report_oid, 'EXECUTE')
       or pg_catalog.strpos(report_definition, 'email_verified_at') = 0 then
      raise exception '% verification boundary, security, or ACL drifted',
        report_oid::text;
    end if;
  end loop;
end;
$$;

select pg_temp.assert_true(
  (
    select report.accounts = 4
    from public.product_growth_funnel_snapshot(
      '2026-10-01 00:00:00+00',
      '2026-10-10 00:00:00+00',
      'production',
      false
    ) as report
    where report.metric = 'accounts_created'
  )
  and (
    select report.accounts = 5
    from public.product_growth_funnel_snapshot(
      '2026-10-01 00:00:00+00',
      '2026-10-10 00:00:00+00',
      'production',
      true
    ) as report
    where report.metric = 'accounts_created'
  ),
  'synthetic preview or internal account exclusions drifted'
);
