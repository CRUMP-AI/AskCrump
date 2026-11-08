begin;

select pg_catalog.set_config('search_path','pg_catalog,public',true);
select pg_catalog.set_config('quote_all_identifiers','off',true);

-- This successor is intentionally narrow: it pins the exact schedule and
-- approval objects it extends plus the exact 065000 reconciliation tail.
create or replace function pg_temp.connected_schedule_approval_predecessor_fingerprint()
returns text language sql stable set search_path='' as $fingerprint$
  select pg_catalog.md5(pg_catalog.string_agg(
    item.value::text,
    E'\n' order by item.value::text collate pg_catalog."C"
  ))
  from (
    select pg_catalog.jsonb_build_array(
      'schema',namespace_row.nspname,pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text,''),
      pg_catalog.obj_description(namespace_row.oid,'pg_namespace')) as value
    from pg_catalog.pg_namespace as namespace_row
    where namespace_row.nspname in ('connected_app_private','connected_schedule_private')
    union all
    select pg_catalog.jsonb_build_array(
      'relation',namespace_row.nspname,class_row.relname,class_row.relkind,
      class_row.relpersistence,class_row.relrowsecurity,class_row.relforcerowsecurity,
      class_row.relreplident,pg_catalog.pg_get_userbyid(class_row.relowner),
      coalesce(class_row.relacl::text,''),coalesce(class_row.reloptions::text,''),
      pg_catalog.obj_description(class_row.oid,'pg_class'))
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname in ('connected_app_private','connected_schedule_private')
      and class_row.relname in (
        'schedules','task_grants','connections','approvals','approval_reviews',
        'action_authority','templates','run_completions')
    union all
    select pg_catalog.jsonb_build_array(
      'column',namespace_row.nspname,class_row.relname,attribute_row.attnum,
      attribute_row.attname,pg_catalog.format_type(attribute_row.atttypid,attribute_row.atttypmod),
      attribute_row.attnotnull,attribute_row.attidentity,attribute_row.attgenerated,
      attribute_row.attstorage,attribute_row.attcompression,attribute_row.attstattarget,
      coalesce(attribute_row.attoptions::text,''),
      coalesce(pg_catalog.pg_get_expr(default_row.adbin,default_row.adrelid),''),
      coalesce(attribute_row.attacl::text,''),
      pg_catalog.col_description(class_row.oid,attribute_row.attnum))
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row on class_row.oid=attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_attrdef as default_row
      on default_row.adrelid=attribute_row.attrelid and default_row.adnum=attribute_row.attnum
    where namespace_row.nspname in ('connected_app_private','connected_schedule_private')
      and class_row.relname in (
        'schedules','task_grants','connections','approvals','approval_reviews',
        'action_authority','templates','run_completions')
      and attribute_row.attnum>0 and not attribute_row.attisdropped
    union all
    select pg_catalog.jsonb_build_array(
      'constraint',namespace_row.nspname,class_row.relname,constraint_row.conname,
      constraint_row.contype,constraint_row.condeferrable,constraint_row.condeferred,
      constraint_row.convalidated,pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    join pg_catalog.pg_class as class_row on class_row.oid=constraint_row.conrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname in ('connected_app_private','connected_schedule_private')
      and class_row.relname in (
        'schedules','task_grants','connections','approvals','approval_reviews',
        'action_authority','templates','run_completions')
    union all
    select pg_catalog.jsonb_build_array(
      'index',namespace_row.nspname,class_row.relname,index_class.relname,
      index_row.indisunique,index_row.indisprimary,index_row.indisvalid,index_row.indisready,
      pg_catalog.pg_get_indexdef(index_row.indexrelid))
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as class_row on class_row.oid=index_row.indrelid
    join pg_catalog.pg_class as index_class on index_class.oid=index_row.indexrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname in ('connected_app_private','connected_schedule_private')
      and class_row.relname in (
        'schedules','task_grants','connections','approvals','approval_reviews',
        'action_authority','templates','run_completions')
    union all
    select pg_catalog.jsonb_build_array(
      'function',namespace_row.nspname,proc_row.proname,
      pg_catalog.pg_get_function_identity_arguments(proc_row.oid),
      pg_catalog.pg_get_functiondef(proc_row.oid),
      pg_catalog.pg_get_userbyid(proc_row.proowner),proc_row.prosecdef,
      proc_row.provolatile,coalesce(proc_row.proconfig::text,''),coalesce(proc_row.proacl::text,''),
      pg_catalog.obj_description(proc_row.oid,'pg_proc'))
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=proc_row.pronamespace
    where (namespace_row.nspname,proc_row.proname) in (
      ('connected_schedule_private','claim_view_v2'),
      ('connected_schedule_private','completion_view_v2'),
      ('connected_schedule_private','template_view_v2'),
      ('connected_app_private','approval_view_v1'),
      ('connected_app_private','owner_lock_v1'),
      ('public','connected_app_claim_schedule_v2'),
      ('public','connected_app_read_schedule_claim_v2'),
      ('public','connected_app_finish_schedule_v2'),
      ('public','connected_app_read_schedule_finish_v2'),
      ('public','connected_app_operator_put_approval_review_v1'),
      ('public','connected_app_operator_decide_approval_v1'),
      ('public','connected_app_create_approval_v1'),
      ('public','connected_app_oauth_reconcile_expired_v1'))
  ) as item
$fingerprint$;

do $preflight$
declare
  predecessor_fingerprint text;
  reconciliation_fingerprint text;
  existing_target_fingerprint text;
  exact_target boolean:=false;
