-- Ask Crump 5.9.76
-- Server-authoritative, content-free Phase 1 in-product lifecycle guidance.

begin;

create table if not exists public.lifecycle_prompt_controls (
  message_key text primary key,
  enabled boolean not null default true,
  holdout_percent smallint not null default 20 check (holdout_percent between 0 and 100),
  updated_at timestamptz not null default now(),
  constraint lifecycle_prompt_controls_key_check check (message_key in (
    'starter-assist', 'first-value-assist', 'continuity-assist',
    'artifact-assist', 'referral-ask'
  ))
);

create table if not exists public.lifecycle_prompt_state (
  user_id uuid not null references public.users(id) on delete cascade,
  message_key text not null,
  environment text not null,
  cohort text not null,
  eligible_at timestamptz,
  first_shown_at timestamptz,
  last_shown_at timestamptz,
  shown_count integer not null default 0,
  dismissed_at timestamptz,
  acted_at timestamptz,
  permanently_suppressed_at timestamptz,
  last_suppression_reason text,
  active_decision_id uuid,
  active_decision_expires_at timestamptz,
  active_intent text,
  active_surface text,
  updated_at timestamptz not null default now(),
  primary key (user_id, message_key, environment),
  constraint lifecycle_prompt_state_key_check check (message_key in (
    'starter-assist', 'first-value-assist', 'continuity-assist',
    'artifact-assist', 'referral-ask'
  )),
  constraint lifecycle_prompt_state_environment_check check (
    environment in ('production', 'preview', 'development')
  ),
  constraint lifecycle_prompt_state_cohort_check check (cohort in ('prompt', 'holdout')),
  constraint lifecycle_prompt_state_shown_count_check check (shown_count >= 0),
  constraint lifecycle_prompt_state_reason_check check (
    last_suppression_reason is null or last_suppression_reason in (
      'account-ineligible', 'channel-disabled', 'quiet-hours', 'unanswered-checkin',
      'target-completed', 'already-shown', 'frequency-cap', 'session-collision',
      'active-work', 'recovery-surface', 'no-safe-intent', 'recent-activity',
      'user-dismissed'
    )
  ),
  constraint lifecycle_prompt_state_intent_check check (
    active_intent is null or active_intent in (
      'document', 'presentation', 'resume', 'video', 'projects'
    )
  ),
  constraint lifecycle_prompt_state_surface_check check (
    active_surface is null or active_surface in (
      'workspace-inline', 'composer-inline', 'post-response-inline'
    )
  )
);

create table if not exists public.lifecycle_prompt_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  message_key text not null,
  environment text not null,
  decision_id uuid not null,
  event_type text not null,
  cohort text not null,
  suppression_reason text,
  intent text,
  client_platform text not null,
  session_hash text not null,
  created_at timestamptz not null default now(),
  constraint lifecycle_prompt_events_key_check check (message_key in (
    'starter-assist', 'first-value-assist', 'continuity-assist',
    'artifact-assist', 'referral-ask'
  )),
  constraint lifecycle_prompt_events_environment_check check (
    environment in ('production', 'preview', 'development')
  ),
  constraint lifecycle_prompt_events_type_check check (
    event_type in ('eligible', 'holdout', 'shown', 'dismissed', 'acted', 'suppressed')
  ),
  constraint lifecycle_prompt_events_cohort_check check (cohort in ('prompt', 'holdout')),
  constraint lifecycle_prompt_events_reason_check check (
    suppression_reason is null or suppression_reason in (
      'account-ineligible', 'channel-disabled', 'quiet-hours', 'unanswered-checkin',
      'target-completed', 'already-shown', 'frequency-cap', 'session-collision',
      'active-work', 'recovery-surface', 'no-safe-intent', 'recent-activity',
      'user-dismissed'
    )
  ),
  constraint lifecycle_prompt_events_intent_check check (
    intent is null or intent in ('document', 'presentation', 'resume', 'video', 'projects')
  ),
  constraint lifecycle_prompt_events_platform_check check (
    client_platform in ('web', 'ios', 'android')
  ),
  constraint lifecycle_prompt_events_session_hash_check check (
    session_hash ~ '^[0-9a-f]{64}$'
  ),
  constraint lifecycle_prompt_events_reason_shape_check check (
    (event_type = 'suppressed' and suppression_reason is not null)
    or (event_type <> 'suppressed' and suppression_reason is null)
  ),
  unique (decision_id, event_type)
);

