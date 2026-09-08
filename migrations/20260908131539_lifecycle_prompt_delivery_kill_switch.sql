-- Ask Crump lifecycle delivery-time kill-switch correction.
-- Re-check the per-message control immediately before recording a prompt as
-- shown so a stale decision cannot render after delivery has been disabled.

begin;

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
  v_control_enabled boolean := false;
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
    select c.enabled into v_control_enabled
    from public.lifecycle_prompt_controls c
    where c.message_key = v_state.message_key;

    if not coalesce(v_control_enabled, false) then
      v_reason := 'channel-disabled';
    else
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

revoke all on function public.record_lifecycle_prompt_action(
  uuid, uuid, text, text, text, text, boolean, boolean, text, text
) from public, anon, authenticated;

grant execute on function public.record_lifecycle_prompt_action(
  uuid, uuid, text, text, text, text, boolean, boolean, text, text
) to service_role;

comment on function public.record_lifecycle_prompt_action(
  uuid, uuid, text, text, text, text, boolean, boolean, text, text
) is 'Records content-free lifecycle actions and rechecks target, safety, frequency, session, and per-message delivery controls before display.';

commit;
