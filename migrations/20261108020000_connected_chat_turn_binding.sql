-- Durable, content-free binding between one authenticated chat request and a
-- future connected-app plan/action. Local release lock remains false.

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);

do $preflight$
declare
  existing_schema oid := pg_catalog.to_regnamespace('connected_chat_private');
  observed_fingerprint text;
begin
  if pg_catalog.to_regclass('public.users') is null
     or pg_catalog.to_regclass('public.chat_jobs') is null
     or pg_catalog.to_regprocedure('public.claim_chat_job_v2(uuid,uuid,uuid)') is null
     or pg_catalog.to_regprocedure('connected_app_private.owner_lock_v1(uuid)') is null then
    raise exception 'connected chat turn binding requires the reviewed chat and connected-app substrate'
      using errcode = '55000';
  end if;
  if not exists (
    select 1
    from pg_catalog.pg_attribute as attribute_row
    where attribute_row.attrelid = 'public.chat_jobs'::pg_catalog.regclass
      and attribute_row.attname = 'claim_token'
      and attribute_row.atttypid = 'uuid'::pg_catalog.regtype
      and attribute_row.attnum > 0
      and not attribute_row.attisdropped
  ) then
    raise exception 'connected chat turn binding requires fenced chat claims'
      using errcode = '55000';
  end if;
  if existing_schema is null then
    if pg_catalog.to_regprocedure(
         'public.connected_chat_claim_turn_v1(uuid,uuid,uuid,text,text)'
       ) is not null
       or pg_catalog.to_regprocedure(
         'public.connected_chat_read_turn_v1(uuid,uuid,uuid,text,text)'
       ) is not null then
      raise exception 'partial connected chat turn target; refusing repair'
        using errcode = '55000';
    end if;
    return;
  end if;

  if pg_catalog.to_regclass('connected_chat_private.turns') is null
     or pg_catalog.to_regprocedure(
       'public.connected_chat_claim_turn_v1(uuid,uuid,uuid,text,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_chat_read_turn_v1(uuid,uuid,uuid,text,text)'
     ) is null then
    raise exception 'partial connected chat turn target; refusing repair'
      using errcode = '55000';
  end if;

  with target as (
    select 'connected_chat_private.turns'::pg_catalog.regclass::oid as relid
  ), manifest as (
    select pg_catalog.jsonb_build_object(
      'schema_owner', (
        select pg_catalog.pg_get_userbyid(namespace_row.nspowner)
        from pg_catalog.pg_namespace as namespace_row
        where namespace_row.nspname = 'connected_chat_private'
      ),
      'schema_acl', (
        select coalesce(namespace_row.nspacl::text, '')
        from pg_catalog.pg_namespace as namespace_row
        where namespace_row.nspname = 'connected_chat_private'
      ),
      'schema_comment', (
        select pg_catalog.obj_description(namespace_row.oid, 'pg_namespace')
        from pg_catalog.pg_namespace as namespace_row
        where namespace_row.nspname = 'connected_chat_private'
      ),
      'classes', (
        select pg_catalog.jsonb_agg(
          class_row.relkind::text || '|' || class_row.relname
          order by class_row.relkind::text collate pg_catalog."C",
            class_row.relname collate pg_catalog."C"
        )
        from pg_catalog.pg_class as class_row
        join pg_catalog.pg_namespace as namespace_row
          on namespace_row.oid = class_row.relnamespace
        where namespace_row.nspname = 'connected_chat_private'
      ),
      'types', (
        select pg_catalog.jsonb_agg(
          type_row.typtype::text || '|' || type_row.typname
          order by type_row.typtype::text collate pg_catalog."C",
            type_row.typname collate pg_catalog."C"
        )
        from pg_catalog.pg_type as type_row
        join pg_catalog.pg_namespace as namespace_row
          on namespace_row.oid = type_row.typnamespace
        where namespace_row.nspname = 'connected_chat_private'
      ),
      'private_functions', (
        select pg_catalog.jsonb_agg(
          proc_row.proname || '|' ||
          pg_catalog.pg_get_function_identity_arguments(proc_row.oid) || '|' ||
          pg_catalog.md5(proc_row.prosrc)
          order by proc_row.proname collate pg_catalog."C",
            pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
              collate pg_catalog."C"
        )
        from pg_catalog.pg_proc as proc_row
        join pg_catalog.pg_namespace as namespace_row
          on namespace_row.oid = proc_row.pronamespace
        where namespace_row.nspname = 'connected_chat_private'
      ),
      'public_function_names', (
        select pg_catalog.jsonb_agg(
          proc_row.proname || '|' ||
          pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
          order by proc_row.proname collate pg_catalog."C",
            pg_catalog.pg_get_function_identity_arguments(proc_row.oid)
              collate pg_catalog."C"
        )
        from pg_catalog.pg_proc as proc_row
        join pg_catalog.pg_namespace as namespace_row
          on namespace_row.oid = proc_row.pronamespace
        where namespace_row.nspname = 'public'
          and proc_row.proname like 'connected_chat\_%' escape '\'
      ),
      'relation', (
        select pg_catalog.jsonb_build_object(
          'owner', pg_catalog.pg_get_userbyid(class_row.relowner),
          'acl', coalesce(class_row.relacl::text, ''),
          'rls', class_row.relrowsecurity,
          'force', class_row.relforcerowsecurity,
          'comment', pg_catalog.obj_description(class_row.oid, 'pg_class')
        )
        from pg_catalog.pg_class as class_row, target
        where class_row.oid = target.relid
      ),
      'columns', (
        select pg_catalog.jsonb_agg(
          attribute_row.attname || '|' ||
          pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) || '|' ||
          attribute_row.attnotnull::text || '|' ||
          coalesce(
            pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid), ''
          ) order by attribute_row.attnum
        )
        from pg_catalog.pg_attribute as attribute_row
        join target on attribute_row.attrelid = target.relid
        left join pg_catalog.pg_attrdef as default_row
          on default_row.adrelid = attribute_row.attrelid
         and default_row.adnum = attribute_row.attnum
        where attribute_row.attnum > 0 and not attribute_row.attisdropped
      ),
      'constraints', (
        select pg_catalog.jsonb_agg(
          constraint_row.contype::text || '|' ||
          pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
          order by constraint_row.contype::text collate pg_catalog."C",
            pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
              collate pg_catalog."C"
        )
        from pg_catalog.pg_constraint as constraint_row, target
        where constraint_row.conrelid = target.relid
      ),
      'indexes', (
        select pg_catalog.jsonb_agg(
          pg_catalog.pg_get_indexdef(index_row.indexrelid)
          order by pg_catalog.pg_get_indexdef(index_row.indexrelid)
            collate pg_catalog."C"
        )
        from pg_catalog.pg_index as index_row, target
        where index_row.indrelid = target.relid
      ),
      'functions', (
        select pg_catalog.jsonb_agg(
          pg_catalog.jsonb_build_object(
            'name', proc_row.proname,
            'args', pg_catalog.pg_get_function_identity_arguments(proc_row.oid),
            'result', pg_catalog.pg_get_function_result(proc_row.oid),
            'source', pg_catalog.md5(proc_row.prosrc),
            'owner', pg_catalog.pg_get_userbyid(proc_row.proowner),
            'security', proc_row.prosecdef,
            'config', proc_row.proconfig,
            'acl', proc_row.proacl::text,
            'comment', pg_catalog.obj_description(proc_row.oid, 'pg_proc')
          ) order by proc_row.proname collate pg_catalog."C"
        )
        from pg_catalog.pg_proc as proc_row
        join pg_catalog.pg_namespace as namespace_row
          on namespace_row.oid = proc_row.pronamespace
        where namespace_row.nspname = 'public'
          and proc_row.proname in (
            'connected_chat_claim_turn_v1', 'connected_chat_read_turn_v1'
          )
      ),
      'policies', (
        select pg_catalog.count(*) from pg_catalog.pg_policy as policy_row, target
        where policy_row.polrelid = target.relid
      ),
      'user_triggers', (
        select pg_catalog.count(*) from pg_catalog.pg_trigger as trigger_row, target
        where trigger_row.tgrelid = target.relid and not trigger_row.tgisinternal
      ),
      'rules', (
        select pg_catalog.count(*) from pg_catalog.pg_rewrite as rule_row, target
        where rule_row.ev_class = target.relid and rule_row.rulename <> '_RETURN'
      ),
      'publications', (
        select pg_catalog.count(*) from pg_catalog.pg_publication_tables
        where schemaname = 'connected_chat_private'
      )
    ) as value
  )
  select pg_catalog.md5(manifest.value::text) into observed_fingerprint
  from manifest;
  if observed_fingerprint <> '4887a4c14128fb5a05d667cdfec50669' then
    raise exception 'connected chat turn target drifted; refusing repair'
      using errcode = '55000';
  end if;
