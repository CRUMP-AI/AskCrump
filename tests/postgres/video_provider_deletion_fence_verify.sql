\set ON_ERROR_STOP on

create schema deletion_fence_harness;

create or replace function deletion_fence_harness.assert_true(
  condition boolean,
  message text
)
returns void
language plpgsql
security invoker
set search_path = pg_catalog, pg_temp
as $$
begin
  if condition is distinct from true then
    raise exception 'assertion failed: %', message;
  end if;
end;
$$;

create table deletion_fence_harness.race_gates (
  name text primary key
);

create or replace function deletion_fence_harness.wait_for_gate(gate_name text)
returns void
language plpgsql
security invoker
set search_path = deletion_fence_harness, pg_catalog, pg_temp
as $$
declare
  deadline timestamptz := clock_timestamp() + interval '60 seconds';
begin
  while exists (
    select 1 from deletion_fence_harness.race_gates where name = gate_name
  ) loop
    if clock_timestamp() >= deadline then
      raise exception 'race gate % timed out', gate_name;
    end if;
    perform pg_sleep(0.05);
  end loop;
end;
$$;

revoke all on schema deletion_fence_harness from public;
revoke all on all tables in schema deletion_fence_harness from public;
revoke all on all functions in schema deletion_fence_harness from public;

-- Catalog-level security contract: the two journals are RLS protected, have
-- no permissive policies, expose no direct access to public clients, and every
-- public RPC remains SECURITY INVOKER with an explicit search path.
select deletion_fence_harness.assert_true(
  (
    select bool_and(c.relrowsecurity)
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname in (
        'video_account_deletion_fences',
        'video_provider_start_claims'
      )
  ),
  'both deletion-fence tables must have RLS enabled'
);

select deletion_fence_harness.assert_true(
  not exists (
    select 1
    from pg_policy p
    join pg_class c on c.oid = p.polrelid
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname in (
        'video_account_deletion_fences',
        'video_provider_start_claims'
      )
  ),
  'service-only deletion-fence tables must not acquire public RLS policies'
);

select deletion_fence_harness.assert_true(
  not has_table_privilege('public', 'public.video_account_deletion_fences', 'select')
    and not has_table_privilege('public', 'public.video_provider_start_claims', 'select')
    and not has_table_privilege('anon', 'public.video_account_deletion_fences', 'select')
    and not has_table_privilege('authenticated', 'public.video_account_deletion_fences', 'select')
    and not has_table_privilege('anon', 'public.video_provider_start_claims', 'select')
    and not has_table_privilege('authenticated', 'public.video_provider_start_claims', 'select')
    and has_table_privilege('service_role', 'public.video_account_deletion_fences', 'select')
    and has_table_privilege('service_role', 'public.video_account_deletion_fences', 'insert')
    and has_table_privilege('service_role', 'public.video_account_deletion_fences', 'update')
    and has_table_privilege('service_role', 'public.video_account_deletion_fences', 'delete')
    and not has_table_privilege('service_role', 'public.video_account_deletion_fences', 'truncate')
    and has_table_privilege('service_role', 'public.video_provider_start_claims', 'select')
    and has_table_privilege('service_role', 'public.video_provider_start_claims', 'insert')
    and has_table_privilege('service_role', 'public.video_provider_start_claims', 'update')
    and has_table_privilege('service_role', 'public.video_provider_start_claims', 'delete')
    and not has_table_privilege('service_role', 'public.video_provider_start_claims', 'truncate'),
  'journal table grants must remain service-only'
);

select deletion_fence_harness.assert_true(
  (
    select count(*) = 10
      and bool_and(has_function_privilege('service_role', p.oid, 'execute'))
      and bool_and(not has_function_privilege('public', p.oid, 'execute'))
      and bool_and(not has_function_privilege('anon', p.oid, 'execute'))
      and bool_and(not has_function_privilege('authenticated', p.oid, 'execute'))
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname in (
        'reserve_video_provider_claim',
        'begin_video_provider_dispatch',
        'record_video_provider_acceptance',
        'finish_video_provider_claim',
        'begin_video_account_deletion',
        'release_video_account_deletion_fence',
        'establish_account_deletion_fence',
        'recover_video_account_deletion_fence',
        'claim_deleted_video_provider_reconciliation',
        'release_deleted_video_provider_reconciliation'
      )
  ),
  'all ten RPC execution grants must be service-only'
);

