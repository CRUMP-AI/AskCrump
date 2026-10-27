\set ON_ERROR_STOP on

do $schema_contract$
declare
  v_table regclass;
begin
  perform public.assert_policy_consent_schema_v1();

  if (
    select count(*)
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'consent_policy_bundles'
  ) <> 17 then
    raise exception 'Unexpected consent policy bundle column count.';
  end if;

  if (
    select count(*)
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'user_policy_acceptance_receipts'
  ) <> 10 then
    raise exception 'Unexpected policy receipt column count.';
  end if;

  foreach v_table in array array[
    'public.consent_policy_bundles'::regclass,
    'public.user_policy_acceptance_receipts'::regclass
  ] loop
    if not (
      select class.relrowsecurity
         and not class.relforcerowsecurity
         and pg_catalog.pg_get_userbyid(class.relowner) = 'postgres'
        from pg_catalog.pg_class as class
       where class.oid = v_table
    ) or exists (
      select 1 from pg_catalog.pg_policy where polrelid = v_table
    ) then
      raise exception 'Unexpected policy table owner/RLS/policy state.';
    end if;
    if pg_catalog.has_table_privilege('anon', v_table, 'SELECT,INSERT,UPDATE,DELETE')
       or pg_catalog.has_table_privilege('authenticated', v_table, 'SELECT,INSERT,UPDATE,DELETE')
       or pg_catalog.has_table_privilege('service_role', v_table, 'SELECT,INSERT,UPDATE,DELETE') then
      raise exception 'Direct table privilege escaped.';
    end if;
  end loop;

  if not exists (
    select 1
      from pg_catalog.pg_constraint
     where conrelid = 'public.user_policy_acceptance_receipts'::regclass
       and conname = 'user_policy_acceptance_receipts_user_fkey'
       and contype = 'f'
       and confrelid = 'public.users'::regclass
       and confdeltype = 'c'
  ) then
    raise exception 'Receipt deletion cascade is missing.';
  end if;
end;
$schema_contract$;

insert into public.users (
  id, email, is_guest, is_verified, registration_submitted_at
) values
  ('11111111-1111-4111-8111-111111111111', 'guest@guest.askcrump.local', true, false, null),
  ('22222222-2222-4222-8222-222222222222', 'pending@example.com', false, false, pg_catalog.clock_timestamp()),
  ('33333333-3333-4333-8333-333333333333', 'account@example.com', false, true, pg_catalog.clock_timestamp()),
  ('44444444-4444-4444-8444-444444444444', 'delete@example.com', false, true, pg_catalog.clock_timestamp());

do $direct_acl$
begin
  begin
    set local role service_role;
    perform 1 from public.user_policy_acceptance_receipts;
    raise exception 'service_role direct receipt select unexpectedly succeeded';
  exception when insufficient_privilege then
    null;
  end;
end;
$direct_acl$;

do $rejections$
begin
  begin
    perform * from public.record_policy_acceptance_v1(
      '11111111-1111-4111-8111-111111111111',
      'ask-crump-legal-stale',
      'guest_gate',
      'web',
      true, true, true, true
    );
    raise exception 'stale policy bundle unexpectedly accepted';
  exception when invalid_parameter_value then
    null;
  end;

  begin
    perform * from public.record_policy_acceptance_v1(
      '11111111-1111-4111-8111-111111111111',
      'ask-crump-legal-2026-08-01-a44e8c36',
      'guest_gate',
      'web',
      false, true, true, true
    );
    raise exception 'false age attestation unexpectedly accepted';
  exception when invalid_parameter_value then
    null;
  end;

  begin
    perform * from public.record_policy_acceptance_v1(
      '33333333-3333-4333-8333-333333333333',
      'ask-crump-legal-2026-08-01-a44e8c36',
      'guest_gate',
      'web',
      true, true, true, true
    );
    raise exception 'mismatched guest provenance unexpectedly accepted';
  exception when invalid_parameter_value then
    null;
  end;
end;
$rejections$;

create temporary table acceptance_bounds (
  label text primary key,
  before_at timestamptz not null,
  accepted_at timestamptz not null,
  after_at timestamptz not null,
  receipt_id uuid not null
);

insert into acceptance_bounds
select
  'guest',
  bounds.before_at,
  receipt.accepted_at,
  pg_catalog.clock_timestamp(),
  receipt.receipt_id
from (select pg_catalog.clock_timestamp() as before_at) as bounds
cross join lateral public.record_policy_acceptance_v1(
  '11111111-1111-4111-8111-111111111111',
  'ask-crump-legal-2026-08-01-a44e8c36',
  'guest_gate',
  'web',
  true, true, true, true
) as receipt;

update public.users
   set registration_submitted_at = pg_catalog.clock_timestamp(),
       email = 'converted@example.com'
 where id = '11111111-1111-4111-8111-111111111111';

insert into acceptance_bounds
select
  'registration',
  bounds.before_at,
  receipt.accepted_at,
  pg_catalog.clock_timestamp(),
  receipt.receipt_id
from (select pg_catalog.clock_timestamp() as before_at) as bounds
cross join lateral public.record_policy_acceptance_v1(
  '11111111-1111-4111-8111-111111111111',
  'ask-crump-legal-2026-08-01-a44e8c36',
  'registration',
  'native',
  true, true, true, true
) as receipt;

select * from public.record_policy_acceptance_v1(
  '22222222-2222-4222-8222-222222222222',
  'ask-crump-legal-2026-08-01-a44e8c36',
  'registration',
  'web',
  true, true, true, true
);

