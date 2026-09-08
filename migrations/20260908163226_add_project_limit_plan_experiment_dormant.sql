-- Ask Crump 5.9.76
-- Dormant Project-limit value-to-plan experiment infrastructure.
-- SOURCE CANDIDATE ONLY: the database control defaults false and the server
-- gate also defaults false. This migration is intentionally not applied here.

begin;

create table if not exists public.project_limit_plan_controls (
  experiment_key text primary key,
  enabled boolean not null default false,
  updated_at timestamptz not null default now(),
  constraint project_limit_plan_controls_key_check check (
    experiment_key = 'project-limit-plan-copy'
  )
);

create table if not exists public.project_limit_plan_state (
  user_id uuid primary key references public.users(id) on delete cascade,
  experiment_key text not null default 'project-limit-plan-copy',
  variant text not null,
  assigned_at timestamptz not null default now(),
  last_shown_at timestamptz,
  last_decision_id uuid,
  last_session_hash text,
  active_decision_id uuid,
  active_session_hash text,
  active_decision_expires_at timestamptz,
  updated_at timestamptz not null default now(),
  constraint project_limit_plan_state_key_check check (
    experiment_key = 'project-limit-plan-copy'
  ),
  constraint project_limit_plan_state_variant_check check (
    variant in ('control', 'value-specific')
  ),
  constraint project_limit_plan_state_session_check check (
    (last_session_hash is null or last_session_hash ~ '^[0-9a-f]{64}$')
    and (active_session_hash is null or active_session_hash ~ '^[0-9a-f]{64}$')
  )
);

create table if not exists public.project_limit_plan_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  decision_id uuid not null unique,
  event_name text not null default 'ProjectLimitPlanMessageShown',
  event_key text not null default 'project-limit-plan-message-shown',
  source text not null default 'recovery_project',
  variant text not null,
  plan text not null default 'professional',
  environment text not null,
  client_platform text not null,
  session_hash text not null,
  created_at timestamptz not null default now(),
  constraint project_limit_plan_events_name_check check (
    event_name = 'ProjectLimitPlanMessageShown'
  ),
  constraint project_limit_plan_events_key_check check (
    event_key = 'project-limit-plan-message-shown'
  ),
  constraint project_limit_plan_events_source_check check (
    source = 'recovery_project'
  ),
  constraint project_limit_plan_events_variant_check check (
    variant in ('control', 'value-specific')
  ),
  constraint project_limit_plan_events_plan_check check (plan = 'professional'),
  constraint project_limit_plan_events_environment_check check (
    environment = 'production'
  ),
  constraint project_limit_plan_events_platform_check check (
    client_platform in ('web', 'ios', 'android')
  ),
  constraint project_limit_plan_events_session_check check (
    session_hash ~ '^[0-9a-f]{64}$'
  )
);

create index if not exists project_limit_plan_events_window_idx
  on public.project_limit_plan_events (created_at desc, variant);
create index if not exists project_limit_plan_events_user_window_idx
  on public.project_limit_plan_events (user_id, created_at desc);

alter table public.project_limit_plan_controls enable row level security;
alter table public.project_limit_plan_state enable row level security;
alter table public.project_limit_plan_events enable row level security;

revoke all on table public.project_limit_plan_controls from public, anon, authenticated;
revoke all on table public.project_limit_plan_state from public, anon, authenticated;
revoke all on table public.project_limit_plan_events from public, anon, authenticated;
grant select, insert, update, delete on table public.project_limit_plan_controls to service_role;
grant select, insert, update, delete on table public.project_limit_plan_state to service_role;
grant select, insert, update, delete on table public.project_limit_plan_events to service_role;

insert into public.project_limit_plan_controls (experiment_key, enabled)
values ('project-limit-plan-copy', false)
on conflict (experiment_key) do nothing;

