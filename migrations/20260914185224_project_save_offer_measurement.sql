-- Ask Crump 5.9.76
-- Add a content-free exposure denominator before the existing result-to-Project
-- intent and completion milestones.

begin;

set local lock_timeout = '5s';

alter table public.product_events
  drop constraint if exists product_events_event_name_check;

alter table public.product_events
  add constraint product_events_event_name_check check (event_name in (
    'AccountCreated',
    'OnboardingCompleted',
    'WorkspaceOpened',
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
  drop constraint if exists product_events_project_save_offer_check;

alter table public.product_events
  add constraint product_events_project_save_offer_check check (
    event_name <> 'ProjectSaveOfferShown'
    or (
      source in ('conversation_result', 'artifact_result')
      and event_key ~ '^project-save-offer-shown:(conversation_result|artifact_result):[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      and plan is null
      and artifact_type is null
      and placement is null
      and campaign is null
      and creative is null
      and intent is null
    )
  );

drop function if exists public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
);

create function public.product_project_continuity_snapshot(
  p_since timestamptz,
  p_until timestamptz default now(),
  p_environment text default 'production',
  p_include_internal boolean default false
)
returns table (
  cohort_since timestamptz,
  cohort_until timestamptz,
  offer_measurement_since timestamptz,
  acquisition text,
  placement text,
  campaign text,
  creative text,
  intent text,
  accounts_created bigint,
  activation_reached bigint,
  project_save_offer_shown bigint,
  project_save_offer_to_intent bigint,
  project_save_offer_without_later_intent bigint,
  project_save_intent_without_prior_offer bigint,
  project_save_intent_reached bigint,
  project_save_completed bigint,
  project_save_paired_completion bigint,
  project_save_intent_without_completion bigint,
  project_save_completion_without_intent bigint,
  project_resumed_after_save bigint,
  offer_to_intent_rate_pct numeric,
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
        where e.event_name = 'ProjectSaveOfferShown'
          and e.event_key ~ '^project-save-offer-shown:(conversation_result|artifact_result):[0-9]{4}-[0-9]{2}-[0-9]{2}$'
          and e.source in ('conversation_result', 'artifact_result')
          and e.created_at >= timestamptz '2026-09-14 18:34:14+00'
      ) as save_offer_at,
      min(e.created_at) filter (
        where e.event_name = 'ProjectSaveIntentReached'
          and e.event_key = 'project-save-intent'
          and e.source in ('new_project', 'existing_project')
          and e.created_at >= timestamptz '2026-09-14 18:34:14+00'
      ) as comparable_save_intent_at,
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
    timestamptz '2026-09-14 18:34:14+00',
    j.acquisition,
    j.placement,
    j.campaign,
    j.creative,
    j.intent,
    count(*)::bigint,
    count(*) filter (where j.activation_at is not null)::bigint,
    count(*) filter (where j.save_offer_at is not null)::bigint,
    count(*) filter (
      where j.save_offer_at is not null
        and j.comparable_save_intent_at >= j.save_offer_at
    )::bigint,
    count(*) filter (
      where j.save_offer_at is not null
        and (
          j.comparable_save_intent_at is null
          or j.comparable_save_intent_at < j.save_offer_at
        )
    )::bigint,
    count(*) filter (
      where j.comparable_save_intent_at is not null
        and (
          j.save_offer_at is null
          or j.save_offer_at > j.comparable_save_intent_at
        )
    )::bigint,
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
        where j.save_offer_at is not null
          and j.comparable_save_intent_at >= j.save_offer_at
      ) / nullif(count(*) filter (where j.save_offer_at is not null), 0),
      2
    ),
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

revoke all on function public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
) from public, anon, authenticated;
grant execute on function public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
) to service_role;

comment on function public.product_project_continuity_snapshot(
  timestamptz, timestamptz, text, boolean
) is
  'Service-role-only, content-free account cohort comparing visible result-save offers, later intent, server-completed saves, and Project resume. Offer comparisons begin 2026-09-14 18:34:14+00 and exclude earlier intent from the new exposure funnel.';

comment on table public.product_events is
  'Server-only, allowlisted product milestones. Project save offer exposure stores only a fixed source and server UTC day. No prompts, responses, filenames, emails, payment details, URLs, project IDs, or arbitrary metadata. Deleted with the owning account.';

commit;
