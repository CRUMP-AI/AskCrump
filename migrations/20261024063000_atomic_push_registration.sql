-- Keep one installation's push destination bound to the session generation
-- that is still current when the database mutation commits.  The production
-- migration runner owns the outer transaction boundary.
--
-- Rollout contract (backwards-compatible migration -> deploy): apply this
-- migration before deploying the RPC caller.  The BEFORE trigger below
-- adapts the previous direct-upsert application version
-- by stamping a current session generation (or disabling the destination when
-- no current generation exists).  That compatibility layer makes it safe to
-- validate the generation constraint before the new application is deployed.

do $preflight$
declare
  function_signature constant text :=
    'public.mutate_push_registration_v1(uuid,uuid,text,text,text,text,boolean,timestamp with time zone)';
  owner_scrub_signature constant text :=
    'public.disable_stale_installation_push_v1()';
  legacy_stamp_signature constant text :=
    'public.stamp_legacy_push_registration_v1()';
  existing_function oid := pg_catalog.to_regprocedure(function_signature);
  existing_owner_scrub oid := pg_catalog.to_regprocedure(owner_scrub_signature);
  existing_legacy_stamp oid := pg_catalog.to_regprocedure(legacy_stamp_signature);
  existing_installation_index oid :=
    pg_catalog.to_regclass('public.push_tokens_installation_id_idx');
