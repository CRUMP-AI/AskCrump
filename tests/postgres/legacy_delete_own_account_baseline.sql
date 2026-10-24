-- Disposable PostgreSQL 17 fixture for the historical no-argument self-delete
-- RPC. All identities and data are synthetic.

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

create schema auth;
grant usage on schema auth to authenticated;

create table auth.users (
  id uuid primary key,
  email text not null
);

create or replace function auth.uid()
returns uuid
language sql
stable
set search_path = ''
as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;

create or replace function public.delete_own_account()
returns void
language plpgsql
security definer
as $function$ begin   delete from auth.users where id = auth.uid(); end $function$;

grant execute on function public.delete_own_account() to service_role;

-- Minimal stand-ins for the current service-only overloads. The legacy
-- migration must not widen or otherwise change either ACL.
create or replace function public.delete_user_account(target_user_id uuid)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform target_user_id;
end;
$$;

create or replace function public.delete_user_account(
  target_user_id uuid,
  reason text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  perform target_user_id, reason;
end;
$$;

revoke all on function public.delete_user_account(uuid) from public, anon, authenticated;
revoke all on function public.delete_user_account(uuid, text) from public, anon, authenticated;
grant execute on function public.delete_user_account(uuid) to service_role;
grant execute on function public.delete_user_account(uuid, text) to service_role;

create schema legacy_delete_fixture;

create table legacy_delete_fixture.before_state as
select
  function_row.oid,
  function_row.prosrc,
  pg_get_function_identity_arguments(function_row.oid) as identity_arguments,
  pg_get_function_result(function_row.oid) as result_type,
  function_row.proowner,
  function_row.prolang,
  function_row.prosecdef
from pg_catalog.pg_proc as function_row
where function_row.oid = 'public.delete_own_account()'::regprocedure;

create table legacy_delete_fixture.service_overload_before as
select
  function_row.oid,
  function_row.prosrc,
  function_row.proowner,
  function_row.prosecdef,
  function_row.proconfig,
  function_row.proacl,
  pg_get_function_identity_arguments(function_row.oid) as identity_arguments,
  pg_get_function_result(function_row.oid) as result_type
from pg_catalog.pg_proc as function_row
where function_row.oid in (
  'public.delete_user_account(uuid)'::regprocedure,
  'public.delete_user_account(uuid,text)'::regprocedure
);

insert into auth.users (id, email)
values
  ('10000000-0000-4000-8000-000000000001', 'synthetic-a@example.test'),
  ('10000000-0000-4000-8000-000000000002', 'synthetic-b@example.test');
