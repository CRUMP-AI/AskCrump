-- Ask Crump artifact delivery journey.
-- Aggregates operational reliability without storing prompts, responses, filenames, or errors.

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
    'PlanIntentReached',
    'ResponseShared',
    'ArtifactRequested',
    'ArtifactPackaged',
    'ArtifactPackagingFailed',
    'ArtifactDownloaded',
    'SubscriptionCheckoutOpened',
    'SubscriptionCheckoutCompleted',
    'BillingPortalOpened',
    'SubscriptionStatusChanged'
  ));

create index if not exists product_events_artifact_journey_idx
  on public.product_events(environment, artifact_type, event_name, created_at)
  where event_name in (
    'ArtifactRequested',
    'ArtifactPackaged',
    'ArtifactPackagingFailed',
    'ArtifactDownloaded'
  );

create or replace function public.product_artifact_journey_snapshot(
  p_since timestamptz,
  p_until timestamptz default now(),
  p_environment text default 'production'
)
returns table (
  artifact_type text,
  requested bigint,
  packaged bigint,
  packaging_failed bigint,
  downloaded bigint,
  request_to_package_rate_pct numeric,
  package_to_download_rate_pct numeric
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
    coalesce(e.artifact_type, 'file') as artifact_type,
    count(*) filter (where e.event_name = 'ArtifactRequested') as requested,
    count(*) filter (where e.event_name = 'ArtifactPackaged') as packaged,
    count(*) filter (where e.event_name = 'ArtifactPackagingFailed') as packaging_failed,
    count(*) filter (where e.event_name = 'ArtifactDownloaded') as downloaded,
    case
      when count(*) filter (where e.event_name = 'ArtifactRequested') > 0 then
        round(
          count(*) filter (where e.event_name = 'ArtifactPackaged') * 100.0
          / count(*) filter (where e.event_name = 'ArtifactRequested'),
          1
        )
      else null
    end as request_to_package_rate_pct,
    case
      when count(*) filter (where e.event_name = 'ArtifactPackaged') > 0 then
        round(
          count(*) filter (where e.event_name = 'ArtifactDownloaded') * 100.0
          / count(*) filter (where e.event_name = 'ArtifactPackaged'),
          1
        )
      else null
    end as package_to_download_rate_pct
  from public.product_events as e
  where e.environment = p_environment
    and e.created_at >= p_since
    and e.created_at < p_until
    and e.event_name in (
      'ArtifactRequested',
      'ArtifactPackaged',
      'ArtifactPackagingFailed',
      'ArtifactDownloaded'
    )
  group by coalesce(e.artifact_type, 'file')
  order by coalesce(e.artifact_type, 'file');
end;
$function$;

revoke execute on function public.product_artifact_journey_snapshot(
  timestamptz,
  timestamptz,
  text
) from public, anon, authenticated;

grant execute on function public.product_artifact_journey_snapshot(
  timestamptz,
  timestamptz,
  text
) to service_role;

comment on function public.product_artifact_journey_snapshot(
  timestamptz,
  timestamptz,
  text
) is
  'Service-role-only aggregate artifact reliability report. Returns counts and rates, never account identifiers, prompts, responses, filenames, URLs, or error text.';

comment on table public.product_events is
  'Server-only, allowlisted product milestones. No prompts, responses, filenames, URLs, emails, payment details, error text, or arbitrary metadata. Deleted with the owning account.';

commit;