select deletion_fence_harness.assert_true(
  not has_function_privilege(
    'public', 'public.require_video_account_deletion_fence()', 'execute'
  )
    and not has_function_privilege(
      'anon', 'public.require_video_account_deletion_fence()', 'execute'
    )
    and not has_function_privilege(
      'authenticated', 'public.require_video_account_deletion_fence()', 'execute'
    )
    and not has_function_privilege(
      'service_role', 'public.require_video_account_deletion_fence()', 'execute'
    ),
  'the trigger function must not be directly executable by any API role'
);

select deletion_fence_harness.assert_true(
  (
    select count(*) = 11
      and bool_and(not p.prosecdef)
      and bool_and(
        coalesce(
          'search_path=public, pg_temp' = any(p.proconfig),
          false
        )
      )
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname in (
        'reserve_video_provider_claim',
        'begin_video_provider_dispatch',
        'record_video_provider_acceptance',
        'finish_video_provider_claim',
        'begin_video_account_deletion',
        'release_video_account_deletion_fence',
        'establish_account_deletion_fence',
        'recover_video_account_deletion_fence',
        'claim_deleted_video_provider_reconciliation',
        'release_deleted_video_provider_reconciliation',
        'require_video_account_deletion_fence'
      )
  ),
  'all eleven public functions must be SECURITY INVOKER with a fixed search path'
);

select deletion_fence_harness.assert_true(
  not exists (
    select 1
    from pg_constraint c
    join pg_class source_table on source_table.oid = c.conrelid
    join pg_namespace n on n.oid = source_table.relnamespace
    where n.nspname = 'public'
      and source_table.relname = 'video_provider_start_claims'
      and c.contype = 'f'
  ),
  'provider claims must survive the public.users cascade without a user FK'
);

select deletion_fence_harness.assert_true(
  (
    select count(*) = 1
    from pg_trigger t
    join pg_class c on c.oid = t.tgrelid
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relname = 'users'
      and t.tgname = 'require_video_account_deletion_fence'
      and not t.tgisinternal
      and (t.tgtype & 2) = 2
      and (t.tgtype & 8) = 8
  ),
  'public.users must have exactly one BEFORE DELETE row trigger'
);

select deletion_fence_harness.assert_true(
  (
    select count(*) = 2
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public'
      and c.relkind = 'i'
      and c.relname in (
        'video_provider_claims_owner_state_idx',
        'video_provider_claims_deletion_idx'
      )
  ),
  'candidate reapply must leave exactly its two named indexes'
);

-- Migration-time backfill preserves real handles, classifies pending handles
-- as unknown, defaults legacy operation types, and ignores terminal work.
select deletion_fence_harness.assert_true(
  exists (
    select 1
    from public.video_provider_start_claims
    where job_id = '09100000-0000-0000-0000-000000000001'
      and state = 'accepted'
      and provider_job_id = 'legacy-provider-job'
      and operation_type = 'extend'
  ),
  'backfill must preserve an accepted provider handle'
);

select deletion_fence_harness.assert_true(
  exists (
    select 1
    from public.video_provider_start_claims
    where job_id = '09100000-0000-0000-0000-000000000002'
      and state = 'unknown'
      and provider_job_id is null
      and operation_type = 'generate'
  ),
  'backfill must classify pending work as unknown'
);

select deletion_fence_harness.assert_true(
  not exists (
    select 1
    from public.video_provider_start_claims
    where job_id in (
      '09100000-0000-0000-0000-000000000003',
      '09100000-0000-0000-0000-000000000004'
    )
  ),
  'backfill must ignore ready and failed work'
);

-- An accepted claim must contain a nonblank provider identifier after trimming.
-- This probes the actual named CHECK constraint rather than a source substring.
set role service_role;
do $$
declare
  failed_constraint text;
