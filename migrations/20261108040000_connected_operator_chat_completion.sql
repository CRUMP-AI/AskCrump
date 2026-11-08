-- Atomically finish one connected-app chat turn with its durable chat reply.
-- The receipt table contains identities and keyed commitments only.

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);

do $preflight$
declare
  target_schema oid := pg_catalog.to_regnamespace('connected_chat_completion_private');
  found_columns text[];
  found_constraints text[];
  found_indexes text[];
  found_classes text[];
  found_types text[];
  found_function_hashes text[];
  found_function_manifest text[];
begin
  if pg_catalog.to_regclass('public.users') is null
     or pg_catalog.to_regclass('public.sessions') is null
     or pg_catalog.to_regclass('public.chat_jobs') is null
     or pg_catalog.to_regclass('public.user_chats') is null
     or pg_catalog.to_regclass('connected_chat_private.turns') is null
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.persist_chat_reply(uuid,uuid,text,jsonb,jsonb)'
     ) is null then
    raise exception 'connected chat completion requires the reviewed chat substrate'
      using errcode = '55000';
  end if;

  if not exists (
    select 1
    from pg_catalog.pg_proc as proc_row
    where proc_row.oid =
      'public.persist_chat_reply(uuid,uuid,text,jsonb,jsonb)'::pg_catalog.regprocedure
      and proc_row.prosecdef
      and proc_row.proconfig = array['search_path=public']::text[]
      and pg_catalog.pg_get_userbyid(proc_row.proowner) = 'postgres'
      and pg_catalog.md5(proc_row.prosrc) = 'e7ce957dd69f6fa93a02039348bc4e91'
      and not pg_catalog.has_function_privilege('public', proc_row.oid, 'EXECUTE')
      and not pg_catalog.has_function_privilege('anon', proc_row.oid, 'EXECUTE')
      and not pg_catalog.has_function_privilege(
        'authenticated', proc_row.oid, 'EXECUTE'
      )
      and pg_catalog.has_function_privilege(
        'service_role', proc_row.oid, 'EXECUTE'
      )
  ) then
    raise exception 'connected chat reply writer drifted' using errcode = '55000';
  end if;

  if target_schema is null then
    if pg_catalog.to_regclass('connected_chat_completion_private.completions')
         is not null
       or pg_catalog.to_regprocedure(
         'public.connected_operator_complete_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,jsonb,jsonb)'
       ) is not null
       or pg_catalog.to_regprocedure(
         'public.connected_operator_read_chat_completion_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text)'
       ) is not null then
      raise exception 'partial connected chat completion target; refusing repair'
        using errcode = '55000';
    end if;
    return;
  end if;

  if pg_catalog.to_regclass('connected_chat_completion_private.completions')
       is null
     or pg_catalog.to_regprocedure(
       'public.connected_operator_complete_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,jsonb,jsonb)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_operator_read_chat_completion_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text)'
     ) is null then
    raise exception 'partial connected chat completion target; refusing repair'
      using errcode = '55000';
  end if;

  select pg_catalog.array_agg(
    attribute_row.attname || '|' ||
    pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod) || '|' ||
    attribute_row.attnotnull::text || '|' ||
    coalesce(
      pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid), ''
    ) order by attribute_row.attnum
  ) into found_columns
  from pg_catalog.pg_attribute as attribute_row
  left join pg_catalog.pg_attrdef as default_row
    on default_row.adrelid = attribute_row.attrelid
   and default_row.adnum = attribute_row.attnum
  where attribute_row.attrelid =
      'connected_chat_completion_private.completions'::pg_catalog.regclass
    and attribute_row.attnum > 0
    and not attribute_row.attisdropped;

  select pg_catalog.array_agg(
    proc_row.proname || '|' || pg_catalog.md5(proc_row.prosrc)
    order by proc_row.proname collate pg_catalog."C"
  ) into found_function_hashes
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname in (
      'connected_operator_complete_chat_v1',
      'connected_operator_read_chat_completion_v1'
    );

  select pg_catalog.array_agg(
    constraint_row.contype::text || '|' ||
    pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
    order by constraint_row.contype::text collate pg_catalog."C",
      pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
        collate pg_catalog."C"
  ) into found_constraints
  from pg_catalog.pg_constraint as constraint_row
  where constraint_row.conrelid =
    'connected_chat_completion_private.completions'::pg_catalog.regclass;

  select pg_catalog.array_agg(
    pg_catalog.pg_get_indexdef(index_row.indexrelid)
    order by pg_catalog.pg_get_indexdef(index_row.indexrelid)
      collate pg_catalog."C"
  ) into found_indexes
  from pg_catalog.pg_index as index_row
  where index_row.indrelid =
    'connected_chat_completion_private.completions'::pg_catalog.regclass;

  select pg_catalog.array_agg(
    class_row.relkind::text || '|' || class_row.relname
    order by class_row.relkind::text collate pg_catalog."C",
      class_row.relname collate pg_catalog."C"
  ) into found_classes
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_chat_completion_private';

  select pg_catalog.array_agg(
    type_row.typtype::text || '|' || type_row.typname
    order by type_row.typtype::text collate pg_catalog."C",
      type_row.typname collate pg_catalog."C"
  ) into found_types
  from pg_catalog.pg_type as type_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = type_row.typnamespace
  where namespace_row.nspname = 'connected_chat_completion_private';

  select pg_catalog.array_agg(
    proc_row.proname || '|' || language_row.lanname || '|' ||
    proc_row.provolatile::text || '|' ||
    pg_catalog.pg_get_function_result(proc_row.oid) || '|' ||
    coalesce(pg_catalog.obj_description(proc_row.oid, 'pg_proc'), '') ||
    '|' || coalesce(proc_row.proacl::text, '')
    order by proc_row.proname collate pg_catalog."C"
  ) into found_function_manifest
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  join pg_catalog.pg_language as language_row
    on language_row.oid = proc_row.prolang
  where namespace_row.nspname = 'public'
    and proc_row.proname in (
      'connected_operator_complete_chat_v1',
      'connected_operator_read_chat_completion_v1'
    );

  if found_columns is distinct from array[
    'completion_id|uuid|true|',
    'owner_id|uuid|true|',
    'turn_id|uuid|true|',
    'job_id|uuid|true|',
    'chat_id|uuid|true|',
    'message_id|uuid|true|',
    'assistant_message_id|uuid|true|',
    'kind|text|true|',
    'completion_key_id|text|true|',
    'response_binding_sha256|text|true|',
    'resulting_revision|bigint|true|',
    'resulting_updated_at|timestamp with time zone|true|',
    'completed_at|timestamp with time zone|true|',
    'created_at|timestamp with time zone|true|statement_timestamp()'
  ]::text[]
     or found_function_hashes is distinct from array[
       'connected_operator_complete_chat_v1|c7598d67398c07b8c0ed053571bbc1fe',
       'connected_operator_read_chat_completion_v1|c4dacc64c97eb09bc98040ecba5e69a7'
     ]::text[]
     or found_constraints is distinct from array[
       'c|CHECK (completion_key_id ~ ''^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$''::text)',
       'c|CHECK (kind = ANY (ARRAY[''delegated''::text, ''clarification''::text, ''pending_approval''::text, ''schedule_created''::text, ''action_terminal''::text]))',
       'c|CHECK (response_binding_sha256 ~ ''^[0-9a-f]{64}$''::text)',
       'c|CHECK (resulting_revision > 0)',
       'f|FOREIGN KEY (job_id) REFERENCES chat_jobs(id) ON DELETE CASCADE',
       'f|FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE',
       'f|FOREIGN KEY (turn_id) REFERENCES connected_chat_private.turns(turn_id) ON DELETE CASCADE',
       'p|PRIMARY KEY (completion_id)',
       'u|UNIQUE (job_id)',
       'u|UNIQUE (owner_id, chat_id, message_id)',
       'u|UNIQUE (turn_id)'
     ]::text[]
     or found_indexes is distinct from array[
       'CREATE INDEX connected_chat_completions_owner_completed_idx ON connected_chat_completion_private.completions USING btree (owner_id, completed_at DESC, completion_id)',
       'CREATE UNIQUE INDEX completions_job_id_key ON connected_chat_completion_private.completions USING btree (job_id)',
       'CREATE UNIQUE INDEX completions_owner_id_chat_id_message_id_key ON connected_chat_completion_private.completions USING btree (owner_id, chat_id, message_id)',
       'CREATE UNIQUE INDEX completions_pkey ON connected_chat_completion_private.completions USING btree (completion_id)',
       'CREATE UNIQUE INDEX completions_turn_id_key ON connected_chat_completion_private.completions USING btree (turn_id)'
     ]::text[]
     or found_classes is distinct from array[
       'i|completions_job_id_key',
       'i|completions_owner_id_chat_id_message_id_key',
       'i|completions_pkey',
       'i|completions_turn_id_key',
       'i|connected_chat_completions_owner_completed_idx',
       'r|completions'
     ]::text[]
     or found_types is distinct from array[
       'b|_completions', 'c|completions'
     ]::text[]
     or found_function_manifest is distinct from array[
       'connected_operator_complete_chat_v1|plpgsql|v|jsonb|ASK_CRUMP_CONNECTED_CHAT_COMPLETION_V1_ATOMIC_REPLY_JOB_TURN_RECEIPT|{postgres=X/postgres,service_role=X/postgres}',
       'connected_operator_read_chat_completion_v1|sql|s|jsonb|ASK_CRUMP_CONNECTED_CHAT_COMPLETION_READ_V1_EXACT_LIVE_SESSION_BINDING|{postgres=X/postgres,service_role=X/postgres}'
     ]::text[]
     or (
       select pg_catalog.pg_get_userbyid(namespace_row.nspowner) <> 'postgres'
         or coalesce(namespace_row.nspacl::text, '') <>
           '{postgres=UC/postgres}'
         or pg_catalog.obj_description(namespace_row.oid, 'pg_namespace') <>
           'ASK_CRUMP_CONNECTED_CHAT_COMPLETION_V1_CONTENT_FREE'
       from pg_catalog.pg_namespace as namespace_row
       where namespace_row.nspname = 'connected_chat_completion_private'
     )
     or (
       select pg_catalog.pg_get_userbyid(class_row.relowner) <> 'postgres'
         or coalesce(class_row.relacl::text, '') <>
           '{postgres=arwdDxtm/postgres}'
         or pg_catalog.obj_description(class_row.oid, 'pg_class') <>
           'ASK_CRUMP_CONNECTED_CHAT_COMPLETIONS_V1_IDENTITIES_AND_KEYED_COMMITMENTS_ONLY'
         or pg_catalog.col_description(class_row.oid, 10) <>
           'ASK_CRUMP_KEYED_HMAC_EXACT_CHAT_COMPLETION_CONTENT_NOT_PLAINTEXT_DIGEST'
       from pg_catalog.pg_class as class_row
       where class_row.oid =
         'connected_chat_completion_private.completions'::pg_catalog.regclass
     )
     or not (
       select class_row.relrowsecurity and class_row.relforcerowsecurity
       from pg_catalog.pg_class as class_row
       where class_row.oid =
         'connected_chat_completion_private.completions'::pg_catalog.regclass
     )
     or exists (
       select 1
       from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid =
         'connected_chat_completion_private.completions'::pg_catalog.regclass
     )
     or exists (
       select 1
       from pg_catalog.pg_trigger as trigger_row
       where trigger_row.tgrelid =
         'connected_chat_completion_private.completions'::pg_catalog.regclass
         and not trigger_row.tgisinternal
     )
     or exists (
       select 1
       from pg_catalog.pg_rewrite as rewrite_row
       where rewrite_row.ev_class =
         'connected_chat_completion_private.completions'::pg_catalog.regclass
     )
     or exists (
       select 1
       from pg_catalog.pg_proc as private_proc
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid = private_proc.pronamespace
       where namespace_row.nspname = 'connected_chat_completion_private'
     )
     or exists (
       select 1
       from pg_catalog.pg_publication as publication_row
       where publication_row.puballtables
     )
     or exists (
       select 1
       from pg_catalog.pg_publication_tables as published_table
       where published_table.schemaname = 'connected_chat_completion_private'
     ) then
    raise exception 'connected chat completion target drifted; refusing repair'
      using errcode = '55000';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_proc as proc_row
    where proc_row.oid in (
      'public.connected_operator_complete_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,jsonb,jsonb)'::pg_catalog.regprocedure,
      'public.connected_operator_read_chat_completion_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text)'::pg_catalog.regprocedure
    )
      and (
        not proc_row.prosecdef
        or proc_row.proconfig is distinct from array['search_path=""']::text[]
        or pg_catalog.pg_get_userbyid(proc_row.proowner) <> 'postgres'
        or pg_catalog.has_function_privilege('public', proc_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('anon', proc_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege(
          'authenticated', proc_row.oid, 'EXECUTE'
        )
        or not pg_catalog.has_function_privilege(
          'service_role', proc_row.oid, 'EXECUTE'
        )
      )
  ) then
    raise exception 'connected chat completion authority drifted; refusing repair'
      using errcode = '55000';
  end if;
end;
$preflight$;

begin;

create schema if not exists connected_chat_completion_private authorization postgres;
comment on schema connected_chat_completion_private is
  'ASK_CRUMP_CONNECTED_CHAT_COMPLETION_V1_CONTENT_FREE';
revoke all on schema connected_chat_completion_private
  from public, anon, authenticated, service_role;

create table if not exists connected_chat_completion_private.completions (
  completion_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  turn_id uuid not null unique
    references connected_chat_private.turns(turn_id) on delete cascade,
  job_id uuid not null unique references public.chat_jobs(id) on delete cascade,
  chat_id uuid not null,
  message_id uuid not null,
  assistant_message_id uuid not null,
  kind text not null check (kind in (
    'delegated', 'clarification', 'pending_approval',
    'schedule_created', 'action_terminal'
  )),
  completion_key_id text not null
    check (completion_key_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
  response_binding_sha256 text not null
    check (response_binding_sha256 ~ '^[0-9a-f]{64}$'),
  resulting_revision bigint not null check (resulting_revision > 0),
  resulting_updated_at timestamptz not null,
  completed_at timestamptz not null,
  created_at timestamptz not null default pg_catalog.statement_timestamp(),
  unique (owner_id, chat_id, message_id)
);
comment on table connected_chat_completion_private.completions is
  'ASK_CRUMP_CONNECTED_CHAT_COMPLETIONS_V1_IDENTITIES_AND_KEYED_COMMITMENTS_ONLY';
comment on column connected_chat_completion_private.completions.response_binding_sha256 is
  'ASK_CRUMP_KEYED_HMAC_EXACT_CHAT_COMPLETION_CONTENT_NOT_PLAINTEXT_DIGEST';
create index if not exists connected_chat_completions_owner_completed_idx
  on connected_chat_completion_private.completions(
    owner_id, completed_at desc, completion_id
  );
alter table connected_chat_completion_private.completions enable row level security;
alter table connected_chat_completion_private.completions force row level security;
revoke all on table connected_chat_completion_private.completions
  from public, anon, authenticated, service_role;

create or replace function public.connected_operator_complete_chat_v1(
  p_completion_id uuid,
  p_owner_id uuid,
  p_session_id uuid,
  p_turn_id uuid,
  p_chat_id uuid,
  p_message_id uuid,
  p_assistant_message_id uuid,
  p_claim_token uuid,
  p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text,
  p_kind text,
  p_completion_key_id text,
  p_response_binding_sha256 text,
  p_title text,
  p_user_message jsonb,
  p_assistant_message jsonb,
  p_response_data jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  now_at timestamptz := pg_catalog.statement_timestamp();
  current_session public.sessions%rowtype;
  current_job public.chat_jobs%rowtype;
  current_turn connected_chat_private.turns%rowtype;
  current_completion connected_chat_completion_private.completions%rowtype;
  resulting_revision bigint;
  resulting_updated_at timestamptz;
begin
  if p_completion_id is null or p_owner_id is null or p_session_id is null
     or p_turn_id is null or p_chat_id is null or p_message_id is null
     or p_assistant_message_id is null or p_claim_token is null
     or p_origin_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_request_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_response_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_completion_key_id !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
     or p_kind not in (
       'delegated', 'clarification', 'pending_approval',
       'schedule_created', 'action_terminal'
     )
     or p_title is null or pg_catalog.btrim(p_title) = ''
     or pg_catalog.octet_length(pg_catalog.convert_to(p_title, 'UTF8')) > 512
     or pg_catalog.jsonb_typeof(p_user_message) <> 'object'
     or pg_catalog.jsonb_typeof(p_assistant_message) <> 'object'
     or pg_catalog.jsonb_typeof(p_response_data) <> 'object'
     or pg_catalog.pg_column_size(p_user_message) > 1048576
     or pg_catalog.pg_column_size(p_assistant_message) > 1048576
     or pg_catalog.pg_column_size(p_response_data) > 1048576
     or p_user_message->>'id' <> p_message_id::text
     or p_user_message->>'role' <> 'user'
     or p_assistant_message->>'id' <> p_assistant_message_id::text
     or p_assistant_message->>'role' <> 'assistant'
     or coalesce(
       p_assistant_message->>'inReplyTo', p_assistant_message->>'in_reply_to'
     ) <> p_message_id::text
     or pg_catalog.jsonb_typeof(p_response_data->'assistantMessage') <> 'object'
     or p_response_data->'assistantMessage'->>'id'
        <> p_assistant_message_id::text
     or coalesce(
       p_response_data->'assistantMessage'->>'inReplyTo',
       p_response_data->'assistantMessage'->>'in_reply_to'
     ) <> p_message_id::text then
    raise exception 'invalid connected chat completion' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_owner_id);

  select session_row.* into current_session
  from public.sessions as session_row
  where session_row.id = p_session_id
    and session_row.user_id = p_owner_id
    and session_row.revoked_at is null
    and session_row.expires_at > now_at
  for update;
  if not found then
    raise exception 'connected chat completion session is unavailable'
      using errcode = '55000';
  end if;

  select job.* into current_job
  from public.chat_jobs as job
  where job.user_id = p_owner_id and job.message_id = p_message_id
  for update;
  if not found or current_job.chat_id <> p_chat_id then
    raise exception 'connected chat completion job drifted' using errcode = '55000';
  end if;

  select turn.* into current_turn
  from connected_chat_private.turns as turn
  where turn.turn_id = p_turn_id
  for update;
  if not found
     or current_turn.job_id <> current_job.id
     or current_turn.owner_id <> p_owner_id
     or current_turn.chat_id <> p_chat_id
     or current_turn.message_id <> p_message_id
     or current_turn.origin_session_binding_sha256
        <> p_origin_session_binding_sha256
     or current_turn.request_binding_sha256 <> p_request_binding_sha256 then
    raise exception 'connected chat completion turn drifted' using errcode = '55000';
  end if;

  select completion.* into current_completion
  from connected_chat_completion_private.completions as completion
  where completion.turn_id = p_turn_id
  for update;
  if found then
    if current_completion.completion_id <> p_completion_id
       or current_completion.owner_id <> p_owner_id
       or current_completion.job_id <> current_job.id
       or current_completion.chat_id <> p_chat_id
       or current_completion.message_id <> p_message_id
       or current_completion.assistant_message_id <> p_assistant_message_id
       or current_completion.kind <> p_kind
       or current_completion.completion_key_id <> p_completion_key_id
       or current_completion.response_binding_sha256
          <> p_response_binding_sha256
       or current_job.status <> 'completed'
       or current_job.response_data is null
       or current_turn.stage <> 'terminal' then
      raise exception 'connected chat completion replay drifted'
        using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'completion_id', current_completion.completion_id,
      'kind', current_completion.kind,
      'response_binding_sha256', current_completion.response_binding_sha256,
      'resulting_revision', current_completion.resulting_revision,
      'resulting_updated_at', current_completion.resulting_updated_at,
      'completed_at', current_completion.completed_at,
      'response_data', current_job.response_data
    );
  end if;

  if exists (
    select 1
    from connected_chat_completion_private.completions as collision
    where collision.completion_id = p_completion_id
  ) then
    raise exception 'connected chat completion identity collided'
      using errcode = '55000';
  end if;

  if current_job.status <> 'processing'
     or current_job.claim_token <> p_claim_token
     or current_turn.stage in ('terminal', 'effect_unknown')
     or current_turn.completion_id is not null
     or (
       p_kind = 'delegated'
       and current_turn.stage not in ('claimed', 'planning', 'planned')
     )
     or (
       p_kind = 'clarification'
       and current_turn.stage not in ('planning', 'planned')
     )
     or (
       p_kind in ('pending_approval', 'schedule_created')
       and current_turn.stage <> 'prepared'
     )
     or (
       p_kind = 'action_terminal'
       and current_turn.stage not in ('prepared', 'executing')
     ) then
    raise exception 'connected chat completion claim or stage is unavailable'
      using errcode = '55000';
  end if;

  select reply.resulting_revision, reply.resulting_updated_at
    into strict resulting_revision, resulting_updated_at
  from public.persist_chat_reply(
    p_owner_id, p_chat_id, p_title, p_user_message, p_assistant_message
  ) as reply;
  if resulting_revision < 1 or resulting_updated_at is null then
    raise exception 'connected chat reply writer returned invalid state'
      using errcode = '55000';
  end if;

  insert into connected_chat_completion_private.completions(
    completion_id, owner_id, turn_id, job_id, chat_id, message_id,
    assistant_message_id, kind, completion_key_id,
    response_binding_sha256, resulting_revision,
    resulting_updated_at, completed_at, created_at
  ) values (
    p_completion_id, p_owner_id, p_turn_id, current_job.id,
    p_chat_id, p_message_id, p_assistant_message_id, p_kind,
    p_completion_key_id, p_response_binding_sha256, resulting_revision,
    resulting_updated_at, now_at, now_at
  ) returning * into current_completion;

  update public.chat_jobs as job
  set status = 'completed', response_data = p_response_data,
      error_code = null, claim_token = null, updated_at = now_at
  where job.id = current_job.id
    and job.status = 'processing'
    and job.claim_token = p_claim_token;
  if not found then
    raise exception 'connected chat completion lost its job fence'
      using errcode = '55000';
  end if;

  update connected_chat_private.turns as turn
  set stage = 'terminal', updated_at = now_at
  where turn.turn_id = p_turn_id
    and turn.stage = current_turn.stage;
  if not found then
    raise exception 'connected chat completion lost its turn fence'
      using errcode = '55000';
  end if;

  return pg_catalog.jsonb_build_object(
    'completion_id', current_completion.completion_id,
    'kind', current_completion.kind,
    'response_binding_sha256', current_completion.response_binding_sha256,
    'resulting_revision', current_completion.resulting_revision,
    'resulting_updated_at', current_completion.resulting_updated_at,
    'completed_at', current_completion.completed_at,
    'response_data', p_response_data
  );
end;
$fn$;
comment on function public.connected_operator_complete_chat_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,
  text,text,text,text,text,text,jsonb,jsonb,jsonb
) is 'ASK_CRUMP_CONNECTED_CHAT_COMPLETION_V1_ATOMIC_REPLY_JOB_TURN_RECEIPT';

