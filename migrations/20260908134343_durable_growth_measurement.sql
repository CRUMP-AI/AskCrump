-- Ask Crump durable growth measurement correction.
-- Treat completed product work as authoritative when best-effort analytics
-- events are missing, without storing or returning customer content.

begin;

create or replace function public.product_growth_funnel_snapshot(
  p_since timestamptz,
  p_until timestamptz default now(),
  p_environment text default 'production',
  p_include_internal boolean default false
)
returns table (
  stage_order smallint,
  metric text,
  accounts bigint,
  eligible bigint,
  rate_pct numeric
)
language plpgsql
stable
security invoker
set search_path = ''
as $function$
begin
  if p_since is null or p_until is null or p_since >= p_until then
    raise exception 'A valid half-open reporting window is required.'
      using errcode = '22023';
  end if;

  if p_environment not in ('production', 'preview', 'development') then
    raise exception 'Invalid reporting environment.'
      using errcode = '22023';
  end if;

  return query
  with cohort as (
    select
      u.id as user_id,
      u.created_at as cohort_at,
      u.is_verified,
      u.subscription_tier,
      u.subscription_status
    from public.users as u
    where u.created_at >= greatest(
      p_since,
      timestamptz '2026-08-23 09:10:55.602863+00'
    )
      and u.created_at < p_until
      and (
        u.registration_environment = p_environment
        or (p_environment = 'production' and u.registration_environment is null)
      )
      and u.deleted_at is null
      and (
        p_include_internal
        or coalesce(u.internal_tier, '') = ''
      )
  ),
  event_facts as (
    select
      c.user_id,
      c.cohort_at,
      c.is_verified,
      c.subscription_tier,
      c.subscription_status,
      min(e.created_at) filter (where e.event_name = 'AccountCreated')
        as account_event_at,
      min(e.created_at) filter (where e.event_name = 'OnboardingCompleted')
        as onboarding_at,
      min(e.created_at) filter (where e.event_name = 'WorkspaceOpened')
        as workspace_at,
      min(e.created_at) filter (where e.event_name = 'RecentWorkResumed')
        as recent_work_resumed_at,
      min(e.created_at) filter (where e.event_name = 'StarterIntentReached')
        as starter_intent_at,
      min(e.created_at) filter (where e.event_name = 'ActivationReached')
        as activation_event_at,
      min(e.created_at) filter (where e.event_name = 'AhaReached')
        as aha_event_at,
      min(e.created_at) filter (
        where e.event_name = 'OutcomeFeedbackSubmitted'
          and e.source = 'useful'
      ) as outcome_useful_at,
      min(e.created_at) filter (
        where e.event_name = 'OutcomeFeedbackSubmitted'
          and e.source = 'needs_work'
      ) as outcome_needs_work_at,
      min(e.created_at) filter (where e.event_name = 'ResponseShared')
        as response_shared_at,
      min(e.created_at) filter (where e.event_name = 'PlanIntentReached')
        as plan_intent_at,
      min(e.created_at) filter (where e.event_name = 'SubscriptionCheckoutOpened')
        as checkout_opened_at,
      min(e.created_at) filter (where e.event_name = 'SubscriptionCheckoutCompleted')
        as checkout_completed_at
    from cohort as c
    left join public.product_events as e
      on e.user_id = c.user_id
      and e.environment = p_environment
      and e.created_at >= c.cohort_at
      and e.created_at < p_until
    group by
      c.user_id,
      c.cohort_at,
      c.is_verified,
      c.subscription_tier,
      c.subscription_status
  ),
  durable_facts as (
    select
      f.*,
      (
        select min(candidate_at)
        from (
          values
            (f.activation_event_at),
            ((
              select min(j.updated_at)
              from public.chat_jobs as j
              where j.user_id = f.user_id
                and j.status = 'completed'
                and j.updated_at >= f.cohort_at
                and j.updated_at < p_until
            ))
        ) as activation_candidates(candidate_at)
      ) as activation_at,
      (
        select min(candidate_at)
        from (
          values
            (f.aha_event_at),
            ((
              select min(pc.created_at)
              from public.project_chats as pc
              join public.projects as project_row
                on project_row.id = pc.project_id
               and project_row.user_id = pc.user_id
              where pc.user_id = f.user_id
                and project_row.archived_at is null
                and pc.created_at >= f.cohort_at
                and pc.created_at < p_until
            )),
            ((
              select min(pf.created_at)
              from public.project_files as pf
              join public.projects as project_row
                on project_row.id = pf.project_id
               and project_row.user_id = pf.user_id
              where pf.user_id = f.user_id
                and project_row.archived_at is null
                and pf.created_at >= f.cohort_at
                and pf.created_at < p_until
            )),
            ((
              select min(file_row.created_at)
              from public.user_files as file_row
              where file_row.user_id = f.user_id
                and file_row.deleted_at is null
                and file_row.status = 'ready'
                and file_row.size_bytes > 0
                and file_row.kind in (
                  'generated_image',
                  'generated_document',
                  'generated_video',
                  'manuscript_export'
                )
                and file_row.created_at >= f.cohort_at
                and file_row.created_at < p_until
            ))
        ) as aha_candidates(candidate_at)
      ) as aha_at
    from event_facts as f
  ),
  journeys as (
    select
      d.*,
      (
        d.activation_at is not null
        and (p_until at time zone 'UTC')::date
          >= (d.activation_at at time zone 'UTC')::date + 2
      ) as d1_eligible,
      exists (
        select 1
        from public.product_events as d1
        where d1.user_id = d.user_id
          and d1.environment = p_environment
          and d1.event_name = 'WorkspaceOpened'
          and d1.created_at < p_until
          and (d1.created_at at time zone 'UTC')::date
            = (d.activation_at at time zone 'UTC')::date + 1
      ) as d1_returned,
      (
        d.activation_at is not null
        and (p_until at time zone 'UTC')::date
          >= (d.activation_at at time zone 'UTC')::date + 8
      ) as d7_eligible,
      exists (
        select 1
        from public.product_events as d7
        where d7.user_id = d.user_id
          and d7.environment = p_environment
          and d7.event_name = 'WorkspaceOpened'
          and d7.created_at < p_until
          and (d7.created_at at time zone 'UTC')::date
            = (d.activation_at at time zone 'UTC')::date + 7
      ) as d7_returned
    from durable_facts as d
  ),
  stats as (
    select
      count(*) as cohort_accounts,
      count(*) filter (where account_event_at is not null) as account_event_accounts,
      count(*) filter (where is_verified) as verified_accounts,
      count(*) filter (where onboarding_at is not null) as onboarding_accounts,
      count(*) filter (where workspace_at is not null) as workspace_accounts,
      count(*) filter (where recent_work_resumed_at is not null) as recent_work_accounts,
      count(*) filter (where starter_intent_at is not null) as starter_intent_accounts,
      count(*) filter (where activation_at is not null) as activation_accounts,
      count(*) filter (where aha_at is not null) as aha_accounts,
      count(*) filter (where outcome_useful_at is not null) as outcome_useful_accounts,
      count(*) filter (where outcome_needs_work_at is not null) as outcome_needs_work_accounts,
      count(*) filter (where response_shared_at is not null) as shared_accounts,
      count(*) filter (where plan_intent_at is not null) as plan_intent_accounts,
      count(*) filter (where checkout_opened_at is not null) as checkout_opened_accounts,
      count(*) filter (where checkout_completed_at is not null) as checkout_completed_accounts,
      count(*) filter (
        where subscription_tier in ('professional', 'enterprise')
          and subscription_status in ('active', 'trialing')
      ) as active_paid_accounts,
      count(*) filter (where d1_eligible) as d1_eligible_accounts,
      count(*) filter (where d1_eligible and d1_returned) as d1_returned_accounts,
      count(*) filter (where d7_eligible) as d7_eligible_accounts,
      count(*) filter (where d7_eligible and d7_returned) as d7_returned_accounts
    from journeys
  )
  select
    values_table.stage_order,
    values_table.metric,
    values_table.accounts,
    values_table.eligible,
    case
      when values_table.eligible > 0 then
        round(values_table.accounts * 100.0 / values_table.eligible, 1)
      else null
    end as rate_pct
  from stats
  cross join lateral (
    values
      (1::smallint, 'accounts_created'::text, cohort_accounts, cohort_accounts),
      (2::smallint, 'account_event_recorded'::text, account_event_accounts, cohort_accounts),
      (3::smallint, 'verified_now'::text, verified_accounts, cohort_accounts),
      (4::smallint, 'onboarding_completed'::text, onboarding_accounts, cohort_accounts),
      (5::smallint, 'workspace_opened'::text, workspace_accounts, cohort_accounts),
      (6::smallint, 'starter_intent_reached'::text, starter_intent_accounts, cohort_accounts),
      (7::smallint, 'activation_reached'::text, activation_accounts, cohort_accounts),
      (8::smallint, 'outcome_confirmed_useful'::text, outcome_useful_accounts, activation_accounts),
      (9::smallint, 'outcome_reported_needs_work'::text, outcome_needs_work_accounts, activation_accounts),
      (10::smallint, 'durable_value_reached'::text, aha_accounts, cohort_accounts),
      (11::smallint, 'recent_work_resumed'::text, recent_work_accounts, cohort_accounts),
      (12::smallint, 'response_shared'::text, shared_accounts, cohort_accounts),
      (13::smallint, 'plan_intent_reached'::text, plan_intent_accounts, cohort_accounts),
      (14::smallint, 'checkout_opened'::text, checkout_opened_accounts, cohort_accounts),
      (15::smallint, 'checkout_completed'::text, checkout_completed_accounts, cohort_accounts),
      (16::smallint, 'active_paid_now'::text, active_paid_accounts, cohort_accounts),
      (17::smallint, 'd1_returned'::text, d1_returned_accounts, d1_eligible_accounts),
      (18::smallint, 'd7_returned'::text, d7_returned_accounts, d7_eligible_accounts)
  ) as values_table(stage_order, metric, accounts, eligible)
  order by values_table.stage_order;
