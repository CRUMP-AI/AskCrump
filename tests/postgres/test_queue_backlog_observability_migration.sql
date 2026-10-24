\set ON_ERROR_STOP on

create or replace function pg_temp.assert_true(condition boolean, failure_message text)
returns void language plpgsql as $$
begin
  if condition is not true then
    raise exception 'queue backlog observability gate failed: %', failure_message;
  end if;
end;
$$;

do $$
begin
  if not exists (
    select 1 from pg_catalog.pg_roles where rolname = 'queue_backlog_untrusted'
  ) then
    create role queue_backlog_untrusted nologin;
  end if;
end;
$$;

select pg_temp.assert_true(
  pg_catalog.to_regprocedure('public.read_email_queue_backlog_v1()') is not null,
  'aggregate RPC must exist'
);
select pg_temp.assert_true(
  (
    select pg_catalog.pg_get_userbyid(proc_row.proowner) = 'postgres'
      and language_row.lanname = 'sql'
      and proc_row.prokind = 'f'
      and proc_row.prosecdef
      and not proc_row.proleakproof
      and proc_row.provolatile = 's'
      and proc_row.proparallel = 'u'
      and proc_row.proretset
      and proc_row.pronargs = 0
      and proc_row.pronargdefaults = 0
      and proc_row.proconfig = array['search_path=""']::text[]
      and pg_catalog.pg_get_function_result(proc_row.oid) =
        'TABLE(verification_active_depth bigint, verification_eligible_depth bigint, verification_oldest_eligible_job_age_seconds bigint, password_reset_active_depth bigint, password_reset_eligible_depth bigint, password_reset_oldest_eligible_job_age_seconds bigint)'
      and pg_catalog.md5(proc_row.prosrc) = 'efae7a5f9fb838ddcfbcdc4385f0b745'
      and pg_catalog.strpos(proc_row.prosrc, 'ASK_CRUMP_EMAIL_QUEUE_BACKLOG_V1') > 0
      and pg_catalog.obj_description(proc_row.oid, 'pg_proc') =
        'ASK_CRUMP_EMAIL_QUEUE_BACKLOG_V1 aggregate-only service-role observability.'
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_language as language_row
      on language_row.oid = proc_row.prolang
    where proc_row.oid = 'public.read_email_queue_backlog_v1()'::regprocedure
  ),
  'RPC catalog contract must remain exact'
);
select pg_temp.assert_true(
  (
    select pg_catalog.count(*) = 2
      and pg_catalog.count(*) filter (
        where grantee_role.rolname = 'postgres'
          and grantor_role.rolname = 'postgres'
          and acl_row.privilege_type = 'EXECUTE'
          and not acl_row.is_grantable
      ) = 1
      and pg_catalog.count(*) filter (
        where grantee_role.rolname = 'service_role'
          and grantor_role.rolname = 'postgres'
          and acl_row.privilege_type = 'EXECUTE'
          and not acl_row.is_grantable
      ) = 1
    from pg_catalog.pg_proc as proc_row
    cross join lateral pg_catalog.aclexplode(proc_row.proacl) as acl_row
    left join pg_catalog.pg_roles as grantee_role on grantee_role.oid = acl_row.grantee
    left join pg_catalog.pg_roles as grantor_role on grantor_role.oid = acl_row.grantor
    where proc_row.oid = 'public.read_email_queue_backlog_v1()'::regprocedure
  ),
  'RPC ACL must contain only owner and service_role execute'
);
select pg_temp.assert_true(
  (
    select pg_catalog.count(*) = 2
      and pg_catalog.bool_and(
        pg_catalog.pg_get_userbyid(proc_row.proowner) = 'postgres'
        and language_row.lanname = 'plpgsql'
        and proc_row.prokind = 'f'
        and proc_row.prosecdef
        and not proc_row.proleakproof
        and proc_row.provolatile = 'v'
        and proc_row.proparallel = 'u'
        and proc_row.proretset
        and proc_row.pronargs = 2
        and proc_row.pronargdefaults = 1
        and proc_row.proconfig is not distinct from array['search_path=""']::text[]
        and pg_catalog.pg_get_expr(proc_row.proargdefaults, 0) is not distinct from '120'
        and pg_catalog.pg_get_function_arguments(proc_row.oid) is not distinct from
          'p_claim_token uuid, p_lease_seconds integer DEFAULT 120'
        and pg_catalog.pg_get_function_result(proc_row.oid) is not distinct from
          'TABLE(job_id uuid, lease_token uuid, attempts integer)'
        and pg_catalog.md5(proc_row.prosrc) = expected.source_md5
        and pg_catalog.strpos(proc_row.prosrc, expected.source_marker) > 0
        and acl_contract.is_exact
        and pg_catalog.has_function_privilege(
          'service_role', expected.signature, 'EXECUTE'
        )
        and not pg_catalog.has_function_privilege(
          'anon', expected.signature, 'EXECUTE'
        )
        and not pg_catalog.has_function_privilege(
          'authenticated', expected.signature, 'EXECUTE'
        )
      )
    from (
      values
        (
          'public.claim_verification_email_job_v1(uuid,integer)',
          'd6dd16c8e13ef88708663ec6b076f9ef',
          'ASK_CRUMP_VERIFICATION_EMAIL_QUEUE_V1'
        ),
        (
          'public.claim_password_reset_email_job_v1(uuid,integer)',
          '800d71fa7c64b0e68f07c07a983b8c2e',
          'ASK_CRUMP_PASSWORD_RESET_EMAIL_QUEUE_V1'
        )
    ) as expected(signature, source_md5, source_marker)
    join pg_catalog.pg_proc as proc_row
      on proc_row.oid = pg_catalog.to_regprocedure(expected.signature)
    join pg_catalog.pg_language as language_row
      on language_row.oid = proc_row.prolang
    cross join lateral (
      select pg_catalog.count(*) = 2
        and pg_catalog.count(*) filter (
          where grantee_role.rolname = 'postgres'
            and grantor_role.rolname = 'postgres'
            and acl_row.privilege_type = 'EXECUTE'
            and not acl_row.is_grantable
        ) = 1
        and pg_catalog.count(*) filter (
          where grantee_role.rolname = 'service_role'
            and grantor_role.rolname = 'postgres'
            and acl_row.privilege_type = 'EXECUTE'
            and not acl_row.is_grantable
        ) = 1 as is_exact
      from pg_catalog.aclexplode(
        coalesce(proc_row.proacl, pg_catalog.acldefault('f', proc_row.proowner))
      ) as acl_row
      left join pg_catalog.pg_roles as grantee_role
        on grantee_role.oid = acl_row.grantee
      left join pg_catalog.pg_roles as grantor_role
        on grantor_role.oid = acl_row.grantor
    ) as acl_contract
  ),
  'both claim RPC catalog and direct ACL contracts must remain exact'
);
select pg_temp.assert_true(
  (
    select pg_catalog.count(*) = 2
      and pg_catalog.bool_and(
        trigger_contract.trigger_count = 4
        and trigger_contract.invalid_count = 0
      )
    from (
      values
        (
          'public.verification_email_jobs'::regclass,
          'verification_email_jobs_user_id_fkey'
        ),
        (
          'public.password_reset_email_jobs'::regclass,
          'password_reset_email_jobs_user_id_fkey'
        )
    ) as expected(queue_table, constraint_name)
    cross join lateral (
      select
        pg_catalog.count(*) as trigger_count,
        pg_catalog.count(*) filter (
          where trigger_row.tgenabled <> 'O'
             or trigger_row.tgisinternal is not true
        ) as invalid_count
      from pg_catalog.pg_trigger as trigger_row
      join pg_catalog.pg_constraint as constraint_row
        on constraint_row.oid = trigger_row.tgconstraint
      where constraint_row.conrelid = expected.queue_table
        and constraint_row.conname = expected.constraint_name
        and constraint_row.contype = 'f'
    ) as trigger_contract
  ),
  'each queue foreign key must retain exactly four enabled internal triggers'
);
select pg_temp.assert_true(
  pg_catalog.has_function_privilege(
    'service_role', 'public.read_email_queue_backlog_v1()', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'anon', 'public.read_email_queue_backlog_v1()', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated', 'public.read_email_queue_backlog_v1()', 'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'queue_backlog_untrusted', 'public.read_email_queue_backlog_v1()', 'EXECUTE'
  ),
  'only service_role may execute the RPC'
);
select pg_temp.assert_true(
  (
    select pg_catalog.count(*) = 1
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname = 'read_email_queue_backlog_v1'
  ),
  'RPC must have no overloads'
);
select pg_temp.assert_true(
  (
    select proc_row.proallargtypes::regtype[] = array[
      'bigint'::regtype, 'bigint'::regtype, 'bigint'::regtype,
      'bigint'::regtype, 'bigint'::regtype, 'bigint'::regtype
    ]
      and proc_row.proargmodes::text = '{t,t,t,t,t,t}'
      and proc_row.proargnames = array[
        'verification_active_depth',
        'verification_eligible_depth',
        'verification_oldest_eligible_job_age_seconds',
        'password_reset_active_depth',
        'password_reset_eligible_depth',
        'password_reset_oldest_eligible_job_age_seconds'
      ]
    from pg_catalog.pg_proc as proc_row
    where proc_row.oid = 'public.read_email_queue_backlog_v1()'::regprocedure
  ),
  'RPC output names, order, and bigint types must remain exact'
);