begin
  begin
    insert into public.video_provider_start_claims(
      job_id, user_id, provider, operation_type, state, provider_job_id
    ) values (
      '09200000-0000-0000-0000-000000000001',
      '09000000-0000-0000-0000-000000000001',
      'runway', 'generate', 'accepted', '   '
    );
    raise exception 'whitespace-only accepted provider ID passed its CHECK constraint';
  exception when check_violation then
    get stacked diagnostics failed_constraint = constraint_name;
    if failed_constraint <> 'video_provider_claim_accepted_id_check' then
      raise;
    end if;
  end;
end;
$$;
reset role;

-- This role is deliberately created after the candidate. Explicit DML grants
-- let the shell tests prove that RLS itself still denies rows and writes,
-- separately from the candidate's table/function revokes.
create role deletion_fence_rls_probe nologin nobypassrls;
grant usage on schema public to deletion_fence_rls_probe;
grant select, insert on table
  public.video_account_deletion_fences,
  public.video_provider_start_claims
to deletion_fence_rls_probe;

-- A bare user delete fails closed and leaves the account intact.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000001');

set role service_role;
do $$
begin
  begin
    delete from public.users
    where id = '10000000-0000-0000-0000-000000000001';
    raise exception 'deletion without a fence unexpectedly succeeded';
  exception when sqlstate '55000' then
    if sqlerrm <> 'video deletion fence is required' then
      raise;
    end if;
  end;
  if not exists (
    select 1 from public.users
    where id = '10000000-0000-0000-0000-000000000001'
  ) then
    raise exception 'failed deletion removed the user';
  end if;
end;
$$;
reset role;

-- A live reservation blocks the fence without leaving a side effect. Even a
-- manually present fence cannot bypass the trigger's reservation check.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000002');

set role service_role;
do $$
declare
  reservation jsonb;
begin
  reservation := public.reserve_video_provider_claim(
    '10000000-0000-0000-0000-000000000002',
    '20000000-0000-0000-0000-000000000002',
    'runway',
    'generate'
  );
  if reservation ->> 'status' <> 'reserved' then
    raise exception 'expected a reservation, got %', reservation;
  end if;
  if public.begin_video_account_deletion(
    '10000000-0000-0000-0000-000000000002',
    '30000000-0000-0000-0000-000000000002'
  ) then
    raise exception 'a live reservation unexpectedly allowed deletion';
  end if;
  if exists (
    select 1 from public.video_account_deletion_fences
    where user_id = '10000000-0000-0000-0000-000000000002'
  ) then
    raise exception 'a rejected deletion left a fence behind';
  end if;

  insert into public.video_account_deletion_fences(user_id, operation_token)
  values (
    '10000000-0000-0000-0000-000000000002',
    '30000000-0000-0000-0000-000000000002'
  );
  begin
    delete from public.users
    where id = '10000000-0000-0000-0000-000000000002';
    raise exception 'trigger accepted a live reservation';
  exception when sqlstate '55000' then
    if sqlerrm <> 'video provider reservation is still settling' then
      raise;
    end if;
  end;
end;
$$;
reset role;

-- An expired reservation is abandoned, then the trigger marks the durable
-- fence deleted while the claim survives the users/media cascade.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000003');
insert into public.media_jobs(
  id, user_id, kind, status, provider, operation_type, provider_job_id
) values (
  '20000000-0000-0000-0000-000000000003',
  '10000000-0000-0000-0000-000000000003',
  'video',
  'queued',
  'gemini',
  'generate',
  'pending:20000000-0000-0000-0000-000000000003'
);

set role service_role;
select public.reserve_video_provider_claim(
  '10000000-0000-0000-0000-000000000003',
  '20000000-0000-0000-0000-000000000003',
  'gemini',
  'generate'
);
reset role;

update public.video_provider_start_claims
set lease_expires_at = now() - interval '1 second'
where job_id = '20000000-0000-0000-0000-000000000003';