create or replace function public.connected_operator_read_chat_completion_v1(
  p_completion_id uuid,
  p_owner_id uuid,
  p_session_id uuid,
  p_turn_id uuid,
  p_chat_id uuid,
  p_message_id uuid,
  p_origin_session_binding_sha256 text,
  p_request_binding_sha256 text,
  p_kind text,
  p_completion_key_id text,
  p_response_binding_sha256 text
)
returns jsonb
language sql
stable
security definer
set search_path = ''
as $fn$
  select pg_catalog.jsonb_build_object(
    'completion_id', completion.completion_id,
    'kind', completion.kind,
    'response_binding_sha256', completion.response_binding_sha256,
    'resulting_revision', completion.resulting_revision,
    'resulting_updated_at', completion.resulting_updated_at,
    'completed_at', completion.completed_at,
    'response_data', job.response_data
  )
  from connected_chat_completion_private.completions as completion
  join connected_chat_private.turns as turn
    on turn.turn_id = completion.turn_id
  join public.chat_jobs as job on job.id = completion.job_id
  where completion.completion_id = p_completion_id
    and completion.owner_id = p_owner_id
    and completion.turn_id = p_turn_id
    and completion.chat_id = p_chat_id
    and completion.message_id = p_message_id
    and completion.kind = p_kind
    and completion.completion_key_id = p_completion_key_id
    and completion.response_binding_sha256 = p_response_binding_sha256
    and turn.owner_id = p_owner_id
    and turn.chat_id = p_chat_id
    and turn.message_id = p_message_id
    and turn.origin_session_binding_sha256 = p_origin_session_binding_sha256
    and turn.request_binding_sha256 = p_request_binding_sha256
    and turn.stage = 'terminal'
    and job.user_id = p_owner_id
    and job.chat_id = p_chat_id
    and job.message_id = p_message_id
    and job.status = 'completed'
    and job.response_data is not null
    and exists (
      select 1
      from public.sessions as session_row
      where session_row.id = p_session_id
        and session_row.user_id = p_owner_id
        and session_row.revoked_at is null
        and session_row.expires_at > pg_catalog.statement_timestamp()
    )