begin
  if pg_catalog.to_regclass('public.sessions') is null
     or pg_catalog.to_regclass('public.push_tokens') is null then
    raise exception 'Push-registration prerequisites are missing.'
      using errcode = '55000';
  end if;

  if not exists (
       select 1
         from pg_catalog.pg_class as table_row
        where table_row.oid = 'public.push_tokens'::regclass
          and table_row.relrowsecurity
     ) then
    raise exception 'push_tokens RLS must remain enabled.'
      using errcode = '55000';
  end if;

  if (
    select pg_catalog.count(*)
      from information_schema.columns
     where table_schema = 'public'
       and (
         (
           table_name = 'sessions'
           and (
             (column_name = 'id' and data_type = 'uuid')
             or (column_name = 'user_id' and data_type = 'uuid')
             or (column_name = 'token_hash' and data_type = 'text')
             or (column_name = 'device_id' and data_type = 'text')
             or (column_name = 'created_at' and data_type = 'timestamp with time zone')
             or (column_name = 'last_activity' and data_type = 'timestamp with time zone')
             or (column_name = 'expires_at' and data_type = 'timestamp with time zone')
             or (column_name = 'revoked_at' and data_type = 'timestamp with time zone')
           )
         )
         or (
           table_name = 'push_tokens'
           and (
             (column_name = 'id' and data_type = 'uuid')
             or (column_name = 'user_id' and data_type = 'uuid')
             or (column_name = 'installation_id' and data_type = 'text')
             or (column_name = 'platform' and data_type = 'text')
             or (column_name = 'token' and data_type = 'text')
             or (column_name = 'enabled' and data_type = 'boolean')
             or (column_name = 'created_at' and data_type = 'timestamp with time zone')
             or (column_name = 'updated_at' and data_type = 'timestamp with time zone')
             or (column_name = 'last_used_at' and data_type = 'timestamp with time zone')
           )
         )
       )
  ) <> 17 then
    raise exception 'Unexpected push-registration table definitions.'
      using errcode = '55000';
  end if;

  if pg_catalog.to_regclass('public.sessions_token_hash_unique') is null
     or pg_catalog.to_regclass('public.sessions_device_id_unique') is null then
    raise exception 'Expected session uniqueness contracts are missing.'
      using errcode = '55000';
  end if;

  if existing_installation_index is not null
     and coalesce((
       select index_row.indisvalid is not true
         or index_row.indisready is not true
         or index_row.indrelid <> 'public.push_tokens'::regclass
         or index_row.indisunique is true
         or index_row.indnkeyatts <> 1
         or index_row.indnatts <> 1
         or index_row.indpred is not null
         or index_row.indexprs is not null
         or access_method.amname <> 'btree'
         or pg_catalog.pg_get_indexdef(index_row.indexrelid, 1, true)
              <> 'installation_id'
         from pg_catalog.pg_index as index_row
         join pg_catalog.pg_class as index_class
           on index_class.oid = index_row.indexrelid
         join pg_catalog.pg_am as access_method
           on access_method.oid = index_class.relam
        where index_row.indexrelid = existing_installation_index
     ), true) then
    raise exception 'Push-token installation index drifted; refusing replacement.'
      using errcode = '55000';
  end if;

  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'service_role')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'anon')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticated') then
    raise exception 'Push-registration database roles are missing.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname = 'mutate_push_registration_v1'
       and function_row.oid <> coalesce(existing_function, 0::oid)
  ) then
    raise exception 'Unexpected mutate_push_registration_v1 overload.'
      using errcode = '55000';
  end if;

  if existing_function is not null
     and (
       select pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
         or function_row.prosecdef is not true
         or function_row.provolatile <> 'v'
         or function_row.proconfig is distinct from array['search_path=""']::text[]
         or pg_catalog.strpos(
              function_row.prosrc,
              'ASK_CRUMP_ATOMIC_PUSH_REGISTRATION_V1'
            ) = 0
         or not pg_catalog.has_function_privilege(
              'service_role', existing_function, 'EXECUTE'
            )
         or pg_catalog.has_function_privilege('anon', existing_function, 'EXECUTE')
         or pg_catalog.has_function_privilege(
              'authenticated', existing_function, 'EXECUTE'
            )
       from pg_catalog.pg_proc as function_row
      where function_row.oid = existing_function
     ) then
    raise exception 'Existing push-registration RPC drifted; refusing replacement.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname = 'disable_stale_installation_push_v1'
       and function_row.oid <> coalesce(existing_owner_scrub, 0::oid)
  ) then
    raise exception 'Unexpected disable_stale_installation_push_v1 overload.'
      using errcode = '55000';
  end if;

  if existing_owner_scrub is not null
     and (
       select pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
         or function_row.prosecdef is true
         or function_row.provolatile <> 'v'
         or function_row.proconfig is distinct from array['search_path=""']::text[]
         or pg_catalog.strpos(
              function_row.prosrc,
              'ASK_CRUMP_DISABLE_STALE_INSTALLATION_PUSH_V1'
            ) = 0
         or pg_catalog.has_function_privilege(
              'service_role', existing_owner_scrub, 'EXECUTE'
            )
         or pg_catalog.has_function_privilege('anon', existing_owner_scrub, 'EXECUTE')
         or pg_catalog.has_function_privilege(
              'authenticated', existing_owner_scrub, 'EXECUTE'
            )
       from pg_catalog.pg_proc as function_row
      where function_row.oid = existing_owner_scrub
     ) then
    raise exception 'Existing installation-owner scrub trigger drifted; refusing replacement.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname = 'stamp_legacy_push_registration_v1'
       and function_row.oid <> coalesce(existing_legacy_stamp, 0::oid)
  ) then
    raise exception 'Unexpected stamp_legacy_push_registration_v1 overload.'
      using errcode = '55000';
  end if;

  if existing_legacy_stamp is not null
     and (
       select pg_catalog.pg_get_userbyid(function_row.proowner) <> 'postgres'
         or function_row.prosecdef is true
         or function_row.provolatile <> 'v'
         or function_row.proconfig is distinct from array['search_path=""']::text[]
         or pg_catalog.strpos(
              function_row.prosrc,
              'ASK_CRUMP_STAMP_LEGACY_PUSH_REGISTRATION_V1'
            ) = 0
         or pg_catalog.has_function_privilege(
              'service_role', existing_legacy_stamp, 'EXECUTE'
            )
         or pg_catalog.has_function_privilege('anon', existing_legacy_stamp, 'EXECUTE')
         or pg_catalog.has_function_privilege(
              'authenticated', existing_legacy_stamp, 'EXECUTE'
            )
       from pg_catalog.pg_proc as function_row
      where function_row.oid = existing_legacy_stamp
     ) then
    raise exception 'Existing legacy push-stamp trigger drifted; refusing replacement.'
      using errcode = '55000';
  end if;

  if exists (
       select 1
         from pg_catalog.pg_trigger as trigger_row
        where trigger_row.tgrelid = 'public.sessions'::regclass
          and trigger_row.tgname = 'disable_stale_installation_push'
          and (
            existing_owner_scrub is null
            or trigger_row.tgfoid <> existing_owner_scrub
            or trigger_row.tgenabled <> 'O'
            or trigger_row.tgisinternal
            or pg_catalog.strpos(
                 pg_catalog.pg_get_triggerdef(trigger_row.oid),
                 'AFTER INSERT OR UPDATE OF user_id, token_hash, device_id, revoked_at ON public.sessions'
               ) = 0
          )
     ) then
    raise exception 'Existing installation-owner scrub trigger drifted; refusing replacement.'
      using errcode = '55000';
  end if;

  if exists (
       select 1
         from pg_catalog.pg_trigger as trigger_row
        where trigger_row.tgrelid = 'public.push_tokens'::regclass
          and trigger_row.tgname = 'stamp_legacy_push_registration'
          and (
            existing_legacy_stamp is null
            or trigger_row.tgfoid <> existing_legacy_stamp
            or trigger_row.tgenabled <> 'O'
            or trigger_row.tgisinternal
            or pg_catalog.strpos(
                 pg_catalog.pg_get_triggerdef(trigger_row.oid),
                 'BEFORE INSERT OR UPDATE OF user_id, installation_id, enabled ON public.push_tokens'
               ) = 0
          )
     ) then
    raise exception 'Existing legacy push-stamp trigger drifted; refusing replacement.'
      using errcode = '55000';
  end if;
