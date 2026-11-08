-- Current-main account lifecycle and guest-writer owner-lock hardening.
-- No measurement marker, fact, or aggregate is introduced by this migration.

select pg_catalog.set_config('search_path', 'pg_catalog,public', false);

-- First-apply guard. The final exact-target manifest below is patched after the
-- target bodies are compiled in a disposable PostgreSQL 17 database.
do $preflight$
declare
  observed text[];
  observed_results text[];
begin
  if not exists (
    select 1
    from pg_catalog.pg_proc as function_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = function_row.pronamespace
    where function_row.oid =
      'connected_app_private.owner_lock_v1(uuid)'::pg_catalog.regprocedure
      and namespace_row.nspname = 'connected_app_private'
      and pg_catalog.md5(function_row.prosrc) =
        'ab70e27e21f3e90e3cf6185638485d75'
      and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
      and function_row.prosecdef
      and function_row.proconfig is not distinct from
        array['search_path=""']::text[]
      and function_row.proacl::text = '{postgres=X/postgres}'
  ) then
    raise exception 'Canonical connected owner lock drifted.'
      using errcode = '55000';
  end if;
  if pg_catalog.to_regprocedure(
       'public.connected_operator_complete_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,jsonb,jsonb)'
     ) is null then
    raise exception 'Connected completion predecessor is missing.' using errcode = '55000';
  end if;
  if not exists (
    select 1
    from pg_catalog.pg_proc as function_row
    join pg_catalog.pg_language as language_row
      on language_row.oid = function_row.prolang
    where function_row.oid =
      'public.connected_operator_complete_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,jsonb,jsonb)'::pg_catalog.regprocedure
      and pg_catalog.md5(function_row.prosrc) = 'c7598d67398c07b8c0ed053571bbc1fe'
      and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
      and function_row.prosecdef
      and language_row.lanname = 'plpgsql'
      and function_row.provolatile = 'v'
      and function_row.proconfig is not distinct from
        array['search_path=""']::text[]
      and pg_catalog.pg_get_function_result(function_row.oid) = 'jsonb'
      and function_row.proacl::text =
        '{postgres=X/postgres,service_role=X/postgres}'
  ) then
    raise exception 'Connected completion predecessor drifted.' using errcode = '55000';
  end if;
  select pg_catalog.array_agg(
    function_row.proname || '(' || pg_catalog.pg_get_function_identity_arguments(function_row.oid) || ')|' ||
    pg_catalog.md5(function_row.prosrc)
    order by function_row.proname collate pg_catalog."C",
      pg_catalog.pg_get_function_identity_arguments(function_row.oid)
        collate pg_catalog."C"
  ) into observed
  from pg_catalog.pg_proc as function_row
  join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = function_row.pronamespace
  where namespace_row.nspname = 'public'
    and function_row.proname in (
      'apply_guest_chat_sync_v2', 'complete_initial_password_setup_v1',
      'consume_password_reset_v1', 'delete_user_account',
      'finalize_password_login_v1', 'persist_guest_chat_reply_v1',
      'verify_guest_and_create_session_v1', 'verify_registered_and_create_session_v1'
    );
  if observed is distinct from array[
    'apply_guest_chat_sync_v2(p_user_id uuid, p_chat_id uuid, p_title text, p_messages jsonb, p_created_at timestamp with time zone, p_updated_at timestamp with time zone, p_deleted_at timestamp with time zone, p_revision bigint)|fef0321411d301b412b3baf9f7bb0560',
    'complete_initial_password_setup_v1(p_user_id uuid, p_session_id uuid, p_session_token_hash text, p_password_hash text)|69dac6860b1eafe7f46155c9a7d0df6a',
    'consume_password_reset_v1(p_token_hash text, p_password_hash text)|1c73dab0aa780e2f67f10215c78ac705',
    'delete_user_account(p_user_id uuid)|e05eaa78260fb44d48fc30b7a3d951c8',
    'delete_user_account(p_user_id uuid, p_storage_bucket text)|fa3c7cddd1c7328e632292a6bff4df1a',
    'finalize_password_login_v1(p_user_id uuid, p_expected_password_hash text, p_upgraded_password_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|d750b8fa15a046c5fc3935ad7570d03d',
    'persist_guest_chat_reply_v1(p_user_id uuid, p_chat_id uuid, p_title text, p_user_message jsonb, p_assistant_message jsonb)|c5f410074d3d72ce3834ac4890005a32',
    'verify_guest_and_create_session_v1(p_user_id uuid, p_verification_token_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|30ec4405e4c6b018ee49dfd08c052657',
    'verify_registered_and_create_session_v1(p_user_id uuid, p_verification_token_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|74c5275a706280dd4583639d1a28c55d'
  ]::text[]
  and observed is distinct from array[
    'apply_guest_chat_sync_v2(p_user_id uuid, p_chat_id uuid, p_title text, p_messages jsonb, p_created_at timestamp with time zone, p_updated_at timestamp with time zone, p_deleted_at timestamp with time zone, p_revision bigint)|d47a6a36d9f1dc2302df928390041235',
    'complete_initial_password_setup_v1(p_user_id uuid, p_session_id uuid, p_session_token_hash text, p_password_hash text)|45a30b4b172cf850db21fd4283a42fc9',
    'consume_password_reset_v1(p_token_hash text, p_password_hash text)|7cb4d1914711769c33fd94ec24d6b0d0',
    'delete_user_account(p_user_id uuid)|e05eaa78260fb44d48fc30b7a3d951c8',
    'delete_user_account(p_user_id uuid, p_storage_bucket text)|7512a874aa85ffd7770d44a2e3b530d7',
    'finalize_password_login_v1(p_user_id uuid, p_expected_password_hash text, p_upgraded_password_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|3f4663e4db141a8513aba73f33d0abec',
    'persist_guest_chat_reply_v1(p_user_id uuid, p_chat_id uuid, p_title text, p_user_message jsonb, p_assistant_message jsonb)|59a70b8a8e24189f07c6c41c7ea44bb9',
    'verify_guest_and_create_session_v1(p_user_id uuid, p_verification_token_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|21e2ef4db85b329592dd3789fa68d04b',
    'verify_registered_and_create_session_v1(p_user_id uuid, p_verification_token_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|722dbbe9c5ad5b2f35b06141f3cfdb4b'
  ]::text[] then
    raise exception 'Account lifecycle predecessor manifest drifted.' using errcode = '55000';
  end if;
  select pg_catalog.array_agg(
    function_row.proname || '(' ||
    pg_catalog.pg_get_function_identity_arguments(function_row.oid) || ')|' ||
    pg_catalog.pg_get_function_result(function_row.oid)
    order by function_row.proname collate pg_catalog."C",
      pg_catalog.pg_get_function_identity_arguments(function_row.oid)
        collate pg_catalog."C"
  ) into observed_results
  from pg_catalog.pg_proc as function_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = function_row.pronamespace
  where namespace_row.nspname = 'public'
    and function_row.proname in (
      'apply_guest_chat_sync_v2', 'complete_initial_password_setup_v1',
      'consume_password_reset_v1', 'delete_user_account',
      'finalize_password_login_v1', 'persist_guest_chat_reply_v1',
      'verify_guest_and_create_session_v1', 'verify_registered_and_create_session_v1'
    );
  if observed_results is distinct from array[
    'apply_guest_chat_sync_v2(p_user_id uuid, p_chat_id uuid, p_title text, p_messages jsonb, p_created_at timestamp with time zone, p_updated_at timestamp with time zone, p_deleted_at timestamp with time zone, p_revision bigint)|TABLE(accepted boolean, resulting_revision bigint, outcome text, stored_chat_count integer, stored_bytes bigint, chat_bytes bigint)',
    'complete_initial_password_setup_v1(p_user_id uuid, p_session_id uuid, p_session_token_hash text, p_password_hash text)|TABLE(password_setup_applied boolean, user_data jsonb, revoked_sessions bigint)',
    'consume_password_reset_v1(p_token_hash text, p_password_hash text)|TABLE(reset_applied boolean)',
    'delete_user_account(p_user_id uuid)|void',
    'delete_user_account(p_user_id uuid, p_storage_bucket text)|void',
    'finalize_password_login_v1(p_user_id uuid, p_expected_password_hash text, p_upgraded_password_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|TABLE(login_applied boolean, user_data jsonb, session_data jsonb, pruned_sessions bigint)',
    'persist_guest_chat_reply_v1(p_user_id uuid, p_chat_id uuid, p_title text, p_user_message jsonb, p_assistant_message jsonb)|TABLE(accepted boolean, outcome text, resulting_revision bigint, resulting_updated_at timestamp with time zone, stored_chat_count integer, stored_bytes bigint, chat_bytes bigint)',
    'verify_guest_and_create_session_v1(p_user_id uuid, p_verification_token_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|TABLE(converted boolean, user_data jsonb, session_data jsonb, revoked_sessions bigint)',
    'verify_registered_and_create_session_v1(p_user_id uuid, p_verification_token_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|TABLE(verification_applied boolean, user_data jsonb, session_data jsonb, pruned_sessions bigint)'
  ]::text[] then
    raise exception 'Account lifecycle result manifest drifted.' using errcode = '55000';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_proc as function_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = function_row.pronamespace
    join pg_catalog.pg_language as language_row
      on language_row.oid = function_row.prolang
    where namespace_row.nspname = 'public'
      and function_row.proname in (
        'apply_guest_chat_sync_v2', 'complete_initial_password_setup_v1',
        'consume_password_reset_v1', 'delete_user_account',
        'finalize_password_login_v1', 'persist_guest_chat_reply_v1',
        'verify_guest_and_create_session_v1', 'verify_registered_and_create_session_v1'
      )
      and (
        pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
        or function_row.prokind <> 'f'
        or not function_row.prosecdef
        or language_row.lanname <> 'plpgsql'
        or function_row.provolatile <> 'v'
        or function_row.proconfig is distinct from array['search_path=""']::text[]
        or not pg_catalog.has_function_privilege(
          'service_role', function_row.oid, 'EXECUTE'
        )
        or pg_catalog.has_function_privilege('public', function_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('anon', function_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege(
          'authenticated', function_row.oid, 'EXECUTE'
        )
      )
  ) then
    raise exception 'Account lifecycle authority manifest drifted.' using errcode = '55000';
  end if;
end;
$preflight$;

create or replace function public.apply_guest_chat_sync_v2(
    p_user_id uuid,
    p_chat_id uuid,
    p_title text,
    p_messages jsonb,
    p_created_at timestamptz,
    p_updated_at timestamptz,
    p_deleted_at timestamptz,
    p_revision bigint
)
returns table(
    accepted boolean,
    resulting_revision bigint,
    outcome text,
    stored_chat_count integer,
    stored_bytes bigint,
    chat_bytes bigint
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_is_guest boolean;
    v_guest_mode_enabled boolean := false;
    v_existed boolean := false;
    v_before_revision bigint := 0;
    v_before_chat_bytes bigint := 0;
    v_before_count integer := 0;
    v_before_total bigint := 0;
    v_applied boolean := false;
    v_after_revision bigint := 0;
    v_after_chat_bytes bigint := 0;
    v_after_count integer := 0;
    v_after_total bigint := 0;
    v_within_caps boolean := false;
    v_safe_reduction boolean := false;
begin
    -- Acquire the shared side of the global guest-write barrier before the
    -- owner row. Disable uses the exclusive side of the same lock, so once it
    -- commits no waiting or newly-started guest sync can persist afterward.
    v_guest_mode_enabled := public.lock_guest_mode_control_v1();

    -- Canonical same-owner serialization precedes every user/chat row lock.
    perform connected_app_private.owner_lock_v1(p_user_id);

    -- Preserve the established child-before-owner row order after the owner
    -- advisory: lock an existing target chat first, but never manufacture one.
    perform 1
      from public.user_chats as target_chat
     where target_chat.user_id = p_user_id
       and target_chat.chat_id = p_chat_id
     for update;

    -- The user row remains the per-owner data serialization point. It is held
    -- through the inner apply/check after any existing child row is locked.
    select candidate.is_guest
      into v_is_guest
      from public.users as candidate
     where candidate.id = p_user_id
     for update;

    if not found then
        return query
        select false, 0::bigint, 'user_not_found'::text, 0, 0::bigint, 0::bigint;
        return;
    end if;

    if not coalesce(v_is_guest, false) then
        return query
        select false, 0::bigint, 'not_guest'::text, 0, 0::bigint, 0::bigint;
        return;
    end if;

    if v_guest_mode_enabled is not true then
        return query
        select false, 0::bigint, 'guest_mode_disabled'::text, 0, 0::bigint, 0::bigint;
        return;
    end if;

    select true,
           candidate.revision,
           pg_catalog.octet_length(candidate.messages::text)::bigint
      into v_existed, v_before_revision, v_before_chat_bytes
      from public.user_chats as candidate
     where candidate.user_id = p_user_id
       and candidate.chat_id = p_chat_id;

    v_existed := coalesce(v_existed, false);
    v_before_revision := coalesce(v_before_revision, 0);
    v_before_chat_bytes := coalesce(v_before_chat_bytes, 0);

    select count(*)::integer,
           coalesce(
               sum(pg_catalog.octet_length(candidate.messages::text)::bigint),
               0::bigint
           )
      into v_before_count, v_before_total
      from public.user_chats as candidate
     where candidate.user_id = p_user_id;

    -- A tombstone may only shrink/close a conversation already owned by the
    -- user. Never manufacture rows from arbitrary unknown deletion ids.
    if p_deleted_at is not null and not v_existed then
        return query
        select false,
               0::bigint,
               'unknown_tombstone'::text,
               v_before_count,
               v_before_total,
               0::bigint;
        return;
    end if;

    begin
        select applied.accepted, applied.resulting_revision
          into v_applied, v_after_revision
          from public.apply_chat_sync(
              p_user_id,
              p_chat_id,
              p_title,
              p_messages,
              p_created_at,
              p_updated_at,
              p_deleted_at,
              p_revision
          ) as applied;

        if not coalesce(v_applied, false) then
            return query
            select false,
                   coalesce(v_after_revision, v_before_revision),
                   'stale'::text,
                   v_before_count,
                   v_before_total,
                   v_before_chat_bytes;
            return;
        end if;

        select candidate.revision,
               pg_catalog.octet_length(candidate.messages::text)::bigint
          into v_after_revision, v_after_chat_bytes
          from public.user_chats as candidate
         where candidate.user_id = p_user_id
           and candidate.chat_id = p_chat_id;

        select count(*)::integer,
               coalesce(
                   sum(pg_catalog.octet_length(candidate.messages::text)::bigint),
                   0::bigint
               )
          into v_after_count, v_after_total
          from public.user_chats as candidate
         where candidate.user_id = p_user_id;

        -- These are product limits, not caller inputs.
        v_within_caps := v_after_count <= 50
            and v_after_chat_bytes <= 200000
            and v_after_total <= 2000000;

        -- Existing data that predates these ceilings must remain cleanable.
        -- A known tombstone or a strict byte reduction may proceed even while
        -- the account is still above a ceiling, provided it cannot increase
        -- row count, chat bytes, or the owner's total bytes.
        v_safe_reduction := v_existed
            and v_after_count <= v_before_count
            and v_after_chat_bytes <= v_before_chat_bytes
            and v_after_total <= v_before_total
            and (
                p_deleted_at is not null
                or v_after_chat_bytes < v_before_chat_bytes
                or v_after_total < v_before_total
            );

        if not v_within_caps and not v_safe_reduction then
            raise exception using
                errcode = 'GX001',
                message = 'guest sync storage quota exceeded';
        end if;
    exception
        when sqlstate 'GX001' then
            -- Entering this handler rolls back only the inner block, including
            -- apply_chat_sync. Re-read the durable pre-candidate state.
            select count(*)::integer,
                   coalesce(
                       sum(pg_catalog.octet_length(candidate.messages::text)::bigint),
                       0::bigint
                   )
              into v_after_count, v_after_total
              from public.user_chats as candidate
             where candidate.user_id = p_user_id;

            select candidate.revision,
                   pg_catalog.octet_length(candidate.messages::text)::bigint
              into v_after_revision, v_after_chat_bytes
              from public.user_chats as candidate
             where candidate.user_id = p_user_id
               and candidate.chat_id = p_chat_id;

            return query
            select false,
                   coalesce(v_after_revision, v_before_revision),
                   'quota_exceeded'::text,
                   v_after_count,
                   v_after_total,
                   coalesce(v_after_chat_bytes, 0::bigint);
            return;
    end;

    return query
    select true,
           v_after_revision,
           'accepted'::text,
           v_after_count,
           v_after_total,
           v_after_chat_bytes;
end;
$$;

comment on function public.apply_guest_chat_sync_v2(
    uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint
) is
'Atomically applies one guest chat sync and enforces fixed post-merge UTF-8 storage caps.';

-- SECURITY DEFINER functions default to PUBLIC execution. This RPC is a
-- backend-only capability and must never be reachable through anon or an end
-- user's authenticated PostgREST session.
revoke all on function public.apply_guest_chat_sync_v2(
    uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint
) from public, anon, authenticated, service_role;
grant execute on function public.apply_guest_chat_sync_v2(
    uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint
) to service_role;

-- Normal /api/chat replies must cross the same guest storage boundary as a
-- later browser sync. The legacy persistence RPC predates guest mode and does
-- not lock the owner or measure the post-merge row, so wrap it in a serialized
-- inner subtransaction and roll back only the candidate reply when it would
-- exceed a database-owned cap.
create or replace function public.persist_guest_chat_reply_v1(
    p_user_id uuid,
    p_chat_id uuid,
    p_title text,
    p_user_message jsonb,
    p_assistant_message jsonb
)
returns table(
    accepted boolean,
    outcome text,
    resulting_revision bigint,
    resulting_updated_at timestamptz,
    stored_chat_count integer,
    stored_bytes bigint,
    chat_bytes bigint
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_is_guest boolean;
    v_guest_mode_enabled boolean := false;
    v_before_count integer := 0;
    v_before_total bigint := 0;
    v_before_chat_bytes bigint := 0;
    v_after_count integer := 0;
    v_after_total bigint := 0;
    v_after_chat_bytes bigint := 0;
    v_revision bigint;
    v_updated_at timestamptz;
begin
    -- Keep the same global control -> owner lock order as reservation and
    -- browser sync. The shared control lock remains held through persistence.
    v_guest_mode_enabled := public.lock_guest_mode_control_v1();

    -- Canonical same-owner serialization precedes every user/chat row lock.
    perform connected_app_private.owner_lock_v1(p_user_id);

    -- Match account deletion's child-before-owner row order after the shared
    -- advisory, while allowing a new chat to remain absent until persistence.
    perform 1
      from public.user_chats as target_chat
     where target_chat.user_id = p_user_id
       and target_chat.chat_id = p_chat_id
     for update;

    select candidate.is_guest
      into v_is_guest
      from public.users as candidate
     where candidate.id = p_user_id
     for update;

    if not found then
        return query select false, 'user_not_found'::text, 0::bigint, null::timestamptz, 0, 0::bigint, 0::bigint;
        return;
    end if;
    if not coalesce(v_is_guest, false) then
        return query select false, 'not_guest'::text, 0::bigint, null::timestamptz, 0, 0::bigint, 0::bigint;
        return;
    end if;
    if v_guest_mode_enabled is not true then
        return query select false, 'guest_mode_disabled'::text, 0::bigint, null::timestamptz, 0, 0::bigint, 0::bigint;
        return;
    end if;

    select count(*)::integer,
           coalesce(sum(pg_catalog.octet_length(candidate.messages::text)::bigint), 0::bigint)
      into v_before_count, v_before_total
      from public.user_chats as candidate
     where candidate.user_id = p_user_id;

    select coalesce(pg_catalog.octet_length(candidate.messages::text)::bigint, 0::bigint)
      into v_before_chat_bytes
      from public.user_chats as candidate
     where candidate.user_id = p_user_id
       and candidate.chat_id = p_chat_id;
    v_before_chat_bytes := coalesce(v_before_chat_bytes, 0::bigint);

    begin
        select persisted.resulting_revision, persisted.resulting_updated_at
          into v_revision, v_updated_at
          from public.persist_chat_reply(
              p_user_id,
              p_chat_id,
              p_title,
              p_user_message,
              p_assistant_message
          ) as persisted;

        select count(*)::integer,
               coalesce(sum(pg_catalog.octet_length(candidate.messages::text)::bigint), 0::bigint)
          into v_after_count, v_after_total
          from public.user_chats as candidate
         where candidate.user_id = p_user_id;

        select coalesce(pg_catalog.octet_length(candidate.messages::text)::bigint, 0::bigint)
          into v_after_chat_bytes
          from public.user_chats as candidate
         where candidate.user_id = p_user_id
           and candidate.chat_id = p_chat_id;
        v_after_chat_bytes := coalesce(v_after_chat_bytes, 0::bigint);

        if not (
            v_after_count <= 50
            and v_after_chat_bytes <= 200000
            and v_after_total <= 2000000
        ) and not (
            v_after_count <= v_before_count
            and v_after_chat_bytes <= v_before_chat_bytes
            and v_after_total <= v_before_total
        ) then
            raise exception using
                errcode = 'GX001',
                message = 'guest reply storage quota exceeded';
        end if;
    exception
        when sqlstate 'GX001' then
            return query select
                false,
                'quota_exceeded'::text,
                0::bigint,
                null::timestamptz,
                v_before_count,
                v_before_total,
                v_before_chat_bytes;
            return;
    end;

    return query select
        true,
        'accepted'::text,
        v_revision,
        v_updated_at,
        v_after_count,
        v_after_total,
        v_after_chat_bytes;
end;
$$;

comment on function public.persist_guest_chat_reply_v1(uuid, uuid, text, jsonb, jsonb) is
'Atomically persists one guest chat reply while enforcing fixed post-merge UTF-8 storage caps.';

revoke all on function public.persist_guest_chat_reply_v1(uuid, uuid, text, jsonb, jsonb)
from public, anon, authenticated, service_role;
grant execute on function public.persist_guest_chat_reply_v1(uuid, uuid, text, jsonb, jsonb)
to service_role;


-- Serialize every same-account authentication and deletion transition on one
-- transaction-scoped owner lock before any row lock is acquired.  This keeps
-- account deletion's child-first row order while removing the users/sessions
-- lock-order cycle with verification, login, password setup, and reset.

do $migration$
begin
  if pg_catalog.to_regprocedure(
    'public.consume_password_reset_v1(text,text)'
  ) is null then
    raise exception 'Required consume_password_reset_v1 contract is missing.';
  end if;
  if pg_catalog.to_regprocedure(
    'public.finalize_password_login_v1(uuid,text,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)'
  ) is null then
    raise exception 'Required finalize_password_login_v1 contract is missing.';
  end if;
  if pg_catalog.to_regprocedure(
    'public.verify_registered_and_create_session_v1(uuid,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)'
  ) is null then
    raise exception 'Required registered verification contract is missing.';
  end if;
  if pg_catalog.to_regprocedure(
    'public.verify_guest_and_create_session_v1(uuid,text,uuid,text,timestamptz,text,text,text,jsonb,text,text)'
  ) is null then
    raise exception 'Required guest verification contract is missing.';
  end if;
  if pg_catalog.to_regprocedure(
    'public.complete_initial_password_setup_v1(uuid,uuid,text,text)'
  ) is null then
    raise exception 'Required initial-password contract is missing.';
  end if;
  if pg_catalog.to_regprocedure(
    'public.delete_user_account(uuid,text)'
  ) is null
     or pg_catalog.to_regprocedure(
       'public.delete_user_account(uuid)'
     ) is null then
    raise exception 'Required account-deletion contracts are missing.';
  end if;
  if pg_catalog.to_regclass('public.users') is null
     or pg_catalog.to_regclass('public.sessions') is null
     or pg_catalog.to_regclass(
       'public.account_storage_deletion_jobs'
     ) is null then
    raise exception 'Required account lifecycle tables are missing.';
  end if;
end;
$migration$;

create or replace function public.consume_password_reset_v1(
  p_token_hash text,
  p_password_hash text
)
returns table(reset_applied boolean)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_candidate_user_id uuid;
  v_user_id uuid;
  v_reset_expires timestamptz;
  v_locked_reset boolean := false;
  v_now timestamptz;
begin
  if p_token_hash is null
     or p_token_hash !~ '^[0-9a-f]{64}$'
     or p_password_hash is null
     or pg_catalog.length(p_password_hash) < 20
     or pg_catalog.length(p_password_hash) > 1024 then
    raise exception 'Invalid password-reset input.' using errcode = '22023';
  end if;

  -- Resolve only a candidate UUID without taking a row lock.  The token and
  -- account state are re-read under the owner advisory and row lock below.
  select account.id
    into v_candidate_user_id
    from public.users as account
   where account.password_reset_token_hash = p_token_hash
   order by account.id
   limit 1;

  if not found then
    return query select false;
    return;
  end if;

  perform connected_app_private.owner_lock_v1(v_candidate_user_id);

  select account.id, account.password_reset_expires
    into v_user_id, v_reset_expires
    from public.users as account
   where account.id = v_candidate_user_id
     and account.password_reset_token_hash = p_token_hash
   for update;
  v_locked_reset := found;

  v_now := pg_catalog.clock_timestamp();
  if not v_locked_reset
     or v_reset_expires is null
     or v_reset_expires <= v_now then
    return query select false;
    return;
  end if;

  update public.users as account
     set password_hash = p_password_hash,
         password_setup_required = false,
         password_inbox_bound_at = v_now,
         is_verified = true,
         is_guest = false,
         verification_token_hash = null,
         verification_token_expires = null,
         password_reset_token_hash = null,
         password_reset_expires = null,
         updated_at = v_now
   where account.id = v_user_id
     and account.password_reset_token_hash = p_token_hash;

  if not found then
    raise exception 'Password-reset state changed while locked.'
      using errcode = '40001';
  end if;

  update public.sessions as session
     set revoked_at = v_now
   where session.user_id = v_user_id
     and session.revoked_at is null;

  return query select true;
end;
$function$;

create or replace function public.verify_registered_and_create_session_v1(
  p_user_id uuid,
  p_verification_token_hash text,
  p_session_id uuid,
  p_session_token_hash text,
  p_session_expires_at timestamptz,
  p_device_id text,
  p_device_name text,
  p_platform text,
  p_device_info jsonb,
  p_ip_address text,
  p_user_agent text
)
returns table(
  verification_applied boolean,
  user_data jsonb,
  session_data jsonb,
  pruned_sessions bigint
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_session public.sessions%rowtype;
  v_now timestamptz;
  v_revoked_sessions bigint := 0;
begin
  if p_user_id is null
     or p_verification_token_hash is null
     or p_verification_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_id is null
     or p_session_token_hash is null
     or p_session_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_expires_at is null then
    raise exception 'Invalid registered-verification input.' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_user_id);

  select account.* into v_user
    from public.users as account
   where account.id = p_user_id
   for update;

  v_now := pg_catalog.clock_timestamp();
  if not found
     or v_user.deleted_at is not null
     or v_user.is_guest is true
     or v_user.is_verified is not false
     or v_user.verification_token_hash is distinct from p_verification_token_hash
     or v_user.verification_token_expires is null
     or v_user.verification_token_expires <= v_now
     or p_session_expires_at <= v_now then
    return query select false, null::jsonb, null::jsonb, 0::bigint;
    return;
  end if;

  update public.users as account
     set is_verified = true,
         password_hash = '!pending-inbox-password-setup-v1!',
         password_setup_required = true,
         password_inbox_bound_at = null,
         verification_token_expires = v_now + interval '15 minutes',
         updated_at = v_now
   where account.id = p_user_id
     and account.is_verified is false
     and account.is_guest is false
     and account.verification_token_hash = p_verification_token_hash
   returning account.* into v_user;

  if not found then
    raise exception 'Registered verification state changed while locked.'
      using errcode = '40001';
  end if;

  update public.sessions as session
     set revoked_at = v_now
   where session.user_id = p_user_id
     and session.revoked_at is null;
  get diagnostics v_revoked_sessions = row_count;

  insert into public.sessions as persisted (
    id, user_id, token_hash, device_id, device_name, platform, device_info,
    ip_address, user_agent, created_at, last_activity, expires_at, revoked_at
  ) values (
    p_session_id, p_user_id, p_session_token_hash, p_device_id, p_device_name,
    p_platform, coalesce(p_device_info, '{}'::jsonb)
      || pg_catalog.jsonb_build_object(
           'passwordSetupProof', 'inbox-verification-v1'
         ),
    p_ip_address, p_user_agent,
    v_now, v_now, p_session_expires_at, null
  )
  on conflict (device_id) do update
     set user_id = excluded.user_id,
         token_hash = excluded.token_hash,
         device_name = excluded.device_name,
         platform = excluded.platform,
         device_info = excluded.device_info,
         ip_address = excluded.ip_address,
         user_agent = excluded.user_agent,
         created_at = excluded.created_at,
         last_activity = excluded.last_activity,
         expires_at = excluded.expires_at,
         revoked_at = null
  returning persisted.* into v_session;

  return query select true, pg_catalog.to_jsonb(v_user),
    pg_catalog.to_jsonb(v_session), v_revoked_sessions;
end;
$function$;

create or replace function public.verify_guest_and_create_session_v1(
  p_user_id uuid,
  p_verification_token_hash text,
  p_session_id uuid,
  p_session_token_hash text,
  p_session_expires_at timestamptz,
  p_device_id text,
  p_device_name text,
  p_platform text,
  p_device_info jsonb,
  p_ip_address text,
  p_user_agent text
)
returns table(
  converted boolean,
  user_data jsonb,
  session_data jsonb,
  revoked_sessions bigint
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_session public.sessions%rowtype;
  v_now timestamptz := pg_catalog.clock_timestamp();
  v_revoked_sessions bigint := 0;
begin
  if p_user_id is null
     or p_verification_token_hash is null
     or p_verification_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_id is null
     or p_session_token_hash is null
     or p_session_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_expires_at is null
     or p_session_expires_at <= v_now then
    raise exception 'Guest verification session values are invalid.'
      using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_user_id);

  select account.* into v_user
    from public.users as account
   where account.id = p_user_id
   for update;

  if not found
     or v_user.deleted_at is not null
     or v_user.is_verified is true
     or v_user.is_guest is not true
     or v_user.verification_token_hash is distinct from p_verification_token_hash
     or v_user.verification_token_expires is null
     or v_user.verification_token_expires <= v_now then
    return;
  end if;

  update public.users as account
     set is_verified = true,
         is_guest = false,
         password_hash = '!pending-inbox-password-setup-v1!',
         password_setup_required = true,
         password_inbox_bound_at = null,
         verification_token_expires = v_now + interval '15 minutes',
         updated_at = v_now
   where account.id = p_user_id
   returning account.* into v_user;

  update public.sessions as session
     set revoked_at = v_now,
         device_info = coalesce(session.device_info, '{}'::jsonb)
           || pg_catalog.jsonb_build_object('guestVerificationRevokedAt', v_now)
   where session.user_id = p_user_id
     and session.revoked_at is null;
  get diagnostics v_revoked_sessions = row_count;

  insert into public.sessions as persisted (
    id, user_id, token_hash, device_id, device_name, platform, device_info,
    ip_address, user_agent, created_at, last_activity, expires_at, revoked_at
  ) values (
    p_session_id, p_user_id, p_session_token_hash, p_device_id, p_device_name,
    p_platform, coalesce(p_device_info, '{}'::jsonb)
      || pg_catalog.jsonb_build_object(
           'passwordSetupProof', 'inbox-verification-v1'
         ),
    p_ip_address, p_user_agent,
    v_now, v_now, p_session_expires_at, null
  )
  on conflict (device_id) do update
     set user_id = excluded.user_id,
         token_hash = excluded.token_hash,
         device_name = excluded.device_name,
         platform = excluded.platform,
         device_info = excluded.device_info,
         ip_address = excluded.ip_address,
         user_agent = excluded.user_agent,
         created_at = excluded.created_at,
         last_activity = excluded.last_activity,
         expires_at = excluded.expires_at,
         revoked_at = null
  returning persisted.* into v_session;

  return query select true, pg_catalog.to_jsonb(v_user),
    pg_catalog.to_jsonb(v_session), v_revoked_sessions;
end;
$function$;

create or replace function public.finalize_password_login_v1(
  p_user_id uuid,
  p_expected_password_hash text,
  p_upgraded_password_hash text,
  p_session_id uuid,
  p_session_token_hash text,
  p_session_expires_at timestamptz,
  p_device_id text,
  p_device_name text,
  p_platform text,
  p_device_info jsonb,
  p_ip_address text,
  p_user_agent text
)
returns table(
  login_applied boolean,
  user_data jsonb,
  session_data jsonb,
  pruned_sessions bigint
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_session public.sessions%rowtype;
  v_now timestamptz;
  v_pruned_sessions bigint := 0;
begin
  if p_user_id is null
     or p_expected_password_hash is null
     or pg_catalog.length(p_expected_password_hash) < 20
     or pg_catalog.length(p_expected_password_hash) > 1024
     or (
       p_upgraded_password_hash is not null
       and (
         pg_catalog.length(p_upgraded_password_hash) < 20
         or pg_catalog.length(p_upgraded_password_hash) > 1024
       )
     )
     or p_session_id is null
     or p_session_token_hash is null
     or p_session_token_hash !~ '^[0-9a-f]{64}$'
     or p_session_expires_at is null then
    raise exception 'Invalid password-login input.' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_user_id);

  select account.*
    into v_user
    from public.users as account
   where account.id = p_user_id
   for update;

  v_now := pg_catalog.clock_timestamp();
  if not found
     or v_user.deleted_at is not null
     or v_user.is_verified is not true
     or v_user.is_guest is true
     or v_user.password_setup_required is not false
     or v_user.password_inbox_bound_at is null
     or v_user.password_hash is distinct from p_expected_password_hash
     or p_session_expires_at <= v_now then
    return query select false, null::jsonb, null::jsonb, 0::bigint;
    return;
  end if;

  update public.users as account
     set password_hash = coalesce(p_upgraded_password_hash, account.password_hash),
         last_login = v_now,
         updated_at = v_now
   where account.id = p_user_id
     and account.password_setup_required is false
     and account.password_inbox_bound_at is not null
     and account.password_hash is not distinct from p_expected_password_hash
   returning account.* into v_user;

  if not found then
    raise exception 'Password-login state changed while locked.'
      using errcode = '40001';
  end if;

  insert into public.sessions as persisted (
    id, user_id, token_hash, device_id, device_name, platform, device_info,
    ip_address, user_agent, created_at, last_activity, expires_at, revoked_at
  ) values (
    p_session_id, p_user_id, p_session_token_hash, p_device_id, p_device_name,
    p_platform, coalesce(p_device_info, '{}'::jsonb), p_ip_address, p_user_agent,
    v_now, v_now, p_session_expires_at, null
  )
  on conflict (device_id) do update
     set user_id = excluded.user_id,
         token_hash = excluded.token_hash,
         device_name = excluded.device_name,
         platform = excluded.platform,
         device_info = excluded.device_info,
         ip_address = excluded.ip_address,
         user_agent = excluded.user_agent,
         created_at = excluded.created_at,
         last_activity = excluded.last_activity,
         expires_at = excluded.expires_at,
         revoked_at = null
  returning persisted.* into v_session;

  update public.sessions as session
     set revoked_at = v_now
   where session.id in (
     select active_session.id
       from public.sessions as active_session
      where active_session.user_id = p_user_id
        and active_session.revoked_at is null
        and active_session.id <> v_session.id
      order by active_session.created_at desc, active_session.id desc
      offset 19
   );
  get diagnostics v_pruned_sessions = row_count;

  return query select true, pg_catalog.to_jsonb(v_user),
    pg_catalog.to_jsonb(v_session), v_pruned_sessions;
end;
$function$;

create or replace function public.complete_initial_password_setup_v1(
  p_user_id uuid,
  p_session_id uuid,
  p_session_token_hash text,
  p_password_hash text
)
returns table(
  password_setup_applied boolean,
  user_data jsonb,
  revoked_sessions bigint
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_user public.users%rowtype;
  v_session public.sessions%rowtype;
  v_now timestamptz;
  v_revoked_sessions bigint := 0;
begin
  if p_user_id is null
     or p_session_id is null
     or p_session_token_hash is null
     or p_session_token_hash !~ '^[0-9a-f]{64}$'
     or p_password_hash is null
     or pg_catalog.length(p_password_hash) < 20
     or pg_catalog.length(p_password_hash) > 1024 then
    raise exception 'Invalid initial-password input.' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_user_id);

  select account.* into v_user
    from public.users as account
   where account.id = p_user_id
   for update;

  v_now := pg_catalog.clock_timestamp();
  if not found
     or v_user.deleted_at is not null
     or v_user.is_verified is not true
     or v_user.is_guest is true
     or v_user.password_setup_required is not true then
    return query select false, null::jsonb, 0::bigint;
    return;
  end if;

  select session.* into v_session
    from public.sessions as session
   where session.id = p_session_id
     and session.user_id = p_user_id
     and session.token_hash = p_session_token_hash
     and session.revoked_at is null
     and session.expires_at > v_now
     and session.device_info ->> 'passwordSetupProof'
       = 'inbox-verification-v1'
   for update;

  if not found then
    return query select false, null::jsonb, 0::bigint;
    return;
  end if;

  update public.users as account
     set password_hash = p_password_hash,
         password_setup_required = false,
         password_inbox_bound_at = v_now,
         password_reset_token_hash = null,
         password_reset_expires = null,
         updated_at = v_now
   where account.id = p_user_id
     and account.password_setup_required is true
   returning account.* into v_user;

  if not found then
    raise exception 'Initial-password state changed while locked.'
      using errcode = '40001';
  end if;

  update public.sessions as session
     set device_info = coalesce(session.device_info, '{}'::jsonb)
       - 'passwordSetupProof'
   where session.id = p_session_id
     and session.user_id = p_user_id
     and session.token_hash = p_session_token_hash;

  update public.sessions as session
     set revoked_at = v_now
   where session.user_id = p_user_id
     and session.id <> p_session_id
     and session.revoked_at is null;
  get diagnostics v_revoked_sessions = row_count;

  return query select true, pg_catalog.to_jsonb(v_user), v_revoked_sessions;
end;
$function$;

create or replace function public.delete_user_account(
  p_user_id uuid,
  p_storage_bucket text
)
returns void
language plpgsql
security definer
set search_path = ''
as $function$
begin
  if p_user_id is null then
    raise exception 'user id is required' using errcode = '22023';
  end if;
  if p_storage_bucket is null
     or p_storage_bucket !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$' then
    raise exception 'invalid storage bucket' using errcode = '22023';
  end if;

  perform connected_app_private.owner_lock_v1(p_user_id);

  insert into public.account_storage_deletion_jobs as job (
    user_id,
    bucket,
    owner_prefix,
    status,
    attempts,
    next_attempt_at,
    final_sweep_after,
    empty_observed_at,
    lease_token,
    lease_expires_at,
    last_error,
    updated_at
  ) values (
    p_user_id,
    p_storage_bucket,
    p_user_id::text || '/',
    'pending',
    0,
    pg_catalog.clock_timestamp(),
    pg_catalog.clock_timestamp() + interval '27 hours',
    null,
    null,
    null,
    null,
    pg_catalog.clock_timestamp()
  )
  on conflict (user_id) do update
  set status = 'pending',
      next_attempt_at = least(job.next_attempt_at, pg_catalog.clock_timestamp()),
      final_sweep_after = greatest(
        job.final_sweep_after,
        pg_catalog.clock_timestamp() + interval '27 hours'
      ),
      empty_observed_at = null,
      lease_token = null,
      lease_expires_at = null,
      last_error = null,
      updated_at = pg_catalog.clock_timestamp();

  if pg_catalog.to_regclass('public.crump_chats') is not null then
    execute 'delete from public.crump_chats where user_id = $1' using p_user_id;
  end if;
  if pg_catalog.to_regclass('public.devices') is not null then
    execute 'delete from public.devices where user_id = $1' using p_user_id;
  end if;
  delete from public.usage_events where user_id = p_user_id;
  delete from public.user_chats where user_id = p_user_id;
  delete from public.user_settings where user_id = p_user_id;
  delete from public.sessions where user_id = p_user_id;
  delete from public.users where id = p_user_id;
end;
$function$;

create or replace function public.delete_user_account(p_user_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $function$
begin
  perform public.delete_user_account(p_user_id, 'crump-files');
end;
$function$;

alter function public.consume_password_reset_v1(text, text)
  owner to postgres;
alter function public.finalize_password_login_v1(
  uuid, text, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) owner to postgres;
alter function public.verify_registered_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) owner to postgres;
alter function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) owner to postgres;
alter function public.complete_initial_password_setup_v1(
  uuid, uuid, text, text
) owner to postgres;
alter function public.delete_user_account(uuid, text) owner to postgres;
alter function public.delete_user_account(uuid) owner to postgres;

revoke all on function public.consume_password_reset_v1(text, text)
  from public, anon, authenticated, service_role;
grant execute on function public.consume_password_reset_v1(text, text)
  to service_role;

revoke all on function public.finalize_password_login_v1(
  uuid, text, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.finalize_password_login_v1(
  uuid, text, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) to service_role;

revoke all on function public.verify_registered_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.verify_registered_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) to service_role;

revoke all on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) to service_role;

revoke all on function public.complete_initial_password_setup_v1(
  uuid, uuid, text, text
) from public, anon, authenticated, service_role;
grant execute on function public.complete_initial_password_setup_v1(
  uuid, uuid, text, text
) to service_role;

revoke all on function public.delete_user_account(uuid, text)
  from public, anon, authenticated, service_role;
grant execute on function public.delete_user_account(uuid, text)
  to service_role;

revoke all on function public.delete_user_account(uuid)
  from public, anon, authenticated, service_role;
grant execute on function public.delete_user_account(uuid)
  to service_role;

comment on function public.consume_password_reset_v1(text, text) is
  'Consumes one password-reset token under the canonical account owner lock, revokes active sessions, and returns only whether the reset applied.';
comment on function public.finalize_password_login_v1(
  uuid, text, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) is
  'Finalizes password login and session issuance under the canonical account owner lock.';
comment on function public.verify_registered_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) is
  'Atomically verifies a registered account, revokes old sessions, and issues one password-setup session under the canonical owner lock.';