end;
$function$;

create or replace function public.product_weekly_attribution_export(
  p_since timestamptz,
  p_until timestamptz default now(),
  p_environment text default 'production',
  p_include_internal boolean default false
)
returns table (
  cohort_since timestamptz,
  cohort_until timestamptz,
  acquisition text,
  placement text,
  campaign text,
  creative text,
  intent text,
  accounts_created bigint,
  account_event_recorded bigint,
  verified_now bigint,
  workspace_opened bigint,
  activation_eligible_24h bigint,
  activation_reached_24h bigint,
  useful_feedback_reached_24h bigint,
  durable_value_eligible_24h bigint,
  durable_value_reached_24h bigint,
  decision_grade_value_reached_24h bigint,
  project_created_reached_24h bigint,
  project_file_reached_24h bigint,
  ready_file_reached_24h bigint,
  d1_eligible bigint,
  d1_returned bigint,
  d7_eligible bigint,
  d7_returned bigint,
  plan_intent_reached bigint,
  subscription_checkout_opened bigint,
  subscription_checkout_completed bigint,
  credit_checkout_opened bigint,
  credit_checkout_completed bigint,
  distinct_payers bigint,
  paid_conversion_eligible bigint,
  active_paid_now bigint,
  refund_accounts bigint,
  recognized_revenue_cents bigint,
  variable_cost_cents bigint
)
language plpgsql
stable
security invoker
set search_path = ''
as $function$
begin
  if p_since is null or p_until is null or p_since >= p_until then
    raise exception 'A valid half-open reporting window is required.'
      using errcode = '22023';
  end if;

  if p_environment not in ('production', 'preview', 'development') then
    raise exception 'Invalid reporting environment.'
      using errcode = '22023';
  end if;

  return query
  with cohort as (
    select
      u.id as user_id,
      u.created_at as cohort_at,
      u.is_verified,
      u.subscription_tier,
      u.subscription_status,
      u.subscription_provider
    from public.users as u
    where u.created_at >= greatest(
      p_since,
      timestamptz '2026-08-23 09:10:55.602863+00'
    )
      and u.created_at < p_until
      and (
        u.registration_environment = p_environment
        or (p_environment = 'production' and u.registration_environment is null)
      )
      and u.deleted_at is null
      and (
        p_include_internal
        or coalesce(u.internal_tier, '') = ''
      )
  ),
  event_facts as (
    select
      c.user_id,
      c.cohort_at,
      c.is_verified,
      c.subscription_tier,
      c.subscription_status,
      c.subscription_provider,
      attribution.source as acquisition,
      attribution.placement,
      attribution.campaign,
      attribution.creative,
      attribution.intent,
      attribution.created_at as account_event_at,
      min(e.created_at) filter (where e.event_name = 'WorkspaceOpened')
        as workspace_at,
      min(e.created_at) filter (where e.event_name = 'ActivationReached')
        as activation_event_at,
      min(e.created_at) filter (
        where e.event_name = 'OutcomeFeedbackSubmitted'
          and e.source = 'useful'
      ) as useful_feedback_at,
      min(e.created_at) filter (where e.event_name = 'AhaReached')
        as aha_event_at,
      min(e.created_at) filter (where e.event_name = 'PlanIntentReached')
        as plan_intent_at,
      min(e.created_at) filter (where e.event_name = 'SubscriptionCheckoutOpened')
        as subscription_checkout_opened_at,
      min(e.created_at) filter (where e.event_name = 'SubscriptionCheckoutCompleted')
        as subscription_checkout_completed_at,
      min(e.created_at) filter (where e.event_name = 'CreditCheckoutOpened')
        as credit_checkout_opened_at,
      min(e.created_at) filter (where e.event_name = 'CreditCheckoutCompleted')
        as credit_checkout_completed_at
    from cohort as c
    left join lateral (
      select
        account.source,
        account.placement,
        account.campaign,
        account.creative,
        account.intent,
        account.created_at
      from public.product_events as account
      where account.user_id = c.user_id
        and account.environment = p_environment
        and account.event_name = 'AccountCreated'
        and account.created_at >= c.cohort_at
        and account.created_at < p_until
      order by account.created_at, account.id
      limit 1
    ) as attribution on true
    left join public.product_events as e
      on e.user_id = c.user_id
      and e.environment = p_environment
      and e.created_at >= c.cohort_at
      and e.created_at < p_until
    group by
      c.user_id,
      c.cohort_at,
      c.is_verified,
      c.subscription_tier,
      c.subscription_status,
      c.subscription_provider,
      attribution.source,
      attribution.placement,
      attribution.campaign,
      attribution.creative,
      attribution.intent,
      attribution.created_at
  ),
  durable_anchors as (
    select
      f.*,
      (
        select min(candidate_at)
        from (
          values
            (f.activation_event_at),
            ((
              select min(j.updated_at)
              from public.chat_jobs as j
              where j.user_id = f.user_id
                and j.status = 'completed'
                and j.updated_at >= f.cohort_at
                and j.updated_at < p_until
            ))
        ) as activation_candidates(candidate_at)
      ) as activation_at,
      (
        select min(candidate_at)
        from (
          values
            (f.aha_event_at),
            ((
              select min(pc.created_at)
              from public.project_chats as pc
              join public.projects as project_row
                on project_row.id = pc.project_id
               and project_row.user_id = pc.user_id
              where pc.user_id = f.user_id
                and project_row.archived_at is null
                and pc.created_at >= f.cohort_at
                and pc.created_at < p_until
            )),
            ((
              select min(pf.created_at)
              from public.project_files as pf
              join public.projects as project_row
                on project_row.id = pf.project_id
               and project_row.user_id = pf.user_id
              where pf.user_id = f.user_id
                and project_row.archived_at is null
                and pf.created_at >= f.cohort_at
                and pf.created_at < p_until
            )),
            ((
              select min(file_row.created_at)
              from public.user_files as file_row
              where file_row.user_id = f.user_id
                and file_row.deleted_at is null
                and file_row.status = 'ready'
                and file_row.size_bytes > 0
                and file_row.kind in (
                  'generated_image',
                  'generated_document',
                  'generated_video',
                  'manuscript_export'
                )
                and file_row.created_at >= f.cohort_at
                and file_row.created_at < p_until
            ))
        ) as aha_candidates(candidate_at)
      ) as durable_value_at
    from event_facts as f
  ),
  journey_signals as (
    select
      f.*,
      f.cohort_at + interval '24 hours' <= p_until as eligible_24h,
      (
        f.activation_at is not null
        and f.activation_at <= f.cohort_at + interval '24 hours'
      ) as activation_24h,
      (
        f.useful_feedback_at is not null
        and f.useful_feedback_at <= f.cohort_at + interval '24 hours'
      ) as useful_feedback_24h,
      (
        f.durable_value_at is not null
        and f.durable_value_at <= f.cohort_at + interval '24 hours'
      ) as durable_value_24h,
      exists (
        select 1
        from public.projects as project_row
        where project_row.user_id = f.user_id
          and project_row.archived_at is null
          and project_row.created_at >= f.cohort_at
          and project_row.created_at <= f.cohort_at + interval '24 hours'
          and project_row.created_at < p_until
      ) as project_created_24h,
      exists (
        select 1
        from public.project_files as project_file
        join public.projects as project_row
          on project_row.id = project_file.project_id
          and project_row.user_id = project_file.user_id
          and project_row.archived_at is null
        join public.user_files as file_row
          on file_row.id = project_file.file_id
          and file_row.user_id = project_file.user_id
          and file_row.deleted_at is null
          and file_row.status = 'ready'
        where project_file.user_id = f.user_id
          and project_file.created_at >= f.cohort_at
          and project_file.created_at <= f.cohort_at + interval '24 hours'
          and project_file.created_at < p_until
      ) as project_file_24h,
      exists (
        select 1
        from public.user_files as file_row
        where file_row.user_id = f.user_id
          and file_row.deleted_at is null
          and file_row.status = 'ready'
          and file_row.created_at >= f.cohort_at
          and file_row.created_at <= f.cohort_at + interval '24 hours'
          and file_row.created_at < p_until
      ) as ready_file_24h,
      exists (
        select 1
        from public.credit_ledger as purchase
        where purchase.user_id = f.user_id
          and purchase.reason = 'credit_purchase'
          and purchase.provider in ('stripe', 'revenuecat')
          and purchase.delta > 0
          and purchase.created_at >= f.cohort_at
          and purchase.created_at < p_until
      ) as credit_payer,
      (
        f.activation_at is not null
        and (p_until at time zone 'UTC')::date
          >= (f.activation_at at time zone 'UTC')::date + 2
      ) as d1_is_eligible,
      exists (
        select 1
        from public.product_events as d1
        where d1.user_id = f.user_id
          and d1.environment = p_environment
          and d1.event_name = 'WorkspaceOpened'
          and d1.created_at < p_until
          and (d1.created_at at time zone 'UTC')::date
            = (f.activation_at at time zone 'UTC')::date + 1
      ) as d1_did_return,
      (
        f.activation_at is not null
        and (p_until at time zone 'UTC')::date
          >= (f.activation_at at time zone 'UTC')::date + 8
      ) as d7_is_eligible,
      exists (
        select 1
        from public.product_events as d7
        where d7.user_id = f.user_id
          and d7.environment = p_environment
          and d7.event_name = 'WorkspaceOpened'
          and d7.created_at < p_until
          and (d7.created_at at time zone 'UTC')::date
            = (f.activation_at at time zone 'UTC')::date + 7
      ) as d7_did_return
    from durable_anchors as f
  ),
  journeys as (
    select
      signals.*,
      (
        signals.activation_24h
        and (
          signals.useful_feedback_24h
          or signals.durable_value_24h
        )
      ) as decision_grade_value_24h,
      (
        signals.subscription_tier in ('professional', 'enterprise')
        and signals.subscription_status = 'active'
        and signals.subscription_provider in ('stripe', 'revenuecat')
      ) as active_subscription_payer
    from journey_signals as signals
  )
  select
    greatest(p_since, timestamptz '2026-08-23 09:10:55.602863+00'),
    p_until,
    j.acquisition,
    j.placement,
    j.campaign,
    j.creative,
    j.intent,
    count(*)::bigint,
    count(*) filter (where j.account_event_at is not null)::bigint,
    count(*) filter (where j.is_verified)::bigint,
    count(*) filter (where j.workspace_at is not null)::bigint,
    count(*) filter (where j.eligible_24h)::bigint,
    count(*) filter (where j.eligible_24h and j.activation_24h)::bigint,
    count(*) filter (where j.eligible_24h and j.useful_feedback_24h)::bigint,
    count(*) filter (where j.eligible_24h)::bigint,
    count(*) filter (where j.eligible_24h and j.durable_value_24h)::bigint,
    count(*) filter (
      where j.eligible_24h and j.decision_grade_value_24h
    )::bigint,
    count(*) filter (where j.eligible_24h and j.project_created_24h)::bigint,
    count(*) filter (where j.eligible_24h and j.project_file_24h)::bigint,
    count(*) filter (where j.eligible_24h and j.ready_file_24h)::bigint,
    count(*) filter (where j.d1_is_eligible)::bigint,
    count(*) filter (where j.d1_is_eligible and j.d1_did_return)::bigint,
    count(*) filter (where j.d7_is_eligible)::bigint,
    count(*) filter (where j.d7_is_eligible and j.d7_did_return)::bigint,
    count(*) filter (where j.plan_intent_at is not null)::bigint,
    count(*) filter (where j.subscription_checkout_opened_at is not null)::bigint,
    count(*) filter (where j.subscription_checkout_completed_at is not null)::bigint,
    count(*) filter (where j.credit_checkout_opened_at is not null)::bigint,
    count(*) filter (where j.credit_checkout_completed_at is not null)::bigint,
    count(*) filter (
      where j.active_subscription_payer or j.credit_payer
    )::bigint,
    count(*) filter (
      where j.eligible_24h and j.decision_grade_value_24h
    )::bigint,
    count(*) filter (where j.active_subscription_payer)::bigint,
    null::bigint,
    null::bigint,
    null::bigint
  from journeys as j
  group by
    j.acquisition,
    j.placement,
    j.campaign,
    j.creative,
    j.intent
  order by
    j.acquisition nulls last,
    j.placement nulls last,
    j.campaign nulls last,
    j.creative nulls last,
    j.intent nulls last;
end;
$function$;

comment on function public.product_growth_funnel_snapshot(
  timestamptz,
  timestamptz,
  text,
  boolean
) is
  'Service-role-only, content-free aggregate funnel. Uses completed chat jobs, Project continuity, and generated files as durable outcomes when best-effort product events are absent; D1/D7 denominators remain activation-based.';

comment on function public.product_weekly_attribution_export(
  timestamptz,
  timestamptz,
  text,
  boolean
) is
  'Service-role-only, content-free weekly cohort grouped by immutable AccountCreated attribution. Uses completed chat jobs, Project continuity, and generated files as durable outcomes when best-effort product events are absent; finance fields remain null.';

revoke all on function public.product_growth_funnel_snapshot(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated;
revoke all on function public.product_weekly_attribution_export(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated;
grant execute on function public.product_growth_funnel_snapshot(
  timestamptz, timestamptz, text, boolean
) to service_role;
grant execute on function public.product_weekly_attribution_export(
  timestamptz, timestamptz, text, boolean
) to service_role;

commit;