set role service_role;
do $$
begin
  if not public.begin_video_account_deletion(
    '10000000-0000-0000-0000-000000000003',
    '30000000-0000-0000-0000-000000000003'
  ) then
    raise exception 'an expired reservation did not allow deletion';
  end if;
  if public.begin_video_provider_dispatch(
    '10000000-0000-0000-0000-000000000003',
    '20000000-0000-0000-0000-000000000003',
    '40000000-0000-0000-0000-000000000003'
  ) then
    raise exception 'an abandoned reservation dispatched through a deletion fence';
  end if;
  delete from public.users
  where id = '10000000-0000-0000-0000-000000000003';
  if not exists (
    select 1 from public.video_provider_start_claims
    where job_id = '20000000-0000-0000-0000-000000000003'
      and state = 'abandoned'
      and deletion_requested_at is not null
  ) then
    raise exception 'expired reservation was not preserved as abandoned';
  end if;
  if not exists (
    select 1 from public.video_account_deletion_fences
    where user_id = '10000000-0000-0000-0000-000000000003'
      and deleted_at is not null
  ) then
    raise exception 'delete trigger did not mark the fence deleted';
  end if;
end;
$$;
reset role;

select deletion_fence_harness.assert_true(
  not exists (
    select 1 from public.media_jobs
    where id = '20000000-0000-0000-0000-000000000003'
  ),
  'media row must cascade after an expired reservation is abandoned'
);

-- RPC retries are idempotent. Acceptance remains durable after deletion even
-- though the media-row repair correctly reports false once the cascade wins.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000004');
insert into public.media_jobs(
  id, user_id, kind, status, provider, operation_type, provider_job_id, metadata
) values (
  '20000000-0000-0000-0000-000000000004',
  '10000000-0000-0000-0000-000000000004',
  'video',
  'queued',
  'runway',
  'generate',
  'pending:20000000-0000-0000-0000-000000000004',
  '{}'::jsonb
);

set role service_role;
do $$
declare
  first_reservation jsonb;
  duplicate_reservation jsonb;
  altered_provider_replay jsonb;
  altered_operation_replay jsonb;
begin
  first_reservation := public.reserve_video_provider_claim(
    '10000000-0000-0000-0000-000000000004',
    '20000000-0000-0000-0000-000000000004',
    'runway',
    'generate'
  );
  duplicate_reservation := public.reserve_video_provider_claim(
    '10000000-0000-0000-0000-000000000004',
    '20000000-0000-0000-0000-000000000004',
    'runway',
    'generate'
  );
  if first_reservation ->> 'status' <> 'reserved'
    or duplicate_reservation ->> 'status' <> 'reserved' then
    raise exception 'reservation replay was not idempotent';
  end if;
  altered_provider_replay := public.reserve_video_provider_claim(
    '10000000-0000-0000-0000-000000000004',
    '20000000-0000-0000-0000-000000000004',
    'gemini',
    'generate'
  );
  altered_operation_replay := public.reserve_video_provider_claim(
    '10000000-0000-0000-0000-000000000004',
    '20000000-0000-0000-0000-000000000004',
    'runway',
    'extend'
  );
  if altered_provider_replay ->> 'status' <> 'claim_unavailable'
    or altered_operation_replay ->> 'status' <> 'claim_unavailable' then
    raise exception 'changed-argument reservation replay was accepted';
  end if;
  if not public.begin_video_provider_dispatch(
    '10000000-0000-0000-0000-000000000004',
    '20000000-0000-0000-0000-000000000004',
    '40000000-0000-0000-0000-000000000004'
  ) or not public.begin_video_provider_dispatch(
    '10000000-0000-0000-0000-000000000004',
    '20000000-0000-0000-0000-000000000004',
    '40000000-0000-0000-0000-000000000004'
  ) then
    raise exception 'dispatch replay was not idempotent';
  end if;
  if not public.record_video_provider_acceptance(
    '10000000-0000-0000-0000-000000000004',
    '20000000-0000-0000-0000-000000000004',
    'runway-provider-job-4'
  ) or not public.record_video_provider_acceptance(
    '10000000-0000-0000-0000-000000000004',
    '20000000-0000-0000-0000-000000000004',
    'runway-provider-job-4'
  ) then
    raise exception 'acceptance replay did not repair the live media row';
  end if;
  if not public.begin_video_account_deletion(
    '10000000-0000-0000-0000-000000000004',
    '30000000-0000-0000-0000-000000000004'
  ) then
    raise exception 'accepted provider start unexpectedly blocked deletion';
  end if;
  delete from public.users
  where id = '10000000-0000-0000-0000-000000000004';
  if public.record_video_provider_acceptance(
    '10000000-0000-0000-0000-000000000004',
    '20000000-0000-0000-0000-000000000004',
    'runway-provider-job-4'
  ) then
    raise exception 'post-delete acceptance unexpectedly found a media row';
  end if;
  begin
    perform public.record_video_provider_acceptance(
      '10000000-0000-0000-0000-000000000004',
      '20000000-0000-0000-0000-000000000004',
      'conflicting-provider-job'
    );
    raise exception 'conflicting provider acceptance unexpectedly succeeded';
  exception when sqlstate '55000' then
    if sqlerrm <> 'provider claim is unavailable or conflicts' then
      raise;
    end if;
  end;
  if not exists (
    select 1 from public.video_provider_start_claims
    where job_id = '20000000-0000-0000-0000-000000000004'
      and state = 'accepted'
      and provider_job_id = 'runway-provider-job-4'
      and deletion_requested_at is not null
  ) then
    raise exception 'accepted provider handle did not survive deletion';
  end if;
  if public.release_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000004',
    '30000000-0000-0000-0000-000000000004'
  ) <> 'user_deleted' then
    raise exception 'post-delete fence release did not report user_deleted';
  end if;