comment on function public.verify_guest_and_create_session_v1(
  uuid, text, uuid, text, timestamptz, text, text, text, jsonb, text, text
) is
  'Atomically converts a verified guest, revokes old sessions, and issues one password-setup session under the canonical owner lock.';
comment on function public.complete_initial_password_setup_v1(
  uuid, uuid, text, text
) is
  'Establishes the first usable password through the exact inbox-verification session under the canonical account owner lock.';
comment on function public.delete_user_account(uuid, text) is
  'Records durable Storage cleanup and deletes account-owned rows child-first under the canonical account owner lock.';
comment on function public.delete_user_account(uuid) is
  'Deletes one account through the canonical private Storage bucket overload.';

do $postflight$
declare
  observed text[];
  observed_results text[];
begin
  if not exists (
    select 1
    from pg_catalog.pg_proc as function_row
    where function_row.oid =
      'connected_app_private.owner_lock_v1(uuid)'::pg_catalog.regprocedure
      and pg_catalog.md5(function_row.prosrc) =
        'ab70e27e21f3e90e3cf6185638485d75'
      and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
      and function_row.prosecdef
      and function_row.proconfig is not distinct from
        array['search_path=""']::text[]
      and function_row.proacl::text = '{postgres=X/postgres}'
  ) then
    raise exception 'Canonical connected owner lock changed.'
      using errcode = '55000';
  end if;
  select pg_catalog.array_agg(
    function_row.proname || '(' ||
    pg_catalog.pg_get_function_identity_arguments(function_row.oid) || ')|' ||
    pg_catalog.md5(function_row.prosrc)
    order by function_row.proname collate pg_catalog."C",
      pg_catalog.pg_get_function_identity_arguments(function_row.oid)
        collate pg_catalog."C"
  ) into observed
  from pg_catalog.pg_proc as function_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = function_row.pronamespace
  where namespace_row.nspname = 'public'
    and function_row.proname in (
      'apply_guest_chat_sync_v2', 'complete_initial_password_setup_v1',
      'consume_password_reset_v1', 'delete_user_account',
      'finalize_password_login_v1', 'persist_guest_chat_reply_v1',
      'verify_guest_and_create_session_v1', 'verify_registered_and_create_session_v1'
    );
  if observed is distinct from array[
    'apply_guest_chat_sync_v2(p_user_id uuid, p_chat_id uuid, p_title text, p_messages jsonb, p_created_at timestamp with time zone, p_updated_at timestamp with time zone, p_deleted_at timestamp with time zone, p_revision bigint)|d47a6a36d9f1dc2302df928390041235',
    'complete_initial_password_setup_v1(p_user_id uuid, p_session_id uuid, p_session_token_hash text, p_password_hash text)|45a30b4b172cf850db21fd4283a42fc9',
    'consume_password_reset_v1(p_token_hash text, p_password_hash text)|7cb4d1914711769c33fd94ec24d6b0d0',
    'delete_user_account(p_user_id uuid)|e05eaa78260fb44d48fc30b7a3d951c8',
    'delete_user_account(p_user_id uuid, p_storage_bucket text)|7512a874aa85ffd7770d44a2e3b530d7',
    'finalize_password_login_v1(p_user_id uuid, p_expected_password_hash text, p_upgraded_password_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|3f4663e4db141a8513aba73f33d0abec',
    'persist_guest_chat_reply_v1(p_user_id uuid, p_chat_id uuid, p_title text, p_user_message jsonb, p_assistant_message jsonb)|59a70b8a8e24189f07c6c41c7ea44bb9',
    'verify_guest_and_create_session_v1(p_user_id uuid, p_verification_token_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|21e2ef4db85b329592dd3789fa68d04b',
    'verify_registered_and_create_session_v1(p_user_id uuid, p_verification_token_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|722dbbe9c5ad5b2f35b06141f3cfdb4b'
  ]::text[] then
    raise exception 'Account lifecycle exact target postflight failed.'
      using errcode = '55000';
  end if;
  select pg_catalog.array_agg(
    function_row.proname || '(' ||
    pg_catalog.pg_get_function_identity_arguments(function_row.oid) || ')|' ||
    pg_catalog.pg_get_function_result(function_row.oid)
    order by function_row.proname collate pg_catalog."C",
      pg_catalog.pg_get_function_identity_arguments(function_row.oid)
        collate pg_catalog."C"
  ) into observed_results
  from pg_catalog.pg_proc as function_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = function_row.pronamespace
  where namespace_row.nspname = 'public'
    and function_row.proname in (
      'apply_guest_chat_sync_v2', 'complete_initial_password_setup_v1',
      'consume_password_reset_v1', 'delete_user_account',
      'finalize_password_login_v1', 'persist_guest_chat_reply_v1',
      'verify_guest_and_create_session_v1', 'verify_registered_and_create_session_v1'
    );
  if observed_results is distinct from array[
    'apply_guest_chat_sync_v2(p_user_id uuid, p_chat_id uuid, p_title text, p_messages jsonb, p_created_at timestamp with time zone, p_updated_at timestamp with time zone, p_deleted_at timestamp with time zone, p_revision bigint)|TABLE(accepted boolean, resulting_revision bigint, outcome text, stored_chat_count integer, stored_bytes bigint, chat_bytes bigint)',
    'complete_initial_password_setup_v1(p_user_id uuid, p_session_id uuid, p_session_token_hash text, p_password_hash text)|TABLE(password_setup_applied boolean, user_data jsonb, revoked_sessions bigint)',
    'consume_password_reset_v1(p_token_hash text, p_password_hash text)|TABLE(reset_applied boolean)',
    'delete_user_account(p_user_id uuid)|void',
    'delete_user_account(p_user_id uuid, p_storage_bucket text)|void',
    'finalize_password_login_v1(p_user_id uuid, p_expected_password_hash text, p_upgraded_password_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|TABLE(login_applied boolean, user_data jsonb, session_data jsonb, pruned_sessions bigint)',
    'persist_guest_chat_reply_v1(p_user_id uuid, p_chat_id uuid, p_title text, p_user_message jsonb, p_assistant_message jsonb)|TABLE(accepted boolean, outcome text, resulting_revision bigint, resulting_updated_at timestamp with time zone, stored_chat_count integer, stored_bytes bigint, chat_bytes bigint)',
    'verify_guest_and_create_session_v1(p_user_id uuid, p_verification_token_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|TABLE(converted boolean, user_data jsonb, session_data jsonb, revoked_sessions bigint)',
    'verify_registered_and_create_session_v1(p_user_id uuid, p_verification_token_hash text, p_session_id uuid, p_session_token_hash text, p_session_expires_at timestamp with time zone, p_device_id text, p_device_name text, p_platform text, p_device_info jsonb, p_ip_address text, p_user_agent text)|TABLE(verification_applied boolean, user_data jsonb, session_data jsonb, pruned_sessions bigint)'
  ]::text[] then
    raise exception 'Account lifecycle exact result postflight failed.'
      using errcode = '55000';
  end if;
  if not exists (
    select 1
    from pg_catalog.pg_proc as function_row
    join pg_catalog.pg_language as language_row
      on language_row.oid = function_row.prolang
    where function_row.oid =
      'public.connected_operator_complete_chat_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,jsonb,jsonb,jsonb)'::pg_catalog.regprocedure
      and pg_catalog.md5(function_row.prosrc) = 'c7598d67398c07b8c0ed053571bbc1fe'
      and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
      and function_row.prosecdef
      and language_row.lanname = 'plpgsql'
      and function_row.provolatile = 'v'
      and function_row.proconfig is not distinct from
        array['search_path=""']::text[]
      and pg_catalog.pg_get_function_result(function_row.oid) = 'jsonb'
      and function_row.proacl::text =
        '{postgres=X/postgres,service_role=X/postgres}'
  ) then
    raise exception 'Connected completion changed during lifecycle hardening.'
      using errcode = '55000';
  end if;
end;
$postflight$;