begin
  if pg_catalog.to_regprocedure('public.connected_app_oauth_reconcile_expired_v1(integer)') is null
     or pg_catalog.to_regprocedure('public.connected_app_claim_schedule_v2(uuid,integer)') is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_list_actions_v1(uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_get_action_v1(uuid,uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_list_approvals_v1(uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_get_approval_v1(uuid,uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_decide_approval_v1(uuid,uuid,text,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,bigint,text,text,text,text,text,timestamp with time zone)'
     ) is null then
    raise exception 'connected schedule approval predecessor is absent' using errcode='55000';
  end if;
  if pg_catalog.to_regprocedure(
       'connected_schedule_private.schedule_approval_target_fingerprint_v1()'
     ) is not null then
    select connected_schedule_private.schedule_approval_target_fingerprint_v1()
      into existing_target_fingerprint;
    if existing_target_fingerprint<>'fd7caa733d4112ade452de4755f39a45' then
      raise exception 'connected schedule approval existing target drifted: %',
        existing_target_fingerprint using errcode='55000';
    end if;
    exact_target:=true;
  else
    select pg_temp.connected_schedule_approval_predecessor_fingerprint()
      into predecessor_fingerprint;
    if predecessor_fingerprint <> '04209d99c31c8d1d01943c424ea4da74' then
      raise exception 'connected schedule approval predecessor drifted: %',
        predecessor_fingerprint using errcode='55000';
    end if;
  end if;
  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    pg_catalog.pg_get_functiondef(proc_row.oid),
    pg_catalog.obj_description(proc_row.oid,'pg_proc'),
    pg_catalog.pg_get_userbyid(proc_row.proowner),proc_row.prosecdef::text,
    proc_row.proleakproof::text,proc_row.proisstrict::text,proc_row.proretset::text,
    proc_row.provolatile::text,proc_row.proparallel::text,proc_row.procost::text,
    proc_row.prorows::text,language_row.lanname,proc_row.proconfig::text,
    proc_row.proacl::text)) into reconciliation_fingerprint
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_language as language_row on language_row.oid=proc_row.prolang
  where proc_row.oid=pg_catalog.to_regprocedure(
    'public.connected_app_oauth_reconcile_expired_v1(integer)');
  if reconciliation_fingerprint<>'52629ef0c6f07fe7ac8eb4292bfc59aa' then
    raise exception 'connected schedule approval reconciliation predecessor drifted'
      using errcode='55000';
  end if;
  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace
       where pnnspid in (
         pg_catalog.to_regnamespace('connected_app_private'),
         pg_catalog.to_regnamespace('connected_schedule_private')))
     or exists(
       select 1 from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname in ('connected_app_private','connected_schedule_private')) then
    raise exception 'connected schedule approval publication exposure refused'
      using errcode='55000';
  end if;
  if not exact_target and (
     pg_catalog.to_regclass('connected_schedule_private.occurrences') is not null
     or exists(
       select 1 from pg_catalog.pg_attribute
       where attrelid=pg_catalog.to_regclass('connected_schedule_private.run_completions')
         and attname='schedule_occurrence_id' and attnum>0 and not attisdropped)
     or exists(
       select 1 from pg_catalog.pg_proc as proc_row
       join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=proc_row.pronamespace
       where namespace_row.nspname in ('public','connected_schedule_private')
         and proc_row.proname in (
           'connected_app_claim_schedule_v3','connected_app_read_schedule_claim_v3',
           'connected_app_finish_schedule_v3','connected_app_read_schedule_finish_v3',
           'connected_app_put_schedule_approval_v1','connected_app_read_schedule_approval_v1',
           'schedule_approval_view_v1','schedule_approval_target_fingerprint_v1'))
     ) then
    raise exception 'connected schedule approval target is partial' using errcode='55000';
  end if;
end;
$preflight$;

create table if not exists connected_schedule_private.occurrences (
  occurrence_id uuid primary key,
  schedule_id uuid not null
    references connected_app_private.schedules(schedule_id) on delete cascade,
  owner_id uuid not null references public.users(id) on delete cascade,
  action_id uuid not null unique,
  approval_id uuid not null unique,
  task_id uuid not null,
  turn_id uuid not null,
  connection_id uuid not null
    references connected_app_private.connections(id) on delete cascade,
  provider text not null check(provider in ('google','microsoft')),
  resource text not null check(resource in ('mail','calendar')),
  action text not null,
  authorization_revision bigint not null check(authorization_revision>=1),
  authorization_snapshot_sha256 text not null
    check(authorization_snapshot_sha256~'^[0-9a-f]{64}$'),
  granted_scopes_sha256 text not null check(granted_scopes_sha256~'^[0-9a-f]{64}$'),
  task_state_revision bigint not null check(task_state_revision>=1),
  parameters_sha256 text not null check(parameters_sha256~'^[0-9a-f]{64}$'),
  resource_version_sha256 text
    check(resource_version_sha256 is null or resource_version_sha256~'^[0-9a-f]{64}$'),
  scheduled_for timestamptz not null,
  occurrence_created_at timestamptz not null,
  current_claim_id uuid,
  approval_binding_sha256 text
    check(approval_binding_sha256 is null or approval_binding_sha256~'^[0-9a-f]{64}$'),
  preview_payload_ref uuid,
  preview_reference_binding_sha256 text
    check(preview_reference_binding_sha256 is null
      or preview_reference_binding_sha256~'^[0-9a-f]{64}$'),
  preview_sha256 text check(preview_sha256 is null or preview_sha256~'^[0-9a-f]{64}$'),
  approval_expires_at timestamptz,
  status text not null default 'pending_approval'
    check(status in ('pending_approval','executed','failed','cancelled','denied','expired')),
  terminal_at timestamptz,
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint connected_schedule_occurrence_preview_shape check(
    (approval_binding_sha256 is null and preview_payload_ref is null
      and preview_reference_binding_sha256 is null and preview_sha256 is null
      and approval_expires_at is null)
    or (approval_binding_sha256 is not null and preview_payload_ref is not null
      and preview_reference_binding_sha256 is not null and preview_sha256 is not null
      and approval_expires_at is not null
      and approval_expires_at>occurrence_created_at
      and approval_expires_at<=occurrence_created_at+interval '15 minutes')),
  constraint connected_schedule_occurrence_terminal_shape check(
    (status='pending_approval' and terminal_at is null)
    or (status<>'pending_approval' and terminal_at is not null))
);
comment on table connected_schedule_private.occurrences is
  'ASK_CRUMP_CONNECTED_SCHEDULE_OCCURRENCES_V1_CONTENT_FREE_FRESH_APPROVAL';
