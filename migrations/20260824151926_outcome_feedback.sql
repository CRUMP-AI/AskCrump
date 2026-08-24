-- Ask Crump 5.9.12
-- Add binary, content-free result feedback to the private product journey.

begin;

alter table public.product_events
  drop constraint if exists product_events_event_name_check;

alter table public.product_events
  add constraint product_events_event_name_check check (event_name in (
    'AccountCreated',
    'OnboardingCompleted',
    'WorkspaceOpened',
    'StarterIntentReached',
    'ActivationReached',
    'AhaReached',
    'OutcomeFeedbackSubmitted',
    'PlanIntentReached',
    'ResponseShared',
    'SubscriptionCheckoutOpened',
    'SubscriptionCheckoutCompleted',
    'BillingPortalOpened',
    'SubscriptionStatusChanged'
  ));

comment on table public.product_events is
  'Server-only, allowlisted product milestones. No prompts, responses, filenames, emails, payment details, or arbitrary metadata. Deleted with the owning account.';

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
    where u.created_at >= p_since
      and u.created_at < p_until
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
      min(e.created_at) filter (where e.event_name = 'AccountCreated')
        as account_event_at,
      min(e.created_at) filter (where e.event_name = 'OnboardingCompleted')
        as onboarding_at,
      min(e.created_at) filter (where e.event_name = 'WorkspaceOpened')
        as workspace_at,
      min(e.created_at) filter (where e.event_name = 'StarterIntentReached')
        as starter_intent_at,
      min(e.created_at) filter (where e.event_name = 'ActivationReached')
        as activation_at,
      min(e.created_at) filter (where e.event_name = 'AhaReached')
        as aha_at,
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
  anchored as (
    select
      f.*,
      coalesce(f.activation_at, f.cohort_at) as retention_anchor_at
    from first_events as f
  ),
  journeys as (
    select
      a.*,
      (
        (p_until at time zone 'UTC')::date
        >= (a.retention_anchor_at at time zone 'UTC')::date + 2
      ) as d1_eligible,
      exists (
        select 1
        from public.product_events as d1
        where d1.user_id = a.user_id
          and d1.environment = p_environment
          and d1.event_name = 'WorkspaceOpened'
          and d1.created_at < p_until
          and (d1.created_at at time zone 'UTC')::date
            = (a.retention_anchor_at at time zone 'UTC')::date + 1
      ) as d1_returned,
      (
        (p_until at time zone 'UTC')::date
        >= (a.retention_anchor_at at time zone 'UTC')::date + 8
      ) as d7_eligible,
      exists (
        select 1
        from public.product_events as d7
        where d7.user_id = a.user_id
          and d7.environment = p_environment
          and d7.event_name = 'WorkspaceOpened'
          and d7.created_at < p_until
          and (d7.created_at at time zone 'UTC')::date
            = (a.retention_anchor_at at time zone 'UTC')::date + 7
      ) as d7_returned
    from anchored as a
  ),
  stats as (
    select
      count(*) as cohort_accounts,
      count(*) filter (where account_event_at is not null) as account_event_accounts,
      count(*) filter (where is_verified) as verified_accounts,
      count(*) filter (where onboarding_at is not null) as onboarding_accounts,
      count(*) filter (where workspace_at is not null) as workspace_accounts,
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
      (11::smallint, 'response_shared'::text, shared_accounts, cohort_accounts),
      (12::smallint, 'plan_intent_reached'::text, plan_intent_accounts, cohort_accounts),
      (13::smallint, 'checkout_opened'::text, checkout_opened_accounts, cohort_accounts),
      (14::smallint, 'checkout_completed'::text, checkout_completed_accounts, cohort_accounts),
      (15::smallint, 'active_paid_now'::text, active_paid_accounts, cohort_accounts),
      (16::smallint, 'd1_returned'::text, d1_returned_accounts, d1_eligible_accounts),
      (17::smallint, 'd7_returned'::text, d7_returned_accounts, d7_eligible_accounts)
  ) as values_table(stage_order, metric, accounts, eligible)
  order by values_table.stage_order;
end;
$function$;

revoke execute on function public.product_growth_funnel_snapshot(
  timestamptz,
  timestamptz,
  text,
  boolean
) from public, anon, authenticated;

grant execute on function public.product_growth_funnel_snapshot(
  timestamptz,
  timestamptz,
  text,
  boolean
) to service_role;

comment on function public.product_growth_funnel_snapshot(
  timestamptz,
  timestamptz,
  text,
  boolean
) is
  'Service-role-only aggregate growth funnel with binary outcome feedback. Returns counts and rates, never account identifiers or user content.';

commit;
