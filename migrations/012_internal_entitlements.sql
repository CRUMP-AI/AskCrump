-- Ask Crump 5.4.0
-- Keep staff/founder QA access separate from customer billing lifecycle state.

begin;

alter table public.users
  add column if not exists internal_tier text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'users_internal_tier_check'
      and conrelid = 'public.users'::regclass
  ) then
    alter table public.users
      add constraint users_internal_tier_check
      check (internal_tier is null or internal_tier in ('professional', 'enterprise'));
  end if;
end $$;

comment on column public.users.internal_tier is
  'Server-managed non-billing entitlement for founder, staff, and QA accounts.';

commit;
