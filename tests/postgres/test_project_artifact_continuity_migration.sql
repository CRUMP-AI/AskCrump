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
  has_function_privilege(
    'service_role',
    'public.product_project_continuity_snapshot(timestamptz,timestamptz,text,boolean)',
    'EXECUTE'
  )
    and not has_function_privilege(
      'anon',
      'public.product_project_continuity_snapshot(timestamptz,timestamptz,text,boolean)',
      'EXECUTE'
    )
    and not has_function_privilege(
      'authenticated',
      'public.product_project_continuity_snapshot(timestamptz,timestamptz,text,boolean)',
      'EXECUTE'
    ),
  'Project continuity snapshot privileges are not service-role only'
);

do $$
declare
  function_row record;
  expected_result constant text := 'TABLE(cohort_since timestamp with time zone, cohort_until timestamp with time zone, offer_measurement_since timestamp with time zone, acquisition text, placement text, campaign text, creative text, intent text, accounts_created bigint, activation_reached bigint, project_save_offer_shown bigint, project_save_offer_to_intent bigint, project_save_offer_without_later_intent bigint, project_save_intent_without_prior_offer bigint, project_save_intent_reached bigint, project_save_completed bigint, project_save_paired_completion bigint, project_save_intent_without_completion bigint, project_save_completion_without_intent bigint, project_resumed_after_save bigint, offer_to_intent_rate_pct numeric, intent_to_completion_rate_pct numeric, completion_to_resume_rate_pct numeric)';
begin
  select
    p.prosecdef,
    p.provolatile,
    p.proconfig,
    pg_get_function_result(p.oid) as result_contract
  into strict function_row
  from pg_proc as p
  join pg_namespace as n on n.oid = p.pronamespace
  where n.nspname = 'public'
    and p.proname = 'product_project_continuity_snapshot'
    and pg_get_function_identity_arguments(p.oid) = 'p_since timestamp with time zone, p_until timestamp with time zone, p_environment text, p_include_internal boolean';

  if function_row.prosecdef
     or function_row.provolatile <> 's'
     or function_row.proconfig <> array['search_path=""']::text[]
     or function_row.result_contract <> expected_result then
    raise exception 'function volatility, invoker security, search path, or return contract drifted';
  end if;
end;
$$;

insert into public.users (
  id, created_at, registration_environment, internal_tier
) values
  ('10000000-0000-4000-8000-000000000001', '2026-09-15 00:00:00+00', 'production', null),
  ('10000000-0000-4000-8000-000000000002', '2026-09-15 00:01:00+00', 'production', null),
  ('10000000-0000-4000-8000-000000000003', '2026-09-15 00:02:00+00', 'production', null),
  ('10000000-0000-4000-8000-000000000004', '2026-09-15 00:03:00+00', 'production', null),
  ('10000000-0000-4000-8000-000000000005', '2026-09-15 00:04:00+00', 'preview', null),
  ('10000000-0000-4000-8000-000000000006', '2026-09-15 00:05:00+00', 'production', 'founder');