$fn$;
comment on function public.connected_operator_read_chat_completion_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text
) is 'ASK_CRUMP_CONNECTED_CHAT_COMPLETION_READ_V1_EXACT_LIVE_SESSION_BINDING';

revoke all on function public.connected_operator_complete_chat_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,
  text,text,text,text,text,text,jsonb,jsonb,jsonb
) from public, anon, authenticated;
revoke all on function public.connected_operator_read_chat_completion_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text
) from public, anon, authenticated;
grant execute on function public.connected_operator_complete_chat_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,
  text,text,text,text,text,text,jsonb,jsonb,jsonb
) to service_role;
grant execute on function public.connected_operator_read_chat_completion_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text
) to service_role;

do $postflight$
declare
  relation_oid oid := pg_catalog.to_regclass(
    'connected_chat_completion_private.completions'
  );
  found_function_hashes text[];
begin
  if relation_oid is null
     or pg_catalog.obj_description(relation_oid, 'pg_class') <>
       'ASK_CRUMP_CONNECTED_CHAT_COMPLETIONS_V1_IDENTITIES_AND_KEYED_COMMITMENTS_ONLY'
     or pg_catalog.col_description(relation_oid, 10) <>
       'ASK_CRUMP_KEYED_HMAC_EXACT_CHAT_COMPLETION_CONTENT_NOT_PLAINTEXT_DIGEST'
     or not (
       select class_row.relrowsecurity and class_row.relforcerowsecurity
       from pg_catalog.pg_class as class_row
       where class_row.oid = relation_oid
     )
     or exists (
       select 1 from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid = relation_oid
     ) then
    raise exception 'connected chat completion relation postflight failed'
      using errcode = '55000';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_proc as proc_row
    where proc_row.oid in (
      'public.connected_operator_complete_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,jsonb,jsonb)'::pg_catalog.regprocedure,
      'public.connected_operator_read_chat_completion_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text)'::pg_catalog.regprocedure
    )
      and (
        not proc_row.prosecdef
        or proc_row.proconfig is distinct from array['search_path=""']::text[]
        or pg_catalog.pg_get_userbyid(proc_row.proowner) <> 'postgres'
        or pg_catalog.has_function_privilege('public', proc_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('anon', proc_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege(
          'authenticated', proc_row.oid, 'EXECUTE'
        )
        or not pg_catalog.has_function_privilege(
          'service_role', proc_row.oid, 'EXECUTE'
        )
      )
  ) then
    raise exception 'connected chat completion authority postflight failed'
      using errcode = '55000';
  end if;

  select pg_catalog.array_agg(
    proc_row.proname || '|' || pg_catalog.md5(proc_row.prosrc)
    order by proc_row.proname collate pg_catalog."C"
  ) into found_function_hashes
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = proc_row.pronamespace
  where namespace_row.nspname = 'public'
    and proc_row.proname in (
      'connected_operator_complete_chat_v1',
      'connected_operator_read_chat_completion_v1'
    );
  if found_function_hashes is distinct from array[
    'connected_operator_complete_chat_v1|c7598d67398c07b8c0ed053571bbc1fe',
    'connected_operator_read_chat_completion_v1|c4dacc64c97eb09bc98040ecba5e69a7'
  ]::text[] then
    raise exception 'connected chat completion source postflight failed'
      using errcode = '55000';
  end if;
end;
$postflight$;

commit;