end;
$$;
reset role;

-- The reservation lease is a deletion-recovery timeout, not a hard dispatch
-- authorization deadline. If dispatch wins the shared user lock, an expired
-- reservation becomes dispatching and deletion preserves it for reconciliation.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000007');
insert into public.media_jobs(
  id, user_id, kind, status, provider, operation_type, provider_job_id
) values (
  '20000000-0000-0000-0000-000000000007',
  '10000000-0000-0000-0000-000000000007',
  'video',
  'queued',
  'gemini',
  'generate',
  'pending:20000000-0000-0000-0000-000000000007'
);

set role service_role;
select public.reserve_video_provider_claim(
  '10000000-0000-0000-0000-000000000007',
  '20000000-0000-0000-0000-000000000007',
  'gemini',
  'generate'
);
reset role;

update public.video_provider_start_claims
set lease_expires_at = now() - interval '1 second'
where job_id = '20000000-0000-0000-0000-000000000007';

set role service_role;
do $$
begin
  if not public.begin_video_provider_dispatch(
    '10000000-0000-0000-0000-000000000007',
    '20000000-0000-0000-0000-000000000007',
    '40000000-0000-0000-0000-000000000007'
  ) then
    raise exception 'expired reservation did not dispatch after winning the user lock';
  end if;
  if not public.begin_video_account_deletion(
    '10000000-0000-0000-0000-000000000007',
    '30000000-0000-0000-0000-000000000007'
  ) then
    raise exception 'dispatching expired reservation unexpectedly blocked deletion';
  end if;
  if not exists (
    select 1 from public.video_provider_start_claims
    where job_id = '20000000-0000-0000-0000-000000000007'
      and state = 'dispatching'
      and deletion_requested_at is not null
  ) then
    raise exception 'dispatch winner was not retained for reconciliation';
  end if;
  delete from public.users
  where id = '10000000-0000-0000-0000-000000000007';
end;
$$;
reset role;

-- A lost begin-deletion response is safe to replay with the same token. A
-- different token cannot take ownership, and only the owner can release.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000006');

set role service_role;
do $$
declare
  original_requested_at timestamptz;
begin
  if not public.begin_video_account_deletion(
    '10000000-0000-0000-0000-000000000006',
    '30000000-0000-0000-0000-000000000006'
  ) then
    raise exception 'initial deletion fence was not created';
  end if;
  select requested_at into original_requested_at
  from public.video_account_deletion_fences
  where user_id = '10000000-0000-0000-0000-000000000006';
  if not public.begin_video_account_deletion(
    '10000000-0000-0000-0000-000000000006',
    '30000000-0000-0000-0000-000000000006'
  ) then
    raise exception 'same-token deletion replay was not idempotent';
  end if;
  if (
    select requested_at <> original_requested_at
    from public.video_account_deletion_fences
    where user_id = '10000000-0000-0000-0000-000000000006'
  ) then
    raise exception 'same-token deletion replay changed requested_at';
  end if;
  if public.begin_video_account_deletion(
    '10000000-0000-0000-0000-000000000006',
    '30000000-0000-0000-0000-000000000099'
  ) then
    raise exception 'different deletion token took ownership';
  end if;
  if public.release_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000006',
    '30000000-0000-0000-0000-000000000099'
  ) <> 'not_owner' then
    raise exception 'wrong deletion token released the fence';
  end if;
  if public.release_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000006',
    '30000000-0000-0000-0000-000000000006'
  ) <> 'released' then
    raise exception 'owning deletion token did not release the fence';
  end if;