select * from public.record_policy_acceptance_v1(
  '33333333-3333-4333-8333-333333333333',
  'ask-crump-legal-2026-08-01-a44e8c36',
  'account_gate',
  'web',
  true, true, true, true
);

create temporary table account_replay_first as
select * from public.record_policy_acceptance_v1(
  '33333333-3333-4333-8333-333333333333',
  'ask-crump-legal-2026-08-01-a44e8c36',
  'account_gate',
  'web',
  true, true, true, true
);

create temporary table account_replay_second as
select * from public.record_policy_acceptance_v1(
  '33333333-3333-4333-8333-333333333333',
  'ask-crump-legal-2026-08-01-a44e8c36',
  'account_gate',
  'web',
  true, true, true, true
);

do $replay_contract$
begin
  if exists (
    select 1
      from account_replay_first as first_call
      cross join account_replay_second as second_call
     where first_call.receipt_id is distinct from second_call.receipt_id
        or first_call.accepted_at is distinct from second_call.accepted_at
  ) or (
    select count(*)
      from public.user_policy_acceptance_receipts
     where user_id = '33333333-3333-4333-8333-333333333333'
       and bundle_id = 'ask-crump-legal-2026-08-01-a44e8c36'
       and acceptance_source = 'account_gate'
  ) <> 1 then
    raise exception 'Acceptance replay created duplicate or unstable evidence.';
  end if;
end;
$replay_contract$;

select * from public.record_policy_acceptance_v1(
  '44444444-4444-4444-8444-444444444444',
  'ask-crump-legal-2026-08-01-a44e8c36',
  'account_gate',
  'web',
  true, true, true, true
);

do $receipt_contract$
declare
  v_current record;
begin
  if exists (
    select 1 from acceptance_bounds
     where accepted_at < before_at or accepted_at > after_at
  ) then
    raise exception 'Receipt timestamp was not database bounded.';
  end if;

  if (
    select count(*)
      from public.user_policy_acceptance_receipts
     where user_id = '11111111-1111-4111-8111-111111111111'
  ) <> 2 then
    raise exception 'Guest-to-registration acceptance history was not preserved.';
  end if;

  select * into v_current
    from public.read_current_policy_acceptance_v1(
      '11111111-1111-4111-8111-111111111111'
    );
  if v_current.bundle_id <> 'ask-crump-legal-2026-08-01-a44e8c36'
     or v_current.bundle_hash <> 'a44e8c3637047ccfda406e35310312b4ea068bed73244a753fee5c4f2173a83a'
     or v_current.acceptance_source <> 'registration' then
    raise exception 'Current receipt readback was not exact.';
  end if;

  if exists (
    select 1 from public.users
     where terms_version is distinct from 'ask-crump-legal-2026-08-01-a44e8c36'
        or terms_accepted_at is null
  ) then
    raise exception 'Legacy acceptance mirrors were not updated.';
  end if;
end;
$receipt_contract$;

do $append_only$
begin
  begin
    update public.user_policy_acceptance_receipts
       set client_platform = 'unknown'
     where user_id = '33333333-3333-4333-8333-333333333333';
    raise exception 'Direct receipt update unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;

  begin
    delete from public.user_policy_acceptance_receipts
     where user_id = '33333333-3333-4333-8333-333333333333';
    raise exception 'Direct receipt delete unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;

  begin
    update public.consent_policy_bundles
       set effective_date = date '2026-08-02'
     where bundle_id = 'ask-crump-legal-2026-08-01-a44e8c36';
    raise exception 'Manifest mutation unexpectedly succeeded';
  exception when sqlstate '55000' then
    null;
  end;
end;
$append_only$;

delete from public.users
 where id = '44444444-4444-4444-8444-444444444444';

do $deletion_contract$
begin
  if exists (
    select 1 from public.user_policy_acceptance_receipts
     where user_id = '44444444-4444-4444-8444-444444444444'
  ) then
    raise exception 'Account deletion did not cascade consent receipts.';
  end if;
  if not exists (
    select 1 from public.consent_policy_bundles
     where bundle_id = 'ask-crump-legal-2026-08-01-a44e8c36'
  ) then
    raise exception 'Account deletion removed the non-personal bundle manifest.';
  end if;
end;
$deletion_contract$;

-- Defense in depth: even if a future migration weakens the all-true CHECK,
-- current receipt lookup must never promote a partial attestation.
begin;
alter table public.user_policy_acceptance_receipts
  drop constraint user_policy_acceptance_receipts_attestations_check;

insert into public.user_policy_acceptance_receipts (
  user_id,
  bundle_id,
  acceptance_source,
  client_platform,
  age_17_plus_attested,
  terms_accepted,
  privacy_notice_acknowledged,
  ai_provider_transmission_authorized
) values (
  '33333333-3333-4333-8333-333333333333',
  'ask-crump-legal-2026-08-01-a44e8c36',
  'registration',
  'web',
  true,
  true,
  true,
  false
);

do $partial_attestation_read$
declare
  v_current record;
begin
  select * into v_current
    from public.read_current_policy_acceptance_v1(
      '33333333-3333-4333-8333-333333333333'
    );
  if v_current.acceptance_source is distinct from 'account_gate' then
    raise exception 'Partial attestation was promoted as current acceptance.';
  end if;
end;
$partial_attestation_read$;
rollback;

select public.assert_policy_consent_schema_v1();
