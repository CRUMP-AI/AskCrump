-- Content-free proof for the operator-owned sanitized demo journey.
-- The function stores nothing and returns only seven fixed booleans. It is
-- executable only by service_role and reads under the caller's privileges.

begin;

create or replace function public.demo_recording_proof_snapshot()
returns table (
  configured boolean,
  protected_identity boolean,
  complete_exchange boolean,
  project_saved boolean,
  project_reopened boolean,
  editable_artifact_ready boolean,
  proof_ready boolean
)
language sql
stable
security invoker
set search_path = ''
as $function$
  with demo as (
    select
      u.id,
      (
        lower(btrim(u.email)) = 'demo@askcrump.com'
        and btrim(u.full_name) = 'Ask Crump Demo'
        and u.is_verified is true
        and lower(coalesce(u.subscription_tier, '')) = 'free'
        and lower(coalesce(u.subscription_status, '')) = 'inactive'
        and lower(coalesce(u.internal_tier, '')) = 'enterprise'
        and lower(coalesce(u.registration_environment, '')) = 'preview'
        and u.deleted_at is null
        and u.subscription_provider is null
        and u.stripe_customer_id is null
        and u.stripe_subscription_id is null
        and u.store_product_id is null
      ) as protected_identity
    from public.users u
    where lower(btrim(u.email)) = 'demo@askcrump.com'
    order by u.created_at desc
    limit 1
  ),
  active_projects as (
    select p.id
    from public.projects p
    join demo d on d.id = p.user_id
    where p.archived_at is null
  ),
  single_active_project as (
    select (array_agg(p.id))[1] as project_id
    from active_projects p
    having count(*) = 1
  ),
  complete_chats as (
    select c.chat_id
    from public.user_chats c
    join demo d on d.id = c.user_id
    where c.deleted_at is null
      and exists (
        select 1
        from jsonb_array_elements(
          case when jsonb_typeof(c.messages) = 'array' then c.messages else '[]'::jsonb end
        ) item
        where item->>'role' = 'user'
          and nullif(btrim(item->>'content'), '') is not null
      )
      and exists (
        select 1
        from jsonb_array_elements(
          case when jsonb_typeof(c.messages) = 'array' then c.messages else '[]'::jsonb end
        ) item
        where item->>'role' = 'assistant'
          and nullif(btrim(item->>'content'), '') is not null
      )
  ),
  saved_journeys as (
    select distinct pc.project_id, pc.chat_id, pc.created_at as saved_at
    from public.project_chats pc
    join demo d on d.id = pc.user_id
    join single_active_project sp on sp.project_id = pc.project_id
    join complete_chats c on c.chat_id = pc.chat_id
  ),
  resumed_journeys as (
    select j.project_id, j.chat_id, min(e.created_at) as resumed_at
    from saved_journeys j
    join demo d on true
    join public.product_events e
      on e.user_id = d.id
     and e.event_name = 'RecentWorkResumed'
     and e.source = 'project'
     and e.environment = 'production'
     and e.created_at >= j.saved_at
    group by j.project_id, j.chat_id
  ),
  editable_artifacts as (
    select distinct r.project_id
    from resumed_journeys r
    join demo d on true
    join public.project_files pf
      on pf.project_id = r.project_id
     and pf.user_id = d.id
     and pf.role = 'generated_document'
     and pf.created_at >= r.resumed_at
    join public.user_files f
      on f.id = pf.file_id
     and f.user_id = d.id
     and f.deleted_at is null
     and f.status = 'ready'
     and f.kind = 'generated_document'
     and f.mime_type in (
       'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
       'application/vnd.openxmlformats-officedocument.presentationml.presentation'
     )
     and f.created_at >= r.resumed_at
  ),
  flags as (
    select
      exists (select 1 from demo) as configured,
      coalesce((select d.protected_identity from demo d), false) as protected_identity,
      exists (select 1 from complete_chats) as complete_exchange,
      exists (select 1 from saved_journeys) as project_saved,
      exists (select 1 from resumed_journeys) as project_reopened,
      exists (select 1 from editable_artifacts) as editable_artifact_ready
  )
  select
    f.configured,
    f.protected_identity,
    f.complete_exchange,
    f.project_saved,
    f.project_reopened,
    f.editable_artifact_ready,
    (
      f.configured
      and f.protected_identity
      and f.complete_exchange
      and f.project_saved
      and f.project_reopened
      and f.editable_artifact_ready
    ) as proof_ready
  from flags f;
$function$;

revoke all on function public.demo_recording_proof_snapshot()
  from public, anon, authenticated;
grant execute on function public.demo_recording_proof_snapshot()
  to service_role;

comment on function public.demo_recording_proof_snapshot() is
  'Service-role-only sanitized demo journey proof. Evaluates roles and relationships privately and returns seven booleans only; never identifiers, content, names, filenames, paths, URLs, or arbitrary metadata.';

commit;
