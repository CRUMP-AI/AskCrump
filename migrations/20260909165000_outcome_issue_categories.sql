-- Add privacy-safe, fixed-category follow-up for a needs-work result.

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
  drop constraint if exists product_events_outcome_issue_category_check;

alter table public.product_events
  add constraint product_events_outcome_issue_category_check check (
    event_name <> 'OutcomeIssueCategorized'
    or (
      source in (
        'accuracy',
        'instructions',
        'format',
        'media_quality',
        'reliability',
        'safety',
        'other'
      )
      and left(event_key, 14) = 'outcome-issue:'
      and plan is null
      and artifact_type is null
      and placement is null
      and campaign is null
      and creative is null
      and intent is null
    )
  );

create or replace function public.product_outcome_issue_snapshot(
  p_since timestamptz,
  p_until timestamptz default now(),
  p_environment text default 'production',
  p_include_internal boolean default false
)
returns table (
  cohort text,
  category text,
  events bigint,
  accounts bigint
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
  select
    case when coalesce(u.internal_tier, '') = '' then 'external' else 'internal' end,
    e.source,
    count(*)::bigint,
    count(distinct e.user_id)::bigint
  from public.product_events as e
  join public.users as u on u.id = e.user_id
  where e.event_name = 'OutcomeIssueCategorized'
    and e.environment = p_environment
    and e.created_at >= p_since
    and e.created_at < p_until
    and (p_include_internal or coalesce(u.internal_tier, '') = '')
  group by 1, e.source
  order by 1, e.source;
end;
$function$;

revoke all on function public.product_outcome_issue_snapshot(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated;
grant execute on function public.product_outcome_issue_snapshot(
  timestamptz, timestamptz, text, boolean
) to service_role;

comment on function public.product_outcome_issue_snapshot(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only aggregate of fixed, content-free needs-work categories. Returns counts only; never prompts, responses, filenames, URLs, or account identifiers.';

comment on table public.product_events is
  'Server-only, allowlisted product milestones. Outcome issue follow-up is fixed-category only. No prompts, responses, filenames, emails, payment details, URLs, or arbitrary metadata. Deleted with the owning account.';

commit;
