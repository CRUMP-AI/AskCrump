-- Ask Crump 5.9.76
-- Remote ledger: 20260914210257. Record content-free destination selections and expose a service-role-only
-- discovery denominator without customer content or account identifiers.

begin;

set local lock_timeout = '5s';

alter table public.product_events
  drop constraint if exists product_events_event_name_check;

alter table public.product_events
  add constraint product_events_event_name_check check (event_name in (
    'AccountCreated',
    'OnboardingCompleted',
    'WorkspaceOpened',
    'NavigationDestinationSelected',
    'StarterIntentReached',
    'ProjectSaveOfferShown',
    'ProjectSaveIntentReached',
    'ProjectSaveCompleted',
    'ActivationReached',
    'AhaReached',
    'OutcomeFeedbackSubmitted',
    'OutcomeIssueCategorized',
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

alter table public.product_events
  drop constraint if exists product_events_navigation_destination_check;

alter table public.product_events
  add constraint product_events_navigation_destination_check check (
    event_name <> 'NavigationDestinationSelected'
    or (
      source in (
        'ask', 'chats', 'projects', 'create', 'video', 'library', 'you',
        'intelligence', 'code'
      )
      and event_key ~ '^navigation-destination-selected:(ask|chats|projects|create|video|library|you|intelligence|code):[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      and plan is null
      and artifact_type is null
      and placement is null
      and campaign is null
      and creative is null
      and intent is null
    )
  );

alter table public.product_events
  validate constraint product_events_navigation_destination_check;

drop function if exists public.product_navigation_discovery_snapshot(
  timestamptz, timestamptz, text, boolean
);

create function public.product_navigation_discovery_snapshot(
  p_since timestamptz,
  p_until timestamptz default now(),
  p_environment text default 'production',
  p_include_internal boolean default false
)
returns table (
  measurement_since timestamptz,
  window_since timestamptz,
  window_until timestamptz,
  destination text,
  active_workspace_accounts bigint,
  selected_accounts bigint,
  selected_account_days bigint,
  selected_account_rate_pct numeric
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
  with destinations(ordinal, destination) as (
    values
      (1, 'ask'::text),
      (2, 'chats'::text),
      (3, 'projects'::text),
      (4, 'create'::text),
      (5, 'video'::text),
      (6, 'library'::text),
      (7, 'you'::text),
      (8, 'intelligence'::text),
      (9, 'code'::text)
  ),
  eligible_events as (
    select
      e.user_id,
      e.event_name,
      e.source,
      e.created_at
    from public.product_events as e
    join public.users as u on u.id = e.user_id
    where e.environment = p_environment
      and e.created_at >= greatest(
        p_since,
        timestamptz '2026-09-14 20:57:00+00'
      )
      and e.created_at < p_until
      and u.registration_environment = p_environment
      and u.deleted_at is null
      and (
        p_include_internal
        or coalesce(u.internal_tier, '') = ''
      )
      and e.event_name in ('WorkspaceOpened', 'NavigationDestinationSelected')
  ),
  active_accounts as (
    select distinct e.user_id
    from eligible_events as e
  ),
  selections as (
    select
      e.user_id,
      e.source as destination,
      e.created_at::date as selected_day
    from eligible_events as e
    where e.event_name = 'NavigationDestinationSelected'
  ),
  denominator as (
    select count(*)::bigint as active_workspace_accounts
    from active_accounts
  )
  select
    timestamptz '2026-09-14 20:57:00+00',
    greatest(p_since, timestamptz '2026-09-14 20:57:00+00'),
    p_until,
    d.destination,
    denominator.active_workspace_accounts,
    count(distinct s.user_id)::bigint,
    count(s.user_id)::bigint,
    round(
      100.0 * count(distinct s.user_id)
        / nullif(denominator.active_workspace_accounts, 0),
      2
    )
  from destinations as d
  cross join denominator
  left join selections as s on s.destination = d.destination
  group by d.ordinal, d.destination, denominator.active_workspace_accounts
  order by d.ordinal;
end;
$function$;

revoke all on function public.product_navigation_discovery_snapshot(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated;
grant execute on function public.product_navigation_discovery_snapshot(
  timestamptz, timestamptz, text, boolean
) to service_role;

comment on function public.product_navigation_discovery_snapshot(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free destination-selection aggregate. Reports fixed destination rows and active-account denominators without customer content or account identifiers.';

comment on table public.product_events is
  'Server-only, allowlisted product milestones. Navigation selection stores only a fixed destination and server UTC day. No prompts, responses, filenames, emails, payment details, URLs, project IDs, or arbitrary metadata. Deleted with the owning account.';

commit;
