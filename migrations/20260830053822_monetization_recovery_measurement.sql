-- Ask Crump 5.9.76
-- Distinguish fixed recovery reasons and include credit purchases in the private
-- monetization funnel without retaining content, prices, or payment details.

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
    'RecentWorkResumed',
    'PlanCenterViewed',
    'PlanIntentReached',
    'ResponseShared',
    'ArtifactRequested',
    'ArtifactPackaged',
    'ArtifactPackagingFailed',
    'ArtifactDownloaded',
    'SubscriptionCheckoutOpened',
    'SubscriptionCheckoutCompleted',
    'CreditCheckoutOpened',
    'CreditCheckoutCompleted',
    'BillingPortalOpened',
    'SubscriptionStatusChanged'
  ));

create index if not exists product_events_monetization_recovery_idx
  on public.product_events(environment, event_name, source, user_id, created_at)
  where event_name in (
    'PlanCenterViewed',
    'SubscriptionCheckoutOpened',
    'SubscriptionCheckoutCompleted',
    'CreditCheckoutOpened',
    'CreditCheckoutCompleted'
  );

create or replace function public.product_plan_conversion_snapshot(
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
  with plan_views as (
    select
      e.user_id,
      min(e.created_at) as viewed_at,
      bool_or(e.source = 'recovery_credits') as recovery_credits,
      bool_or(e.source = 'recovery_subscription') as recovery_subscription,
      bool_or(e.source = 'recovery_feature') as recovery_feature,
      bool_or(e.source = 'recovery_project') as recovery_project,
      bool_or(e.source = 'recovery_usage') as recovery_usage
    from public.product_events as e
    join public.users as u on u.id = e.user_id
    where e.environment = p_environment
      and e.event_name = 'PlanCenterViewed'
      and e.created_at >= p_since
      and e.created_at < p_until
      and u.deleted_at is null
      and (
        p_include_internal
        or coalesce(u.internal_tier, '') = ''
      )
    group by e.user_id
  ),
  journeys as (
    select
      v.*,
      exists (
        select 1
        from public.product_events as opened
        where opened.user_id = v.user_id
          and opened.environment = p_environment
          and opened.event_name = 'SubscriptionCheckoutOpened'
          and opened.created_at >= v.viewed_at
          and opened.created_at < p_until
      ) as subscription_checkout_opened,
      exists (
        select 1
        from public.product_events as completed
        where completed.user_id = v.user_id
          and completed.environment = p_environment
          and completed.event_name = 'SubscriptionCheckoutCompleted'
          and completed.created_at >= v.viewed_at
          and completed.created_at < p_until
      ) as subscription_checkout_completed,
      exists (
        select 1
        from public.product_events as opened
        where opened.user_id = v.user_id
          and opened.environment = p_environment
          and opened.event_name = 'CreditCheckoutOpened'
          and opened.created_at >= v.viewed_at
          and opened.created_at < p_until
      ) as credit_checkout_opened,
      exists (
        select 1
        from public.product_events as completed
        where completed.user_id = v.user_id
          and completed.environment = p_environment
          and completed.event_name = 'CreditCheckoutCompleted'
          and completed.created_at >= v.viewed_at
          and completed.created_at < p_until
      ) as credit_checkout_completed
    from plan_views as v
  ),
  stats as (
    select
      count(*) as plan_view_accounts,
      count(*) filter (where subscription_checkout_opened) as subscription_checkout_opened_accounts,
      count(*) filter (where subscription_checkout_completed) as subscription_checkout_completed_accounts,
      count(*) filter (where credit_checkout_opened) as credit_checkout_opened_accounts,
      count(*) filter (where credit_checkout_completed) as credit_checkout_completed_accounts,
      count(*) filter (where recovery_credits) as recovery_credit_accounts,
      count(*) filter (where recovery_subscription) as recovery_subscription_accounts,
      count(*) filter (where recovery_feature) as recovery_feature_accounts,
      count(*) filter (where recovery_project) as recovery_project_accounts,
      count(*) filter (where recovery_usage) as recovery_usage_accounts
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
      (1::smallint, 'plan_center_viewed'::text, plan_view_accounts, plan_view_accounts),
      (2::smallint, 'checkout_opened_after_plan_view'::text, subscription_checkout_opened_accounts, plan_view_accounts),
      (3::smallint, 'checkout_completed_after_plan_view'::text, subscription_checkout_completed_accounts, plan_view_accounts),
      (4::smallint, 'credit_checkout_opened_after_plan_view'::text, credit_checkout_opened_accounts, plan_view_accounts),
      (5::smallint, 'credit_checkout_completed_after_plan_view'::text, credit_checkout_completed_accounts, plan_view_accounts),
      (6::smallint, 'recovery_credit_viewed'::text, recovery_credit_accounts, plan_view_accounts),
      (7::smallint, 'recovery_subscription_viewed'::text, recovery_subscription_accounts, plan_view_accounts),
      (8::smallint, 'recovery_feature_limit_viewed'::text, recovery_feature_accounts, plan_view_accounts),
      (9::smallint, 'recovery_project_limit_viewed'::text, recovery_project_accounts, plan_view_accounts),
      (10::smallint, 'recovery_usage_limit_viewed'::text, recovery_usage_accounts, plan_view_accounts)
  ) as values_table(stage_order, metric, accounts, eligible)
  order by values_table.stage_order;
end;
$function$;

revoke execute on function public.product_plan_conversion_snapshot(
  timestamptz,
  timestamptz,
  text,
  boolean
) from public, anon, authenticated;

grant execute on function public.product_plan_conversion_snapshot(
  timestamptz,
  timestamptz,
  text,
  boolean
) to service_role;

comment on function public.product_plan_conversion_snapshot(
  timestamptz,
  timestamptz,
  text,
  boolean
) is
  'Service-role-only Plan-center recovery and subscription/credit checkout summary. Returns aggregate counts and rates only; never account identifiers, content, prices, or payment details.';

commit;