comment on column connected_schedule_private.occurrences.parameters_sha256 is
  'ASK_CRUMP_KEYED_HMAC_PAYLOAD_COMMITMENT_NOT_PLAINTEXT';
create unique index if not exists connected_schedule_one_open_occurrence_idx
  on connected_schedule_private.occurrences(schedule_id)
  where terminal_at is null;
create unique index if not exists connected_schedule_occurrence_claim_idx
  on connected_schedule_private.occurrences(current_claim_id)
  where current_claim_id is not null;
create index if not exists connected_schedule_occurrence_owner_idx
  on connected_schedule_private.occurrences(owner_id,updated_at desc,occurrence_id);
alter table connected_schedule_private.occurrences enable row level security;
alter table connected_schedule_private.occurrences force row level security;

alter table connected_schedule_private.run_completions
  add column if not exists schedule_occurrence_id uuid
  references connected_schedule_private.occurrences(occurrence_id) on delete cascade;
create index if not exists connected_schedule_run_completion_occurrence_idx
  on connected_schedule_private.run_completions(schedule_occurrence_id,completion_id)
  where schedule_occurrence_id is not null;

create or replace function connected_schedule_private.claim_view_v3(p_claim_id uuid)
returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_schedule_private.claim_view_v2(p_claim_id)
    || pg_catalog.jsonb_build_object(
      'occurrence_id',occurrence.occurrence_id,
      'occurrence_action_id',occurrence.action_id,
      'occurrence_approval_id',occurrence.approval_id,
      'occurrence_created_at',occurrence.occurrence_created_at)
  from connected_app_private.schedules as schedule
  left join connected_schedule_private.occurrences as occurrence
    on occurrence.current_claim_id=schedule.claim_id
  where schedule.claim_id=p_claim_id
$fn$;