end;
$preflight$;

alter table public.push_tokens
  add column if not exists registration_session_id uuid,
  add column if not exists registration_session_token_hash text,
  add column if not exists registration_generation timestamptz;

create index if not exists push_tokens_installation_id_idx
  on public.push_tokens (installation_id);

comment on column public.push_tokens.registration_session_id is
  'Session row that last established this installation push destination.';
comment on column public.push_tokens.registration_session_token_hash is
  'Opaque session generation hash used only for stale-registration fencing.';
comment on column public.push_tokens.registration_generation is
  'Server-issued session creation time used to reject older cross-installation token claims.';

create or replace function public.stamp_legacy_push_registration_v1()
returns trigger
language plpgsql
volatile
security invoker
set search_path = ''
as $function$
declare
  -- ASK_CRUMP_STAMP_LEGACY_PUSH_REGISTRATION_V1
  current_session public.sessions%rowtype;
begin
  if not new.enabled then
    return new;
  end if;

  -- The release preceding this migration wrote push_tokens directly and did
  -- not know the generation columns.  Serialize that legacy write with the
  -- matching session row so a concurrent account rotation cannot commit a
  -- destination for the former owner.  New RPC writes pass through the same
  -- compatibility boundary and receive the identical authoritative stamp.
  select session_row.*
    into current_session
    from public.sessions as session_row
   where session_row.user_id = new.user_id
     and session_row.device_id = new.installation_id
     and session_row.revoked_at is null
     and session_row.expires_at > pg_catalog.clock_timestamp()
   for update;

  if found then
    new.registration_session_id := current_session.id;
    new.registration_session_token_hash := current_session.token_hash;
    new.registration_generation := current_session.created_at;
  else
    -- A stale legacy request must remain a successful database write so the
    -- mixed-version deployment does not 500, but it may never create a
    -- deliverable destination for another or expired session.
    new.enabled := false;
    new.registration_session_id := null;
    new.registration_session_token_hash := null;
    new.registration_generation := null;
  end if;
  return new;
end;
$function$;

revoke all on function public.stamp_legacy_push_registration_v1()
  from public, anon, authenticated, service_role;

drop trigger if exists stamp_legacy_push_registration on public.push_tokens;
create trigger stamp_legacy_push_registration
before insert or update of user_id, installation_id, enabled
on public.push_tokens
for each row
execute function public.stamp_legacy_push_registration_v1();

comment on function public.stamp_legacy_push_registration_v1() is
  'Adapts pre-RPC direct writes by binding enabled destinations to the current locked session or disabling them fail-closed.';

-- Preserve only legacy destinations that can be bound to one currently active
-- server session.  Everything else stays fail-closed until the native client
-- presents a fresh provider token through the atomic RPC below.
with current_session as (
  select session_row.id,
         session_row.user_id,
         session_row.device_id,
         session_row.token_hash,
         session_row.created_at
    from public.sessions as session_row
   where session_row.device_id is not null
     and session_row.revoked_at is null
     and session_row.expires_at > pg_catalog.clock_timestamp()
)
update public.push_tokens as destination
   set registration_session_id = session_row.id,
       registration_session_token_hash = session_row.token_hash,
       registration_generation = session_row.created_at,
       updated_at = pg_catalog.clock_timestamp()
  from current_session as session_row
 where destination.enabled
   and destination.user_id = session_row.user_id
   and destination.installation_id = session_row.device_id
   and (
     destination.registration_session_id is null
     or destination.registration_session_token_hash is null
     or destination.registration_generation is null
   );

update public.push_tokens as destination
   set enabled = false,
       updated_at = pg_catalog.clock_timestamp()
 where destination.enabled
   and (
     destination.registration_session_id is null
     or destination.registration_session_token_hash is null
     or destination.registration_generation is null
   );

do $generation_constraint$
declare
  existing_constraint oid;
