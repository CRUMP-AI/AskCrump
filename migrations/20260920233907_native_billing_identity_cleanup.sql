-- A free native customer can exist in RevenueCat before a store purchase.
-- Keep service-role-only evidence on the account, and snapshot the cleanup
-- obligation on its deletion job so switching native billing off later cannot
-- silently skip provider cleanup.

begin;

set local lock_timeout = '5s';

alter table public.users
  add column if not exists native_billing_identity_possible_at timestamptz;

alter table public.account_deletion_jobs
  add column if not exists native_billing_identity_possible boolean not null default false;

comment on column public.users.native_billing_identity_possible_at is
  'Server-written monotonic evidence that a native RevenueCat customer may exist.';
comment on column public.account_deletion_jobs.native_billing_identity_possible is
  'Durable native provider-cleanup obligation surviving deletion of the user row.';

-- Existing RLS and grants remain unchanged; this adds no browser-role access.

commit;
