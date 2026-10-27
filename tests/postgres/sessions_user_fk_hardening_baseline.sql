\set ON_ERROR_STOP on

drop schema if exists public cascade;
create schema public authorization postgres;

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'sessions_fk_observer'
  ) then
    create role sessions_fk_observer nologin;
  end if;
end;
$$;

revoke all on schema public from public;
grant usage on schema public to sessions_fk_observer;

create table public.users (
  id uuid primary key
);

create table public.sessions (
  id uuid primary key,
  user_id uuid not null
);

alter table public.users enable row level security;
alter table public.sessions enable row level security;

grant select on public.users, public.sessions to sessions_fk_observer;

insert into public.users (id)
values ('81000000-0000-4000-8000-000000000001');

insert into public.sessions (id, user_id)
values (
  '82000000-0000-4000-8000-000000000001',
  '81000000-0000-4000-8000-000000000001'
);
