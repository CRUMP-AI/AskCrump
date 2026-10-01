\set ON_ERROR_STOP on

create role anon nologin;
create role authenticated nologin;
create role service_role nologin;

create table public.users (
  id uuid primary key,
  created_at timestamptz not null,
  registration_environment text not null default 'production',
  deleted_at timestamptz,
  internal_tier text
);

create table public.product_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  environment text not null,
  event_name text not null,
  event_key text not null,
  source text,
  plan text,
  artifact_type text,
  placement text,
  campaign text,
  creative text,
  intent text,
  created_at timestamptz not null default now(),
  constraint product_events_event_name_check check (event_name <> '')
);