create index if not exists lifecycle_prompt_events_user_time_idx
  on public.lifecycle_prompt_events (user_id, created_at desc);
create index if not exists lifecycle_prompt_events_key_time_idx
  on public.lifecycle_prompt_events (message_key, environment, created_at desc);
create index if not exists lifecycle_prompt_events_session_idx
  on public.lifecycle_prompt_events (user_id, environment, session_hash, event_type);
create unique index if not exists lifecycle_prompt_holdout_once_idx
  on public.lifecycle_prompt_events (user_id, message_key, environment, event_type)
  where event_type = 'holdout';
create unique index if not exists lifecycle_prompt_suppression_once_per_session_idx
  on public.lifecycle_prompt_events (
    user_id, message_key, environment, event_type, suppression_reason, session_hash
  ) where event_type = 'suppressed';

alter table public.lifecycle_prompt_controls enable row level security;
alter table public.lifecycle_prompt_state enable row level security;
alter table public.lifecycle_prompt_events enable row level security;

revoke all on table public.lifecycle_prompt_controls from public, anon, authenticated;
revoke all on table public.lifecycle_prompt_state from public, anon, authenticated;
revoke all on table public.lifecycle_prompt_events from public, anon, authenticated;
grant select, insert, update, delete on table public.lifecycle_prompt_controls to service_role;
grant select, insert, update, delete on table public.lifecycle_prompt_state to service_role;
grant select, insert, update, delete on table public.lifecycle_prompt_events to service_role;

insert into public.lifecycle_prompt_controls (message_key, enabled, holdout_percent)
values
  ('starter-assist', true, 20),
  ('first-value-assist', true, 20),
  ('continuity-assist', true, 20),
  ('artifact-assist', true, 20),
  ('referral-ask', true, 20)
on conflict (message_key) do nothing;

