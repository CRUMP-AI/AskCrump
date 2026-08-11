-- Ask Crump release hardening
-- Source-control guard for the atomic session rotation introduced in this
-- release. Production already has sessions_device_id_unique.
--
-- This migration intentionally refuses to guess which session to keep if a
-- non-production environment contains duplicate non-null device IDs. Resolve
-- duplicates explicitly before retrying rather than silently deleting data.

begin;

do $$
begin
  if exists (
    select 1
    from public.sessions
    where device_id is not null
    group by device_id
    having count(*) > 1
  ) then
    raise exception 'Ask Crump migration stopped: duplicate non-null sessions.device_id values exist. Resolve them before creating sessions_device_id_unique.';
  end if;
end $$;

create unique index if not exists sessions_device_id_unique
  on public.sessions (device_id);

commit;