end;
$preflight$;

begin;

create schema if not exists connected_chat_private authorization postgres;
comment on schema connected_chat_private is
  'ASK_CRUMP_CONNECTED_CHAT_TURN_BINDING_V1_CONTENT_FREE';
revoke all on schema connected_chat_private from public, anon, authenticated, service_role;

create table if not exists connected_chat_private.turns (
  turn_id uuid primary key default pg_catalog.gen_random_uuid(),
  job_id uuid not null unique references public.chat_jobs(id) on delete cascade,
  owner_id uuid not null references public.users(id) on delete cascade,
  chat_id uuid not null,
  message_id uuid not null,
  origin_session_binding_sha256 text not null
    check (origin_session_binding_sha256 ~ '^[0-9a-f]{64}$'),
  request_binding_sha256 text not null
    check (request_binding_sha256 ~ '^[0-9a-f]{64}$'),
  stage text not null default 'claimed'
    check (stage in (
      'claimed', 'planning', 'planned', 'prepared', 'executing',
      'terminal', 'effect_unknown'
    )),
  planning_id uuid unique,
  planning_binding_sha256 text
    check (planning_binding_sha256 is null or planning_binding_sha256 ~ '^[0-9a-f]{64}$'),
  plan_payload_id uuid unique,
  plan_payload_sha256 text
    check (plan_payload_sha256 is null or plan_payload_sha256 ~ '^[0-9a-f]{64}$'),
  plan_reference_binding_sha256 text
    check (
      plan_reference_binding_sha256 is null
      or plan_reference_binding_sha256 ~ '^[0-9a-f]{64}$'
    ),
  preparation_request_id uuid unique,
  action_id uuid unique,
  result_payload_id uuid unique,
  completion_id uuid unique,
  created_at timestamptz not null default pg_catalog.statement_timestamp(),
  updated_at timestamptz not null default pg_catalog.statement_timestamp(),
  unique (owner_id, message_id),
  unique (owner_id, chat_id, message_id),
  check ((planning_id is null) = (planning_binding_sha256 is null)),
  check ((plan_payload_id is null) = (plan_payload_sha256 is null)),
  check (
    (plan_payload_id is null) = (plan_reference_binding_sha256 is null)
  ),
  check ((result_payload_id is null) = (completion_id is null))
);
comment on table connected_chat_private.turns is
  'ASK_CRUMP_CONNECTED_CHAT_TURNS_V1_OPAQUE_BINDINGS_ONLY';
