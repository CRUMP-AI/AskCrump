-- Ask Crump guest mode
-- Anonymous visitor accounts: a guest is a real users row flagged is_guest,
-- with a small chat allowance counted in guest_message_count. Registering
-- upgrades the same row, so the guest's conversation carries into the
-- account they create.

begin;

set local lock_timeout = '5s';
set local statement_timeout = '30s';

alter table public.users
  add column if not exists is_guest boolean not null default false;

alter table public.users
  add column if not exists guest_message_count integer not null default 0;

commit;
