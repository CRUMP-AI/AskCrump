\set ON_ERROR_STOP on

create role anon nologin;
create role authenticated nologin;
create role service_role nologin;

create table public.users (
  id uuid primary key,
  email text not null,
  password_hash text not null,
  full_name text,
  is_verified boolean not null default false,
  verification_token_hash text,
  verification_token_expires timestamptz,
  updated_at timestamptz not null default pg_catalog.clock_timestamp()
);

grant select on public.users to service_role;