end;
$$;
reset role;

-- The BEFORE DELETE trigger independently snapshots legacy pending work and
-- marks the existing fence when a caller reaches the final account delete.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000005');
insert into public.media_jobs(
  id, user_id, kind, status, provider, operation_type, provider_job_id
) values (
  '20000000-0000-0000-0000-000000000005',
  '10000000-0000-0000-0000-000000000005',
  'video',
  'processing',
  'gemini',
  'extend',
  'pending:20000000-0000-0000-0000-000000000005'
);

set role service_role;
insert into public.video_account_deletion_fences(user_id, operation_token)
values (
  '10000000-0000-0000-0000-000000000005',
  '30000000-0000-0000-0000-000000000005'
);
delete from public.users
where id = '10000000-0000-0000-0000-000000000005';
do $$
begin
  if not exists (
    select 1 from public.video_provider_start_claims
    where job_id = '20000000-0000-0000-0000-000000000005'
      and state = 'unknown'
      and provider_job_id is null
      and operation_type = 'extend'
      and deletion_requested_at is not null
  ) then
    raise exception 'trigger did not preserve legacy pending work as unknown';
  end if;
  if not exists (
    select 1 from public.video_account_deletion_fences
    where user_id = '10000000-0000-0000-0000-000000000005'
      and deleted_at is not null
  ) then
    raise exception 'trigger did not finalize the legacy deletion fence';
  end if;
end;
$$;
reset role;

-- A token-owned fence with no durable job is released immediately, and only a
-- successful exact-token release clears provider-claim deletion markers.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000008');
set role service_role;
select public.begin_video_account_deletion(
  '10000000-0000-0000-0000-000000000008',
  '30000000-0000-0000-0000-000000000008'
);
insert into public.video_provider_start_claims(
  job_id, user_id, provider, operation_type, state, provider_job_id,
  deletion_requested_at
) values (
  '20000000-0000-0000-0000-000000000008',
  '10000000-0000-0000-0000-000000000008',
  'runway', 'generate', 'accepted', 'provider-job-8', now()
);
do $$
begin
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000008',
    '30000000-0000-0000-0000-000000000008'
  ) <> 'released' then
    raise exception 'jobless exact-token fence was not released';
  end if;
  if exists (
    select 1 from public.video_account_deletion_fences
    where user_id = '10000000-0000-0000-0000-000000000008'
  ) then
    raise exception 'jobless exact-token recovery retained its fence';
  end if;
  if exists (
    select 1 from public.video_provider_start_claims
    where job_id = '20000000-0000-0000-0000-000000000008'
      and deletion_requested_at is not null
  ) then
    raise exception 'successful exact-token recovery retained deletion_requested_at';
  end if;
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000008',
    '30000000-0000-0000-0000-000000000008'
  ) <> 'already_released' then
    raise exception 'released recovery was not idempotent';
  end if;
end;
$$;
reset role;

-- Stale-orphan takeover uses the database clock under the exact fence lock.
-- A recent jobless fence is preserved even if an application clock is ahead.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000012');
set role service_role;
select public.begin_video_account_deletion(
  '10000000-0000-0000-0000-000000000012',
  '30000000-0000-0000-0000-000000000013'
);
do $$
begin
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000012',
    '30000000-0000-0000-0000-000000000013',
    true
  ) <> 'still_reconciling' then
    raise exception 'database clock did not preserve a recent jobless fence';
  end if;
  if not exists (
    select 1 from public.video_account_deletion_fences
    where user_id = '10000000-0000-0000-0000-000000000012'
      and operation_token = '30000000-0000-0000-0000-000000000013'
  ) then
    raise exception 'recent stale-takeover probe removed its exact fence';
  end if;
