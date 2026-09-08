-- Ask Crump lifecycle durable-product-facts correction.
-- Keep lifecycle decisions and outcome measurement truthful when best-effort
-- product-event writes are absent after durable product work succeeds.

begin;

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
  v_is_verified boolean := false;
  v_deleted_at timestamptz;
  v_created_at timestamptz;
  v_registration_environment text;
  v_has_first_request boolean := false;
  v_has_activation boolean := false;
  v_has_project boolean := false;
  v_has_project_continuity boolean := false;
  v_has_artifact boolean := false;
  v_has_aha boolean := false;
  v_latest_feedback text;
  v_intent text;
begin
  if p_environment not in ('production', 'preview', 'development') then
    return jsonb_build_object('accountEligible', false);
  end if;

  select
    u.is_verified,
    u.deleted_at,
    u.created_at,
    u.registration_environment
  into
    v_is_verified,
    v_deleted_at,
    v_created_at,
    v_registration_environment
  from public.users u
  where u.id = p_user_id;
  if not found then
    return jsonb_build_object('accountEligible', false);
  end if;

  select (
    exists (
      select 1 from public.message_receipts r where r.user_id = p_user_id
    ) or exists (
      select 1 from public.chat_jobs j where j.user_id = p_user_id
    )
  ) into v_has_first_request;

  select (
    exists (
      select 1 from public.chat_jobs j
      where j.user_id = p_user_id and j.status = 'completed'
    ) or exists (
      select 1 from public.product_events e
      where e.user_id = p_user_id
        and e.environment = p_environment
        and e.event_name = 'ActivationReached'
    )
  ) into v_has_activation;

  select exists (
    select 1 from public.projects p
    where p.user_id = p_user_id and p.archived_at is null
  ) into v_has_project;

  select (
    exists (
      select 1
      from public.project_chats pc
      join public.projects p
        on p.id = pc.project_id
       and p.user_id = pc.user_id
      where pc.user_id = p_user_id
        and p.archived_at is null
    ) or exists (
      select 1
      from public.project_files pf
      join public.projects p
        on p.id = pf.project_id
       and p.user_id = pf.user_id
      where pf.user_id = p_user_id
        and p.archived_at is null
    )
  ) into v_has_project_continuity;

  select (
    exists (
      select 1 from public.user_files f
      where f.user_id = p_user_id
        and f.deleted_at is null
        and f.status = 'ready'
        and f.size_bytes > 0
        and f.kind in (
          'generated_image', 'generated_document', 'generated_video', 'manuscript_export'
        )
    ) or exists (
      select 1 from public.product_events e
      where e.user_id = p_user_id
        and e.environment = p_environment
        and (
          (e.event_name = 'AhaReached' and e.event_key = 'first-durable-artifact')
          or e.event_name in ('ArtifactPackaged', 'ArtifactDownloaded')
        )
    )
  ) into v_has_artifact;

  select (
    v_has_project_continuity or v_has_artifact or exists (
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
    'accountEligible',
      coalesce(v_is_verified, false)
      and v_deleted_at is null
      and (
        v_registration_environment = p_environment
        or (p_environment = 'production' and v_registration_environment is null)
      ),
    'accountAgeSeconds', greatest(
      0,
      floor(extract(epoch from (now() - coalesce(v_created_at, now()))))::bigint
    ),
    'hasFirstRequest', v_has_first_request,
    'hasActivation', v_has_activation,
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
      (
        exists (
          select 1 from public.product_events p
          where p.user_id = q.user_id
            and p.environment = p_environment
            and p.created_at >= q.eligible_at
            and p.created_at < q.eligible_at + interval '24 hours'
            and (
              (q.message_key in ('starter-assist', 'first-value-assist') and p.event_name = 'ActivationReached')
              or (
                q.message_key = 'continuity-assist'
                and p.event_name = 'AhaReached'
                and p.event_key = 'first-durable-project'
              )
              or (
                q.message_key = 'artifact-assist'
                and (
                  (p.event_name = 'AhaReached' and p.event_key = 'first-durable-artifact')
                  or p.event_name in ('ArtifactPackaged', 'ArtifactDownloaded')
                )
              )
              or (q.message_key = 'referral-ask' and p.event_name = 'ResponseShared')
            )
        )
        or (
          q.message_key in ('starter-assist', 'first-value-assist')
          and exists (
            select 1 from public.chat_jobs j
            where j.user_id = q.user_id
              and j.status = 'completed'
              and j.updated_at >= q.eligible_at
              and j.updated_at < q.eligible_at + interval '24 hours'
          )
        )
        or (
          q.message_key = 'continuity-assist'
          and exists (
            select 1
            from public.project_chats pc
            join public.projects p
              on p.id = pc.project_id
             and p.user_id = pc.user_id
            where pc.user_id = q.user_id
              and p.archived_at is null
              and pc.created_at >= q.eligible_at
              and pc.created_at < q.eligible_at + interval '24 hours'
          )
        )
        or (
          q.message_key = 'artifact-assist'
          and exists (
            select 1 from public.user_files f
            where f.user_id = q.user_id
              and f.deleted_at is null
              and f.status = 'ready'
              and f.size_bytes > 0
              and f.kind in (
                'generated_image', 'generated_document', 'generated_video', 'manuscript_export'
              )
              and f.created_at >= q.eligible_at
              and f.created_at < q.eligible_at + interval '24 hours'
          )
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

comment on function public.lifecycle_prompt_facts(uuid, text) is
  'Content-free lifecycle facts. Durable completed responses, Project attachments, and generated files remain authoritative when best-effort product events are absent.';
comment on function public.product_weekly_lifecycle_export(timestamptz, timestamptz, text) is
  'Privacy-safe service-role weekly lifecycle export. Counts durable response, conversation-to-Project, and generated-file outcomes in addition to content-free product events.';

revoke all on function public.lifecycle_prompt_facts(uuid, text)
  from public, anon, authenticated;
revoke all on function public.product_weekly_lifecycle_export(timestamptz, timestamptz, text)
  from public, anon, authenticated;
grant execute on function public.lifecycle_prompt_facts(uuid, text)
  to service_role;
grant execute on function public.product_weekly_lifecycle_export(timestamptz, timestamptz, text)
  to service_role;

commit;