create or replace function connected_schedule_private.completion_view_v3(
  p_schedule_id uuid,p_claim_id uuid,p_completion_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_schedule_private.completion_view_v2(
      p_schedule_id,p_claim_id,p_completion_id)
    || pg_catalog.jsonb_build_object(
      'occurrence_id',completion.schedule_occurrence_id)
  from connected_schedule_private.run_completions as completion
  where completion.schedule_id=p_schedule_id and completion.claim_id=p_claim_id
    and completion.completion_id=p_completion_id
$fn$;

create or replace function connected_schedule_private.schedule_approval_view_v1(
  p_occurrence_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'occurrence_id',occurrence.occurrence_id,
    'schedule_id',occurrence.schedule_id,
    'owner_id',occurrence.owner_id,
    'approval_id',occurrence.approval_id,
    'action_id',occurrence.action_id,
    'task_id',occurrence.task_id,
    'turn_id',occurrence.turn_id,
    'connection_id',occurrence.connection_id,
    'provider',occurrence.provider,
    'resource',occurrence.resource,
    'action',occurrence.action,
    'authorization_revision',occurrence.authorization_revision,
    'authorization_snapshot_sha256',occurrence.authorization_snapshot_sha256,
    'granted_scopes_sha256',occurrence.granted_scopes_sha256,
    'policy_version',review.policy_version,
    'action_revision',review.action_revision,
    'approval_class',review.approval_class,
    'approval_binding_sha256',occurrence.approval_binding_sha256,
    'parameters_sha256',occurrence.parameters_sha256,
    'resource_version_sha256',occurrence.resource_version_sha256,
    'preview_sha256',occurrence.preview_sha256,
    'review_payload_ref',occurrence.preview_payload_ref,
    'status',case
      when occurrence.status='executed' then 'executed'
      when occurrence.status='cancelled' or occurrence.status='failed' then 'cancelled'
      when occurrence.status='denied' then 'denied'
      when occurrence.status='expired' then 'expired'
      when review.status='pending' and review.expires_at<=pg_catalog.statement_timestamp()
        then 'expired'
      else review.status end,
    'occurrence_created_at',occurrence.occurrence_created_at,
    'expires_at',review.expires_at,
    'decided_at',review.decided_at,
    'approved_at',approval.approved_at,
    'consumed_at',approval.consumed_at)
  from connected_schedule_private.occurrences as occurrence
  join connected_app_private.approval_reviews as review
    on review.approval_id=occurrence.approval_id
   and review.action_id=occurrence.action_id
   and review.owner_id=occurrence.owner_id
  left join connected_app_private.approvals as approval
    on approval.approval_id=review.approval_id
   and approval.action_id=review.action_id
   and approval.owner_id=review.owner_id
  where occurrence.occurrence_id=p_occurrence_id
$fn$;

create or replace function public.connected_app_claim_schedule_v3(
  p_claim_id uuid,p_occurrence_id uuid,p_occurrence_action_id uuid,
  p_occurrence_approval_id uuid,p_lease_seconds integer
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  claimed jsonb;
  schedule_row connected_app_private.schedules%rowtype;
  template_row connected_schedule_private.templates%rowtype;
  occurrence_row connected_schedule_private.occurrences%rowtype;
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  if p_claim_id is null or p_occurrence_id is null or p_occurrence_action_id is null
     or p_occurrence_approval_id is null then
    raise exception 'invalid schedule occurrence claim' using errcode='22023';
  end if;
  claimed:=public.connected_app_claim_schedule_v2(p_claim_id,p_lease_seconds);
  if claimed is null then return null; end if;
  select schedule.* into strict schedule_row
  from connected_app_private.schedules as schedule
  where schedule.claim_id=p_claim_id for update;
  if not schedule_row.requires_approval_every_run then
    return connected_schedule_private.claim_view_v3(p_claim_id);
  end if;
  perform connected_app_private.owner_lock_v1(schedule_row.owner_id);
  select template.* into strict template_row
  from connected_schedule_private.templates as template
  where template.template_id=schedule_row.action_template_ref for update;
  select occurrence.* into occurrence_row
  from connected_schedule_private.occurrences as occurrence
  where occurrence.schedule_id=schedule_row.schedule_id
    and occurrence.terminal_at is null for update;
  if found then
    if occurrence_row.owner_id<>schedule_row.owner_id
       or occurrence_row.task_id<>schedule_row.task_id
       or occurrence_row.turn_id<>template_row.turn_id
       or occurrence_row.connection_id<>schedule_row.connection_id
       or occurrence_row.provider<>schedule_row.provider
       or occurrence_row.resource<>schedule_row.resource
       or occurrence_row.action<>schedule_row.action
       or occurrence_row.authorization_revision<>template_row.authorization_revision
       or occurrence_row.authorization_snapshot_sha256<>
          template_row.authorization_snapshot_sha256
       or occurrence_row.granted_scopes_sha256<>template_row.granted_scopes_sha256
       or occurrence_row.task_state_revision<>schedule_row.task_state_revision
       or occurrence_row.parameters_sha256<>schedule_row.parameters_sha256
       or occurrence_row.resource_version_sha256 is distinct from
          template_row.resource_version_sha256 then
      raise exception 'schedule occurrence authority drifted' using errcode='55000';
    end if;
    update connected_schedule_private.occurrences as occurrence
    set current_claim_id=p_claim_id,updated_at=now_at
    where occurrence.occurrence_id=occurrence_row.occurrence_id;
  else
    insert into connected_schedule_private.occurrences(
      occurrence_id,schedule_id,owner_id,action_id,approval_id,task_id,turn_id,
      connection_id,provider,resource,action,authorization_revision,
      authorization_snapshot_sha256,granted_scopes_sha256,task_state_revision,
      parameters_sha256,resource_version_sha256,scheduled_for,
      occurrence_created_at,current_claim_id
    ) values (
      p_occurrence_id,schedule_row.schedule_id,schedule_row.owner_id,
      p_occurrence_action_id,p_occurrence_approval_id,schedule_row.task_id,
      template_row.turn_id,schedule_row.connection_id,schedule_row.provider,
      schedule_row.resource,schedule_row.action,template_row.authorization_revision,
      template_row.authorization_snapshot_sha256,template_row.granted_scopes_sha256,
      schedule_row.task_state_revision,schedule_row.parameters_sha256,
      template_row.resource_version_sha256,schedule_row.next_run_at,now_at,p_claim_id
    );
  end if;
  return connected_schedule_private.claim_view_v3(p_claim_id);
end;
$fn$;

create or replace function public.connected_app_read_schedule_claim_v3(p_claim_id uuid)
returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_schedule_private.claim_view_v3(p_claim_id)
$fn$;

create or replace function public.connected_app_put_schedule_approval_v1(
  p_occurrence_id uuid,p_schedule_id uuid,p_owner_id uuid,p_claim_id uuid,
  p_approval_id uuid,p_action_id uuid,p_task_id uuid,p_turn_id uuid,
  p_connection_id uuid,p_provider text,p_resource text,p_action text,
  p_authorization_revision bigint,p_authorization_snapshot_sha256 text,
  p_granted_scopes_sha256 text,p_policy_version text,p_action_revision bigint,
  p_approval_class text,p_approval_binding_sha256 text,p_parameters_sha256 text,
  p_resource_version_sha256 text,p_preview_sha256 text,p_review_payload_ref uuid,
  p_preview_reference_binding_sha256 text,p_created_at timestamptz,
  p_expires_at timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  occurrence_row connected_schedule_private.occurrences%rowtype;
  schedule_row connected_app_private.schedules%rowtype;
  connection_row connected_app_private.connections%rowtype;
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  if p_occurrence_id is null or p_schedule_id is null or p_owner_id is null
     or p_claim_id is null or p_approval_id is null or p_action_id is null
     or p_review_payload_ref is null
     or p_preview_reference_binding_sha256!~'^[0-9a-f]{64}$'
     or p_created_at<now_at-interval '5 minutes'
     or p_created_at>now_at+interval '1 minute'
     or p_expires_at<=now_at
     or p_expires_at>p_created_at+interval '15 minutes' then
    raise exception 'invalid schedule occurrence approval' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select occurrence.* into occurrence_row
  from connected_schedule_private.occurrences as occurrence
  where occurrence.occurrence_id=p_occurrence_id for update;
  select schedule.* into schedule_row
  from connected_app_private.schedules as schedule
  where schedule.schedule_id=p_schedule_id and schedule.owner_id=p_owner_id for update;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.id=p_connection_id and connection.owner_id=p_owner_id for update;
  if occurrence_row.occurrence_id is null or schedule_row.schedule_id is null
     or connection_row.id is null or occurrence_row.terminal_at is not null
     or schedule_row.status<>'active' or schedule_row.claim_id<>p_claim_id
     or schedule_row.claim_expires_at<=now_at
     or occurrence_row.current_claim_id<>p_claim_id
     or occurrence_row.schedule_id<>p_schedule_id
     or occurrence_row.owner_id<>p_owner_id
     or occurrence_row.approval_id<>p_approval_id
     or occurrence_row.action_id<>p_action_id
     or occurrence_row.task_id<>p_task_id or occurrence_row.turn_id<>p_turn_id
     or occurrence_row.connection_id<>p_connection_id
     or occurrence_row.provider<>p_provider or occurrence_row.resource<>p_resource
     or occurrence_row.action<>p_action
     or occurrence_row.authorization_revision<>p_authorization_revision
     or occurrence_row.authorization_snapshot_sha256<>
        p_authorization_snapshot_sha256
     or occurrence_row.granted_scopes_sha256<>p_granted_scopes_sha256
     or occurrence_row.task_state_revision<>p_action_revision
     or occurrence_row.parameters_sha256<>p_parameters_sha256
     or occurrence_row.resource_version_sha256 is distinct from
        p_resource_version_sha256
     or occurrence_row.occurrence_created_at<>p_created_at
     or connection_row.authorization_state<>'active'
     or connection_row.revoked_at is not null
     or connection_row.provider<>p_provider or connection_row.resource<>p_resource
     or connection_row.authorization_revision<>p_authorization_revision
     or connection_row.authorization_snapshot_sha256<>
        p_authorization_snapshot_sha256
     or connection_row.granted_scopes_sha256<>p_granted_scopes_sha256
     or connection_row.authorization_expires_at is null
     or connection_row.authorization_expires_at<=p_expires_at
     or not(p_action=any(connection_row.granted_actions)) then
    raise exception 'schedule occurrence approval authority changed' using errcode='55000';
  end if;
  if occurrence_row.approval_binding_sha256 is not null then
    if occurrence_row.approval_binding_sha256<>p_approval_binding_sha256
       or occurrence_row.preview_payload_ref<>p_review_payload_ref
       or occurrence_row.preview_reference_binding_sha256<>
          p_preview_reference_binding_sha256
       or occurrence_row.preview_sha256<>p_preview_sha256
       or occurrence_row.approval_expires_at<>p_expires_at then
      raise exception 'schedule occurrence approval replay drifted' using errcode='55000';
    end if;
    return connected_schedule_private.schedule_approval_view_v1(p_occurrence_id);
  end if;
  perform public.connected_app_operator_put_approval_review_v1(
    p_approval_id,p_action_id,p_owner_id,p_task_id,p_turn_id,p_connection_id,
    p_provider,p_resource,p_action,p_authorization_revision,
    p_authorization_snapshot_sha256,p_granted_scopes_sha256,p_policy_version,
    p_action_revision,p_approval_class,p_approval_binding_sha256,
    p_parameters_sha256,p_resource_version_sha256,p_preview_sha256,
    p_review_payload_ref,p_created_at,p_expires_at);
  update connected_schedule_private.occurrences as occurrence set
    approval_binding_sha256=p_approval_binding_sha256,
    preview_payload_ref=p_review_payload_ref,
    preview_reference_binding_sha256=p_preview_reference_binding_sha256,
    preview_sha256=p_preview_sha256,approval_expires_at=p_expires_at,
    updated_at=now_at
  where occurrence.occurrence_id=p_occurrence_id;
  return connected_schedule_private.schedule_approval_view_v1(p_occurrence_id);
end;
$fn$;

create or replace function public.connected_app_read_schedule_approval_v1(
  p_owner_id uuid,p_occurrence_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_schedule_private.schedule_approval_view_v1(occurrence.occurrence_id)
  from connected_schedule_private.occurrences as occurrence
  where occurrence.owner_id=p_owner_id
    and occurrence.occurrence_id=p_occurrence_id
$fn$;

create or replace function public.connected_app_finish_schedule_v3(
  p_completion_id uuid,p_schedule_id uuid,p_owner_id uuid,p_claim_id uuid,
  p_task_state_revision bigint,p_outcome text,p_operation_id uuid,
  p_next_run_at timestamptz,p_finished_at timestamptz,p_occurrence_id uuid
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  schedule_row connected_app_private.schedules%rowtype;
  occurrence_row connected_schedule_private.occurrences%rowtype;
  completion_row connected_schedule_private.run_completions%rowtype;
  review_row connected_app_private.approval_reviews%rowtype;
  approval_row connected_app_private.approvals%rowtype;
  occurrence_terminal boolean:=false;
  occurrence_status text;
begin
  if p_occurrence_id is null then
    if p_outcome<>'read' then
      raise exception 'write schedule completion lacks occurrence' using errcode='55000';
    end if;
    perform public.connected_app_finish_schedule_v2(
      p_completion_id,p_schedule_id,p_owner_id,p_claim_id,p_task_state_revision,
      p_outcome,p_operation_id,p_next_run_at,p_finished_at);
    return connected_schedule_private.completion_view_v3(
      p_schedule_id,p_claim_id,p_completion_id);
  end if;
  if p_completion_id is null or p_schedule_id is null or p_owner_id is null
     or p_claim_id is null or p_task_state_revision<1
     or p_outcome not in ('succeeded','ambiguous','waiting_approval',
       'invalid_template','failed_no_retry','cancelled_unknown')
     or ((p_outcome in ('waiting_approval','invalid_template'))<>
       (p_operation_id is null))
     or p_finished_at<now_at-interval '5 minutes'
     or p_finished_at>now_at+interval '1 minute'
     or p_next_run_at<p_finished_at+interval '60 seconds'
     or p_next_run_at>p_finished_at+interval '31 days' then
    raise exception 'invalid schedule occurrence completion' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select completion.* into completion_row
  from connected_schedule_private.run_completions as completion
  where completion.completion_id=p_completion_id
     or (completion.schedule_id=p_schedule_id and completion.claim_id=p_claim_id)
  order by completion.completion_id limit 1 for update;
  if found then
    if completion_row.completion_id<>p_completion_id
       or completion_row.schedule_id<>p_schedule_id
       or completion_row.owner_id<>p_owner_id
       or completion_row.claim_id<>p_claim_id
       or completion_row.task_state_revision<>p_task_state_revision
       or completion_row.outcome<>p_outcome
       or completion_row.operation_id is distinct from p_operation_id
       or completion_row.next_run_at<>p_next_run_at
       or completion_row.finished_at<>p_finished_at
       or completion_row.schedule_occurrence_id<>p_occurrence_id then
      raise exception 'schedule occurrence completion replay drifted' using errcode='55000';
    end if;
    return connected_schedule_private.completion_view_v3(
      p_schedule_id,p_claim_id,p_completion_id);
  end if;
  select schedule.* into schedule_row
  from connected_app_private.schedules as schedule
  where schedule.schedule_id=p_schedule_id and schedule.owner_id=p_owner_id for update;
  select occurrence.* into occurrence_row
  from connected_schedule_private.occurrences as occurrence
  where occurrence.occurrence_id=p_occurrence_id for update;
  if schedule_row.schedule_id is null or occurrence_row.occurrence_id is null
     or schedule_row.status<>'active' or schedule_row.claim_id<>p_claim_id
     or schedule_row.claim_expires_at<=now_at
     or schedule_row.task_state_revision<>p_task_state_revision
     or occurrence_row.schedule_id<>p_schedule_id
     or occurrence_row.owner_id<>p_owner_id
     or occurrence_row.current_claim_id<>p_claim_id
     or occurrence_row.task_state_revision<>p_task_state_revision
     or (p_operation_id is not null
       and p_operation_id<>occurrence_row.action_id)
     or occurrence_row.terminal_at is not null then
    raise exception 'schedule occurrence completion claim is stale' using errcode='55000';
  end if;
  if p_outcome='waiting_approval' then
    select review.* into review_row
    from connected_app_private.approval_reviews as review
    where review.approval_id=occurrence_row.approval_id for update;
    if review_row.approval_id is null then
      occurrence_terminal:=now_at>=occurrence_row.occurrence_created_at+interval '15 minutes';
      occurrence_status:='expired';
    elsif review_row.status='denied' then
      occurrence_terminal:=true; occurrence_status:='denied';
    elsif review_row.status='pending' and review_row.expires_at<=now_at then
      occurrence_terminal:=true; occurrence_status:='expired';
    else
      occurrence_status:='pending_approval';
    end if;
  else
    if p_outcome in ('succeeded','ambiguous') then
      select approval.* into approval_row
      from connected_app_private.approvals as approval
      where approval.approval_id=occurrence_row.approval_id for update;
      if approval_row.approval_id is null
         or approval_row.owner_id<>p_owner_id
         or approval_row.action_id<>occurrence_row.action_id
         or approval_row.connection_id<>occurrence_row.connection_id
         or approval_row.parameters_sha256<>occurrence_row.parameters_sha256
         or approval_row.authorization_revision<>
            occurrence_row.authorization_revision
         or approval_row.authorization_snapshot_sha256<>
            occurrence_row.authorization_snapshot_sha256
         or approval_row.expires_at<=now_at
         or approval_row.consumed_at is null
         or approval_row.consumed_by_operation_id<>p_operation_id then
        raise exception 'schedule occurrence completion lacks consumed approval'
          using errcode='55000';
      end if;
    end if;
    occurrence_terminal:=true;
    occurrence_status:=case
      when p_outcome in ('succeeded','ambiguous') then 'executed'
      else 'failed' end;
  end if;
  insert into connected_schedule_private.run_completions(
    completion_id,schedule_id,owner_id,claim_id,task_state_revision,outcome,
    operation_id,next_run_at,finished_at,recorded_at,schedule_occurrence_id
  ) values (
    p_completion_id,p_schedule_id,p_owner_id,p_claim_id,p_task_state_revision,
    p_outcome,p_operation_id,p_next_run_at,p_finished_at,now_at,p_occurrence_id);
  update connected_schedule_private.occurrences as occurrence set
    current_claim_id=null,status=occurrence_status,
    terminal_at=case when occurrence_terminal then now_at else null end,
    updated_at=now_at
  where occurrence.occurrence_id=p_occurrence_id;
  update connected_app_private.schedules as schedule set
    claim_id=null,claim_expires_at=null,
    completed_claim_id=case when occurrence_terminal then p_claim_id
      else schedule.completed_claim_id end,
    completed_at=case when occurrence_terminal then now_at else schedule.completed_at end,
    status=case when p_outcome='invalid_template' then 'paused' else 'active' end,
    next_run_at=case when p_outcome='invalid_template' then null else p_next_run_at end,
    updated_at=now_at
  where schedule.schedule_id=p_schedule_id;
  update connected_app_private.task_grants set revoked_at=now_at
  where grant_id=p_claim_id and revoked_at is null;
  return connected_schedule_private.completion_view_v3(
    p_schedule_id,p_claim_id,p_completion_id);
end;
$fn$;

create or replace function public.connected_app_read_schedule_finish_v3(
  p_schedule_id uuid,p_claim_id uuid,p_completion_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_schedule_private.completion_view_v3(
    p_schedule_id,p_claim_id,p_completion_id)
$fn$;

create or replace function connected_schedule_private.cancel_open_occurrence_v1()
returns trigger language plpgsql security definer set search_path='' as $fn$
begin
  if old.status='active' and new.status in ('paused','cancelled') then
    update connected_schedule_private.occurrences as occurrence set
      status='cancelled',current_claim_id=null,
      terminal_at=pg_catalog.clock_timestamp(),updated_at=pg_catalog.clock_timestamp()
    where occurrence.schedule_id=new.schedule_id and occurrence.terminal_at is null;
  end if;
  return new;
end;
$fn$;
drop trigger if exists connected_schedule_cancel_occurrence_v1
  on connected_app_private.schedules;
create trigger connected_schedule_cancel_occurrence_v1
after update of status on connected_app_private.schedules
for each row execute function connected_schedule_private.cancel_open_occurrence_v1();

-- Preserve the existing decision contract and add the schedule-occurrence
-- fence before creating one-use execution authority.  Chat approvals remain
-- unchanged because they have no occurrence row.
create or replace function public.connected_app_operator_decide_approval_v1(
  p_decision_id uuid,p_owner_id uuid,p_session_binding_sha256 text,
  p_approval_id uuid,p_action_id uuid,p_connection_id uuid,
  p_task_id uuid,p_turn_id uuid,p_provider text,p_resource text,
  p_action text,p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,p_granted_scopes_sha256 text,
  p_policy_version text,p_action_revision bigint,
  p_approval_binding_sha256 text,p_parameters_sha256 text,
  p_resource_version_sha256 text,p_preview_sha256 text,
  p_decision text,p_decided_at timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  review_row connected_app_private.approval_reviews%rowtype;
  connection_row connected_app_private.connections%rowtype;
  occurrence_row connected_schedule_private.occurrences%rowtype;
  schedule_row connected_app_private.schedules%rowtype;
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  if p_decision_id is null or p_owner_id is null or p_approval_id is null
     or p_session_binding_sha256!~'^[0-9a-f]{64}$'
     or p_decision not in ('approved','denied')
     or p_decided_at<now_at-interval '5 minutes'
     or p_decided_at>now_at+interval '1 minute' then
    raise exception 'invalid approval decision' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select review.* into review_row
  from connected_app_private.approval_reviews as review
  where review.owner_id=p_owner_id and review.approval_id=p_approval_id for update;
  if not found then return null; end if;
  if review_row.status<>'pending' then
    if review_row.decision_id=p_decision_id
       and review_row.decision_session_binding_sha256=p_session_binding_sha256
       and review_row.status=p_decision then
      return connected_app_private.approval_view_v1(p_owner_id,p_approval_id);
    end if;
    raise exception 'approval was already decided' using errcode='55000';
  end if;
  if review_row.action_id<>p_action_id or review_row.connection_id<>p_connection_id
     or review_row.task_id<>p_task_id or review_row.turn_id<>p_turn_id
     or review_row.provider<>p_provider or review_row.resource<>p_resource
     or review_row.action<>p_action
     or review_row.authorization_revision<>p_authorization_revision
     or review_row.authorization_snapshot_sha256<>p_authorization_snapshot_sha256
     or review_row.granted_scopes_sha256<>p_granted_scopes_sha256
     or review_row.policy_version<>p_policy_version
     or review_row.action_revision<>p_action_revision
     or review_row.approval_binding_sha256<>p_approval_binding_sha256
     or review_row.parameters_sha256<>p_parameters_sha256
     or review_row.resource_version_sha256 is distinct from p_resource_version_sha256
     or review_row.preview_sha256<>p_preview_sha256
     or review_row.expires_at<=now_at or p_decided_at>review_row.expires_at then
    raise exception 'approval decision binding changed' using errcode='55000';
  end if;
  select occurrence.* into occurrence_row
  from connected_schedule_private.occurrences as occurrence
  where occurrence.approval_id=p_approval_id and occurrence.owner_id=p_owner_id
  for update;
  if found then
    select schedule.* into schedule_row
    from connected_app_private.schedules as schedule
    where schedule.schedule_id=occurrence_row.schedule_id
      and schedule.owner_id=p_owner_id for update;
    if schedule_row.schedule_id is null or schedule_row.status<>'active'
       or occurrence_row.terminal_at is not null
       or occurrence_row.action_id<>p_action_id
       or occurrence_row.connection_id<>p_connection_id
       or occurrence_row.task_id<>p_task_id or occurrence_row.turn_id<>p_turn_id
       or occurrence_row.task_state_revision<>p_action_revision
       or occurrence_row.approval_binding_sha256<>p_approval_binding_sha256
       or occurrence_row.approval_expires_at<=now_at then
      raise exception 'schedule approval occurrence is no longer current'
        using errcode='55000';
    end if;
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id=p_owner_id and connection.id=p_connection_id for update;
  if not found or connection_row.authorization_state<>'active'
     or connection_row.provider<>p_provider or connection_row.resource<>p_resource
     or connection_row.authorization_revision<>p_authorization_revision
     or connection_row.authorization_snapshot_sha256<>p_authorization_snapshot_sha256
     or connection_row.granted_scopes_sha256<>p_granted_scopes_sha256
     or not(p_action=any(connection_row.granted_actions))
     or (connection_row.authorization_expires_at is not null
         and connection_row.authorization_expires_at<=now_at) then
    raise exception 'approval connection authority changed' using errcode='55000';
  end if;
  if p_decision='approved' then
    perform public.connected_app_create_approval_v1(
      review_row.approval_id,review_row.action_id,review_row.owner_id,
      review_row.task_id,review_row.turn_id,review_row.connection_id,
      review_row.provider,review_row.resource,review_row.action,
      review_row.authorization_revision,review_row.authorization_snapshot_sha256,
      review_row.approval_class,review_row.parameters_sha256,
      review_row.resource_version_sha256,review_row.approval_binding_sha256,
      p_decided_at,review_row.expires_at);
  end if;
  update connected_app_private.approval_reviews as review set
    status=p_decision,decision_id=p_decision_id,
    decision_session_binding_sha256=p_session_binding_sha256,
    decided_at=p_decided_at,updated_at=now_at
  where review.approval_id=p_approval_id;
  return connected_app_private.approval_view_v1(p_owner_id,p_approval_id);
end;
$fn$;

create or replace function connected_schedule_private.schedule_approval_target_fingerprint_v1()
returns text language sql stable security definer set search_path='' as $fingerprint$
  select pg_catalog.md5(pg_catalog.string_agg(
    item.value::text,
    E'\n' order by item.value::text collate pg_catalog."C"
  ))
  from (
    select pg_catalog.jsonb_build_array(
      'relation',namespace_row.nspname,class_row.relname,class_row.relkind,
      class_row.relpersistence,class_row.relrowsecurity,class_row.relforcerowsecurity,
      pg_catalog.pg_get_userbyid(class_row.relowner),coalesce(class_row.relacl::text,''),
      pg_catalog.obj_description(class_row.oid,'pg_class')) as value
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_schedule_private'
      and class_row.relname in ('occurrences','run_completions')
    union all
    select pg_catalog.jsonb_build_array(
      'column',class_row.relname,attribute_row.attnum,attribute_row.attname,
      pg_catalog.format_type(attribute_row.atttypid,attribute_row.atttypmod),
      attribute_row.attnotnull,coalesce(pg_catalog.pg_get_expr(default_row.adbin,default_row.adrelid),''),
      coalesce(attribute_row.attacl::text,''),
      pg_catalog.col_description(class_row.oid,attribute_row.attnum))
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row on class_row.oid=attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_attrdef as default_row
      on default_row.adrelid=attribute_row.attrelid and default_row.adnum=attribute_row.attnum
    where namespace_row.nspname='connected_schedule_private'
      and class_row.relname in ('occurrences','run_completions')
      and attribute_row.attnum>0 and not attribute_row.attisdropped
    union all
    select pg_catalog.jsonb_build_array(
      'constraint',class_row.relname,constraint_row.conname,constraint_row.contype,
      constraint_row.condeferrable,constraint_row.condeferred,constraint_row.convalidated,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    join pg_catalog.pg_class as class_row on class_row.oid=constraint_row.conrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_schedule_private'
      and class_row.relname in ('occurrences','run_completions')
    union all
    select pg_catalog.jsonb_build_array(
      'index',class_row.relname,index_class.relname,index_row.indisunique,
      index_row.indisprimary,index_row.indisvalid,index_row.indisready,
      pg_catalog.pg_get_indexdef(index_row.indexrelid))
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as class_row on class_row.oid=index_row.indrelid
    join pg_catalog.pg_class as index_class on index_class.oid=index_row.indexrelid
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_schedule_private'
      and class_row.relname in ('occurrences','run_completions')
    union all
    select pg_catalog.jsonb_build_array(
      'trigger',trigger_row.tgname,pg_catalog.pg_get_triggerdef(trigger_row.oid,true),
      pg_catalog.obj_description(trigger_row.oid,'pg_trigger'))
    from pg_catalog.pg_trigger as trigger_row
    where trigger_row.tgrelid=pg_catalog.to_regclass('connected_app_private.schedules')
      and not trigger_row.tgisinternal
      and trigger_row.tgname='connected_schedule_cancel_occurrence_v1'
    union all
    select pg_catalog.jsonb_build_array(
      'function',namespace_row.nspname,proc_row.proname,
      pg_catalog.pg_get_function_identity_arguments(proc_row.oid),
      pg_catalog.pg_get_functiondef(proc_row.oid),
      pg_catalog.pg_get_userbyid(proc_row.proowner),proc_row.prosecdef,
      proc_row.provolatile,coalesce(proc_row.proconfig::text,''),
      coalesce(proc_row.proacl::text,''),pg_catalog.obj_description(proc_row.oid,'pg_proc'))
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=proc_row.pronamespace
    where (namespace_row.nspname,proc_row.proname) in (
      ('connected_schedule_private','claim_view_v3'),
      ('connected_schedule_private','completion_view_v3'),
      ('connected_schedule_private','schedule_approval_view_v1'),
      ('connected_schedule_private','cancel_open_occurrence_v1'),
      ('connected_schedule_private','schedule_approval_target_fingerprint_v1'),
      ('connected_app_private','action_view_v1'),
      ('connected_app_private','approval_view_v1'),
      ('public','connected_app_claim_schedule_v3'),
      ('public','connected_app_read_schedule_claim_v3'),
      ('public','connected_app_finish_schedule_v3'),
      ('public','connected_app_read_schedule_finish_v3'),
      ('public','connected_app_put_schedule_approval_v1'),
      ('public','connected_app_read_schedule_approval_v1'),
      ('public','connected_app_operator_list_actions_v1'),
      ('public','connected_app_operator_get_action_v1'),
      ('public','connected_app_operator_list_approvals_v1'),
      ('public','connected_app_operator_get_approval_v1'),
      ('public','connected_app_operator_decide_approval_v1'))
  ) as item
$fingerprint$;

comment on function connected_schedule_private.schedule_approval_target_fingerprint_v1() is
  'ASK_CRUMP_CONNECTED_SCHEDULE_APPROVAL_TARGET_FINGERPRINT_V1';

do $authority$
declare function_row record;
begin
  alter table connected_schedule_private.occurrences owner to postgres;
  alter table connected_schedule_private.run_completions owner to postgres;
  revoke all on table connected_schedule_private.occurrences from public,anon,authenticated,service_role;
  revoke all on table connected_schedule_private.run_completions from public,anon,authenticated,service_role;
  for function_row in
    select proc_row.oid::pg_catalog.regprocedure as signature,
      namespace_row.nspname as schema_name
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=proc_row.pronamespace
    where (namespace_row.nspname,proc_row.proname) in (
      ('connected_schedule_private','claim_view_v3'),
      ('connected_schedule_private','completion_view_v3'),
      ('connected_schedule_private','schedule_approval_view_v1'),
      ('connected_schedule_private','cancel_open_occurrence_v1'),
      ('connected_schedule_private','schedule_approval_target_fingerprint_v1'),
      ('public','connected_app_claim_schedule_v3'),
      ('public','connected_app_read_schedule_claim_v3'),
      ('public','connected_app_finish_schedule_v3'),
      ('public','connected_app_read_schedule_finish_v3'),
      ('public','connected_app_put_schedule_approval_v1'),
      ('public','connected_app_read_schedule_approval_v1'),
      ('public','connected_app_operator_decide_approval_v1'))
  loop
    execute pg_catalog.format('alter function %s owner to postgres',function_row.signature);
    execute pg_catalog.format(
      'revoke all on function %s from public,anon,authenticated,service_role',
      function_row.signature);
    if function_row.schema_name='public' then
      execute pg_catalog.format(
        'grant execute on function %s to service_role',function_row.signature);
    end if;
  end loop;
end;
$authority$;

do $postflight$
declare target_fingerprint text;
begin
  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace
       where pnnspid in (
         pg_catalog.to_regnamespace('connected_app_private'),
         pg_catalog.to_regnamespace('connected_schedule_private')))
     or exists(
       select 1 from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname in ('connected_app_private','connected_schedule_private')) then
    raise exception 'connected schedule approval target publication exposure'
      using errcode='55000';
  end if;
  if not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_claim_schedule_v3(uuid,uuid,uuid,uuid,integer)','EXECUTE')
     or pg_catalog.has_function_privilege(
       'anon','public.connected_app_claim_schedule_v3(uuid,uuid,uuid,uuid,integer)','EXECUTE')
     or pg_catalog.has_function_privilege(
       'authenticated','public.connected_app_claim_schedule_v3(uuid,uuid,uuid,uuid,integer)','EXECUTE')
     or pg_catalog.has_table_privilege('service_role','connected_schedule_private.occurrences','SELECT')
     or not (select relrowsecurity and relforcerowsecurity
       from pg_catalog.pg_class
       where oid=pg_catalog.to_regclass('connected_schedule_private.occurrences')) then
    raise exception 'connected schedule approval target authority drifted'
      using errcode='55000';
  end if;
  select connected_schedule_private.schedule_approval_target_fingerprint_v1()
    into target_fingerprint;
  if target_fingerprint<>'fd7caa733d4112ade452de4755f39a45' then
    raise exception 'connected schedule approval postflight drifted: %',target_fingerprint
      using errcode='55000';
  end if;
end;
$postflight$;

commit;
