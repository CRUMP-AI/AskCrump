-- Ask Crump 5.9.76
-- Preserve one allowlisted, content-free first-touch tuple on AccountCreated and
-- expose service-role-only weekly cohort aggregates with explicit denominators.

begin;

alter table public.users
  add column if not exists registration_environment text;

do $user_constraints$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'users_registration_environment_check'
      and conrelid = 'public.users'::regclass
  ) then
    alter table public.users
      add constraint users_registration_environment_check check (
        registration_environment is null
        or registration_environment in ('production', 'preview', 'development')
      );
  end if;
end
$user_constraints$;

comment on column public.users.registration_environment is
  'Server-derived account-creation environment. Separates production cohorts from preview and development even when the optional analytics write fails.';

alter table public.product_events
  add column if not exists placement text,
  add column if not exists campaign text,
  add column if not exists creative text,
  add column if not exists intent text;

do $constraints$
begin
  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'product_events_placement_check'
      and conrelid = 'public.product_events'::regclass
  ) then
    alter table public.product_events
      add constraint product_events_placement_check check (
        placement is null or placement in (
          'response-share', 'profile-link', 'workflow-guide', 'organic-social',
          'creator-cohort'
        )
      );
  end if;

  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'product_events_campaign_check'
      and conrelid = 'public.product_events'::regclass
  ) then
    alter table public.product_events
      add constraint product_events_campaign_check check (
        campaign is null or campaign in (
          'presentation-proof-current',
          'real-product-continuity',
          'rough-idea-launch-plan',
          'project-memory-boundaries',
          'editable-powerpoint-review',
          'creator-cohort-01'
        )
      );
  end if;

  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'product_events_creative_check'
      and conrelid = 'public.product_events'::regclass
  ) then
    alter table public.product_events
      add constraint product_events_creative_check check (
        creative is null or creative in (
          'fb-static', 'ig-feed', 'ig-story', 'search-article',
          'continuity-feed', 'continuity-story', 'project-memory-feed',
          'project-memory-story', 'presentation-feed', 'presentation-story',
          'personal-invite'
        )
      );
  end if;

  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'product_events_intent_check'
      and conrelid = 'public.product_events'::regclass
  ) then
    alter table public.product_events
      add constraint product_events_intent_check check (
        intent is null or intent in (
          'document', 'presentation', 'resume', 'video', 'projects'
        )
      );
  end if;

  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'product_events_account_attribution_only_check'
      and conrelid = 'public.product_events'::regclass
  ) then
    alter table public.product_events
      add constraint product_events_account_attribution_only_check check (
        event_name = 'AccountCreated'
        or (
          placement is null
          and campaign is null
          and creative is null
          and intent is null
        )
      );
  end if;

  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'product_events_account_acquisition_check'
      and conrelid = 'public.product_events'::regclass
  ) then
    alter table public.product_events
      add constraint product_events_account_acquisition_check check (
        event_name <> 'AccountCreated'
        or source is null
        or source in (
          'direct', 'instagram', 'facebook', 'facebook-pinned', 'linkedin',
          'tiktok', 'youtube', 'x', 'referral', 'organic', 'organic-search',
          'clevercrump', 'founder-outreach'
        )
      );
  end if;

  if not exists (
    select 1 from pg_catalog.pg_constraint
    where conname = 'product_events_campaign_registry_check'
      and conrelid = 'public.product_events'::regclass
  ) then
    alter table public.product_events
      add constraint product_events_campaign_registry_check check (
        (campaign is null and creative is null)
        or (
          campaign = 'presentation-proof-current'
          and source in ('facebook', 'instagram')
          and placement in ('profile-link', 'organic-social')
          and intent = 'presentation'
          and (creative is null or creative in ('fb-static', 'ig-feed', 'ig-story'))
        )
        or (
          campaign = 'real-product-continuity'
          and source in ('facebook', 'instagram')
          and placement in ('profile-link', 'organic-social')
          and intent = 'projects'
          and (
            creative is null
            or creative in ('continuity-feed', 'continuity-story')
          )
        )
        or (
          campaign = 'rough-idea-launch-plan'
          and source = 'organic-search'
          and placement = 'workflow-guide'
          and intent = 'projects'
          and (creative is null or creative = 'search-article')
        )
        or (
          campaign = 'project-memory-boundaries'
          and source in ('organic-search', 'facebook', 'instagram')
          and placement in ('workflow-guide', 'organic-social')
          and intent = 'projects'
          and (
            creative is null
            or creative in (
              'search-article', 'project-memory-feed', 'project-memory-story'
            )
          )
        )
        or (
          campaign = 'editable-powerpoint-review'
          and source in ('organic-search', 'facebook', 'instagram')
          and placement in ('workflow-guide', 'organic-social')
          and intent = 'presentation'
          and (
            creative is null
            or creative in (
              'search-article', 'presentation-feed', 'presentation-story'
            )
          )
        )
        or (
          campaign = 'creator-cohort-01'
          and source = 'founder-outreach'
          and placement = 'creator-cohort'
          and intent = 'projects'
          and (creative is null or creative = 'personal-invite')
        )
      );
  end if;
end
$constraints$;

comment on column public.product_events.placement is
  'Allowlisted first-touch entry surface, stored only on AccountCreated.';
comment on column public.product_events.campaign is
  'Registered content-free first-touch campaign label, stored only on AccountCreated.';
comment on column public.product_events.creative is
  'Registered content-free first-touch asset-family label, stored only on AccountCreated.';
comment on column public.product_events.intent is
  'Allowlisted promised product outcome, stored only on AccountCreated.';