create or replace function public.claim_project_limit_plan_message(
  p_user_id uuid,
  p_environment text,
  p_client_platform text,
  p_session_hash text,
  p_project_limit_code text,
  p_feature_enabled boolean default false
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_control_enabled boolean := false;
  v_project_count integer := 0;
  v_has_durable_work boolean := false;
  v_state public.project_limit_plan_state%rowtype;
  v_decision_id uuid := gen_random_uuid();
begin
  -- A disabled server gate is a read-only, mutation-free path.
  if not coalesce(p_feature_enabled, false)
    or coalesce(p_environment, '') <> 'production'
    or coalesce(p_client_platform, '') not in ('web', 'ios', 'android')
    or coalesce(p_session_hash, '') !~ '^[0-9a-f]{64}$'
    or coalesce(p_project_limit_code, '') <> 'PROJECT_LIMIT_REACHED'
  then
    return jsonb_build_object('eligible', false, 'reason', 'feature-disabled');
  end if;

  select enabled into v_control_enabled
  from public.project_limit_plan_controls
  where experiment_key = 'project-limit-plan-copy';
  if not coalesce(v_control_enabled, false) then
    return jsonb_build_object('eligible', false, 'reason', 'feature-disabled');
  end if;

  -- Serialize assignment, suppression, and exposure across retries/devices.
  perform pg_advisory_xact_lock(hashtextextended(
    'project-limit-plan-copy:' || p_user_id::text,
    0
  ));

  select * into v_user
  from public.users
  where id = p_user_id
  for update;
  if not found
    or not coalesce(v_user.is_verified, false)
    or v_user.deleted_at is not null
    or coalesce(v_user.registration_environment, '') <> 'production'
    or coalesce(v_user.internal_tier, '') <> ''
    or coalesce(v_user.subscription_tier, 'free') <> 'free'
    or coalesce(v_user.subscription_status, 'inactive') <> 'inactive'
    -- Conservative commerce exclusion: any provider identity represents a
    -- prior/pending/recovery state and is held out of this first experiment.
    or v_user.stripe_customer_id is not null
    or v_user.stripe_subscription_id is not null
    or v_user.store_product_id is not null
    or v_user.subscription_provider is not null
  then
    return jsonb_build_object('eligible', false, 'reason', 'account-ineligible');
  end if;

  select count(*)::integer into v_project_count
  from public.projects p
  where p.user_id = p_user_id and p.archived_at is null;
  if v_project_count <> 2 then
    return jsonb_build_object('eligible', false, 'reason', 'project-count');
  end if;

  select (
    exists (
      select 1
      from public.project_chats pc
      join public.projects p
        on p.id = pc.project_id
       and p.user_id = pc.user_id
       and p.archived_at is null
      join public.user_chats c
        on c.user_id = pc.user_id
       and c.chat_id = pc.chat_id
       and c.deleted_at is null
      where pc.user_id = p_user_id
        and jsonb_typeof(c.messages) = 'array'
        and exists (
          select 1
          from jsonb_array_elements(c.messages) message
          where message ->> 'role' = 'assistant'
            and btrim(coalesce(message ->> 'content', '')) <> ''
        )
    )
    or exists (
      select 1
      from public.project_files pf
      join public.projects p
        on p.id = pf.project_id
       and p.user_id = pf.user_id
       and p.archived_at is null
      join public.user_files f
        on f.id = pf.file_id
       and f.user_id = pf.user_id
       and f.deleted_at is null
       and f.status = 'ready'
       and f.size_bytes > 0
      where pf.user_id = p_user_id
    )
  ) into v_has_durable_work;
  if not coalesce(v_has_durable_work, false) then
    return jsonb_build_object('eligible', false, 'reason', 'bare-projects');
  end if;

  -- Active work and every existing durable prompt/revenue recovery take
  -- priority. A Project-limit message is never layered over another prompt.
  if exists (
      select 1 from public.lifecycle_prompt_state l
      where l.user_id = p_user_id
        and l.environment = p_environment
        and l.active_decision_expires_at > now()
    )
    or exists (
      select 1 from public.chat_jobs j
      where j.user_id = p_user_id and j.status = 'processing'
    )
    or exists (
      select 1 from public.media_jobs j
      where j.user_id = p_user_id and j.status in ('queued', 'processing')
    )
    or exists (
      select 1 from public.manuscript_runs r
      where r.user_id = p_user_id and r.status in ('queued', 'running', 'paused', 'awaiting_credits')
    )
    or exists (
      select 1 from public.code_tasks t
      where t.user_id = p_user_id
        and t.status in ('queued', 'provisioning', 'running', 'awaiting_approval', 'verifying')
    )
    or exists (
      select 1 from public.product_events e
      where e.user_id = p_user_id
        and e.environment = p_environment
        and (
          (e.event_name = 'PlanCenterViewed' and e.created_at >= now() - interval '10 minutes')
          or (e.event_name = 'SubscriptionCheckoutOpened' and e.created_at >= now() - interval '24 hours')
        )
    )
  then
    return jsonb_build_object('eligible', false, 'reason', 'prompt-priority');
  end if;

  if exists (
    select 1 from public.project_limit_plan_events e
    where e.user_id = p_user_id
      and e.environment = p_environment
      and e.created_at >= now() - interval '30 days'
  ) then
    return jsonb_build_object('eligible', false, 'reason', 'frequency-cap');
  end if;

  insert into public.project_limit_plan_state (user_id, variant)
  values (
    p_user_id,
    case when random() < 0.5 then 'control' else 'value-specific' end
  )
  on conflict (user_id) do nothing;

  select * into v_state
  from public.project_limit_plan_state
  where user_id = p_user_id
  for update;
  if v_state.variant not in ('control', 'value-specific') then
    return jsonb_build_object('eligible', false, 'reason', 'assignment-invalid');
  end if;

  if v_state.active_decision_id is not null
    and v_state.active_decision_expires_at > now()
  then
    if v_state.active_session_hash is distinct from p_session_hash then
      return jsonb_build_object('eligible', false, 'reason', 'session-collision');
    end if;
    return jsonb_build_object(
      'eligible', true,
      'decisionId', v_state.active_decision_id,
      'variant', v_state.variant
    );
  end if;

  update public.project_limit_plan_state
  set
    active_decision_id = v_decision_id,
    active_session_hash = p_session_hash,
    active_decision_expires_at = now() + interval '10 minutes',
    updated_at = now()
  where user_id = p_user_id;

  return jsonb_build_object(
    'eligible', true,
    'decisionId', v_decision_id,
    'variant', v_state.variant
  );
end
$function$;

create or replace function public.record_project_limit_plan_message_shown(
  p_user_id uuid,
  p_decision_id uuid,
  p_environment text,
  p_client_platform text,
  p_session_hash text,
  p_feature_enabled boolean default false
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_state public.project_limit_plan_state%rowtype;
  v_control_enabled boolean := false;
  v_project_count integer := 0;
  v_has_durable_work boolean := false;
begin
  if not coalesce(p_feature_enabled, false)
    or coalesce(p_environment, '') <> 'production'
    or coalesce(p_client_platform, '') not in ('web', 'ios', 'android')
    or coalesce(p_session_hash, '') !~ '^[0-9a-f]{64}$'
  then
    return jsonb_build_object('recorded', false);
  end if;

  perform pg_advisory_xact_lock(hashtextextended(
    'project-limit-plan-copy:' || p_user_id::text,
    0
  ));

  select enabled into v_control_enabled
  from public.project_limit_plan_controls
  where experiment_key = 'project-limit-plan-copy';
  if not coalesce(v_control_enabled, false) then
    return jsonb_build_object('recorded', false);
  end if;

  select * into v_state
  from public.project_limit_plan_state
  where user_id = p_user_id
  for update;
  if not found then
    return jsonb_build_object('recorded', false);
  end if;

  if exists (
    select 1 from public.project_limit_plan_events e
    where e.user_id = p_user_id
      and e.decision_id = p_decision_id
      and e.session_hash = p_session_hash
  ) then
    return jsonb_build_object('recorded', true, 'variant', v_state.variant);
  end if;

  if v_state.active_decision_id is distinct from p_decision_id
    or v_state.active_session_hash is distinct from p_session_hash
    or coalesce(v_state.active_decision_expires_at, '-infinity'::timestamptz) <= now()
    or coalesce(v_state.variant, '') not in ('control', 'value-specific')
  then
    return jsonb_build_object('recorded', false);
  end if;

  -- Delivery-time recheck: do not show stale treatment after account, value,
  -- active-work, commerce, or prompt-priority state changes.
  select * into v_user from public.users where id = p_user_id for update;
  if not found
    or not coalesce(v_user.is_verified, false)
    or v_user.deleted_at is not null
    or coalesce(v_user.registration_environment, '') <> 'production'
    or coalesce(v_user.internal_tier, '') <> ''
    or coalesce(v_user.subscription_tier, 'free') <> 'free'
    or coalesce(v_user.subscription_status, 'inactive') <> 'inactive'
    or v_user.stripe_customer_id is not null
    or v_user.stripe_subscription_id is not null
    or v_user.store_product_id is not null
    or v_user.subscription_provider is not null
  then
    return jsonb_build_object('recorded', false);
  end if;

  select count(*)::integer into v_project_count
  from public.projects p
  where p.user_id = p_user_id and p.archived_at is null;
  if v_project_count <> 2 then
    return jsonb_build_object('recorded', false);
  end if;

  select (
    exists (
      select 1
      from public.project_chats pc
      join public.projects p
        on p.id = pc.project_id and p.user_id = pc.user_id and p.archived_at is null
      join public.user_chats c
        on c.user_id = pc.user_id and c.chat_id = pc.chat_id and c.deleted_at is null
      where pc.user_id = p_user_id
        and jsonb_typeof(c.messages) = 'array'
        and exists (
          select 1 from jsonb_array_elements(c.messages) message
          where message ->> 'role' = 'assistant'
            and btrim(coalesce(message ->> 'content', '')) <> ''
        )
    )
    or exists (
      select 1
      from public.project_files pf
      join public.projects p
        on p.id = pf.project_id and p.user_id = pf.user_id and p.archived_at is null
      join public.user_files f
        on f.id = pf.file_id and f.user_id = pf.user_id
       and f.deleted_at is null and f.status = 'ready' and f.size_bytes > 0
      where pf.user_id = p_user_id
    )
  ) into v_has_durable_work;
  if not coalesce(v_has_durable_work, false) then
    return jsonb_build_object('recorded', false);
  end if;

  if exists (
      select 1 from public.lifecycle_prompt_state l
      where l.user_id = p_user_id and l.environment = p_environment
        and l.active_decision_expires_at > now()
    )
    or exists (select 1 from public.chat_jobs j where j.user_id = p_user_id and j.status = 'processing')
    or exists (select 1 from public.media_jobs j where j.user_id = p_user_id and j.status in ('queued', 'processing'))
    or exists (select 1 from public.manuscript_runs r where r.user_id = p_user_id and r.status in ('queued', 'running', 'paused', 'awaiting_credits'))
    or exists (select 1 from public.code_tasks t where t.user_id = p_user_id and t.status in ('queued', 'provisioning', 'running', 'awaiting_approval', 'verifying'))
    or exists (
      select 1 from public.product_events e
      where e.user_id = p_user_id and e.environment = p_environment
        and (
          (e.event_name = 'PlanCenterViewed' and e.created_at >= now() - interval '10 minutes')
          or (e.event_name = 'SubscriptionCheckoutOpened' and e.created_at >= now() - interval '24 hours')
        )
    )
    or exists (
      select 1 from public.project_limit_plan_events e
      where e.user_id = p_user_id and e.environment = p_environment
        and e.created_at >= now() - interval '30 days'
    )
  then
    return jsonb_build_object('recorded', false);
  end if;

  insert into public.project_limit_plan_events (
    user_id, decision_id, variant, environment, client_platform, session_hash
  ) values (
    p_user_id, p_decision_id, v_state.variant, p_environment,
    p_client_platform, p_session_hash
  );
  update public.project_limit_plan_state
  set
    last_shown_at = now(),
    last_decision_id = p_decision_id,
    last_session_hash = p_session_hash,
    active_decision_id = null,
    active_session_hash = null,
    active_decision_expires_at = null,
    updated_at = now()
  where user_id = p_user_id;

  return jsonb_build_object('recorded', true, 'variant', v_state.variant);
end
$function$;

create or replace function public.product_project_limit_plan_snapshot(
  p_since timestamptz,
  p_until timestamptz,
  p_environment text default 'production'
)
returns table (
  variant text,
  eligible_exposure_accounts bigint,
  plan_center_view_accounts bigint,
  professional_checkout_open_accounts bigint,
  verified_completion_accounts bigint,
  reconciled_entitlement_accounts bigint,
  d1_eligible_accounts bigint,
  d1_returned_accounts bigint,
  d7_eligible_accounts bigint,
  d7_returned_accounts bigint,
  failure_accounts text,
  cancellation_accounts text,
  refund_accounts text,
  dispute_accounts text,
  chargeback_accounts text,
  recognized_revenue_cents text
)
language plpgsql
stable
security invoker
set search_path = ''
as $function$
begin
  if p_since is null or p_until is null or p_since >= p_until then
    raise exception 'A valid half-open reporting window is required.' using errcode = '22023';
  end if;
  if p_environment <> 'production' then
    raise exception 'This experiment accepts production cohorts only.' using errcode = '22023';
  end if;

  return query
  with arms(variant) as (
    values ('control'::text), ('value-specific'::text)
  ),
  exposures as (
    select distinct on (e.user_id, e.variant)
      e.user_id,
      e.variant,
      e.created_at as exposed_at
    from public.project_limit_plan_events e
    join public.users u on u.id = e.user_id
    where e.environment = p_environment
      and e.created_at >= p_since
      and e.created_at < p_until
      and u.registration_environment = 'production'
      and u.deleted_at is null
      and coalesce(u.internal_tier, '') = ''
    order by e.user_id, e.variant, e.created_at
  ),
  measured as (
    select
      x.*,
      exists (
        select 1 from public.product_events e
        where e.user_id = x.user_id
          and e.environment = p_environment
          and e.event_name = 'PlanCenterViewed'
          and e.source = 'recovery_project'
          and e.created_at >= x.exposed_at and e.created_at < p_until
      ) as plan_viewed,
      exists (
        select 1 from public.product_events e
        where e.user_id = x.user_id
          and e.environment = p_environment
          and e.event_name = 'SubscriptionCheckoutOpened'
          and e.plan = 'professional'
          and e.created_at >= x.exposed_at and e.created_at < p_until
      ) as checkout_opened,
      exists (
        select 1 from public.product_events e
        where e.user_id = x.user_id
          and e.environment = p_environment
          and e.event_name = 'SubscriptionCheckoutCompleted'
          and e.plan = 'professional'
          and e.created_at >= x.exposed_at and e.created_at < p_until
      ) as checkout_completed,
      (
        u.subscription_tier = 'professional'
        and u.subscription_status in ('active', 'trialing')
        and u.subscription_provider in ('stripe', 'revenuecat')
      ) as reconciled_entitlement,
      x.exposed_at <= p_until - interval '1 day' as d1_eligible,
      exists (
        select 1 from public.product_events e
        where e.user_id = x.user_id
          and e.environment = p_environment
          and e.event_name in ('WorkspaceOpened', 'RecentWorkResumed')
          and e.created_at >= x.exposed_at + interval '1 day'
          and e.created_at < x.exposed_at + interval '2 days'
          and e.created_at < p_until
      ) as d1_returned,
      x.exposed_at <= p_until - interval '7 days' as d7_eligible,
      exists (
        select 1 from public.product_events e
        where e.user_id = x.user_id
          and e.environment = p_environment
          and e.event_name in ('WorkspaceOpened', 'RecentWorkResumed')
          and e.created_at >= x.exposed_at + interval '6 days'
          and e.created_at < x.exposed_at + interval '8 days'
          and e.created_at < p_until
      ) as d7_returned
    from exposures x
    join public.users u on u.id = x.user_id
  )
  select
    a.variant,
    count(distinct m.user_id)::bigint,
    count(distinct m.user_id) filter (where m.plan_viewed)::bigint,
    count(distinct m.user_id) filter (where m.checkout_opened)::bigint,
    count(distinct m.user_id) filter (where m.checkout_completed)::bigint,
    count(distinct m.user_id) filter (where m.reconciled_entitlement)::bigint,
    count(distinct m.user_id) filter (where m.d1_eligible)::bigint,
    count(distinct m.user_id) filter (where m.d1_eligible and m.d1_returned)::bigint,
    count(distinct m.user_id) filter (where m.d7_eligible)::bigint,
    count(distinct m.user_id) filter (where m.d7_eligible and m.d7_returned)::bigint,
    'unavailable'::text,
    'unavailable'::text,
    'unavailable'::text,
    'unavailable'::text,
    'unavailable'::text,
    'unavailable'::text
  from arms a
  left join measured m on m.variant = a.variant
  group by a.variant
  order by a.variant;
end
$function$;

comment on table public.project_limit_plan_state is
  'Server-only durable random assignment and 30-day exposure state; contains no customer content.';
comment on table public.project_limit_plan_events is
  'Server-only fixed-field ProjectLimitPlanMessageShown evidence; marketing receives aggregates only.';
comment on function public.product_project_limit_plan_snapshot(timestamptz, timestamptz, text) is
  'Content-free, service-role-only Project-limit experiment funnel. Unsupported finance and reversal inputs return unavailable.';

revoke all on function public.claim_project_limit_plan_message(
  uuid, text, text, text, text, boolean
) from public, anon, authenticated;
revoke all on function public.product_project_limit_plan_snapshot(
  timestamptz, timestamptz, text
) from public, anon, authenticated;
revoke all on function public.record_project_limit_plan_message_shown(
  uuid, uuid, text, text, text, boolean
) from public, anon, authenticated;
grant execute on function public.claim_project_limit_plan_message(
  uuid, text, text, text, text, boolean
) to service_role;
grant execute on function public.product_project_limit_plan_snapshot(
  timestamptz, timestamptz, text
) to service_role;
grant execute on function public.record_project_limit_plan_message_shown(
  uuid, uuid, text, text, text, boolean
) to service_role;

commit;
