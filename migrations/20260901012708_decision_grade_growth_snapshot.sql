-- Ask Crump 5.9.76
-- Complete the privacy-safe weekly cohort with independent useful feedback,
-- decision-grade first value, durable Project/file adoption, and authoritative payer semantics.

begin;

drop function if exists public.product_weekly_attribution_export(
  timestamptz,
  timestamptz,
  text,
  boolean
);

create function public.product_weekly_attribution_export(
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
      and u.registration_environment = p_environment
      and u.deleted_at is null
      and (
        p_include_internal
        or coalesce(u.internal_tier, '') = ''
      )
  ),
  first_events as (
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
        as activation_at,
      min(e.created_at) filter (
        where e.event_name = 'OutcomeFeedbackSubmitted'
          and e.source = 'useful'
      ) as useful_feedback_at,
      min(e.created_at) filter (where e.event_name = 'AhaReached')
        as aha_at,
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
        f.aha_at is not null
        and f.aha_at <= f.cohort_at + interval '24 hours'
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
    from first_events as f
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

revoke execute on function public.product_weekly_attribution_export(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated;
grant execute on function public.product_weekly_attribution_export(
  timestamptz, timestamptz, text, boolean
) to service_role;

comment on function public.product_weekly_attribution_export(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free weekly cohort grouped by the immutable AccountCreated tuple. Technical activation, useful feedback, natural durable value, decision-grade value, Project/file adoption, retention, checkout diagnostics, and provider-backed payer counts remain distinct. Returns counts only; finance fields remain null until an authoritative finance export supplies them.';

commit;
