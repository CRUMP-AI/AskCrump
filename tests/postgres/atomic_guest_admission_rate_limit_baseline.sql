-- Disposable PostgreSQL 17 fixture for atomic guest-admission rate limiting.
-- All hashes and events are synthetic.

\set ON_ERROR_STOP on

do $$
begin
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end;
$$;

create extension if not exists pgcrypto;
create extension if not exists dblink;

grant usage on schema public to service_role;

create table public.rate_limit_events (
  id uuid primary key default gen_random_uuid(),
  scope text not null,
  key_hash text not null,
  created_at timestamptz not null default pg_catalog.clock_timestamp()
);

create index rate_limit_events_lookup_idx
  on public.rate_limit_events(scope, key_hash, created_at desc);

alter table public.rate_limit_events enable row level security;

create or replace function public.consume_rate_limit_event(
  p_scope text,
  p_key_hash text,
  p_limit integer,
  p_window_seconds integer
)
returns table(used integer, allowed boolean, retry_after integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  current_used integer;
begin
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_scope || ':' || p_key_hash, 0)
  );
  select count(*)::integer
    into current_used
    from public.rate_limit_events
   where scope = p_scope
     and key_hash = p_key_hash
     and created_at >= pg_catalog.clock_timestamp()
       - pg_catalog.make_interval(secs => p_window_seconds);
  if current_used >= p_limit then
    return query select current_used, false, p_window_seconds;
    return;
  end if;
  insert into public.rate_limit_events(scope, key_hash)
  values (p_scope, p_key_hash);
  return query select current_used + 1, true, 0;
end;
$$;

revoke all on function public.consume_rate_limit_event(text, text, integer, integer)
  from public, anon, authenticated, service_role;
grant execute on function public.consume_rate_limit_event(text, text, integer, integer)
  to service_role;