select pg_temp.assert_true(
  not pg_catalog.has_table_privilege(
    'service_role', 'public.verification_email_jobs', 'SELECT'
  )
  and not pg_catalog.has_table_privilege(
    'service_role', 'public.password_reset_email_jobs', 'SELECT'
  )
  and not pg_catalog.has_table_privilege(
    'anon', 'public.verification_email_jobs', 'SELECT'
  )
  and not pg_catalog.has_table_privilege(
    'authenticated', 'public.password_reset_email_jobs', 'SELECT'
  )
  and not pg_catalog.has_table_privilege(
    'queue_backlog_untrusted', 'public.verification_email_jobs', 'SELECT'
  ),
  'direct queue reads must remain denied'
);
select pg_temp.assert_true(
  (
    select relrowsecurity and relforcerowsecurity
      and coalesce(relacl::text, '') = '{postgres=arwdDxtm/postgres}'
    from pg_catalog.pg_class
    where oid = 'public.verification_email_jobs'::regclass
  ) and (
    select relrowsecurity and relforcerowsecurity
      and coalesce(relacl::text, '') = '{postgres=arwdDxtm/postgres}'
    from pg_catalog.pg_class
    where oid = 'public.password_reset_email_jobs'::regclass
  ),
  'queue RLS and table ACLs must remain unchanged'
);
select pg_temp.assert_true(
  not exists (
    select 1 from pg_catalog.pg_policy
    where polrelid in (
      'public.verification_email_jobs'::regclass,
      'public.password_reset_email_jobs'::regclass
    )
  )
  and not exists (
    select 1
    from pg_catalog.pg_attribute
    where attrelid in (
      'public.verification_email_jobs'::regclass,
      'public.password_reset_email_jobs'::regclass
    )
      and attnum > 0 and not attisdropped and attacl is not null
  ),
  'migration must add no queue policies or column grants'
);

