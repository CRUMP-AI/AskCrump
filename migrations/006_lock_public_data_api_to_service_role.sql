-- Ask Crump release hardening
-- Mirrors the production migration applied 2026-08-11 as
-- Supabase migration: lock_public_data_api_to_service_role.
--
-- Architecture: browser/native clients never query Supabase directly. The
-- authenticated Python API is the only application database gateway and uses
-- the service-role credential server-side.

begin;

revoke all privileges on all tables in schema public from anon, authenticated;
revoke all privileges on all sequences in schema public from anon, authenticated;
revoke execute on all functions in schema public from anon, authenticated;

-- Prevent future objects created by the application owner from silently
-- reopening browser-role access after a migration/rebuild.
alter default privileges for role postgres in schema public
  revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public
  revoke execute on functions from anon, authenticated;

-- These historical policies were named as service-role policies but were
-- scoped broadly enough to be misleading/dangerous when table grants existed.
drop policy if exists "Service role full access users" on public.users;
drop policy if exists "Service role full access settings" on public.user_settings;

commit;