begin
  select constraint_row.oid
    into existing_constraint
    from pg_catalog.pg_constraint as constraint_row
   where constraint_row.conrelid = 'public.push_tokens'::regclass
     and constraint_row.conname = 'push_tokens_enabled_generation_check';

  if existing_constraint is not null
     and (
       select constraint_row.contype <> 'c'
         or not constraint_row.convalidated
         or pg_catalog.strpos(
              pg_catalog.pg_get_constraintdef(constraint_row.oid),
              'registration_session_id IS NOT NULL'
            ) = 0
         or pg_catalog.strpos(
              pg_catalog.pg_get_constraintdef(constraint_row.oid),
              'registration_session_token_hash IS NOT NULL'
            ) = 0
         or pg_catalog.strpos(
              pg_catalog.pg_get_constraintdef(constraint_row.oid),
              'registration_generation IS NOT NULL'
            ) = 0
       from pg_catalog.pg_constraint as constraint_row
      where constraint_row.oid = existing_constraint
     ) then
    raise exception 'Enabled push-generation constraint drifted; refusing replacement.'
      using errcode = '55000';
  end if;

  if existing_constraint is null then
    alter table public.push_tokens
      add constraint push_tokens_enabled_generation_check
      check (
        not enabled
        or (
          registration_session_id is not null
          and registration_session_token_hash is not null
          and registration_generation is not null
        )
      ) not valid;
    alter table public.push_tokens
      validate constraint push_tokens_enabled_generation_check;
  end if;
end;
$generation_constraint$;

create or replace function public.disable_stale_installation_push_v1()
returns trigger
language plpgsql
volatile
security invoker
set search_path = ''
as $function$
begin
  -- ASK_CRUMP_DISABLE_STALE_INSTALLATION_PUSH_V1
  -- Session creation/rotation and this cleanup share one database transaction.
  -- Therefore an expired A session rotated to B can never commit while leaving
  -- A's already-enabled destination attached to the same installation.
  if tg_op = 'UPDATE'
     and old.device_id is not null
     and (
       old.device_id is distinct from new.device_id
       or old.user_id is distinct from new.user_id
       or old.token_hash is distinct from new.token_hash
       or new.revoked_at is not null
     ) then
    update public.push_tokens as destination
       set enabled = false,
           updated_at = pg_catalog.clock_timestamp()
     where destination.installation_id = old.device_id
       and destination.registration_session_id = old.id
       and destination.registration_session_token_hash = old.token_hash
       and destination.enabled;
  end if;

  -- Revocation must only invalidate the exact registered generation.  A late
  -- revoke from an older session may never disable a newer session's token.
  if new.revoked_at is not null then
    update public.push_tokens as destination
       set enabled = false,
           updated_at = pg_catalog.clock_timestamp()
     where destination.installation_id = new.device_id
       and destination.registration_session_id = new.id
       and destination.registration_session_token_hash = new.token_hash
       and destination.enabled;
    return new;
  end if;

  if new.device_id is not null then
    update public.push_tokens as destination
       set enabled = false,
           updated_at = pg_catalog.clock_timestamp()
     where destination.installation_id = new.device_id
       and destination.enabled
       and (
         destination.user_id is distinct from new.user_id
         or destination.registration_session_id is distinct from new.id
         or destination.registration_session_token_hash is distinct from new.token_hash
       );
  end if;
  return new;
end;
$function$;

revoke all on function public.disable_stale_installation_push_v1()
  from public, anon, authenticated, service_role;

drop trigger if exists disable_stale_installation_push on public.sessions;
create trigger disable_stale_installation_push
after insert or update of user_id, token_hash, device_id, revoked_at
on public.sessions
for each row
execute function public.disable_stale_installation_push_v1();

comment on function public.disable_stale_installation_push_v1() is
  'Disables another account push destination inside the transaction that rotates a native installation session.';

create or replace function public.mutate_push_registration_v1(
  p_user_id uuid,
  p_session_id uuid,
  p_session_token_hash text,
  p_installation_id text,
  p_platform text,
  p_token text,
  p_enabled boolean,
  p_session_expires_at timestamptz
)
returns table (
  applied boolean,
  stale boolean,
  owner_id uuid,
  enabled boolean
)
language plpgsql
volatile
security definer
set search_path = ''
as $function$
declare
  -- ASK_CRUMP_ATOMIC_PUSH_REGISTRATION_V1
  v_now timestamptz := pg_catalog.clock_timestamp();
  v_session public.sessions%rowtype;
  v_newer_generation boolean := false;