create or replace function public.record_account_created_event(
  p_user_id uuid,
  p_event_key text,
  p_environment text,
  p_client_platform text,
  p_acquisition text default null,
  p_placement text default null,
  p_campaign text default null,
  p_creative text default null,
  p_intent text default null
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_acquisition text := lower(btrim(coalesce(p_acquisition, '')));
  v_placement text := lower(btrim(coalesce(p_placement, '')));
  v_campaign text := lower(btrim(coalesce(p_campaign, '')));
  v_creative text := lower(btrim(coalesce(p_creative, '')));
  v_intent text := lower(btrim(coalesce(p_intent, '')));
begin
  if v_acquisition not in (
    'direct', 'instagram', 'facebook', 'facebook-pinned', 'linkedin',
    'tiktok', 'youtube', 'x', 'referral', 'organic', 'organic-search',
    'clevercrump', 'founder-outreach'
  ) then
    v_acquisition := null;
  end if;

  if v_placement not in (
    'response-share', 'profile-link', 'workflow-guide', 'organic-social',
    'creator-cohort'
  ) then
    v_placement := null;
  end if;

  if v_intent not in (
    'document', 'presentation', 'resume', 'video', 'projects'
  ) then
    v_intent := null;
  end if;

  if not (
    (
      v_campaign = 'presentation-proof-current'
      and v_acquisition in ('facebook', 'instagram')
      and v_placement in ('profile-link', 'organic-social')
      and v_intent = 'presentation'
    )
    or (
      v_campaign = 'real-product-continuity'
      and v_acquisition in ('facebook', 'instagram')
      and v_placement in ('profile-link', 'organic-social')
      and v_intent = 'projects'
    )
    or (
      v_campaign = 'rough-idea-launch-plan'
      and v_acquisition = 'organic-search'
      and v_placement = 'workflow-guide'
      and v_intent = 'projects'
    )
    or (
      v_campaign = 'project-memory-boundaries'
      and v_acquisition in ('organic-search', 'facebook', 'instagram')
      and v_placement in ('workflow-guide', 'organic-social')
      and v_intent = 'projects'
    )
    or (
      v_campaign = 'editable-powerpoint-review'
      and v_acquisition in ('organic-search', 'facebook', 'instagram')
      and v_placement in ('workflow-guide', 'organic-social')
      and v_intent = 'presentation'
    )
    or (
      v_campaign = 'creator-cohort-01'
      and v_acquisition = 'founder-outreach'
      and v_placement = 'creator-cohort'
      and v_intent = 'projects'
    )
  ) then
    v_campaign := null;
  end if;

  if v_campaign is null or not (
    (v_campaign = 'presentation-proof-current' and v_creative in ('fb-static', 'ig-feed', 'ig-story'))
    or (v_campaign = 'real-product-continuity' and v_creative in ('continuity-feed', 'continuity-story'))
    or (v_campaign = 'rough-idea-launch-plan' and v_creative = 'search-article')
    or (v_campaign = 'project-memory-boundaries' and v_creative in ('search-article', 'project-memory-feed', 'project-memory-story'))
    or (v_campaign = 'editable-powerpoint-review' and v_creative in ('search-article', 'presentation-feed', 'presentation-story'))
    or (v_campaign = 'creator-cohort-01' and v_creative = 'personal-invite')
  ) then
    v_creative := null;
  end if;

  insert into public.product_events (
    user_id,
    event_name,
    event_key,
    environment,
    client_platform,
    source,
    placement,
    campaign,
    creative,
    intent
  ) values (
    p_user_id,
    'AccountCreated',
    p_event_key,
    p_environment,
    p_client_platform,
    v_acquisition,
    v_placement,
    v_campaign,
    v_creative,
    v_intent
  )
  on conflict (user_id, event_name, event_key, environment) do nothing;

  return found;
end;
$function$;

revoke execute on function public.record_account_created_event(
  uuid, text, text, text, text, text, text, text, text
) from public, anon, authenticated;
grant execute on function public.record_account_created_event(
  uuid, text, text, text, text, text, text, text, text
) to service_role;

comment on function public.record_account_created_event(
  uuid, text, text, text, text, text, text, text, text
) is
  'Service-role-only idempotent AccountCreated writer. Discards unknown first-touch labels and stores no referrer, URL, search term, content, filename, email, or arbitrary metadata.';

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
  durable_value_eligible_24h bigint,
  durable_value_reached_24h bigint,
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
      u.subscription_status
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
      attribution.source,
      attribution.placement,
      attribution.campaign,
      attribution.creative,
      attribution.intent,
      attribution.created_at
  ),
  journeys as (
    select
      f.*,
      f.cohort_at + interval '24 hours' <= p_until as eligible_24h,
      (
        f.activation_at is not null
        and f.activation_at <= f.cohort_at + interval '24 hours'
      ) as activation_24h,
      (
        f.aha_at is not null
        and f.aha_at <= f.cohort_at + interval '24 hours'
      ) as durable_value_24h,
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
    count(*) filter (where j.eligible_24h)::bigint,
    count(*) filter (where j.eligible_24h and j.durable_value_24h)::bigint,
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
      where j.subscription_checkout_completed_at is not null
        or j.credit_checkout_completed_at is not null
    )::bigint,
    count(*) filter (where j.activation_at is not null)::bigint,
    count(*) filter (
      where j.subscription_tier in ('professional', 'enterprise')
        and j.subscription_status in ('active', 'trialing')
    )::bigint,
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
  'Service-role-only, content-free cohort export grouped by the first AccountCreated acquisition tuple and filtered by the server-derived account registration environment. D1 and D7 use activated-user denominators. Returns counts and explicit eligibility denominators only. Refund, recognized-revenue, and variable-cost fields remain null until supplied by an authoritative finance export; checkout events are never represented as revenue.';

commit;