create or replace function public.lifecycle_prompt_facts(
  p_user_id uuid,
  p_environment text
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_has_project boolean := false;
  v_has_artifact boolean := false;
  v_has_aha boolean := false;
  v_latest_feedback text;
  v_intent text;
begin
  if p_environment not in ('production', 'preview', 'development') then
    return jsonb_build_object('accountEligible', false);
  end if;

  select * into v_user from public.users where id = p_user_id;
  if not found then
    return jsonb_build_object('accountEligible', false);
  end if;

  select exists (
    select 1 from public.projects p
    where p.user_id = p_user_id and p.archived_at is null
  ) into v_has_project;

  select exists (
    select 1 from public.product_events e
    where e.user_id = p_user_id
      and e.environment = p_environment
      and (
        (e.event_name = 'AhaReached' and e.event_key = 'first-durable-artifact')
        or e.event_name in ('ArtifactPackaged', 'ArtifactDownloaded')
      )
  ) into v_has_artifact;

  select (
    v_has_project or v_has_artifact or exists (
      select 1 from public.product_events e
      where e.user_id = p_user_id
        and e.environment = p_environment
        and e.event_name = 'AhaReached'
    )
  ) into v_has_aha;

  select e.source into v_latest_feedback
  from public.product_events e
  where e.user_id = p_user_id
    and e.environment = p_environment
    and e.event_name = 'OutcomeFeedbackSubmitted'
    and e.source in ('useful', 'needs_work')
  order by e.created_at desc
  limit 1;

  select e.intent into v_intent
  from public.product_events e
  where e.user_id = p_user_id
    and e.environment = p_environment
    and e.event_name = 'AccountCreated'
    and e.intent in ('document', 'presentation', 'resume', 'video', 'projects')
  order by e.created_at asc
  limit 1;

  return jsonb_build_object(
    'accountEligible', coalesce(v_user.is_verified, false) and v_user.deleted_at is null,
    'accountAgeSeconds', greatest(
      0,
      floor(extract(epoch from (now() - coalesce(v_user.created_at, now()))))::bigint
    ),
    'hasFirstRequest', exists (
      select 1 from public.message_receipts r where r.user_id = p_user_id
    ),
    'hasActivation', exists (
      select 1 from public.product_events e
      where e.user_id = p_user_id
        and e.environment = p_environment
        and e.event_name = 'ActivationReached'
    ),
    'hasProject', v_has_project,
    'hasArtifact', v_has_artifact,
    'hasAha', v_has_aha,
    'hasRecentWork', exists (
      select 1 from public.product_events e
      where e.user_id = p_user_id
        and e.environment = p_environment
        and e.event_name = 'RecentWorkResumed'
    ),
    'latestFeedback', v_latest_feedback,
    'acquisitionIntent', v_intent
  );
end
$function$;

create or replace function public.claim_lifecycle_prompt(
  p_user_id uuid,
  p_session_hash text,
  p_environment text,
  p_client_platform text,
  p_message_key text,
  p_intent text,
  p_surface text,
  p_active_work boolean default false,
  p_recovery_surface boolean default false,
  p_current_surface text default 'other'
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_control public.lifecycle_prompt_controls%rowtype;
  v_state public.lifecycle_prompt_state%rowtype;
  v_facts jsonb;
  v_decision uuid := gen_random_uuid();
  v_reason text;
  v_terminal boolean := false;
  v_is_holdout boolean;
  v_target_valid boolean := false;
  v_existing_shown boolean := false;
begin
  if p_message_key not in (
    'starter-assist', 'first-value-assist', 'continuity-assist',
    'artifact-assist', 'referral-ask'
  ) or p_environment not in ('production', 'preview', 'development')
    or p_client_platform not in ('web', 'ios', 'android')
    or p_session_hash !~ '^[0-9a-f]{64}$'
    or p_surface not in ('workspace-inline', 'composer-inline', 'post-response-inline')
    or coalesce(p_current_surface, 'other') not in ('ask', 'projects', 'create', 'other')
    or (p_intent is not null and p_intent not in (
      'document', 'presentation', 'resume', 'video', 'projects'
    ))
  then
    return jsonb_build_object('eligible', false);
  end if;

  if not (
    (p_message_key = 'starter-assist' and p_surface = 'workspace-inline')
    or (p_message_key = 'first-value-assist' and p_intent is null and p_surface = 'composer-inline')
    or (p_message_key = 'continuity-assist' and p_intent = 'projects' and p_surface = 'post-response-inline')
    or (p_message_key = 'artifact-assist' and p_intent in ('document', 'presentation', 'resume') and p_surface = 'workspace-inline')
    or (p_message_key = 'referral-ask' and p_intent is null and p_surface = 'post-response-inline')
  ) then
    return jsonb_build_object('eligible', false);
  end if;

  perform 1 from public.users where id = p_user_id for update;
  if not found then
    return jsonb_build_object('eligible', false);
  end if;

  select * into v_control
  from public.lifecycle_prompt_controls
  where message_key = p_message_key;
  if not found then
    return jsonb_build_object('eligible', false);
  end if;

  v_is_holdout := mod(
    (('x' || substr(md5(p_user_id::text || ':' || p_message_key), 1, 8))::bit(32)::bigint),
    100
  ) < v_control.holdout_percent;

  insert into public.lifecycle_prompt_state (
    user_id, message_key, environment, cohort, updated_at
  ) values (
    p_user_id, p_message_key, p_environment,
    case when v_is_holdout then 'holdout' else 'prompt' end,
    now()
  ) on conflict (user_id, message_key, environment) do nothing;

  select * into v_state
  from public.lifecycle_prompt_state
  where user_id = p_user_id
    and message_key = p_message_key
    and environment = p_environment
  for update;

  v_facts := public.lifecycle_prompt_facts(p_user_id, p_environment);
  if not coalesce((v_facts ->> 'accountEligible')::boolean, false) then
    v_reason := 'account-ineligible';
    v_terminal := true;
  elsif not v_control.enabled then
    v_reason := 'channel-disabled';
  elsif coalesce(p_recovery_surface, false) then
    v_reason := 'recovery-surface';
    v_terminal := true;
  elsif coalesce(p_active_work, false) then
    v_reason := 'active-work';
    v_terminal := true;
  elsif (p_current_surface = 'projects' and p_message_key in ('starter-assist', 'continuity-assist'))
    or (p_current_surface = 'create' and p_message_key = 'artifact-assist') then
    v_reason := 'active-work';
    v_terminal := true;
  else
    v_target_valid := case p_message_key
      when 'starter-assist' then
        not coalesce((v_facts ->> 'hasFirstRequest')::boolean, false)
        and not coalesce((v_facts ->> 'hasActivation')::boolean, false)
      when 'first-value-assist' then
        not coalesce((v_facts ->> 'hasActivation')::boolean, false)
        and coalesce((v_facts ->> 'accountAgeSeconds')::bigint, 0) >= 60
      when 'continuity-assist' then
        coalesce((v_facts ->> 'hasActivation')::boolean, false)
        and not coalesce((v_facts ->> 'hasAha')::boolean, false)
      when 'artifact-assist' then
        (
          coalesce((v_facts ->> 'hasActivation')::boolean, false)
          or coalesce((v_facts ->> 'hasProject')::boolean, false)
        ) and not coalesce((v_facts ->> 'hasArtifact')::boolean, false)
      when 'referral-ask' then
        (
          (
            coalesce((v_facts ->> 'hasAha')::boolean, false)
            and v_facts ->> 'latestFeedback' = 'useful'
          )
          or coalesce((v_facts ->> 'hasRecentWork')::boolean, false)
        ) and coalesce(v_facts ->> 'latestFeedback', '') <> 'needs_work'
      else false
    end;
    if not v_target_valid then
      v_reason := 'target-completed';
    end if;
  end if;

  if v_reason is null and v_state.active_decision_id is not null
    and v_state.active_decision_expires_at > now()
    and v_state.active_intent is not distinct from p_intent
    and v_state.active_surface = p_surface then
    select exists (
      select 1 from public.lifecycle_prompt_events e
      where e.decision_id = v_state.active_decision_id and e.event_type = 'shown'
    ) into v_existing_shown;
    if not v_existing_shown then
      return jsonb_build_object(
        'eligible', true,
        'messageKey', p_message_key,
        'intent', p_intent,
        'surface', p_surface,
        'decisionId', v_state.active_decision_id
      );
    end if;
  end if;

  if v_reason is null and exists (
    select 1 from public.lifecycle_prompt_events e
    where e.user_id = p_user_id
      and e.environment = p_environment
      and e.session_hash = p_session_hash
      and e.event_type = 'shown'
  ) then
    v_reason := 'session-collision';
    v_terminal := true;
  end if;

  if v_reason is null and (
    select count(*) from public.lifecycle_prompt_events e
    where e.user_id = p_user_id
      and e.environment = p_environment
      and e.event_type = 'shown'
      and e.created_at >= now() - interval '7 days'
  ) >= 2 then
    v_reason := 'frequency-cap';
    v_terminal := true;
  end if;

  if v_reason is null then
    if p_message_key = 'starter-assist' and (
      v_state.shown_count >= 2
      or (v_state.last_shown_at is not null and v_state.last_shown_at > now() - interval '24 hours')
    ) then
      v_reason := 'already-shown';
    elsif p_message_key = 'first-value-assist' and (
      v_state.shown_count >= 2
      or (v_state.last_shown_at is not null and v_state.last_shown_at > now() - interval '7 days')
    ) then
      v_reason := 'already-shown';
    elsif p_message_key = 'continuity-assist' and v_state.shown_count >= 1 then
      v_reason := 'already-shown';
    elsif p_message_key = 'artifact-assist'
      and v_state.last_shown_at is not null
      and v_state.last_shown_at > now() - interval '7 days' then
      v_reason := 'already-shown';
    elsif p_message_key = 'referral-ask' and (
      v_state.shown_count >= 3
      or (v_state.last_shown_at is not null and v_state.last_shown_at > now() - interval '30 days')
    ) then
      v_reason := 'already-shown';
    elsif p_message_key = 'referral-ask'
      and v_state.dismissed_at is not null
      and v_state.dismissed_at > now() - interval '90 days' then
      v_reason := 'user-dismissed';
    end if;
  end if;

  if v_reason is null and v_state.cohort = 'holdout' then
    update public.lifecycle_prompt_state
    set eligible_at = coalesce(eligible_at, now()), updated_at = now()
    where user_id = p_user_id and message_key = p_message_key and environment = p_environment;
    insert into public.lifecycle_prompt_events (
      user_id, message_key, environment, decision_id, event_type, cohort,
      intent, client_platform, session_hash
    ) values (
      p_user_id, p_message_key, p_environment, v_decision, 'holdout', 'holdout',
      p_intent, p_client_platform, p_session_hash
    ) on conflict do nothing;
    return jsonb_build_object(
      'eligible', false, 'suppressionReason', 'channel-disabled', 'terminal', true
    );
  end if;

  if v_reason is not null then
    update public.lifecycle_prompt_state
    set
      last_suppression_reason = v_reason,
      permanently_suppressed_at = case
        when v_reason = 'target-completed' then coalesce(permanently_suppressed_at, now())
        else permanently_suppressed_at
      end,
      updated_at = now()
    where user_id = p_user_id and message_key = p_message_key and environment = p_environment;
    insert into public.lifecycle_prompt_events (
      user_id, message_key, environment, decision_id, event_type, cohort,
      suppression_reason, intent, client_platform, session_hash
    ) values (
      p_user_id, p_message_key, p_environment, v_decision, 'suppressed', v_state.cohort,
      v_reason, p_intent, p_client_platform, p_session_hash
    ) on conflict do nothing;
    return jsonb_build_object(
      'eligible', false, 'suppressionReason', v_reason, 'terminal', v_terminal
    );
  end if;

  update public.lifecycle_prompt_state
  set
    eligible_at = coalesce(eligible_at, now()),
    active_decision_id = v_decision,
    active_decision_expires_at = now() + interval '10 minutes',
    active_intent = p_intent,
    active_surface = p_surface,
    last_suppression_reason = null,
    updated_at = now()
  where user_id = p_user_id and message_key = p_message_key and environment = p_environment;

  insert into public.lifecycle_prompt_events (
    user_id, message_key, environment, decision_id, event_type, cohort,
    intent, client_platform, session_hash
  ) values (
    p_user_id, p_message_key, p_environment, v_decision, 'eligible', 'prompt',
    p_intent, p_client_platform, p_session_hash
  );

  return jsonb_build_object(
    'eligible', true,
    'messageKey', p_message_key,
    'intent', p_intent,
    'surface', p_surface,
    'decisionId', v_decision
  );
end
$function$;

create or replace function public.record_lifecycle_prompt_action(
  p_user_id uuid,
  p_decision_id uuid,
  p_action text,
  p_session_hash text,
  p_environment text,
  p_client_platform text,
  p_active_work boolean default false,
  p_recovery_surface boolean default false,
  p_current_surface text default 'other',
  p_suppression_reason text default null
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $function$
declare
  v_state public.lifecycle_prompt_state%rowtype;
  v_facts jsonb;
  v_reason text;
  v_target_valid boolean := true;
  v_inserted integer := 0;
begin
  if p_action not in ('shown', 'dismissed', 'acted', 'suppressed')
    or p_environment not in ('production', 'preview', 'development')
    or p_client_platform not in ('web', 'ios', 'android')
    or p_session_hash !~ '^[0-9a-f]{64}$'
    or coalesce(p_current_surface, 'other') not in ('ask', 'projects', 'create', 'other')
  then
    return jsonb_build_object('recorded', false);
  end if;

  select * into v_state
  from public.lifecycle_prompt_state
  where user_id = p_user_id
    and environment = p_environment
    and active_decision_id = p_decision_id
  for update;
  if not found then
    return jsonb_build_object('recorded', false);
  end if;

  if p_action = 'shown' and exists (
    select 1 from public.lifecycle_prompt_events e
    where e.decision_id = p_decision_id and e.event_type = 'shown'
  ) then
    return jsonb_build_object('recorded', true);
  end if;

  if p_action = 'shown' then
    v_facts := public.lifecycle_prompt_facts(p_user_id, p_environment);
    if v_state.active_decision_expires_at <= now() then
      v_reason := 'recent-activity';
    elsif not coalesce((v_facts ->> 'accountEligible')::boolean, false) then
      v_reason := 'account-ineligible';
    elsif coalesce(p_recovery_surface, false) then
      v_reason := 'recovery-surface';
    elsif coalesce(p_active_work, false) then
      v_reason := 'active-work';
    elsif (p_current_surface = 'projects' and v_state.message_key in ('starter-assist', 'continuity-assist'))
      or (p_current_surface = 'create' and v_state.message_key = 'artifact-assist') then
      v_reason := 'active-work';
    else
      v_target_valid := case v_state.message_key
        when 'starter-assist' then
          not coalesce((v_facts ->> 'hasFirstRequest')::boolean, false)
          and not coalesce((v_facts ->> 'hasActivation')::boolean, false)
        when 'first-value-assist' then
          not coalesce((v_facts ->> 'hasActivation')::boolean, false)
        when 'continuity-assist' then
          coalesce((v_facts ->> 'hasActivation')::boolean, false)
          and not coalesce((v_facts ->> 'hasAha')::boolean, false)
        when 'artifact-assist' then
          not coalesce((v_facts ->> 'hasArtifact')::boolean, false)
        when 'referral-ask' then
          (
            (
              coalesce((v_facts ->> 'hasAha')::boolean, false)
              and v_facts ->> 'latestFeedback' = 'useful'
            )
            or coalesce((v_facts ->> 'hasRecentWork')::boolean, false)
          ) and coalesce(v_facts ->> 'latestFeedback', '') <> 'needs_work'
        else false
      end;
      if not v_target_valid then v_reason := 'target-completed'; end if;
    end if;

    if v_reason is null and exists (
      select 1 from public.lifecycle_prompt_events e
      where e.user_id = p_user_id
        and e.environment = p_environment
        and e.session_hash = p_session_hash
        and e.event_type = 'shown'
    ) then
      v_reason := 'session-collision';
    end if;
    if v_reason is null and (
      select count(*) from public.lifecycle_prompt_events e
      where e.user_id = p_user_id
        and e.environment = p_environment
        and e.event_type = 'shown'
        and e.created_at >= now() - interval '7 days'
    ) >= 2 then
      v_reason := 'frequency-cap';
    end if;

    if v_reason is not null then
      insert into public.lifecycle_prompt_events (
        user_id, message_key, environment, decision_id, event_type, cohort,
        suppression_reason, intent, client_platform, session_hash
      ) values (
        p_user_id, v_state.message_key, p_environment, p_decision_id,
        'suppressed', v_state.cohort, v_reason, v_state.active_intent,
        p_client_platform, p_session_hash
      ) on conflict do nothing;
      update public.lifecycle_prompt_state
      set
        last_suppression_reason = v_reason,
        permanently_suppressed_at = case
          when v_reason = 'target-completed' then coalesce(permanently_suppressed_at, now())
          else permanently_suppressed_at
        end,
        updated_at = now()
      where user_id = p_user_id
        and message_key = v_state.message_key
        and environment = p_environment;
      return jsonb_build_object(
        'recorded', false, 'suppressionReason', v_reason
      );
    end if;
  end if;

  if p_action in ('dismissed', 'acted') and not exists (
    select 1 from public.lifecycle_prompt_events e
    where e.decision_id = p_decision_id and e.event_type = 'shown'
  ) then
    return jsonb_build_object('recorded', false);
  end if;

  if p_action = 'suppressed' then
    if p_suppression_reason not in (
      'account-ineligible', 'channel-disabled', 'quiet-hours', 'unanswered-checkin',
      'target-completed', 'already-shown', 'frequency-cap', 'session-collision',
      'active-work', 'recovery-surface', 'no-safe-intent', 'recent-activity',
      'user-dismissed'
    ) then
      return jsonb_build_object('recorded', false);
    end if;
    insert into public.lifecycle_prompt_events (
      user_id, message_key, environment, decision_id, event_type, cohort,
      suppression_reason, intent, client_platform, session_hash
    ) values (
      p_user_id, v_state.message_key, p_environment, p_decision_id,
      'suppressed', v_state.cohort, p_suppression_reason, v_state.active_intent,
      p_client_platform, p_session_hash
    ) on conflict do nothing;
    update public.lifecycle_prompt_state
    set last_suppression_reason = p_suppression_reason, updated_at = now()
    where user_id = p_user_id
      and message_key = v_state.message_key
      and environment = p_environment;
    return jsonb_build_object('recorded', true);
  end if;

  insert into public.lifecycle_prompt_events (
    user_id, message_key, environment, decision_id, event_type, cohort,
    intent, client_platform, session_hash
  ) values (
    p_user_id, v_state.message_key, p_environment, p_decision_id, p_action,
    v_state.cohort, v_state.active_intent, p_client_platform, p_session_hash
  ) on conflict (decision_id, event_type) do nothing;
  get diagnostics v_inserted = row_count;

  if p_action = 'shown' and v_inserted = 1 then
    update public.lifecycle_prompt_state
    set
      first_shown_at = coalesce(first_shown_at, now()),
      last_shown_at = now(),
      shown_count = shown_count + 1,
      updated_at = now()
    where user_id = p_user_id
      and message_key = v_state.message_key
      and environment = p_environment;
  elsif p_action = 'dismissed' then
    update public.lifecycle_prompt_state
    set dismissed_at = coalesce(dismissed_at, now()), updated_at = now()
    where user_id = p_user_id
      and message_key = v_state.message_key
      and environment = p_environment;
  elsif p_action = 'acted' then
    update public.lifecycle_prompt_state
    set acted_at = coalesce(acted_at, now()), updated_at = now()
    where user_id = p_user_id
      and message_key = v_state.message_key
      and environment = p_environment;
  end if;

  return jsonb_build_object('recorded', true);
end
$function$;

create or replace function public.product_weekly_lifecycle_export(
  p_since timestamptz,
  p_until timestamptz,
  p_environment text default 'production'
)
returns table (
  row_type text,
  message_key text,
  intent text,
  cohort text,
  suppression_reason text,
  eligible_accounts bigint,
  shown_accounts bigint,
  acted_accounts bigint,
  target_completed_24h_accounts bigint,
  d7_eligible_accounts bigint,
  d7_returned_accounts bigint,
  dismissed_accounts bigint,
  suppression_count bigint
)
language sql
security invoker
set search_path = ''
as $function$
  with eligibility as (
    select distinct on (e.user_id, e.message_key, e.environment, e.decision_id)
      e.user_id,
      e.message_key,
      e.intent,
      e.cohort,
      e.decision_id,
      e.created_at as eligible_at
    from public.lifecycle_prompt_events e
    join public.users u on u.id = e.user_id
    where e.environment = p_environment
      and e.event_type in ('eligible', 'holdout')
      and e.created_at >= p_since
      and e.created_at < p_until
      and u.deleted_at is null
      and coalesce(u.internal_tier, '') = ''
      and (
        u.registration_environment = p_environment
        or (p_environment = 'production' and u.registration_environment is null)
      )
    order by e.user_id, e.message_key, e.environment, e.decision_id, e.created_at
  ),
  measured as (
    select
      q.*,
      exists (
        select 1 from public.lifecycle_prompt_events e
        where e.decision_id = q.decision_id and e.event_type = 'shown'
      ) as shown,
      exists (
        select 1 from public.lifecycle_prompt_events e
        where e.decision_id = q.decision_id and e.event_type = 'acted'
      ) as acted,
      exists (
        select 1 from public.lifecycle_prompt_events e
        where e.decision_id = q.decision_id and e.event_type = 'dismissed'
      ) as dismissed,
      exists (
        select 1 from public.product_events p
        where p.user_id = q.user_id
          and p.environment = p_environment
          and p.created_at >= q.eligible_at
          and p.created_at < q.eligible_at + interval '24 hours'
          and (
            (q.message_key in ('starter-assist', 'first-value-assist') and p.event_name = 'ActivationReached')
            or (q.message_key = 'continuity-assist' and p.event_name = 'AhaReached')
            or (
              q.message_key = 'artifact-assist'
              and (
                (p.event_name = 'AhaReached' and p.event_key = 'first-durable-artifact')
                or p.event_name in ('ArtifactPackaged', 'ArtifactDownloaded')
              )
            )
            or (q.message_key = 'referral-ask' and p.event_name = 'ResponseShared')
          )
      ) as target_completed_24h,
      q.eligible_at <= p_until - interval '7 days' as d7_eligible,
      exists (
        select 1 from public.product_events p
        where p.user_id = q.user_id
          and p.environment = p_environment
          and p.event_name in ('WorkspaceOpened', 'RecentWorkResumed')
          and p.created_at >= q.eligible_at + interval '6 days'
          and p.created_at < q.eligible_at + interval '8 days'
      ) as d7_returned
    from eligibility q
  ),
  cohort_rows as (
    select
      'cohort'::text as row_type,
      m.message_key,
      m.intent,
      m.cohort,
      null::text as suppression_reason,
      count(distinct m.user_id)::bigint as eligible_accounts,
      count(distinct m.user_id) filter (where m.shown)::bigint as shown_accounts,
      count(distinct m.user_id) filter (where m.acted)::bigint as acted_accounts,
      count(distinct m.user_id) filter (where m.target_completed_24h)::bigint as target_completed_24h_accounts,
      count(distinct m.user_id) filter (where m.d7_eligible)::bigint as d7_eligible_accounts,
      count(distinct m.user_id) filter (where m.d7_eligible and m.d7_returned)::bigint as d7_returned_accounts,
      count(distinct m.user_id) filter (where m.dismissed)::bigint as dismissed_accounts,
      0::bigint as suppression_count
    from measured m
    group by m.message_key, m.intent, m.cohort
  ),
  suppression_rows as (
    select
      'suppression'::text as row_type,
      e.message_key,
      e.intent,
      e.cohort,
      e.suppression_reason,
      0::bigint as eligible_accounts,
      0::bigint as shown_accounts,
      0::bigint as acted_accounts,
      0::bigint as target_completed_24h_accounts,
      0::bigint as d7_eligible_accounts,
      0::bigint as d7_returned_accounts,
      0::bigint as dismissed_accounts,
      count(*)::bigint as suppression_count
    from public.lifecycle_prompt_events e
    join public.users u on u.id = e.user_id
    where e.environment = p_environment
      and e.event_type = 'suppressed'
      and e.created_at >= p_since
      and e.created_at < p_until
      and u.deleted_at is null
      and coalesce(u.internal_tier, '') = ''
      and (
        u.registration_environment = p_environment
        or (p_environment = 'production' and u.registration_environment is null)
      )
    group by e.message_key, e.intent, e.cohort, e.suppression_reason
  )
  select * from cohort_rows
  union all
  select * from suppression_rows
  order by message_key, intent nulls first, cohort, row_type, suppression_reason nulls first;
$function$;

comment on table public.lifecycle_prompt_state is
  'Content-free, server-owned per-account lifecycle prompt state. Never stores rendered copy, URLs, names, or customer content.';
comment on table public.lifecycle_prompt_events is
  'Content-free lifecycle eligibility, holdout, delivery, action, and suppression evidence.';
comment on function public.product_weekly_lifecycle_export(timestamptz, timestamptz, text) is
  'Privacy-safe service-role weekly lifecycle cohort and suppression export; excludes internal accounts.';

revoke all on function public.lifecycle_prompt_facts(uuid, text) from public, anon, authenticated;
revoke all on function public.claim_lifecycle_prompt(
  uuid, text, text, text, text, text, text, boolean, boolean, text
) from public, anon, authenticated;
revoke all on function public.record_lifecycle_prompt_action(
  uuid, uuid, text, text, text, text, boolean, boolean, text, text
) from public, anon, authenticated;
revoke all on function public.product_weekly_lifecycle_export(
  timestamptz, timestamptz, text
) from public, anon, authenticated;

grant execute on function public.lifecycle_prompt_facts(uuid, text) to service_role;
grant execute on function public.claim_lifecycle_prompt(
  uuid, text, text, text, text, text, text, boolean, boolean, text
) to service_role;
grant execute on function public.record_lifecycle_prompt_action(
  uuid, uuid, text, text, text, text, boolean, boolean, text, text
) to service_role;
grant execute on function public.product_weekly_lifecycle_export(
  timestamptz, timestamptz, text
) to service_role;

commit;