truncate table public.verification_email_jobs, public.password_reset_email_jobs;
set role service_role;
select
  verification_active_depth,
  verification_eligible_depth,
  verification_oldest_eligible_job_age_seconds is null as verification_oldest_is_null,
  password_reset_active_depth,
  password_reset_eligible_depth,
  password_reset_oldest_eligible_job_age_seconds is null as password_reset_oldest_is_null
from public.read_email_queue_backlog_v1() \gset empty_
reset role;
select pg_temp.assert_true(
  :'empty_verification_active_depth' = '0'
  and :'empty_verification_eligible_depth' = '0'
  and :'empty_verification_oldest_is_null' = 't'
  and :'empty_password_reset_active_depth' = '0'
  and :'empty_password_reset_eligible_depth' = '0'
  and :'empty_password_reset_oldest_is_null' = 't',
  'empty queues must return zero depth and null oldest ages'
);

do $$
declare
  denied boolean;
  role_name text;
begin
  foreach role_name in array array['anon', 'authenticated', 'queue_backlog_untrusted'] loop
    denied := false;
    execute pg_catalog.format('set local role %I', role_name);
    begin
      perform * from public.read_email_queue_backlog_v1();
    exception when insufficient_privilege then
      denied := true;
    end;
    reset role;
    if not denied then
      raise exception 'role % unexpectedly executed queue backlog RPC', role_name;
    end if;
  end loop;

  denied := false;
  set local role service_role;
  begin
    perform * from public.verification_email_jobs;
  exception when insufficient_privilege then
    denied := true;
  end;
  reset role;
  if not denied then
    raise exception 'service_role unexpectedly read verification queue directly';
  end if;

  denied := false;
  set local role service_role;
  begin
    perform * from public.password_reset_email_jobs;
  exception when insufficient_privilege then
    denied := true;
  end;
  reset role;
  if not denied then
    raise exception 'service_role unexpectedly read password-reset queue directly';
  end if;
