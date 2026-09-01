-- Ask Crump 5.9.76
-- Separate result-save intent from launchpad task choice, record the exact
-- server-completed result action, and expose a content-free continuity receipt.

begin;

alter table public.product_events
  drop constraint if exists product_events_event_name_check;

alter table public.product_events
  add constraint product_events_event_name_check check (event_name in (
    'AccountCreated',
    'OnboardingCompleted',
    'WorkspaceOpened',
    'StarterIntentReached',
    'ProjectSaveIntentReached',
    'ProjectSaveCompleted',
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

create function public.product_project_continuity_snapshot(
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
  activation_reached bigint,
  project_save_intent_reached bigint,
  project_save_completed bigint,
  project_save_paired_completion bigint,
  project_save_intent_without_completion bigint,
  project_save_completion_without_intent bigint,
  project_resumed_after_save bigint,
  intent_to_completion_rate_pct numeric,
  completion_to_resume_rate_pct numeric
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
      u.created_at as cohort_at
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
  journey as (
    select
      c.user_id,
      attribution.source as acquisition,
      attribution.placement,
      attribution.campaign,
      attribution.creative,
      attribution.intent,
      min(e.created_at) filter (
        where e.event_name = 'ActivationReached'
      ) as activation_at,
      min(e.created_at) filter (
        where e.event_name = 'ProjectSaveIntentReached'
          and e.event_key = 'project-save-intent'
          and e.source in ('new_project', 'existing_project')
      ) as save_intent_at,
      min(e.created_at) filter (
        where e.event_name = 'ProjectSaveCompleted'
          and e.event_key = 'result-action-save'
          and e.source in ('new_project', 'existing_project')
      ) as save_completed_at,
      min(e.created_at) filter (
        where e.event_name = 'RecentWorkResumed'
          and e.source = 'project'
      ) as project_resumed_at
    from cohort as c
    left join lateral (
      select
        account.source,
        account.placement,
        account.campaign,
        account.creative,
        account.intent
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
      attribution.source,
      attribution.placement,
      attribution.campaign,
      attribution.creative,
      attribution.intent
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
    count(*) filter (where j.activation_at is not null)::bigint,
    count(*) filter (where j.save_intent_at is not null)::bigint,
    count(*) filter (where j.save_completed_at is not null)::bigint,
    count(*) filter (
      where j.save_intent_at is not null
        and j.save_completed_at is not null
    )::bigint,
    count(*) filter (
      where j.save_intent_at is not null
        and j.save_completed_at is null
    )::bigint,
    count(*) filter (
      where j.save_completed_at is not null
        and j.save_intent_at is null
    )::bigint,
    count(*) filter (
      where j.save_completed_at is not null
        and j.project_resumed_at >= j.save_completed_at
    )::bigint,
    round(
      100.0 * count(*) filter (
        where j.save_intent_at is not null
          and j.save_completed_at is not null
      ) / nullif(count(*) filter (where j.save_intent_at is not null), 0),
      2
    ),
    round(
      100.0 * count(*) filter (
        where j.save_completed_at is not null
          and j.project_resumed_at >= j.save_completed_at
      ) / nullif(count(*) filter (where j.save_completed_at is not null), 0),
      2
    )
  from journey as j
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

revoke execute on function public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated;
grant execute on function public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
) to service_role;

comment on function public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free account cohort comparing result-save intent, server-completed result saves, and later Project resume. Returns grouped counts and observed-to-date diagnostics only; it is not a D1/D7 retention report.';

commit;
