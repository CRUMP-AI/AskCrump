-- Disposable PostgreSQL 17 fixture for the durable password-reset-email queue.

do $$
begin
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'service_role') then
    create role service_role nologin;
  end if;
end;
$$;

create table public.users (
  id uuid primary key,
  email text not null,
  password_hash text,
  is_verified boolean not null default false,
  is_guest boolean not null default false,
  verification_token_hash text,
  verification_token_expires timestamptz,
  deleted_at timestamptz,
  password_reset_token_hash text,
  password_reset_expires timestamptz,
  email_verified_at timestamptz,
  last_login timestamptz,
  updated_at timestamptz default now()
);

create table public.sessions (
  id uuid primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  revoked_at timestamptz
);

create unique index users_email_lower_unique on public.users (lower(email));
create unique index users_password_reset_token_hash_unique
  on public.users(password_reset_token_hash)
  where password_reset_token_hash is not null;

create or replace function public.consume_password_reset_v1(
  p_token_hash text,
  p_password_hash text
)
returns table (reset_applied boolean)
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_user_id uuid;
  v_reset_expires timestamptz;
  v_now timestamptz;
begin
  if p_token_hash is null
     or p_token_hash !~ '^[0-9a-f]{64}$'
     or p_password_hash is null
     or pg_catalog.length(p_password_hash) < 20
     or pg_catalog.length(p_password_hash) > 1024 then
    raise exception 'Invalid password-reset input.'
      using errcode = '22023';
  end if;

  select account.id, account.password_reset_expires
    into v_user_id, v_reset_expires
    from public.users as account
   where account.password_reset_token_hash = p_token_hash
   order by account.id
   limit 1
   for update;

  -- The partial unique index makes the locked row the sole account for this
  -- bearer token. Sample the security clock only after acquiring its row lock;
  -- an unrelated writer cannot extend a token by making this reset wait.
  v_now := pg_catalog.clock_timestamp();

  if not found or v_reset_expires is null or v_reset_expires <= v_now then
    return query select false;
    return;
  end if;

  update public.users as account
     set password_hash = p_password_hash,
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

  -- A trigger failure or any other error here rolls the user update and token
  -- consumption back with this statement, leaving a safe retry path.
  update public.sessions as session
     set revoked_at = v_now
   where session.user_id = v_user_id
     and session.revoked_at is null;

  return query select true;
end;
$$;

alter function public.consume_password_reset_v1(text,text) owner to postgres;
revoke all on function public.consume_password_reset_v1(text,text)
  from public, anon, authenticated, service_role;
grant execute on function public.consume_password_reset_v1(text,text)
  to service_role;

comment on function public.consume_password_reset_v1(text,text) is
  'Atomically consumes one password-reset token, updates its account, and revokes every active session.';