begin
  if p_user_id is null
     or p_session_id is null
     or p_session_token_hash is null
     or p_session_token_hash !~ '^[0-9a-f]{64}$'
     or p_installation_id is null
     or pg_catalog.length(p_installation_id) < 8
     or pg_catalog.length(p_installation_id) > 200
     or p_enabled is null then
    raise exception 'Invalid push-registration precondition.'
      using errcode = '22023';
  end if;

  if p_enabled
     and (
       p_platform not in ('ios', 'android')
       or p_token is null
       or pg_catalog.length(p_token) < 20
       or pg_catalog.length(p_token) > 5000
       or p_session_expires_at is null
       or p_session_expires_at <= v_now
     ) then
    raise exception 'Invalid push-registration destination.'
      using errcode = '22023';
  end if;

  select session_row.*
    into v_session
    from public.sessions as session_row
   where session_row.id = p_session_id
   for update;

  if not found
     or v_session.user_id is distinct from p_user_id
     or v_session.token_hash is distinct from p_session_token_hash
     or v_session.device_id is distinct from p_installation_id
     or v_session.revoked_at is not null
     or v_session.expires_at <= v_now then
    return query select false, true, null::uuid, false;
    return;
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'askcrump.push.installation:' || p_installation_id,
      0
    )
  );
  if p_enabled then
    -- A SELECT FOR UPDATE cannot serialize a globally unique token while its
    -- row is still absent (for example, after an app reinstall changes the
    -- installation ID but APNs/FCM reuses the device token).  Take this second
    -- advisory lock in the fixed installation-then-token order so exactly one
    -- claimant can inspect and transfer the token at a time.
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended('askcrump.push.token:' || p_token, 0)
    );
  end if;

  -- Lock every row the operation may supersede after the installation lock.
  perform 1
    from public.push_tokens as destination
   where destination.installation_id = p_installation_id
      or (p_enabled and destination.token = p_token)
   order by destination.id
   for update;

  select coalesce(
           pg_catalog.bool_or(
             destination.registration_generation > v_session.created_at
             or (
               destination.registration_generation = v_session.created_at
               and destination.registration_session_id > v_session.id
             )
           ),
           false
         )
    into v_newer_generation
    from public.push_tokens as destination
   where destination.installation_id = p_installation_id
      or (p_enabled and destination.token = p_token);

  if v_newer_generation then
    return query select false, true, null::uuid, false;
    return;
  end if;

  if not p_enabled then
    update public.push_tokens as destination
       set enabled = false,
           updated_at = v_now
     where destination.user_id = p_user_id
       and destination.installation_id = p_installation_id
       and (
         destination.registration_session_token_hash is null
         or destination.registration_session_token_hash = p_session_token_hash
       );
    return query select true, false, p_user_id, false;
    return;
  end if;

  update public.push_tokens as destination
     set enabled = false,
         updated_at = v_now
   where destination.installation_id = p_installation_id
     and destination.user_id <> p_user_id;

  delete from public.push_tokens as destination
   where destination.token = p_token
     and (
       destination.user_id <> p_user_id
       or destination.installation_id <> p_installation_id
     );

  insert into public.push_tokens as destination (
    user_id,
    installation_id,
    platform,
    token,
    enabled,
    updated_at,
    last_used_at,
    registration_session_id,
    registration_session_token_hash,
    registration_generation
  ) values (
    p_user_id,
    p_installation_id,
    p_platform,
    p_token,
    true,
    v_now,
    v_now,
    p_session_id,
    p_session_token_hash,
    v_session.created_at
  )
  on conflict (user_id, installation_id) do update
     set platform = excluded.platform,
         token = excluded.token,
         enabled = true,
         updated_at = excluded.updated_at,
         last_used_at = excluded.last_used_at,
         registration_session_id = excluded.registration_session_id,
         registration_session_token_hash = excluded.registration_session_token_hash,
         registration_generation = excluded.registration_generation;

  update public.sessions as session_row
     set last_activity = v_now,
         expires_at = greatest(
           session_row.expires_at,
           p_session_expires_at
         )
   where session_row.id = p_session_id
     and session_row.user_id = p_user_id
     and session_row.token_hash = p_session_token_hash
     and session_row.revoked_at is null;

  return query select true, false, p_user_id, true;
end;
$function$;

revoke all on function public.mutate_push_registration_v1(
  uuid, uuid, text, text, text, text, boolean, timestamptz
) from public, anon, authenticated, service_role;

grant execute on function public.mutate_push_registration_v1(
  uuid, uuid, text, text, text, text, boolean, timestamptz
) to service_role;

comment on function public.mutate_push_registration_v1(
  uuid, uuid, text, text, text, text, boolean, timestamptz
) is
  'Atomically binds or disables one installation push destination only while its owner and server-issued session generation remain current.';