insert into public.product_events (
  user_id, environment, event_name, event_key, source, created_at
) values
  ('10000000-0000-4000-8000-000000000001', 'production', 'AccountCreated', 'account-created', 'organic', '2026-09-15 00:00:00+00'),
  ('10000000-0000-4000-8000-000000000002', 'production', 'AccountCreated', 'account-created', 'organic', '2026-09-15 00:01:00+00'),
  ('10000000-0000-4000-8000-000000000003', 'production', 'AccountCreated', 'account-created', 'organic', '2026-09-15 00:02:00+00'),
  ('10000000-0000-4000-8000-000000000004', 'production', 'AccountCreated', 'account-created', 'organic', '2026-09-15 00:03:00+00'),
  ('10000000-0000-4000-8000-000000000005', 'preview', 'AccountCreated', 'account-created', 'organic', '2026-09-15 00:04:00+00'),
  ('10000000-0000-4000-8000-000000000006', 'production', 'AccountCreated', 'account-created', 'organic', '2026-09-15 00:05:00+00'),

  ('10000000-0000-4000-8000-000000000001', 'production', 'ProjectSaveOfferShown', 'project-save-offer-shown:artifact_result:2026-09-15', 'artifact_result', '2026-09-15 01:00:00+00'),
  ('10000000-0000-4000-8000-000000000001', 'production', 'ProjectSaveIntentReached', 'project-save-intent', 'new_project', '2026-09-15 01:01:00+00'),
  ('10000000-0000-4000-8000-000000000001', 'production', 'ProjectSaveCompleted', 'result-artifact-save', 'generated_document', '2026-09-15 01:00:30+00'),
  ('10000000-0000-4000-8000-000000000001', 'production', 'ProjectSaveCompleted', 'result-artifact-save', 'generated_image', '2026-09-15 01:02:00+00'),
  ('10000000-0000-4000-8000-000000000001', 'production', 'RecentWorkResumed', 'recent-work-resumed:project:2026-09-16', 'project', '2026-09-16 01:02:00+00'),

  ('10000000-0000-4000-8000-000000000002', 'production', 'RecentWorkResumed', 'recent-work-resumed:project:2026-09-15', 'project', '2026-09-15 01:59:00+00'),
  ('10000000-0000-4000-8000-000000000002', 'production', 'ProjectSaveCompleted', 'result-artifact-save', 'generated_image', '2026-09-15 02:00:00+00'),

  ('10000000-0000-4000-8000-000000000003', 'production', 'ProjectSaveOfferShown', 'project-save-offer-shown:conversation_result:2026-09-15', 'conversation_result', '2026-09-15 03:00:00+00'),
  ('10000000-0000-4000-8000-000000000003', 'production', 'ProjectSaveIntentReached', 'project-save-intent', 'existing_project', '2026-09-15 03:01:00+00'),
  ('10000000-0000-4000-8000-000000000003', 'production', 'ProjectSaveCompleted', 'result-action-save', 'existing_project', '2026-09-15 03:02:00+00'),
  ('10000000-0000-4000-8000-000000000003', 'production', 'RecentWorkResumed', 'recent-work-resumed:project:2026-09-17', 'project', '2026-09-17 03:02:00+00'),

  ('10000000-0000-4000-8000-000000000004', 'production', 'ProjectSaveCompleted', 'result-artifact-save', 'generated_video', '2026-09-15 04:00:00+00'),
  ('10000000-0000-4000-8000-000000000004', 'production', 'ProjectSaveCompleted', 'result-artifact-save', 'new_project', '2026-09-15 04:01:00+00'),
  ('10000000-0000-4000-8000-000000000004', 'production', 'ProjectSaveCompleted', 'result-action-save', 'generated_document', '2026-09-15 04:02:00+00'),
  ('10000000-0000-4000-8000-000000000004', 'production', 'ProjectSaveCompleted', 'result-action-save', 'new_project', '2026-09-20 00:00:00+00'),

  ('10000000-0000-4000-8000-000000000005', 'preview', 'ProjectSaveCompleted', 'result-artifact-save', 'generated_document', '2026-09-15 05:00:00+00'),
  ('10000000-0000-4000-8000-000000000006', 'production', 'ProjectSaveCompleted', 'result-artifact-save', 'generated_document', '2026-09-15 06:00:00+00');

do $$
declare
  observed record;
begin
  select * into observed
  from public.product_project_continuity_snapshot(
    timestamptz '2026-09-15 00:00:00+00',
    timestamptz '2026-09-20 00:00:00+00',
    'production',
    false
  )
  where acquisition = 'organic';

  if observed.accounts_created <> 4 then
    raise exception 'expected four external production accounts, got %', observed.accounts_created;
  end if;
  if observed.project_save_offer_shown <> 2
     or observed.project_save_offer_to_intent <> 2
     or observed.project_save_offer_without_later_intent <> 0
     or observed.project_save_intent_without_prior_offer <> 0 then
    raise exception 'offer-to-intent counts were not preserved';
  end if;
  if observed.project_save_intent_reached <> 2
     or observed.project_save_completed <> 3
     or observed.project_save_paired_completion <> 2
     or observed.project_save_intent_without_completion <> 0
     or observed.project_save_completion_without_intent <> 1 then
    raise exception 'conversation and generated-artifact completions were not classified exactly';
  end if;
  if observed.project_resumed_after_save <> 2 then
    raise exception 'resume-after-save count was not preserved';
  end if;
  if observed.offer_to_intent_rate_pct <> 100.00
     or observed.intent_to_completion_rate_pct <> 100.00
     or observed.completion_to_resume_rate_pct <> 66.67 then
    raise exception 'continuity rates were not derived from the corrected denominators';
  end if;
end;
$$;

select pg_temp.assert_true(
  (
    select project_save_completed
    from public.product_project_continuity_snapshot(
      timestamptz '2026-09-15 00:00:00+00',
      timestamptz '2026-09-20 00:00:00+00',
      'production',
      true
    )
    where acquisition = 'organic'
  ) = 4,
  'explicit internal inclusion did not add the founder completion'
);