end;
$$;
update public.video_account_deletion_fences
set requested_at = now() - interval '16 minutes'
where user_id = '10000000-0000-0000-0000-000000000012';
do $$
begin
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000012',
    '30000000-0000-0000-0000-000000000013',
    true
  ) <> 'released' then
    raise exception 'database-stale jobless fence was not released';
  end if;
end;
$$;
reset role;

-- A same-token job models a lost insert response. It remains fenced during the
-- reconciliation window, then job abandonment and exact-fence release commit
-- together after the database clock proves the job stale.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000009');
set role service_role;
select public.begin_video_account_deletion(
  '10000000-0000-0000-0000-000000000009',
  '30000000-0000-0000-0000-000000000009'
);
insert into public.account_deletion_jobs(
  user_id, operation_token, state, fenced_at, finalize_after, next_attempt_at,
  created_at
) values (
  '10000000-0000-0000-0000-000000000009',
  '30000000-0000-0000-0000-000000000009',
  'fencing', now(), now() + interval '30 hours', now() + interval '15 minutes',
  now() - interval '1 year'
);
do $$
begin
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000009',
    '30000000-0000-0000-0000-000000000009'
  ) <> 'still_reconciling' then
    raise exception 'recent same-token job did not remain fenced';
  end if;
  if not exists (
    select 1 from public.video_account_deletion_fences
    where user_id = '10000000-0000-0000-0000-000000000009'
      and operation_token = '30000000-0000-0000-0000-000000000009'
  ) then
    raise exception 'recent lost-insert recovery released the video fence';
  end if;
end;
$$;
update public.account_deletion_jobs
set created_at = now() + interval '1 year'
where user_id = '10000000-0000-0000-0000-000000000009';
update public.video_account_deletion_fences
set requested_at = now() - interval '16 minutes'
where user_id = '10000000-0000-0000-0000-000000000009';
do $$
begin
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000009',
    '30000000-0000-0000-0000-000000000009'
  ) <> 'abandoned' then
    raise exception 'stale same-token job was not atomically abandoned';
  end if;
  if not exists (
    select 1 from public.account_deletion_jobs
    where user_id = '10000000-0000-0000-0000-000000000009'
      and state = 'abandoned' and completed_at is not null
      and next_attempt_at is null
      and last_error_code = 'DELETION_FENCE_NOT_ESTABLISHED'
  ) or exists (
    select 1 from public.video_account_deletion_fences
    where user_id = '10000000-0000-0000-0000-000000000009'
  ) then
    raise exception 'stale recovery did not commit job and fence together';
  end if;
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000009',
    '30000000-0000-0000-0000-000000000009'
  ) <> 'already_released' then
    raise exception 'completed same-token recovery replay was not idempotent';
  end if;
end;
$$;
reset role;

-- A different durable-job token or fence token is an operator-visible conflict.
-- Neither row nor provider-claim deletion state may be altered.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000010');
insert into public.account_deletion_jobs(
  user_id, operation_token, state, fenced_at, finalize_after, next_attempt_at,
  created_at
) values (
  '10000000-0000-0000-0000-000000000010',
  '30000000-0000-0000-0000-000000000010',
  'fencing', now() - interval '16 minutes', now() + interval '30 hours', now(),
  now() - interval '16 minutes'
);
insert into public.video_account_deletion_fences(user_id, operation_token)
values (
  '10000000-0000-0000-0000-000000000010',
  '30000000-0000-0000-0000-000000000011'
);
insert into public.video_provider_start_claims(
  job_id, user_id, provider, operation_type, state, provider_job_id,
  deletion_requested_at
) values (
  '20000000-0000-0000-0000-000000000010',
  '10000000-0000-0000-0000-000000000010',
  'gemini', 'generate', 'accepted', 'provider-job-10', now()
);
set role service_role;
do $$
begin
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000010',
    '30000000-0000-0000-0000-000000000011'
  ) <> 'job_conflict' then
    raise exception 'different durable-job token was not rejected';
  end if;
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000010',
    '30000000-0000-0000-0000-000000000010'
  ) <> 'not_owner' then
    raise exception 'different fence token was not rejected';
  end if;
  if not exists (
    select 1 from public.video_account_deletion_fences
    where user_id = '10000000-0000-0000-0000-000000000010'
      and operation_token = '30000000-0000-0000-0000-000000000011'
  ) or not exists (
    select 1 from public.video_provider_start_claims
    where job_id = '20000000-0000-0000-0000-000000000010'
      and deletion_requested_at is not null
  ) then
    raise exception 'wrong-token recovery mutated protected state';
  end if;