end;
$$;

create schema queue_backlog_shadow;
create table queue_backlog_shadow.verification_email_jobs (status text);
create table queue_backlog_shadow.password_reset_email_jobs (status text);
insert into queue_backlog_shadow.verification_email_jobs values ('queued');
insert into queue_backlog_shadow.password_reset_email_jobs values ('queued');
grant usage on schema queue_backlog_shadow to service_role;
grant select on all tables in schema queue_backlog_shadow to service_role;
set role service_role;
set search_path = queue_backlog_shadow, public, pg_catalog;
select * from public.read_email_queue_backlog_v1() \gset hostile_
reset role;
reset search_path;
select pg_temp.assert_true(
  :'hostile_verification_active_depth' = '0'
  and :'hostile_password_reset_active_depth' = '0',
  'hostile caller search_path must not redirect queue reads'
);
revoke all on all tables in schema queue_backlog_shadow from service_role;
revoke all on schema queue_backlog_shadow from service_role;
drop schema queue_backlog_shadow cascade;

do $$
declare
  sampled_at timestamptz := pg_catalog.statement_timestamp();
  metrics record;
begin
  insert into public.verification_email_jobs (
    id, delivery_mode, user_id, recipient_fingerprint,
    verification_token_hash, verification_token_expires, alias_key_id,
    alias_nonce, intent, plan, status, attempts, next_attempt_at,
    lease_token, lease_expires_at, template_version, app_name, app_url,
    support_email, from_email, terminal_at, created_at, updated_at,
    claim_token_history
  ) values
    ('81000000-0000-4000-8000-000000000001', 'suppressed', null,
     repeat('1',64), repeat('a',64), sampled_at + interval '6 minutes', 'k1',
     'verification_nonce_0001', null, null, 'queued', 0, sampled_at,
     null, null, 'verification-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '10.75 seconds', sampled_at, '{}'::uuid[]),
    ('81000000-0000-4000-8000-000000000002', 'suppressed', null,
     repeat('2',64), repeat('b',64), sampled_at + interval '6 minutes', 'k1',
     'verification_nonce_0002', null, null, 'processing', 1, sampled_at,
     '81100000-0000-4000-8000-000000000002', sampled_at,
     'verification-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '5 seconds', sampled_at,
     array['81100000-0000-4000-8000-000000000002'::uuid]),
    ('81000000-0000-4000-8000-000000000003', 'suppressed', null,
     repeat('3',64), repeat('c',64), sampled_at + interval '6 minutes', 'k1',
     'verification_nonce_0003', null, null, 'queued', 0,
     sampled_at + interval '1 second', null, null, 'verification-v1',
     'Ask Crump', 'https://askcrump.com', 'support@example.test',
     'from@example.test', null, sampled_at - interval '4 seconds', sampled_at,
     '{}'::uuid[]),
    ('81000000-0000-4000-8000-000000000004', 'suppressed', null,
     repeat('4',64), repeat('d',64), sampled_at + interval '6 minutes', 'k1',
     'verification_nonce_0004', null, null, 'processing', 1, sampled_at,
     '81100000-0000-4000-8000-000000000004',
     sampled_at + interval '1 second', 'verification-v1', 'Ask Crump',
     'https://askcrump.com', 'support@example.test', 'from@example.test', null,
     sampled_at - interval '4 seconds', sampled_at,
     array['81100000-0000-4000-8000-000000000004'::uuid]),
    ('81000000-0000-4000-8000-000000000005', 'suppressed', null,
     repeat('5',64), repeat('e',64), sampled_at + interval '6 minutes', 'k1',
     'verification_nonce_0005', null, null, 'queued', 6, sampled_at,
     null, null, 'verification-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '4 seconds', sampled_at,
     array_fill('81100000-0000-4000-8000-000000000005'::uuid, array[6])),
    ('81000000-0000-4000-8000-000000000006', 'suppressed', null,
     repeat('6',64), repeat('f',64), sampled_at + interval '5 minutes', 'k1',
     'verification_nonce_0006', null, null, 'queued', 0, sampled_at,
     null, null, 'verification-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '4 seconds', sampled_at, '{}'::uuid[]),
    ('81000000-0000-4000-8000-000000000007', 'suppressed', null,
     repeat('7',64), repeat('0',64), sampled_at + interval '6 minutes', 'k1',
     'verification_nonce_0007', null, null, 'queued', 0, sampled_at,
     null, null, 'verification-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '23 hours', sampled_at, '{}'::uuid[]),
    ('81000000-0000-4000-8000-000000000008', 'suppressed', null,
     repeat('8',64), repeat('1',64), sampled_at + interval '6 minutes', 'k1',
     'verification_nonce_0008', null, null, 'provider_accepted', 0, sampled_at,
     null, null, 'verification-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', sampled_at,
     sampled_at - interval '4 seconds', sampled_at, '{}'::uuid[]),
    ('81000000-0000-4000-8000-000000000009', 'suppressed', null,
     repeat('9',64), repeat('2',64), sampled_at + interval '6 minutes', 'k1',
     'verification_nonce_0009', null, null, 'queued', 0, sampled_at,
     null, null, 'verification-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at + interval '2 seconds', sampled_at, '{}'::uuid[]),
    ('81000000-0000-4000-8000-000000000010', 'suppressed', null,
     repeat('a',64), repeat('3',64), sampled_at + interval '6 minutes', 'k1',
     'verification_nonce_0010', null, null, 'queued', 0, sampled_at,
     null, null, 'verification-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '3.25 seconds', sampled_at, '{}'::uuid[]);

  insert into public.password_reset_email_jobs (
    id, delivery_mode, user_id, recipient_fingerprint,
    password_reset_token_hash, password_reset_expires, alias_key_id,
    alias_nonce, status, attempts, next_attempt_at, lease_token,
    lease_expires_at, template_version, app_name, app_url, support_email,
    from_email, terminal_at, created_at, updated_at, claim_token_history
  ) values
    ('82000000-0000-4000-8000-000000000001', 'suppressed', null,
     repeat('1',64), repeat('a',64), sampled_at + interval '121 seconds', 'k1',
     'password_reset_nonce_0001', 'queued', 0, sampled_at, null, null,
     'password-reset-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '20.75 seconds', sampled_at, '{}'::uuid[]),
    ('82000000-0000-4000-8000-000000000002', 'suppressed', null,
     repeat('2',64), repeat('b',64), sampled_at + interval '121 seconds', 'k1',
     'password_reset_nonce_0002', 'processing', 1, sampled_at,
     '82100000-0000-4000-8000-000000000002', sampled_at,
     'password-reset-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '5 seconds', sampled_at,
     array['82100000-0000-4000-8000-000000000002'::uuid]),
    ('82000000-0000-4000-8000-000000000003', 'suppressed', null,
     repeat('3',64), repeat('c',64), sampled_at + interval '121 seconds', 'k1',
     'password_reset_nonce_0003', 'queued', 0, sampled_at + interval '1 second',
     null, null, 'password-reset-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '4 seconds', sampled_at, '{}'::uuid[]),
    ('82000000-0000-4000-8000-000000000004', 'suppressed', null,
     repeat('4',64), repeat('d',64), sampled_at + interval '121 seconds', 'k1',
     'password_reset_nonce_0004', 'processing', 1, sampled_at,
     '82100000-0000-4000-8000-000000000004',
     sampled_at + interval '1 second', 'password-reset-v1', 'Ask Crump',
     'https://askcrump.com', 'support@example.test', 'from@example.test', null,
     sampled_at - interval '4 seconds', sampled_at,
     array['82100000-0000-4000-8000-000000000004'::uuid]),
    ('82000000-0000-4000-8000-000000000005', 'suppressed', null,
     repeat('5',64), repeat('e',64), sampled_at + interval '121 seconds', 'k1',
     'password_reset_nonce_0005', 'queued', 6, sampled_at, null, null,
     'password-reset-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '4 seconds', sampled_at,
     array_fill('82100000-0000-4000-8000-000000000005'::uuid, array[6])),
    ('82000000-0000-4000-8000-000000000006', 'suppressed', null,
     repeat('6',64), repeat('f',64), sampled_at + interval '120 seconds', 'k1',
     'password_reset_nonce_0006', 'queued', 0, sampled_at, null, null,
     'password-reset-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '4 seconds', sampled_at, '{}'::uuid[]),
    ('82000000-0000-4000-8000-000000000007', 'suppressed', null,
     repeat('7',64), repeat('0',64), sampled_at + interval '121 seconds', 'k1',
     'password_reset_nonce_0007', 'queued', 0, sampled_at, null, null,
     'password-reset-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '55 minutes', sampled_at, '{}'::uuid[]),
    ('82000000-0000-4000-8000-000000000008', 'suppressed', null,
     repeat('8',64), repeat('1',64), sampled_at + interval '121 seconds', 'k1',
     'password_reset_nonce_0008', 'provider_accepted', 0, sampled_at, null, null,
     'password-reset-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', sampled_at,
     sampled_at - interval '4 seconds', sampled_at, '{}'::uuid[]),
    ('82000000-0000-4000-8000-000000000009', 'suppressed', null,
     repeat('9',64), repeat('2',64), sampled_at + interval '121 seconds', 'k1',
     'password_reset_nonce_0009', 'queued', 0, sampled_at, null, null,
     'password-reset-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at + interval '2 seconds', sampled_at, '{}'::uuid[]),
    ('82000000-0000-4000-8000-000000000010', 'suppressed', null,
     repeat('a',64), repeat('3',64), sampled_at + interval '121 seconds', 'k1',
     'password_reset_nonce_0010', 'queued', 0, sampled_at, null, null,
     'password-reset-v1', 'Ask Crump', 'https://askcrump.com',
     'support@example.test', 'from@example.test', null,
     sampled_at - interval '3.25 seconds', sampled_at, '{}'::uuid[]);

  select * into metrics from public.read_email_queue_backlog_v1();
  if metrics.verification_active_depth <> 9
     or metrics.verification_eligible_depth <> 4
     or metrics.verification_oldest_eligible_job_age_seconds <> 10
     or metrics.password_reset_active_depth <> 9
     or metrics.password_reset_eligible_depth <> 4
     or metrics.password_reset_oldest_eligible_job_age_seconds <> 20 then
    raise exception 'mixed eligibility metrics were %, expected 9/4/10 and 9/4/20',
      row_to_json(metrics);
  end if;
end;
$$;

select pg_temp.assert_true(
  (
    select pg_catalog.pg_typeof(verification_active_depth) = 'bigint'::regtype
      and pg_catalog.pg_typeof(verification_eligible_depth) = 'bigint'::regtype
      and pg_catalog.pg_typeof(verification_oldest_eligible_job_age_seconds) = 'bigint'::regtype
      and pg_catalog.pg_typeof(password_reset_active_depth) = 'bigint'::regtype
      and pg_catalog.pg_typeof(password_reset_eligible_depth) = 'bigint'::regtype
      and pg_catalog.pg_typeof(password_reset_oldest_eligible_job_age_seconds) = 'bigint'::regtype
    from public.read_email_queue_backlog_v1()
  ),
  'all six metrics must be bigint'
);

do $$
declare
  verification_queued_plan json;
  verification_processing_plan json;
  password_queued_plan json;
  password_processing_plan json;
begin
  set local enable_seqscan = off;
  execute $plan$
    explain (format json)
    select created_at from public.verification_email_jobs
    where status = 'queued'
      and next_attempt_at <= statement_timestamp()
      and attempts < 6
      and verification_token_expires > statement_timestamp() + interval '5 minutes'
      and created_at > statement_timestamp() - interval '23 hours'
  $plan$ into verification_queued_plan;
  execute $plan$
    explain (format json)
    select created_at from public.verification_email_jobs
    where status = 'processing'
      and lease_expires_at <= statement_timestamp()
      and attempts < 6
      and verification_token_expires > statement_timestamp() + interval '5 minutes'
      and created_at > statement_timestamp() - interval '23 hours'
  $plan$ into verification_processing_plan;
  execute $plan$
    explain (format json)
    select created_at from public.password_reset_email_jobs
    where status = 'queued'
      and next_attempt_at <= statement_timestamp()
      and attempts < 6
      and password_reset_expires > statement_timestamp() + interval '120 seconds'
      and created_at > statement_timestamp() - interval '55 minutes'
  $plan$ into password_queued_plan;
  execute $plan$
    explain (format json)
    select created_at from public.password_reset_email_jobs
    where status = 'processing'
      and lease_expires_at <= statement_timestamp()
      and attempts < 6
      and password_reset_expires > statement_timestamp() + interval '120 seconds'
      and created_at > statement_timestamp() - interval '55 minutes'
  $plan$ into password_processing_plan;

  if pg_catalog.strpos(
       verification_queued_plan::text, 'verification_email_jobs_ready_idx'
     ) = 0
     or pg_catalog.strpos(
       verification_processing_plan::text,
       'verification_email_jobs_expired_lease_idx'
     ) = 0
     or pg_catalog.strpos(
       password_queued_plan::text, 'password_reset_email_jobs_ready_idx'
     ) = 0
     or pg_catalog.strpos(
       password_processing_plan::text,
       'password_reset_email_jobs_expired_lease_idx'
     ) = 0 then
    raise exception 'representative queue plans did not use all four partial indexes';
  end if;
end;
$$;

truncate table public.verification_email_jobs, public.password_reset_email_jobs;
do $$
declare
  sampled_at timestamptz := pg_catalog.statement_timestamp();
  metrics record;
begin
  insert into public.verification_email_jobs (
    id, delivery_mode, recipient_fingerprint, verification_token_hash,
    verification_token_expires, alias_key_id, alias_nonce, status,
    template_version, app_name, app_url, support_email, from_email,
    next_attempt_at, created_at, updated_at
  ) values (
    '83000000-0000-4000-8000-000000000001', 'suppressed', repeat('1',64),
    repeat('a',64), sampled_at + interval '6 minutes', 'k1',
    'future_created_nonce_01', 'queued', 'verification-v1', 'Ask Crump',
    'https://askcrump.com', 'support@example.test', 'from@example.test',
    sampled_at, sampled_at + interval '2 seconds', sampled_at
  );
  insert into public.password_reset_email_jobs (
    id, delivery_mode, recipient_fingerprint, password_reset_token_hash,
    password_reset_expires, alias_key_id, alias_nonce, status,
    template_version, app_name, app_url, support_email, from_email,
    next_attempt_at, created_at, updated_at
  ) values (
    '84000000-0000-4000-8000-000000000001', 'suppressed', repeat('1',64),
    repeat('a',64), sampled_at + interval '121 seconds', 'k1',
    'future_created_nonce_02', 'queued', 'password-reset-v1', 'Ask Crump',
    'https://askcrump.com', 'support@example.test', 'from@example.test',
    sampled_at, sampled_at + interval '2 seconds', sampled_at
  );
  select * into metrics from public.read_email_queue_backlog_v1();
  if metrics.verification_eligible_depth <> 1
     or metrics.verification_oldest_eligible_job_age_seconds <> 0
     or metrics.password_reset_eligible_depth <> 1
     or metrics.password_reset_oldest_eligible_job_age_seconds <> 0 then
    raise exception 'future created_at ages were not clamped to zero: %',
      row_to_json(metrics);
  end if;
end;
$$;

truncate table public.verification_email_jobs, public.password_reset_email_jobs;
select pg_temp.assert_true(
  (
    select verification_active_depth = 0
      and verification_eligible_depth = 0
      and verification_oldest_eligible_job_age_seconds is null
      and password_reset_active_depth = 0
      and password_reset_eligible_depth = 0
      and password_reset_oldest_eligible_job_age_seconds is null
    from public.read_email_queue_backlog_v1()
  ),
  'empty queues must remain exact after mixed fixtures'
);