comment on column connected_chat_private.turns.request_binding_sha256 is
  'ASK_CRUMP_KEYED_HMAC_EXACT_CHAT_BODY_ATTACHMENTS_TIMEZONE_NOT_PLAINTEXT_DIGEST';
comment on column connected_chat_private.turns.origin_session_binding_sha256 is
  'ASK_CRUMP_KEYED_HMAC_AUTHENTICATED_ORIGIN_SESSION';
create index if not exists connected_chat_turns_owner_updated_idx
  on connected_chat_private.turns(owner_id, updated_at desc, turn_id);
create index if not exists connected_chat_turns_stage_idx
  on connected_chat_private.turns(stage, updated_at, turn_id);
alter table connected_chat_private.turns enable row level security;
alter table connected_chat_private.turns force row level security;
revoke all on table connected_chat_private.turns from public, anon, authenticated, service_role;

create or replace function public.connected_chat_claim_turn_v1(
  p_owner_id uuid,
  p_chat_id uuid,
  p_message_id uuid,
  p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text
)
returns table(
  job_state text,
  turn_id uuid,
  stage text,
  claim_token uuid,
  response_data jsonb,
  updated_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  current_job public.chat_jobs%rowtype;
  current_turn connected_chat_private.turns%rowtype;
  next_claim_token uuid := pg_catalog.gen_random_uuid();
  now_at timestamptz := pg_catalog.statement_timestamp();
  inserted_job boolean := false;
begin
  if p_owner_id is null or p_chat_id is null or p_message_id is null
     or p_origin_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_request_binding_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid connected chat turn binding' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);

  insert into public.chat_jobs(
    user_id, chat_id, message_id, status, claim_token, created_at, updated_at
  ) values (
    p_owner_id, p_chat_id, p_message_id, 'processing', next_claim_token,
    now_at, now_at
  )
  on conflict (user_id, message_id) do nothing
  returning * into current_job;
  inserted_job := found;

  if not inserted_job then
    select job.* into current_job
    from public.chat_jobs as job
    where job.user_id = p_owner_id and job.message_id = p_message_id
    for update;
    if not found then
      raise exception 'connected chat job disappeared' using errcode = '55000';
    end if;
  end if;

  select turn.* into current_turn
  from connected_chat_private.turns as turn
  where turn.job_id = current_job.id
  for update;

  if inserted_job then
    if found then
      raise exception 'new chat job collided with a connected turn' using errcode = '55000';
    end if;
    insert into connected_chat_private.turns(
      job_id, owner_id, chat_id, message_id,
      origin_session_binding_sha256, request_binding_sha256,
      stage, created_at, updated_at
    ) values (
      current_job.id, p_owner_id, p_chat_id, p_message_id,
      p_origin_session_binding_sha256, p_request_binding_sha256,
      'claimed', now_at, now_at
    ) returning * into current_turn;
    return query select
      'claimed'::text, current_turn.turn_id, current_turn.stage,
      current_job.claim_token, null::jsonb, now_at;
    return;
  end if;

  if not found
     or current_job.chat_id <> p_chat_id
     or current_turn.owner_id <> p_owner_id
     or current_turn.chat_id <> p_chat_id
     or current_turn.message_id <> p_message_id
     or current_turn.origin_session_binding_sha256
        <> p_origin_session_binding_sha256
     or current_turn.request_binding_sha256 <> p_request_binding_sha256 then
    raise exception 'connected chat turn replay drifted' using errcode = '55000';
  end if;

  if current_job.status = 'completed' then
    if current_turn.stage <> 'terminal' or current_job.response_data is null then
      raise exception 'connected chat terminal state drifted' using errcode = '55000';
    end if;
    return query select
      'completed'::text, current_turn.turn_id, current_turn.stage,
      null::uuid, current_job.response_data, current_job.updated_at;
    return;
  end if;

  if current_turn.stage = 'effect_unknown' then
    raise exception 'connected chat effect is unknown' using errcode = '55000';
  end if;

  if current_job.status = 'processing'
     and current_job.updated_at > now_at - interval '8 minutes' then
    return query select
      'busy'::text, current_turn.turn_id, current_turn.stage,
      null::uuid, null::jsonb, current_job.updated_at;
    return;
  end if;

  update public.chat_jobs as job
  set status = 'processing', error_code = null,
      claim_token = next_claim_token, updated_at = now_at
  where job.id = current_job.id
  returning * into current_job;
  update connected_chat_private.turns as turn
  set updated_at = now_at
  where turn.turn_id = current_turn.turn_id
  returning * into current_turn;

  return query select
    'claimed'::text, current_turn.turn_id, current_turn.stage,
    current_job.claim_token, null::jsonb, now_at;
end;
$fn$;
comment on function public.connected_chat_claim_turn_v1(uuid,uuid,uuid,text,text) is
  'ASK_CRUMP_CONNECTED_CHAT_CLAIM_V1_EXACT_REQUEST_SESSION_NO_REWRITE';

create or replace function public.connected_chat_read_turn_v1(
  p_owner_id uuid,
  p_chat_id uuid,
  p_message_id uuid,
  p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'turn_id', turn.turn_id,
    'stage', turn.stage,
    'planning_id', turn.planning_id,
    'plan_payload_id', turn.plan_payload_id,
    'preparation_request_id', turn.preparation_request_id,
    'action_id', turn.action_id,
    'result_payload_id', turn.result_payload_id,
    'completion_id', turn.completion_id,
    'updated_at', turn.updated_at
  )
  from connected_chat_private.turns as turn
  where turn.owner_id = p_owner_id
    and turn.chat_id = p_chat_id
    and turn.message_id = p_message_id
    and turn.origin_session_binding_sha256 = p_origin_session_binding_sha256
    and turn.request_binding_sha256 = p_request_binding_sha256
$fn$;
comment on function public.connected_chat_read_turn_v1(uuid,uuid,uuid,text,text) is
  'ASK_CRUMP_CONNECTED_CHAT_READ_V1_OWNER_SESSION_REQUEST_BOUND_CONTENT_FREE';

revoke all on function public.connected_chat_claim_turn_v1(uuid,uuid,uuid,text,text)
  from public, anon, authenticated;
revoke all on function public.connected_chat_read_turn_v1(uuid,uuid,uuid,text,text)
  from public, anon, authenticated;
grant execute on function public.connected_chat_claim_turn_v1(uuid,uuid,uuid,text,text)
  to service_role;
grant execute on function public.connected_chat_read_turn_v1(uuid,uuid,uuid,text,text)
  to service_role;

do $postflight$
declare
  relation_oid oid := pg_catalog.to_regclass('connected_chat_private.turns');
  found_columns text[];
  found_function_hashes text[];
begin
  if relation_oid is null
     or pg_catalog.pg_get_userbyid(
       (select namespace_row.nspowner
        from pg_catalog.pg_namespace as namespace_row
        where namespace_row.nspname = 'connected_chat_private')
     ) <> 'postgres'
     or not (
       select class_row.relrowsecurity and class_row.relforcerowsecurity
       from pg_catalog.pg_class as class_row
       where class_row.oid = relation_oid
     )
     or exists (
       select 1 from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid = relation_oid
     )
     or pg_catalog.to_regprocedure(
       'public.connected_chat_claim_turn_v1(uuid,uuid,uuid,text,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_chat_read_turn_v1(uuid,uuid,uuid,text,text)'
     ) is null then
    raise exception 'connected chat turn postflight failed' using errcode = '55000';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_proc as proc_row
    where proc_row.oid in (
      'public.connected_chat_claim_turn_v1(uuid,uuid,uuid,text,text)'::pg_catalog.regprocedure,
      'public.connected_chat_read_turn_v1(uuid,uuid,uuid,text,text)'::pg_catalog.regprocedure
    )
      and (
        not proc_row.prosecdef
        or proc_row.proconfig is distinct from array['search_path=""']::text[]
        or pg_catalog.has_function_privilege('public', proc_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('anon', proc_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('authenticated', proc_row.oid, 'EXECUTE')
        or not pg_catalog.has_function_privilege('service_role', proc_row.oid, 'EXECUTE')
      )
  ) then
    raise exception 'connected chat function authority drifted' using errcode = '55000';
  end if;

  select pg_catalog.array_agg(attribute_row.attname order by attribute_row.attnum)
    into found_columns
  from pg_catalog.pg_attribute as attribute_row
  where attribute_row.attrelid = relation_oid
    and attribute_row.attnum > 0
    and not attribute_row.attisdropped;
  if found_columns is distinct from array[
    'turn_id', 'job_id', 'owner_id', 'chat_id', 'message_id',
    'origin_session_binding_sha256', 'request_binding_sha256', 'stage',
    'planning_id', 'planning_binding_sha256', 'plan_payload_id',
    'plan_payload_sha256', 'plan_reference_binding_sha256',
    'preparation_request_id', 'action_id', 'result_payload_id',
    'completion_id', 'created_at', 'updated_at'
  ]::text[]
     or (select pg_catalog.count(*) from pg_catalog.pg_constraint
         where conrelid = relation_oid) <> 22
     or (select pg_catalog.count(*) from pg_catalog.pg_index
         where indrelid = relation_oid) <> 12
     or pg_catalog.obj_description(relation_oid, 'pg_class')
        <> 'ASK_CRUMP_CONNECTED_CHAT_TURNS_V1_OPAQUE_BINDINGS_ONLY'
     or pg_catalog.col_description(relation_oid, 6)
        <> 'ASK_CRUMP_KEYED_HMAC_AUTHENTICATED_ORIGIN_SESSION'
     or pg_catalog.col_description(relation_oid, 7)
        <> 'ASK_CRUMP_KEYED_HMAC_EXACT_CHAT_BODY_ATTACHMENTS_TIMEZONE_NOT_PLAINTEXT_DIGEST'
  then
    raise exception 'connected chat relation manifest drifted' using errcode = '55000';
  end if;

  select pg_catalog.array_agg(
    proc_row.proname || '|' || pg_catalog.md5(proc_row.prosrc)
    order by proc_row.proname collate pg_catalog."C"
  ) into found_function_hashes
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname like 'connected_chat\_%' escape '\';
  if found_function_hashes is distinct from array[
    'connected_chat_claim_turn_v1|8146318bd8dc48049bfb587d97f3fbcf',
    'connected_chat_read_turn_v1|a56f614868fcf2b9501d4ec5589424da'
  ]::text[] then
    raise exception 'connected chat function source drifted' using errcode = '55000';
  end if;
end;
$postflight$;

commit;