end;
$$;
reset role;

-- Without a database-authored fence timestamp, an unfinished job cannot prove
-- that a paused establishment is stale. Keep it incomplete and fail-closed.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000013');
insert into public.account_deletion_jobs(
  user_id, operation_token, state, fenced_at, finalize_after, next_attempt_at,
  created_at
) values (
  '10000000-0000-0000-0000-000000000013',
  '30000000-0000-0000-0000-000000000014',
  'fencing', now() - interval '1 year', now() + interval '30 hours', now(),
  now() - interval '1 year'
);
set role service_role;
do $$
begin
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000013',
    '30000000-0000-0000-0000-000000000014'
  ) <> 'still_reconciling' then
    raise exception 'job without a video fence did not remain fail-closed';
  end if;
  if not exists (
    select 1 from public.account_deletion_jobs
    where user_id = '10000000-0000-0000-0000-000000000013'
      and completed_at is null
  ) then
    raise exception 'fenceless live job was altered by recovery';
  end if;
end;
$$;
reset role;

-- Establishment binds all three fences atomically. Recovery then reports the
-- account as deleting, and after user deletion it preserves the tombstoned
-- video fence while returning user_deleted.
insert into public.users(id) values ('10000000-0000-0000-0000-000000000011');
set role service_role;
select public.begin_video_account_deletion(
  '10000000-0000-0000-0000-000000000011',
  '30000000-0000-0000-0000-000000000012'
);
insert into public.account_deletion_jobs(
  user_id, operation_token, state, fenced_at, finalize_after, next_attempt_at
) values (
  '10000000-0000-0000-0000-000000000011',
  '30000000-0000-0000-0000-000000000012',
  'fencing', now(), now() + interval '30 hours', now()
);
do $$
begin
  if public.establish_account_deletion_fence(
    '10000000-0000-0000-0000-000000000011',
    '30000000-0000-0000-0000-000000000012',
    now()
  ) <> 'fenced' then
    raise exception 'matching durable/video token did not fence the user';
  end if;
  if not public.begin_video_account_deletion(
    '10000000-0000-0000-0000-000000000011',
    '30000000-0000-0000-0000-000000000012'
  ) then
    raise exception 'established same-token begin replay was rejected';
  end if;
  if public.begin_video_account_deletion(
    '10000000-0000-0000-0000-000000000011',
    '30000000-0000-0000-0000-000000000099'
  ) then
    raise exception 'non-active user accepted a different begin token';
  end if;
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000011',
    '30000000-0000-0000-0000-000000000012'
  ) <> 'account_deleting' then
    raise exception 'recovery did not preserve an established users fence';
  end if;
  if public.release_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000011',
    '30000000-0000-0000-0000-000000000012'
  ) <> 'account_deleting' then
    raise exception 'legacy release did not preserve an established users fence';
  end if;
  delete from public.users
  where id = '10000000-0000-0000-0000-000000000011';
  if public.recover_video_account_deletion_fence(
    '10000000-0000-0000-0000-000000000011',
    '30000000-0000-0000-0000-000000000012'
  ) <> 'user_deleted' then
    raise exception 'post-delete recovery did not report user_deleted';
  end if;
  if not exists (
    select 1 from public.video_account_deletion_fences
    where user_id = '10000000-0000-0000-0000-000000000011'
      and operation_token = '30000000-0000-0000-0000-000000000012'
      and deleted_at is not null
  ) then
    raise exception 'post-delete recovery removed the tombstoned fence';
  end if;
end;
$$;
reset role;

truncate table
  public.video_provider_start_claims,
  public.video_account_deletion_fences,
  public.account_deletion_jobs,
  public.media_jobs,
  public.users;
