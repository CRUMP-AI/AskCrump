-- Serialize credential changes and authenticated-session persistence on the
-- owning user row. Generated locally with Supabase CLI 2.117.0; unapplied.

begin;

alter table public.users
  add column if not exists auth_generation bigint not null default 0;

alter table public.sessions
  add column if not exists auth_generation bigint not null default 0;

alter table public.users
  drop constraint if exists users_auth_generation_nonnegative,
  add constraint users_auth_generation_nonnegative check (auth_generation >= 0);

alter table public.sessions
  drop constraint if exists sessions_auth_generation_nonnegative,
  add constraint sessions_auth_generation_nonnegative check (auth_generation >= 0);

create or replace function public.persist_auth_session(
  p_user_id uuid,
  p_expected_auth_generation bigint,
  p_session_id uuid,
  p_token_hash text,
  p_device_id text,
  p_device_name text,
  p_platform text,
  p_device_info jsonb,
  p_ip_address text,
  p_user_agent text,
  p_now timestamptz,
  p_expires_at timestamptz
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  persisted public.sessions%rowtype;
  current_generation bigint;
begin
  if p_user_id is null
     or p_expected_auth_generation is null
     or p_session_id is null
     or p_token_hash is null
     or p_now is null
     or p_expires_at is null then
    return null;
  end if;

  -- This row lock is the shared serialization boundary with password reset.
  select account.auth_generation
    into current_generation
  from public.users as account
  where account.id = p_user_id
    and account.deleted_at is null
    and account.auth_generation = p_expected_auth_generation
  for update;

  if not found then
    return null;
  end if;

  if p_device_id is not null then
    insert into public.sessions (
      id,
      user_id,
      token_hash,
      auth_generation,
      device_id,
      device_name,
      platform,
      device_info,
      ip_address,
      user_agent,
      created_at,
      last_activity,
      expires_at,
      revoked_at
    )
    values (
      p_session_id,
      p_user_id,
      p_token_hash,
      current_generation,
      p_device_id,
      p_device_name,
      p_platform,
      coalesce(p_device_info, '{}'::jsonb),
      p_ip_address,
      p_user_agent,
      p_now,
      p_now,
      p_expires_at,
      null
    )
    on conflict (device_id) do update
      set user_id = excluded.user_id,
          token_hash = excluded.token_hash,
          auth_generation = excluded.auth_generation,
          device_name = excluded.device_name,
          platform = excluded.platform,
          device_info = excluded.device_info,
          ip_address = excluded.ip_address,
          user_agent = excluded.user_agent,
          created_at = excluded.created_at,
          last_activity = excluded.last_activity,
          expires_at = excluded.expires_at,
          revoked_at = null
    returning * into persisted;
  else
    insert into public.sessions (
      id,
      user_id,
      token_hash,
      auth_generation,
      device_id,
      device_name,
      platform,
      device_info,
      ip_address,
      user_agent,
      created_at,
      last_activity,
      expires_at,
      revoked_at
    )
    values (
      p_session_id,
      p_user_id,
      p_token_hash,
      current_generation,
      null,
      p_device_name,
      p_platform,
      coalesce(p_device_info, '{}'::jsonb),
      p_ip_address,
      p_user_agent,
      p_now,
      p_now,
      p_expires_at,
      null
    )
    returning * into persisted;
  end if;

  -- Preserve the existing bounded-session policy inside the same transaction.
  with ranked_active as (
    select active.id,
           row_number() over (
             order by active.created_at desc, active.id desc
           ) as session_rank
    from public.sessions as active
    where active.user_id = p_user_id
      and active.revoked_at is null
  )
  update public.sessions as stale
     set revoked_at = p_now
    from ranked_active
   where stale.id = ranked_active.id
     and ranked_active.session_rank > 20;

  return to_jsonb(persisted);
end;
$$;

create or replace function public.consume_password_reset(
  p_presented_token_hash text,
  p_new_password_hash text,
  p_now timestamptz
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  reset_user_id uuid;
  next_generation bigint;
begin
  if p_presented_token_hash is null
     or p_new_password_hash is null
     or p_now is null then
    return null;
  end if;

  -- UPDATE owns the user-row lock. A competing session persistence or reset
  -- must complete on one side of this single transactional boundary.
  update public.users as account
     set password_hash = p_new_password_hash,
         auth_generation = account.auth_generation + 1,
         is_verified = true,
         verification_token_hash = null,
         verification_token_expires = null,
         password_reset_token_hash = null,
         password_reset_expires = null,
         full_name = case when account.is_verified then account.full_name else null end,
         terms_accepted_at = case
           when account.is_verified then account.terms_accepted_at else null
         end,
         terms_version = case when account.is_verified then account.terms_version else null end,
         updated_at = p_now
   where account.password_reset_token_hash = p_presented_token_hash
     and account.password_reset_expires > p_now
     and account.deleted_at is null
  returning account.id, account.auth_generation
       into reset_user_id, next_generation;

  if not found then
    return null;
  end if;

  update public.sessions as active
     set revoked_at = p_now
   where active.user_id = reset_user_id
     and active.revoked_at is null;

  return jsonb_build_object(
    'id', reset_user_id,
    'auth_generation', next_generation
  );
end;
$$;

revoke all on function public.persist_auth_session(
  uuid, bigint, uuid, text, text, text, text, jsonb, text, text, timestamptz, timestamptz
) from public, anon, authenticated;
revoke all on function public.persist_auth_session(
  uuid, bigint, uuid, text, text, text, text, jsonb, text, text, timestamptz, timestamptz
) from service_role;
grant execute on function public.persist_auth_session(
  uuid, bigint, uuid, text, text, text, text, jsonb, text, text, timestamptz, timestamptz
) to service_role;

revoke all on function public.consume_password_reset(text, text, timestamptz)
  from public, anon, authenticated;
revoke all on function public.consume_password_reset(text, text, timestamptz)
  from service_role;
grant execute on function public.consume_password_reset(text, text, timestamptz)
  to service_role;

comment on function public.persist_auth_session(
  uuid, bigint, uuid, text, text, text, text, jsonb, text, text, timestamptz, timestamptz
) is 'Private atomic generation check and authenticated-session persistence boundary.';

comment on function public.consume_password_reset(text, text, timestamptz)
  is 'Private atomic reset-token consumption, credential-generation advance, and session revocation boundary.';

commit;
