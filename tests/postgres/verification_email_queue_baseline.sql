-- Disposable PostgreSQL 17 fixture for the durable verification-email queue.

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
  is_verified boolean default false,
  deleted_at timestamptz,
  verification_token_hash text,
  verification_token_expires timestamptz,
  updated_at timestamptz default now()
);

create unique index users_email_lower_unique on public.users (lower(email));
