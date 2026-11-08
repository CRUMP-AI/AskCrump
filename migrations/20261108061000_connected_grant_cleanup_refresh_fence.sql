begin;

select pg_catalog.set_config('search_path', 'pg_catalog,public', true);
select pg_catalog.set_config('quote_all_identifiers', 'off', true);

create or replace function pg_temp.connected_cleanup_target_fingerprint()
returns text language sql stable set search_path = '' as $fingerprint$
  select pg_catalog.md5(
    pg_catalog.string_agg(item.value::text, E'\n' order by item.value::text)
  )
  from (
    select pg_catalog.jsonb_build_array(
      'schema', namespace_row.nspname,
      pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text, ''),
      pg_catalog.obj_description(namespace_row.oid, 'pg_namespace')
    ) as value
    from pg_catalog.pg_namespace as namespace_row
    where namespace_row.nspname = 'connected_app_private'

    union all
    select pg_catalog.jsonb_build_array(
      'relation', namespace_row.nspname, class_row.relname, class_row.relkind,
      class_row.relpersistence, class_row.relrowsecurity,
      class_row.relforcerowsecurity, class_row.relreplident,
      pg_catalog.pg_get_userbyid(class_row.relowner),
      coalesce(class_row.relacl::text, ''), coalesce(class_row.reloptions::text, ''),
      pg_catalog.obj_description(class_row.oid, 'pg_class')
    )
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname in (
        'credential_refresh_lease_history', 'provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history'
      )

    union all
    select pg_catalog.jsonb_build_array(
      'column', class_row.relname, attribute_row.attnum, attribute_row.attname,
      pg_catalog.format_type(attribute_row.atttypid, attribute_row.atttypmod),
      attribute_row.attnotnull, attribute_row.attidentity,
      attribute_row.attgenerated, attribute_row.attstorage,
      attribute_row.attcompression, attribute_row.attstattarget,
      coalesce(attribute_row.attoptions::text, ''),
      coalesce(pg_catalog.pg_get_expr(default_row.adbin, default_row.adrelid), ''),
      coalesce(attribute_row.attacl::text, ''),
      pg_catalog.col_description(class_row.oid, attribute_row.attnum)
    )
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row on class_row.oid = attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    left join pg_catalog.pg_attrdef as default_row
      on default_row.adrelid = attribute_row.attrelid
     and default_row.adnum = attribute_row.attnum
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname in (
        'credential_refresh_lease_history', 'provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history'
      )
      and attribute_row.attnum > 0 and not attribute_row.attisdropped

    union all
    select pg_catalog.jsonb_build_array(
      'constraint', class_row.relname, constraint_row.conname,
      constraint_row.contype, constraint_row.condeferrable,
      constraint_row.condeferred, constraint_row.convalidated,
      pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
    )
    from pg_catalog.pg_constraint as constraint_row
    join pg_catalog.pg_class as class_row on class_row.oid = constraint_row.conrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname in (
        'credential_refresh_lease_history', 'provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history'
      )

    union all
    select pg_catalog.jsonb_build_array(
      'index', table_row.relname, index_row.relname,
      index_meta.indisunique, index_meta.indisprimary, index_meta.indisvalid,
      index_meta.indisready, index_meta.indislive,
      pg_catalog.pg_get_indexdef(index_row.oid)
    )
    from pg_catalog.pg_index as index_meta
    join pg_catalog.pg_class as index_row on index_row.oid = index_meta.indexrelid
    join pg_catalog.pg_class as table_row on table_row.oid = index_meta.indrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = table_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and table_row.relname in (
        'credential_refresh_lease_history', 'provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history'
      )

    union all
    select pg_catalog.jsonb_build_array(
      'function', namespace_row.nspname, procedure_row.proname,
      pg_catalog.pg_get_function_identity_arguments(procedure_row.oid),
      pg_catalog.pg_get_userbyid(procedure_row.proowner), procedure_row.prosecdef,
      procedure_row.provolatile, procedure_row.proparallel,
      coalesce(procedure_row.proconfig::text, ''),
      coalesce(procedure_row.proacl::text, ''),
      pg_catalog.obj_description(procedure_row.oid, 'pg_proc'),
      pg_catalog.pg_get_functiondef(procedure_row.oid)
    )
    from pg_catalog.pg_proc as procedure_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = procedure_row.pronamespace
    where namespace_row.nspname in ('public', 'connected_app_private')
      and procedure_row.proname in (
        'cleanup_digest_uuid_v1', 'queue_credential_cleanup_v1',
        'queue_provisional_cleanup_v1', 'flag_owner_cleanup_v1',
        'connected_app_credential_claim_refresh_v1',
        'connected_app_credential_finish_refresh_v1',
        'connected_app_credential_quarantine_refresh_v1',
        'connected_app_credential_claim_refresh_v2',
        'connected_app_credential_finish_refresh_v2',
        'connected_app_credential_commit_refresh_v2',
        'connected_app_credential_quarantine_refresh_v2',
        'connected_app_provider_cleanup_begin_v1',
        'connected_app_provider_cleanup_attach_v1',
        'connected_app_provider_cleanup_release_v1',
        'connected_app_provider_cleanup_release_recover_v1',
        'connected_app_provider_cleanup_claim_v1',
        'connected_app_provider_cleanup_recover_v1',
        'connected_app_provider_cleanup_finish_v1'
      )

    union all
    select pg_catalog.jsonb_build_array(
      'trigger', namespace_row.nspname, class_row.relname, trigger_row.tgname,
      trigger_row.tgenabled, pg_catalog.pg_get_triggerdef(trigger_row.oid, true)
    )
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid = trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where not trigger_row.tgisinternal
      and (
        (
          namespace_row.nspname = 'connected_app_private'
          and class_row.relname in (
            'credential_refresh_lease_history', 'provider_grant_cleanup_jobs',
            'provider_grant_cleanup_claim_history', 'credential_envelopes',
            'oauth_provisional_credentials'
          )
        )
        or (
          namespace_row.nspname = 'public' and class_row.relname = 'users'
          and trigger_row.tgname = 'connected_cleanup_owner_before_delete'
        )
      )

    union all
    select pg_catalog.jsonb_build_array(
      'policy', schemaname, tablename, policyname, permissive, roles::text,
      cmd, coalesce(qual, ''), coalesce(with_check, '')
    )
    from pg_catalog.pg_policies
    where schemaname = 'connected_app_private'
      and tablename in (
        'credential_refresh_lease_history', 'provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history'
      )

    union all
    select pg_catalog.jsonb_build_array(
      'rule', namespace_row.nspname, class_row.relname, rewrite_row.rulename,
      rewrite_row.ev_enabled, pg_catalog.pg_get_ruledef(rewrite_row.oid, true)
    )
    from pg_catalog.pg_rewrite as rewrite_row
    join pg_catalog.pg_class as class_row on class_row.oid = rewrite_row.ev_class
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where namespace_row.nspname = 'connected_app_private'
      and class_row.relname in (
        'credential_refresh_lease_history', 'provider_grant_cleanup_jobs',
        'provider_grant_cleanup_claim_history'
      )
      and rewrite_row.rulename <> '_RETURN'

    union all
    select pg_catalog.jsonb_build_array(
      'publication', publication_row.pubname, publication_row.puballtables,
      publication_row.pubinsert, publication_row.pubupdate,
      publication_row.pubdelete, publication_row.pubtruncate,
      coalesce(namespace_row.nspname, ''), coalesce(class_row.relname, '')
    )
    from pg_catalog.pg_publication as publication_row
    left join pg_catalog.pg_publication_rel as publication_rel
      on publication_rel.prpubid = publication_row.oid
    left join pg_catalog.pg_class as class_row on class_row.oid = publication_rel.prrelid
    left join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where publication_row.puballtables
       or (
         namespace_row.nspname = 'connected_app_private'
         and class_row.relname in (
           'credential_refresh_lease_history', 'provider_grant_cleanup_jobs',
           'provider_grant_cleanup_claim_history'
         )
       )

    union all
    select pg_catalog.jsonb_build_array(
      'role', role_row.rolname, role_row.rolsuper,
      role_row.rolcreaterole, role_row.rolcreatedb, role_row.rolcanlogin,
      role_row.rolreplication, role_row.rolbypassrls
    )
    from pg_catalog.pg_roles as role_row
    where role_row.rolname in ('postgres', 'service_role', 'authenticated', 'anon')

    union all
    select pg_catalog.jsonb_build_array(
      'membership', member_role.rolname, granted_role.rolname,
      membership.admin_option, membership.inherit_option,
      membership.set_option, grantor_role.rolname
    )
    from pg_catalog.pg_auth_members as membership
    join pg_catalog.pg_roles as member_role on member_role.oid = membership.member
    join pg_catalog.pg_roles as granted_role on granted_role.oid = membership.roleid
    join pg_catalog.pg_roles as grantor_role on grantor_role.oid = membership.grantor
    where member_role.rolname in ('postgres', 'service_role', 'authenticated', 'anon')
       or granted_role.rolname in ('postgres', 'service_role', 'authenticated', 'anon')
  ) as item
$fingerprint$;

-- This successor never repairs an unknown base.  The runtime-v2 target and
-- both encrypted custody stores must be the exact reviewed predecessors.
do $preflight$
declare
  target_count integer;
  observed_target_fingerprint text;
begin
  if pg_catalog.to_regclass('connected_app_private.connections') is null
     or pg_catalog.to_regclass('connected_app_private.credential_envelopes') is null
     or pg_catalog.to_regclass('connected_app_private.oauth_provisional_credentials') is null
     or pg_catalog.obj_description(
          pg_catalog.to_regprocedure(
            'public.connected_app_claim_action_v2(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,text,text,text,bigint,uuid,uuid,integer,timestamp with time zone)'
          ), 'pg_proc'
        ) is distinct from
          'ASK_CRUMP_CONNECTED_APP_CLAIM_ACTION_V2_INVOCATION_BOUND_NO_LEGACY_FALLBACK'
     or pg_catalog.obj_description(
          pg_catalog.to_regclass('connected_app_private.credential_envelopes'), 'pg_class'
        ) is distinct from
          'ASK_CRUMP_CONNECTED_CREDENTIAL_ENVELOPES_V1_ENCRYPTED_REFRESH_ONLY'
     or pg_catalog.obj_description(
          pg_catalog.to_regclass('connected_app_private.oauth_provisional_credentials'), 'pg_class'
        ) is distinct from
          'ASK_CRUMP_CONNECTED_OAUTH_PROVISIONAL_CREDENTIALS_V1_ENCRYPTED_REFRESH_ONLY'
     or pg_catalog.has_function_privilege(
          'service_role',
          'public.connected_app_claim_action_v1(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,text,text,bigint,uuid,uuid,integer,timestamp with time zone)',
          'EXECUTE'
        )
     or not exists (
          select 1 from pg_catalog.pg_proc as function_row
          where function_row.oid =
            pg_catalog.to_regprocedure('connected_app_private.owner_lock_v1(uuid)')
            and pg_catalog.md5(function_row.prosrc) =
              'ab70e27e21f3e90e3cf6185638485d75'
            and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
            and function_row.prosecdef
            and function_row.proconfig is not distinct from
              array['search_path=""']::text[]
            and function_row.proacl::text = '{postgres=X/postgres}'
        )
     or not exists (
          select 1 from pg_catalog.pg_proc as function_row
          where function_row.oid =
            pg_catalog.to_regprocedure('public.delete_user_account(uuid,text)')
            and pg_catalog.md5(function_row.prosrc) =
              '7512a874aa85ffd7770d44a2e3b530d7'
            and pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
            and function_row.prosecdef
            and function_row.proconfig is not distinct from
              array['search_path=""']::text[]
            and function_row.proacl::text =
              '{postgres=X/postgres,service_role=X/postgres}'
        ) then
    raise exception 'connected cleanup/refresh exact predecessor drifted'
      using errcode = '55000';
  end if;

  if exists (
    select 1
    from pg_catalog.pg_publication as publication_row
    left join pg_catalog.pg_publication_rel as publication_rel
      on publication_rel.prpubid = publication_row.oid
    left join pg_catalog.pg_class as class_row
      on class_row.oid = publication_rel.prrelid
    left join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = class_row.relnamespace
    where publication_row.puballtables
       or (
         namespace_row.nspname = 'connected_app_private'
         and class_row.relname in (
           'credential_refresh_lease_history', 'provider_grant_cleanup_jobs',
           'provider_grant_cleanup_claim_history'
         )
       )
  ) then
    raise exception 'connected cleanup/refresh publication exposure refused'
      using errcode = '55000';
  end if;

  select pg_catalog.count(*) into target_count
  from pg_catalog.pg_class as class_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid = class_row.relnamespace
  where namespace_row.nspname = 'connected_app_private'
    and class_row.relname in (
      'credential_refresh_lease_history', 'provider_grant_cleanup_jobs',
      'provider_grant_cleanup_claim_history'
    ) and class_row.relkind = 'r';
  if target_count not in (0, 3) then
    raise exception 'connected cleanup/refresh state is partial; refusing repair'
      using errcode = '55000';
  end if;
  if target_count = 3 and (
       pg_catalog.obj_description(
         pg_catalog.to_regclass('connected_app_private.credential_refresh_lease_history'),
         'pg_class'
       ) is distinct from
         'ASK_CRUMP_CONNECTED_REFRESH_LEASE_HISTORY_V2_PERMANENT_REPLAY_FENCE'
       or pg_catalog.obj_description(
         pg_catalog.to_regclass('connected_app_private.provider_grant_cleanup_jobs'),
         'pg_class'
       ) is distinct from
         'ASK_CRUMP_CONNECTED_PROVIDER_GRANT_CLEANUP_V1_ENCRYPTED_DURABLE_OUTBOX'
       or pg_catalog.obj_description(
         pg_catalog.to_regclass(
           'connected_app_private.provider_grant_cleanup_claim_history'
         ), 'pg_class'
       ) is distinct from
         'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_CLAIM_HISTORY_V1_PERMANENT_REPLAY_FENCE'
       or pg_catalog.obj_description(
         pg_catalog.to_regprocedure(
           'public.connected_app_credential_claim_refresh_v2(text,text,uuid,integer)'
         ), 'pg_proc'
       ) is distinct from
         'ASK_CRUMP_CONNECTED_REFRESH_CLAIM_V2_EXPIRED_ID_NEVER_REVIVES'
       or pg_catalog.obj_description(
         pg_catalog.to_regprocedure(
           'public.connected_app_provider_cleanup_claim_v1(uuid,integer)'
         ), 'pg_proc'
       ) is distinct from
         'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_CLAIM_V1_ONE_WINNER'
     ) then
    raise exception 'connected cleanup/refresh exact target drifted; refusing repair'
      using errcode = '55000';
  end if;
  if target_count = 3 then
    observed_target_fingerprint := pg_temp.connected_cleanup_target_fingerprint();
    if observed_target_fingerprint is distinct from 'e90e794c75b45084d89d6b1247d3287e' then
      raise exception 'connected cleanup/refresh target fingerprint drifted: %',
        observed_target_fingerprint using errcode = '55000';
    end if;
  end if;
end;
$preflight$;

create table if not exists connected_app_private.credential_refresh_lease_history (
  lease_id uuid primary key,
  credential_handle_sha256 text not null
    check (credential_handle_sha256 ~ '^[0-9a-f]{64}$'),
  expected_record_binding_sha256 text not null
    check (expected_record_binding_sha256 ~ '^[0-9a-f]{64}$'),
  outcome text not null check (outcome in ('expired', 'finished', 'quarantined')),
  issued_at timestamptz not null,
  expires_at timestamptz not null,
  retired_at timestamptz not null,
  constraint connected_refresh_history_lifetime check (
    expires_at > issued_at and retired_at >= issued_at
  )
);
comment on table connected_app_private.credential_refresh_lease_history is
  'ASK_CRUMP_CONNECTED_REFRESH_LEASE_HISTORY_V2_PERMANENT_REPLAY_FENCE';
create index if not exists connected_refresh_history_handle_idx
  on connected_app_private.credential_refresh_lease_history(
    credential_handle_sha256, retired_at desc
  );
alter table connected_app_private.credential_refresh_lease_history enable row level security;
alter table connected_app_private.credential_refresh_lease_history force row level security;

create table if not exists connected_app_private.provider_grant_cleanup_jobs (
  cleanup_id uuid primary key,
  owner_id uuid,
  owner_id_sha256 text not null check (owner_id_sha256 ~ '^[0-9a-f]{64}$'),
  connection_id uuid,
  connection_id_sha256 text not null check (connection_id_sha256 ~ '^[0-9a-f]{64}$'),
  exchange_id uuid,
  provider text not null check (provider in ('google', 'microsoft')),
  source_kind text not null check (
    source_kind in ('exchange_unknown', 'provisional', 'credential')
  ),
  source_binding_sha256 text not null unique
    check (source_binding_sha256 ~ '^[0-9a-f]{64}$'),
  status text not null check (
    status in (
      'exchange_pending', 'retained', 'cleanup_pending', 'claimed',
      'retry', 'succeeded', 'released', 'user_action_required'
    )
  ),
  encrypted_record jsonb,
  claim_id uuid,
  claim_expires_at timestamptz,
  attempts integer not null default 0 check (attempts between 0 and 32),
  deadline_at timestamptz,
  provider_receipt_sha256 text
    check (provider_receipt_sha256 is null or provider_receipt_sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null,
  updated_at timestamptz not null,
  finished_at timestamptz,
  constraint connected_cleanup_claim_shape check (
    (status = 'claimed' and claim_id is not null and claim_expires_at is not null)
    or (status <> 'claimed' and claim_id is null and claim_expires_at is null)
  ),
  constraint connected_cleanup_secret_shape check (
    (source_kind = 'exchange_unknown' and encrypted_record is null)
    or (
      source_kind in ('provisional', 'credential')
      and (
        (
          status in ('succeeded', 'released', 'user_action_required')
          and encrypted_record is null
        )
        or (
          status not in ('succeeded', 'released', 'user_action_required')
          and encrypted_record is not null
        )
      )
    )
  ),
  constraint connected_cleanup_time_order check (
    updated_at >= created_at and (finished_at is null or finished_at >= created_at)
  )
);
comment on table connected_app_private.provider_grant_cleanup_jobs is
  'ASK_CRUMP_CONNECTED_PROVIDER_GRANT_CLEANUP_V1_ENCRYPTED_DURABLE_OUTBOX';
create index if not exists connected_provider_cleanup_claim_idx
  on connected_app_private.provider_grant_cleanup_jobs(status, updated_at, cleanup_id)
  where status in ('cleanup_pending', 'retry', 'claimed');
create index if not exists connected_provider_cleanup_owner_idx
  on connected_app_private.provider_grant_cleanup_jobs(owner_id, connection_id)
  where owner_id is not null;
create unique index if not exists connected_provider_cleanup_live_claim_idx
  on connected_app_private.provider_grant_cleanup_jobs(claim_id)
  where claim_id is not null;
alter table connected_app_private.provider_grant_cleanup_jobs enable row level security;
alter table connected_app_private.provider_grant_cleanup_jobs force row level security;

create table if not exists connected_app_private.provider_grant_cleanup_claim_history (
  claim_id uuid primary key,
  cleanup_id uuid not null,
  source_binding_sha256 text not null
    check (source_binding_sha256 ~ '^[0-9a-f]{64}$'),
  outcome text not null check (
    outcome in ('expired', 'succeeded', 'retry', 'user_action_required')
  ),
  retired_at timestamptz not null
);
comment on table connected_app_private.provider_grant_cleanup_claim_history is
  'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_CLAIM_HISTORY_V1_PERMANENT_REPLAY_FENCE';
create index if not exists connected_provider_cleanup_claim_history_job_idx
  on connected_app_private.provider_grant_cleanup_claim_history(cleanup_id, retired_at desc);
alter table connected_app_private.provider_grant_cleanup_claim_history enable row level security;
alter table connected_app_private.provider_grant_cleanup_claim_history force row level security;

create or replace function connected_app_private.cleanup_digest_uuid_v1(p_value uuid)
returns text language sql immutable security definer set search_path = '' as $fn$
  select pg_catalog.encode(
    pg_catalog.sha256(pg_catalog.convert_to(p_value::text, 'UTF8')), 'hex'
  )
$fn$;

create or replace function connected_app_private.queue_credential_cleanup_v1()
returns trigger language plpgsql security definer set search_path = '' as $fn$
declare
  cleanup_value uuid := pg_catalog.gen_random_uuid();
begin
  -- Serialize with claim/finish before a ciphertext-owning row disappears.
  -- A claim ID is globally one-use even when direct revocation (rather than
  -- owner deletion) wins this race.
  perform 1
  from connected_app_private.provider_grant_cleanup_jobs as job
  where job.source_binding_sha256 = old.record_binding_sha256
  for update;
  insert into connected_app_private.provider_grant_cleanup_claim_history (
    claim_id, cleanup_id, source_binding_sha256, outcome, retired_at
  )
  select job.claim_id, job.cleanup_id, job.source_binding_sha256,
         'expired', pg_catalog.clock_timestamp()
  from connected_app_private.provider_grant_cleanup_jobs as job
  where job.source_binding_sha256 = old.record_binding_sha256
    and job.claim_id is not null
  on conflict (claim_id) do nothing;
  insert into connected_app_private.provider_grant_cleanup_jobs (
    cleanup_id, owner_id, owner_id_sha256, connection_id, connection_id_sha256,
    exchange_id, provider, source_kind, source_binding_sha256, status,
    encrypted_record, created_at, updated_at
  ) values (
    cleanup_value,
    null,
    connected_app_private.cleanup_digest_uuid_v1(old.owner_id),
    null,
    connected_app_private.cleanup_digest_uuid_v1(old.connection_id),
    null, old.provider, 'credential', old.record_binding_sha256,
    'cleanup_pending', pg_catalog.to_jsonb(old),
    pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp()
  ) on conflict (source_binding_sha256) do update set
    status = case
      when connected_app_private.provider_grant_cleanup_jobs.status in
        ('succeeded', 'released', 'user_action_required')
      then connected_app_private.provider_grant_cleanup_jobs.status
      else 'cleanup_pending' end,
    owner_id = coalesce(
      connected_app_private.provider_grant_cleanup_jobs.owner_id,
      excluded.owner_id
    ),
    connection_id = coalesce(
      connected_app_private.provider_grant_cleanup_jobs.connection_id,
      excluded.connection_id
    ),
    encrypted_record = case
      when connected_app_private.provider_grant_cleanup_jobs.status in
        ('succeeded', 'released', 'user_action_required')
      then connected_app_private.provider_grant_cleanup_jobs.encrypted_record
      else excluded.encrypted_record end,
    claim_id = case
      when connected_app_private.provider_grant_cleanup_jobs.status in
        ('succeeded', 'released', 'user_action_required')
      then connected_app_private.provider_grant_cleanup_jobs.claim_id
      else null end,
    claim_expires_at = case
      when connected_app_private.provider_grant_cleanup_jobs.status in
        ('succeeded', 'released', 'user_action_required')
      then connected_app_private.provider_grant_cleanup_jobs.claim_expires_at
      else null end,
    updated_at = pg_catalog.clock_timestamp();
  return old;
end;
$fn$;

create or replace function connected_app_private.queue_provisional_cleanup_v1()
returns trigger language plpgsql security definer set search_path = '' as $fn$
declare
  cleanup_value uuid := pg_catalog.gen_random_uuid();
begin
  perform 1
  from connected_app_private.provider_grant_cleanup_jobs as job
  where job.source_binding_sha256 = old.record_binding_sha256
  for update;
  insert into connected_app_private.provider_grant_cleanup_claim_history (
    claim_id, cleanup_id, source_binding_sha256, outcome, retired_at
  )
  select job.claim_id, job.cleanup_id, job.source_binding_sha256,
         'expired', pg_catalog.clock_timestamp()
  from connected_app_private.provider_grant_cleanup_jobs as job
  where job.source_binding_sha256 = old.record_binding_sha256
    and job.claim_id is not null
  on conflict (claim_id) do nothing;
  insert into connected_app_private.provider_grant_cleanup_jobs (
    cleanup_id, owner_id, owner_id_sha256, connection_id, connection_id_sha256,
    exchange_id, provider, source_kind, source_binding_sha256, status,
    encrypted_record, created_at, updated_at
  ) values (
    cleanup_value,
    null,
    connected_app_private.cleanup_digest_uuid_v1(old.owner_id),
    null,
    connected_app_private.cleanup_digest_uuid_v1(old.connection_id),
    old.exchange_id, old.provider, 'provisional', old.record_binding_sha256,
    'cleanup_pending', pg_catalog.to_jsonb(old),
    pg_catalog.clock_timestamp(), pg_catalog.clock_timestamp()
  ) on conflict (source_binding_sha256) do update set
    status = case
      when connected_app_private.provider_grant_cleanup_jobs.status in
        ('succeeded', 'released', 'user_action_required')
      then connected_app_private.provider_grant_cleanup_jobs.status
      else 'cleanup_pending' end,
    owner_id = coalesce(
      connected_app_private.provider_grant_cleanup_jobs.owner_id,
      excluded.owner_id
    ),
    connection_id = coalesce(
      connected_app_private.provider_grant_cleanup_jobs.connection_id,
      excluded.connection_id
    ),
    encrypted_record = case
      when connected_app_private.provider_grant_cleanup_jobs.status in
        ('succeeded', 'released', 'user_action_required')
      then connected_app_private.provider_grant_cleanup_jobs.encrypted_record
      else excluded.encrypted_record end,
    claim_id = case
      when connected_app_private.provider_grant_cleanup_jobs.status in
        ('succeeded', 'released', 'user_action_required')
      then connected_app_private.provider_grant_cleanup_jobs.claim_id
      else null end,
    claim_expires_at = case
      when connected_app_private.provider_grant_cleanup_jobs.status in
        ('succeeded', 'released', 'user_action_required')
      then connected_app_private.provider_grant_cleanup_jobs.claim_expires_at
      else null end,
    updated_at = pg_catalog.clock_timestamp();
  return old;
end;
$fn$;

create or replace function connected_app_private.flag_owner_cleanup_v1()
returns trigger language plpgsql security definer set search_path = '' as $fn$
begin
  perform connected_app_private.owner_lock_v1(old.id);
  perform 1
  from connected_app_private.provider_grant_cleanup_jobs as job
  where job.owner_id = old.id
  for update;

  insert into connected_app_private.provider_grant_cleanup_claim_history (
    claim_id, cleanup_id, source_binding_sha256, outcome, retired_at
  )
  select job.claim_id, job.cleanup_id, job.source_binding_sha256,
         'expired', pg_catalog.clock_timestamp()
  from connected_app_private.provider_grant_cleanup_jobs as job
  where job.owner_id = old.id and job.claim_id is not null
  on conflict (claim_id) do nothing;

  update connected_app_private.provider_grant_cleanup_jobs as job
  set status = case
        when job.source_kind = 'exchange_unknown'
          then 'user_action_required'
        when job.status in (
          'retained', 'exchange_pending', 'cleanup_pending', 'claimed', 'retry'
        )
          then 'cleanup_pending'
        else job.status
      end,
      owner_id = null,
      connection_id = null,
      encrypted_record = case when job.source_kind = 'exchange_unknown'
        then null else job.encrypted_record end,
      claim_id = null,
      claim_expires_at = null,
      finished_at = case when job.source_kind = 'exchange_unknown'
        then pg_catalog.clock_timestamp() else job.finished_at end,
      updated_at = pg_catalog.clock_timestamp()
  where job.owner_id = old.id
    and job.status not in ('succeeded', 'released', 'user_action_required');
  return old;
end;
$fn$;

drop trigger if exists connected_cleanup_credential_before_delete
  on connected_app_private.credential_envelopes;
create trigger connected_cleanup_credential_before_delete
before delete on connected_app_private.credential_envelopes
for each row execute function connected_app_private.queue_credential_cleanup_v1();
drop trigger if exists connected_cleanup_provisional_before_delete
  on connected_app_private.oauth_provisional_credentials;
create trigger connected_cleanup_provisional_before_delete
before delete on connected_app_private.oauth_provisional_credentials
for each row execute function connected_app_private.queue_provisional_cleanup_v1();
drop trigger if exists connected_cleanup_owner_before_delete on public.users;
create trigger connected_cleanup_owner_before_delete
before delete on public.users
for each row execute function connected_app_private.flag_owner_cleanup_v1();

create or replace function public.connected_app_credential_claim_refresh_v2(
  p_credential_handle_sha256 text,
  p_expected_record_binding_sha256 text,
  p_lease_id uuid,
  p_lease_seconds integer
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare
  envelope connected_app_private.credential_envelopes%rowtype;
  connection_row connected_app_private.connections%rowtype;
  lease connected_app_private.credential_refresh_leases%rowtype;
  retired connected_app_private.credential_refresh_lease_history%rowtype;
  database_now timestamptz := pg_catalog.clock_timestamp();
begin
  if p_credential_handle_sha256 !~ '^[0-9a-f]{64}$'
     or p_expected_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_lease_id is null
     or p_lease_seconds < 1 or p_lease_seconds > 30 then
    raise exception 'invalid credential refresh v2 lease' using errcode = '22023';
  end if;

  -- Preserve the canonical owner -> connection -> credential lock order used
  -- by authorization changes and account deletion.  Taking the credential
  -- lock first and then delegating to v1 would introduce a deadlock edge.
  if exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = p_credential_handle_sha256
  ) or exists (
    select 1 from connected_app_private.credential_refresh_quarantines
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    raise exception 'credential refresh generation retired' using errcode = '55000';
  end if;
  select * into envelope from connected_app_private.credential_envelopes
  where credential_handle_sha256 = p_credential_handle_sha256;
  if not found then
    raise exception 'credential refresh authority mismatch' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(envelope.owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = envelope.owner_id
    and connection.id = envelope.connection_id
  for update;
  if not found
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> envelope.provider
     or connection_row.connection_incarnation_id <> envelope.connection_incarnation_id
     or connection_row.account_kind <> envelope.account_kind
     or connection_row.authorization_revision <> envelope.authorization_revision
     or connection_row.authorization_snapshot_sha256
       <> envelope.authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> envelope.granted_actions_sha256
     or connection_row.granted_scopes_sha256 <> envelope.granted_scopes_sha256
     or connection_row.external_account_id_sha256 <> envelope.external_account_id_hash
     or connection_row.authorization_expires_at <> envelope.authorization_expires_at
     or connection_row.authorization_expires_at <= database_now
     or connection_row.credential_ref_sha256 <> p_credential_handle_sha256 then
    raise exception 'credential refresh authority mismatch' using errcode = '55000';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-credential:' || p_credential_handle_sha256, 0)
  );
  if exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = p_credential_handle_sha256
  ) or exists (
    select 1 from connected_app_private.credential_refresh_quarantines
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    raise exception 'credential refresh generation retired' using errcode = '55000';
  end if;
  select * into envelope from connected_app_private.credential_envelopes
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if not found
     or envelope.record_binding_sha256 <> p_expected_record_binding_sha256
     or envelope.owner_id <> connection_row.owner_id
     or envelope.connection_id <> connection_row.id
     or envelope.provider <> connection_row.provider
     or envelope.connection_incarnation_id <> connection_row.connection_incarnation_id
     or envelope.account_kind <> connection_row.account_kind
     or envelope.authorization_revision <> connection_row.authorization_revision
     or envelope.authorization_snapshot_sha256
       <> connection_row.authorization_snapshot_sha256
     or envelope.granted_actions_sha256 <> connection_row.granted_actions_sha256
     or envelope.granted_scopes_sha256 <> connection_row.granted_scopes_sha256
     or envelope.external_account_id_hash <> connection_row.external_account_id_sha256
     or envelope.authorization_expires_at <> connection_row.authorization_expires_at
     or envelope.credential_handle_sha256 <> connection_row.credential_ref_sha256 then
    raise exception 'credential refresh authority mismatch' using errcode = '55000';
  end if;
  select * into retired
  from connected_app_private.credential_refresh_lease_history
  where lease_id = p_lease_id for update;
  if found then
    if retired.credential_handle_sha256 <> p_credential_handle_sha256
       or retired.expected_record_binding_sha256 <> p_expected_record_binding_sha256 then
      raise exception 'credential refresh retired lease binding drifted'
        using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'status', 'stale', 'credential_handle_sha256', retired.credential_handle_sha256,
      'lease_id', retired.lease_id,
      'expected_record_binding_sha256', retired.expected_record_binding_sha256,
      'issued_at', retired.issued_at, 'expires_at', retired.expires_at
    );
  end if;
  select * into lease from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if found and lease.lease_id = p_lease_id then
    if lease.expected_record_binding_sha256 <> p_expected_record_binding_sha256 then
      raise exception 'credential refresh lease binding drifted' using errcode = '55000';
    end if;
    if lease.expires_at > database_now then
      return pg_catalog.jsonb_build_object(
        'status', 'claimed', 'credential_handle_sha256', lease.credential_handle_sha256,
        'lease_id', lease.lease_id,
        'expected_record_binding_sha256', lease.expected_record_binding_sha256,
        'issued_at', lease.issued_at, 'expires_at', lease.expires_at
      );
    end if;
    insert into connected_app_private.credential_refresh_lease_history (
      lease_id, credential_handle_sha256, expected_record_binding_sha256,
      outcome, issued_at, expires_at, retired_at
    ) values (
      lease.lease_id, lease.credential_handle_sha256,
      lease.expected_record_binding_sha256, 'expired', lease.issued_at,
      lease.expires_at, database_now
    ) on conflict (lease_id) do nothing;
    delete from connected_app_private.credential_refresh_leases
    where credential_handle_sha256 = lease.credential_handle_sha256
      and lease_id = lease.lease_id;
    return pg_catalog.jsonb_build_object(
      'status', 'stale', 'credential_handle_sha256', lease.credential_handle_sha256,
      'lease_id', lease.lease_id,
      'expected_record_binding_sha256', lease.expected_record_binding_sha256,
      'issued_at', lease.issued_at, 'expires_at', lease.expires_at
    );
  end if;
  if found and lease.expires_at > database_now then
    return pg_catalog.jsonb_build_object(
      'status', 'busy', 'credential_handle_sha256', lease.credential_handle_sha256,
      'lease_id', lease.lease_id,
      'expected_record_binding_sha256', lease.expected_record_binding_sha256,
      'issued_at', lease.issued_at, 'expires_at', lease.expires_at
    );
  end if;
  if found then
    insert into connected_app_private.credential_refresh_lease_history (
      lease_id, credential_handle_sha256, expected_record_binding_sha256,
      outcome, issued_at, expires_at, retired_at
    ) values (
      lease.lease_id, lease.credential_handle_sha256,
      lease.expected_record_binding_sha256, 'expired', lease.issued_at,
      lease.expires_at, database_now
    ) on conflict (lease_id) do nothing;
    delete from connected_app_private.credential_refresh_leases
    where credential_handle_sha256 = lease.credential_handle_sha256
      and lease_id = lease.lease_id;
  end if;
  insert into connected_app_private.credential_refresh_leases (
    credential_handle_sha256, lease_id, expected_record_binding_sha256,
    issued_at, expires_at
  ) values (
    p_credential_handle_sha256, p_lease_id, p_expected_record_binding_sha256,
    database_now, database_now + pg_catalog.make_interval(secs => p_lease_seconds)
  ) returning * into lease;
  return pg_catalog.jsonb_build_object(
    'status', 'claimed', 'credential_handle_sha256', lease.credential_handle_sha256,
    'lease_id', lease.lease_id,
    'expected_record_binding_sha256', lease.expected_record_binding_sha256,
    'issued_at', lease.issued_at, 'expires_at', lease.expires_at
  );
end;
$fn$;
comment on function public.connected_app_credential_claim_refresh_v2(text,text,uuid,integer) is
  'ASK_CRUMP_CONNECTED_REFRESH_CLAIM_V2_EXPIRED_ID_NEVER_REVIVES';

create or replace function public.connected_app_credential_finish_refresh_v2(
  p_credential_handle_sha256 text,
  p_lease_id uuid,
  p_expected_record_binding_sha256 text
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare
  lease connected_app_private.credential_refresh_leases%rowtype;
  retired connected_app_private.credential_refresh_lease_history%rowtype;
  database_now timestamptz := pg_catalog.clock_timestamp();
begin
  if p_credential_handle_sha256 !~ '^[0-9a-f]{64}$'
     or p_expected_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_lease_id is null then
    raise exception 'invalid credential refresh v2 finish' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-credential:' || p_credential_handle_sha256, 0)
  );
  select * into retired from connected_app_private.credential_refresh_lease_history
  where lease_id = p_lease_id for update;
  if found then
    if retired.credential_handle_sha256 = p_credential_handle_sha256
       and retired.expected_record_binding_sha256 = p_expected_record_binding_sha256
       and retired.outcome in ('finished', 'expired') then
      return pg_catalog.jsonb_build_object(
        'status', case when retired.outcome = 'finished' then 'finished' else 'stale' end,
        'lease_id', p_lease_id
      );
    end if;
    raise exception 'credential refresh v2 finish replay drifted' using errcode = '55000';
  end if;
  select * into lease from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if not found or lease.lease_id <> p_lease_id
     or lease.expected_record_binding_sha256 <> p_expected_record_binding_sha256 then
    raise exception 'credential refresh v2 finish lease drifted' using errcode = '55000';
  end if;
  if lease.expires_at <= database_now then
    insert into connected_app_private.credential_refresh_lease_history (
      lease_id, credential_handle_sha256, expected_record_binding_sha256,
      outcome, issued_at, expires_at, retired_at
    ) values (
      lease.lease_id, lease.credential_handle_sha256,
      lease.expected_record_binding_sha256, 'expired', lease.issued_at,
      lease.expires_at, database_now
    );
    delete from connected_app_private.credential_refresh_leases
    where credential_handle_sha256 = p_credential_handle_sha256 and lease_id = p_lease_id;
    return pg_catalog.jsonb_build_object('status', 'stale', 'lease_id', p_lease_id);
  end if;
  insert into connected_app_private.credential_refresh_lease_history (
    lease_id, credential_handle_sha256, expected_record_binding_sha256,
    outcome, issued_at, expires_at, retired_at
  ) values (
    lease.lease_id, lease.credential_handle_sha256,
    lease.expected_record_binding_sha256, 'finished', lease.issued_at,
    lease.expires_at, database_now
  );
  delete from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256 and lease_id = p_lease_id;
  return pg_catalog.jsonb_build_object('status', 'finished', 'lease_id', p_lease_id);
end;
$fn$;
comment on function public.connected_app_credential_finish_refresh_v2(text,uuid,text) is
  'ASK_CRUMP_CONNECTED_REFRESH_FINISH_V2_EXACT_LEASE_AND_RECORD_BINDING';

create or replace function public.connected_app_credential_commit_refresh_v2(
  p_owner_id uuid,
  p_connection_id uuid,
  p_provider text,
  p_credential_handle_sha256 text,
  p_connection_incarnation_id uuid,
  p_oauth_client_id_sha256 text,
  p_account_kind text,
  p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,
  p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,
  p_external_account_id_hash text,
  p_authorization_expires_at timestamptz,
  p_secret_revision bigint,
  p_created_at timestamptz,
  p_updated_at timestamptz,
  p_authority_binding_sha256 text,
  p_metadata_binding_sha256 text,
  p_key_id text,
  p_wrapped_key_nonce text,
  p_wrapped_key_ciphertext text,
  p_secret_nonce text,
  p_secret_ciphertext text,
  p_record_binding_sha256 text,
  p_expected_record_binding_sha256 text,
  p_lease_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare
  envelope connected_app_private.credential_envelopes%rowtype;
  connection_row connected_app_private.connections%rowtype;
  lease connected_app_private.credential_refresh_leases%rowtype;
  retired connected_app_private.credential_refresh_lease_history%rowtype;
  database_now timestamptz := pg_catalog.clock_timestamp();
begin
  if p_credential_handle_sha256 !~ '^[0-9a-f]{64}$'
     or p_expected_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_lease_id is null then
    raise exception 'invalid credential refresh v2 commit' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = p_owner_id and connection.id = p_connection_id
  for update;
  if not found
     or connection_row.authorization_state <> 'active'
     or connection_row.provider <> p_provider
     or connection_row.connection_incarnation_id <> p_connection_incarnation_id
     or connection_row.account_kind <> p_account_kind
     or connection_row.authorization_revision <> p_authorization_revision
     or connection_row.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or connection_row.granted_actions_sha256 <> p_granted_actions_sha256
     or connection_row.granted_scopes_sha256 <> p_granted_scopes_sha256
     or connection_row.external_account_id_sha256 <> p_external_account_id_hash
     or connection_row.authorization_expires_at <> p_authorization_expires_at
     or connection_row.authorization_expires_at <= database_now
     or connection_row.credential_ref_sha256 <> p_credential_handle_sha256 then
    raise exception 'credential refresh v2 commit authority drifted' using errcode = '55000';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-credential:' || p_credential_handle_sha256, 0)
  );
  if exists (
    select 1 from connected_app_private.credential_secret_tombstones
    where credential_handle_sha256 = p_credential_handle_sha256
  ) or exists (
    select 1 from connected_app_private.credential_refresh_quarantines
    where credential_handle_sha256 = p_credential_handle_sha256
  ) then
    raise exception 'credential refresh v2 commit generation retired' using errcode = '55000';
  end if;
  select * into envelope from connected_app_private.credential_envelopes
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if not found
     or envelope.record_binding_sha256 <> p_expected_record_binding_sha256
     or envelope.owner_id <> p_owner_id
     or envelope.connection_id <> p_connection_id
     or envelope.provider <> p_provider
     or envelope.connection_incarnation_id <> p_connection_incarnation_id
     or envelope.oauth_client_id_sha256 <> p_oauth_client_id_sha256
     or envelope.account_kind <> p_account_kind
     or envelope.authorization_revision <> p_authorization_revision
     or envelope.authorization_snapshot_sha256 <> p_authorization_snapshot_sha256
     or envelope.granted_actions_sha256 <> p_granted_actions_sha256
     or envelope.granted_scopes_sha256 <> p_granted_scopes_sha256
     or envelope.external_account_id_hash <> p_external_account_id_hash
     or envelope.authorization_expires_at <> p_authorization_expires_at
     or envelope.created_at <> p_created_at
     or p_secret_revision <> envelope.secret_revision + 1
     or p_updated_at <= envelope.updated_at then
    -- Exact response-loss replay is resolved below from permanent history and
    -- the already-committed target binding; all other CAS drift is rejected.
    select * into retired from connected_app_private.credential_refresh_lease_history
    where lease_id = p_lease_id for update;
    if found
       and retired.outcome = 'finished'
       and retired.credential_handle_sha256 = p_credential_handle_sha256
       and retired.expected_record_binding_sha256 = p_expected_record_binding_sha256
       and envelope.record_binding_sha256 = p_record_binding_sha256 then
      return pg_catalog.jsonb_build_object(
        'status', 'present', 'record', pg_catalog.to_jsonb(envelope)
      );
    end if;
    raise exception 'credential refresh v2 commit CAS drifted' using errcode = '55000';
  end if;
  select * into retired from connected_app_private.credential_refresh_lease_history
  where lease_id = p_lease_id for update;
  if found then
    raise exception 'credential refresh v2 commit lease retired' using errcode = '55000';
  end if;
  select * into lease from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if not found
     or lease.lease_id <> p_lease_id
     or lease.expected_record_binding_sha256 <> p_expected_record_binding_sha256 then
    raise exception 'credential refresh v2 commit lease drifted' using errcode = '55000';
  end if;
  if lease.expires_at <= database_now then
    insert into connected_app_private.credential_refresh_lease_history (
      lease_id, credential_handle_sha256, expected_record_binding_sha256,
      outcome, issued_at, expires_at, retired_at
    ) values (
      lease.lease_id, lease.credential_handle_sha256,
      lease.expected_record_binding_sha256, 'expired', lease.issued_at,
      lease.expires_at, database_now
    );
    delete from connected_app_private.credential_refresh_leases
    where credential_handle_sha256 = p_credential_handle_sha256 and lease_id = p_lease_id;
    return pg_catalog.jsonb_build_object('status', 'stale', 'record', null);
  end if;
  update connected_app_private.credential_envelopes set
    secret_revision = p_secret_revision,
    updated_at = p_updated_at,
    authority_binding_sha256 = p_authority_binding_sha256,
    metadata_binding_sha256 = p_metadata_binding_sha256,
    key_id = p_key_id,
    wrapped_key_nonce = p_wrapped_key_nonce,
    wrapped_key_ciphertext = p_wrapped_key_ciphertext,
    secret_nonce = p_secret_nonce,
    secret_ciphertext = p_secret_ciphertext,
    record_binding_sha256 = p_record_binding_sha256
  where credential_handle_sha256 = p_credential_handle_sha256
  returning * into envelope;
  insert into connected_app_private.credential_refresh_lease_history (
    lease_id, credential_handle_sha256, expected_record_binding_sha256,
    outcome, issued_at, expires_at, retired_at
  ) values (
    lease.lease_id, lease.credential_handle_sha256,
    lease.expected_record_binding_sha256, 'finished', lease.issued_at,
    lease.expires_at, database_now
  );
  delete from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256 and lease_id = p_lease_id;
  return pg_catalog.jsonb_build_object(
    'status', 'present', 'record', pg_catalog.to_jsonb(envelope)
  );
end;
$fn$;
comment on function public.connected_app_credential_commit_refresh_v2(
  uuid,uuid,text,text,uuid,text,text,bigint,text,text,text,text,timestamptz,
  bigint,timestamptz,timestamptz,text,text,text,text,text,text,text,text,text,uuid
) is 'ASK_CRUMP_CONNECTED_REFRESH_COMMIT_V2_LEASE_BOUND_ATOMIC_ROTATION';

create or replace function public.connected_app_credential_quarantine_refresh_v2(
  p_credential_handle_sha256 text,
  p_lease_id uuid,
  p_expected_record_binding_sha256 text
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare
  lease connected_app_private.credential_refresh_leases%rowtype;
  retired connected_app_private.credential_refresh_lease_history%rowtype;
  quarantine connected_app_private.credential_refresh_quarantines%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_credential_handle_sha256 !~ '^[0-9a-f]{64}$'
     or p_expected_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_lease_id is null then
    raise exception 'invalid credential refresh v2 quarantine' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-credential:' || p_credential_handle_sha256, 0)
  );
  select * into retired from connected_app_private.credential_refresh_lease_history
  where lease_id = p_lease_id for update;
  if found then
    if retired.credential_handle_sha256 = p_credential_handle_sha256
       and retired.expected_record_binding_sha256 = p_expected_record_binding_sha256
       and retired.outcome = 'quarantined' then
      return pg_catalog.jsonb_build_object(
        'status', 'quarantined',
        'credential_handle_sha256', retired.credential_handle_sha256,
        'lease_id', retired.lease_id,
        'expected_record_binding_sha256', retired.expected_record_binding_sha256,
        'quarantined_at', retired.retired_at
      );
    end if;
    raise exception 'credential refresh v2 quarantine replay drifted'
      using errcode = '55000';
  end if;
  select * into quarantine
  from connected_app_private.credential_refresh_quarantines
  where credential_handle_sha256 = p_credential_handle_sha256
  for update;
  if found then
    if quarantine.lease_id <> p_lease_id
       or quarantine.expected_record_binding_sha256
         <> p_expected_record_binding_sha256 then
      raise exception 'credential refresh v2 quarantine replay drifted'
        using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'status', 'quarantined',
      'credential_handle_sha256', quarantine.credential_handle_sha256,
      'lease_id', quarantine.lease_id,
      'expected_record_binding_sha256', quarantine.expected_record_binding_sha256,
      'quarantined_at', quarantine.quarantined_at
    );
  end if;
  select * into lease from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256 for update;
  if not found or lease.lease_id <> p_lease_id
     or lease.expected_record_binding_sha256 <> p_expected_record_binding_sha256 then
    raise exception 'credential refresh v2 quarantine lease drifted'
      using errcode = '55000';
  end if;
  insert into connected_app_private.credential_refresh_quarantines (
    credential_handle_sha256, lease_id,
    expected_record_binding_sha256, quarantined_at
  ) values (
    p_credential_handle_sha256, p_lease_id,
    p_expected_record_binding_sha256, now_at
  ) returning * into quarantine;
  insert into connected_app_private.credential_refresh_lease_history (
    lease_id, credential_handle_sha256, expected_record_binding_sha256,
    outcome, issued_at, expires_at, retired_at
  ) values (
    lease.lease_id, lease.credential_handle_sha256,
    lease.expected_record_binding_sha256, 'quarantined', lease.issued_at,
    lease.expires_at, now_at
  );
  delete from connected_app_private.credential_refresh_leases
  where credential_handle_sha256 = p_credential_handle_sha256
    and lease_id = p_lease_id;
  return pg_catalog.jsonb_build_object(
    'status', 'quarantined',
    'credential_handle_sha256', quarantine.credential_handle_sha256,
    'lease_id', quarantine.lease_id,
    'expected_record_binding_sha256', quarantine.expected_record_binding_sha256,
    'quarantined_at', quarantine.quarantined_at
  );
end;
$fn$;
comment on function public.connected_app_credential_quarantine_refresh_v2(text,uuid,text) is
  'ASK_CRUMP_CONNECTED_REFRESH_QUARANTINE_V2_PERMANENT_EXACT_REPLAY';

create or replace function public.connected_app_provider_cleanup_begin_v1(
  p_cleanup_id uuid, p_owner_id uuid, p_connection_id uuid, p_exchange_id uuid,
  p_provider text, p_exchange_binding_sha256 text, p_deadline_at timestamptz
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  job connected_app_private.provider_grant_cleanup_jobs%rowtype;
  now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_cleanup_id is null or p_owner_id is null or p_connection_id is null
     or p_exchange_id is null or p_provider not in ('google', 'microsoft')
     or p_exchange_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_deadline_at <= now_at
     or p_deadline_at > now_at + interval '30 minutes' then
    raise exception 'invalid provider cleanup begin' using errcode = '22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select * into connection_row from connected_app_private.connections
  where owner_id = p_owner_id and id = p_connection_id for update;
  if not found or connection_row.provider <> p_provider
     or connection_row.authorization_state not in ('pending', 'active') then
    raise exception 'provider cleanup begin authority drifted' using errcode = '55000';
  end if;
  insert into connected_app_private.provider_grant_cleanup_jobs (
    cleanup_id, owner_id, owner_id_sha256, connection_id, connection_id_sha256,
    exchange_id, provider, source_kind, source_binding_sha256, status,
    encrypted_record, deadline_at, created_at, updated_at
  ) values (
    p_cleanup_id, p_owner_id, connected_app_private.cleanup_digest_uuid_v1(p_owner_id),
    p_connection_id, connected_app_private.cleanup_digest_uuid_v1(p_connection_id),
    p_exchange_id, p_provider, 'exchange_unknown', p_exchange_binding_sha256,
    'exchange_pending', null, p_deadline_at, now_at, now_at
  ) on conflict (cleanup_id) do nothing;
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where cleanup_id = p_cleanup_id;
  if job.owner_id_sha256 <> connected_app_private.cleanup_digest_uuid_v1(p_owner_id)
     or job.connection_id_sha256
       <> connected_app_private.cleanup_digest_uuid_v1(p_connection_id)
     or job.exchange_id is distinct from p_exchange_id
     or job.provider is distinct from p_provider
     or job.source_binding_sha256 is distinct from p_exchange_binding_sha256 then
    raise exception 'provider cleanup begin replay drifted' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'status', job.status, 'cleanup_id', job.cleanup_id,
    'source_binding_sha256', job.source_binding_sha256,
    'created_at', job.created_at, 'updated_at', job.updated_at
  );
end;
$fn$;
comment on function public.connected_app_provider_cleanup_begin_v1(uuid,uuid,uuid,uuid,text,text,timestamptz) is
  'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_BEGIN_V1_BEFORE_TOKEN_DISPATCH';

create or replace function public.connected_app_provider_cleanup_attach_v1(
  p_cleanup_id uuid, p_exchange_binding_sha256 text, p_source_kind text,
  p_source_binding_sha256 text, p_encrypted_record jsonb
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare
  job connected_app_private.provider_grant_cleanup_jobs%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  if p_source_kind not in ('provisional', 'credential')
     or p_exchange_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_source_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_encrypted_record is null or pg_catalog.jsonb_typeof(p_encrypted_record) <> 'object'
     or pg_catalog.length(p_encrypted_record::text) > 262144 then
    raise exception 'invalid provider cleanup attachment' using errcode = '22023';
  end if;
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where cleanup_id = p_cleanup_id;
  if not found or job.owner_id is null then
    raise exception 'provider cleanup attachment drifted' using errcode = '55000';
  end if;
  perform connected_app_private.owner_lock_v1(job.owner_id);
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where cleanup_id = p_cleanup_id for update;
  if not found then
    raise exception 'provider cleanup attachment drifted' using errcode = '55000';
  end if;
  if job.status = 'retained'
     and job.source_kind = p_source_kind
     and job.source_binding_sha256 = p_source_binding_sha256
     and job.encrypted_record = p_encrypted_record then
    return pg_catalog.jsonb_build_object(
      'status', job.status, 'cleanup_id', job.cleanup_id,
      'source_binding_sha256', job.source_binding_sha256,
      'created_at', job.created_at, 'updated_at', job.updated_at
    );
  end if;
  if job.owner_id is null or job.connection_id is null
     or job.source_binding_sha256 <> p_exchange_binding_sha256
     or job.status <> 'exchange_pending' then
    raise exception 'provider cleanup attachment drifted' using errcode = '55000';
  end if;
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id = job.owner_id and connection.id = job.connection_id
  for update;
  if not found or connection_row.provider <> job.provider
     or connection_row.authorization_state not in ('pending', 'active') then
    raise exception 'provider cleanup attachment authority drifted' using errcode = '55000';
  end if;
  update connected_app_private.provider_grant_cleanup_jobs set
    source_kind = p_source_kind, source_binding_sha256 = p_source_binding_sha256,
    encrypted_record = p_encrypted_record, status = 'retained',
    updated_at = pg_catalog.clock_timestamp()
  where cleanup_id = p_cleanup_id returning * into job;
  return pg_catalog.jsonb_build_object(
    'status', job.status, 'cleanup_id', job.cleanup_id,
    'source_binding_sha256', job.source_binding_sha256,
    'created_at', job.created_at, 'updated_at', job.updated_at
  );
end;
$fn$;
comment on function public.connected_app_provider_cleanup_attach_v1(uuid,text,text,text,jsonb) is
  'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_ATTACH_V1_ENCRYPTED_BEFORE_GRANT_COMMIT';

create or replace function public.connected_app_provider_cleanup_release_v1(
  p_cleanup_id uuid, p_source_binding_sha256 text
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare job connected_app_private.provider_grant_cleanup_jobs%rowtype;
declare credential connected_app_private.credential_envelopes%rowtype;
begin
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where cleanup_id = p_cleanup_id;
  if not found or job.source_binding_sha256 <> p_source_binding_sha256 then
    raise exception 'provider cleanup release drifted' using errcode = '55000';
  end if;
  if job.status <> 'released' then
    if job.owner_id is null or job.connection_id is null
       or job.source_kind <> 'provisional'
       or job.status not in ('retained', 'cleanup_pending') then
      raise exception 'provider cleanup release state drifted' using errcode = '55000';
    end if;
    perform connected_app_private.owner_lock_v1(job.owner_id);
    select * into job from connected_app_private.provider_grant_cleanup_jobs
    where cleanup_id = p_cleanup_id for update;
    if not found or job.owner_id is null or job.connection_id is null
       or job.source_kind <> 'provisional'
       or job.source_binding_sha256 <> p_source_binding_sha256
       or job.status not in ('retained', 'cleanup_pending') then
      raise exception 'provider cleanup release state drifted' using errcode = '55000';
    end if;
    if (job.encrypted_record->>'credential_handle_sha256') !~ '^[0-9a-f]{64}$' then
      raise exception 'provider cleanup release credential drifted' using errcode = '55000';
    end if;
    select * into credential from connected_app_private.credential_envelopes
    where credential_handle_sha256 = job.encrypted_record->>'credential_handle_sha256'
    for update;
    if not found or credential.owner_id <> job.owner_id
       or credential.connection_id <> job.connection_id
       or credential.provider <> job.provider then
      raise exception 'provider cleanup release custody not transferred' using errcode = '55000';
    end if;
    if not exists (
      select 1 from connected_app_private.oauth_provisional_tombstones
      where credential_handle_sha256 = job.encrypted_record->>'credential_handle_sha256'
        and record_binding_sha256 = job.source_binding_sha256
        and record_existed
    ) then
      raise exception 'provider cleanup release source custody retained' using errcode = '55000';
    end if;
    update connected_app_private.provider_grant_cleanup_jobs set
      owner_id = null, connection_id = null, encrypted_record = null,
      status = 'released', finished_at = pg_catalog.clock_timestamp(),
      updated_at = pg_catalog.clock_timestamp()
    where cleanup_id = p_cleanup_id returning * into job;
  end if;
  return pg_catalog.jsonb_build_object('status', job.status, 'cleanup_id', job.cleanup_id);
end;
$fn$;
comment on function public.connected_app_provider_cleanup_release_v1(uuid,text) is
  'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_RELEASE_V1_EXACT_TRANSFER_AND_SOURCE_ERASURE';

create or replace function public.connected_app_provider_cleanup_release_recover_v1(
  p_cleanup_id uuid, p_credential_handle_sha256 text
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare job connected_app_private.provider_grant_cleanup_jobs%rowtype;
begin
  if p_cleanup_id is null
     or p_credential_handle_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid provider cleanup release recovery' using errcode = '22023';
  end if;
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where cleanup_id = p_cleanup_id;
  if not found then
    raise exception 'provider cleanup release recovery missing' using errcode = '55000';
  end if;
  if job.status = 'released' then
    return pg_catalog.jsonb_build_object('status', job.status, 'cleanup_id', job.cleanup_id);
  end if;
  if job.owner_id is null or job.connection_id is null
     or job.source_kind <> 'provisional'
     or job.status not in ('retained', 'cleanup_pending')
     or (job.encrypted_record->>'credential_handle_sha256')
          <> p_credential_handle_sha256 then
    raise exception 'provider cleanup release recovery drifted' using errcode = '55000';
  end if;
  -- The exact-binding release performs the owner lock, row re-read, final
  -- credential custody proof, and permanent provisional tombstone proof.
  -- This wrapper discloses no source binding to the caller and exists solely
  -- for replay after the source row was durably erased.
  return public.connected_app_provider_cleanup_release_v1(
    p_cleanup_id, job.source_binding_sha256
  );
end;
$fn$;
comment on function public.connected_app_provider_cleanup_release_recover_v1(uuid,text) is
  'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_RELEASE_RECOVER_V1_FINAL_CREDENTIAL_AND_TOMBSTONE';

create or replace function public.connected_app_provider_cleanup_claim_v1(
  p_claim_id uuid, p_lease_seconds integer
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare job connected_app_private.provider_grant_cleanup_jobs%rowtype;
declare retired connected_app_private.provider_grant_cleanup_claim_history%rowtype;
declare now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_claim_id is null or p_lease_seconds < 5 or p_lease_seconds > 120 then
    raise exception 'invalid provider cleanup claim' using errcode = '22023';
  end if;
  select * into retired
  from connected_app_private.provider_grant_cleanup_claim_history
  where claim_id = p_claim_id;
  if found then
    return pg_catalog.jsonb_build_object('status', 'stale', 'record', null);
  end if;
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where claim_id = p_claim_id for update;
  if found then
    if job.status = 'claimed' and job.claim_expires_at > now_at then
      return pg_catalog.jsonb_build_object(
        'status', 'claimed', 'record', pg_catalog.jsonb_build_object(
          'cleanup_id', job.cleanup_id, 'provider', job.provider,
          'source_kind', job.source_kind,
          'source_binding_sha256', job.source_binding_sha256,
          'encrypted_record', job.encrypted_record,
          'claim_id', job.claim_id, 'claim_expires_at', job.claim_expires_at,
          'attempts', job.attempts
        )
      );
    end if;
    insert into connected_app_private.provider_grant_cleanup_claim_history (
      claim_id, cleanup_id, source_binding_sha256, outcome, retired_at
    ) values (
      job.claim_id, job.cleanup_id, job.source_binding_sha256, 'expired', now_at
    );
    update connected_app_private.provider_grant_cleanup_jobs set
      status = case when attempts >= 32 then 'user_action_required'
        else 'cleanup_pending' end,
      owner_id = case when attempts >= 32 then null else owner_id end,
      connection_id = case when attempts >= 32 then null else connection_id end,
      encrypted_record = case when attempts >= 32 then null else encrypted_record end,
      claim_id = null, claim_expires_at = null,
      finished_at = case when attempts >= 32 then now_at else null end,
      updated_at = now_at
    where cleanup_id = job.cleanup_id;
    return pg_catalog.jsonb_build_object('status', 'stale', 'record', null);
  end if;

  -- A host may disappear after the token endpoint returns but before it can
  -- attach encrypted token custody.  Once the bounded exchange deadline has
  -- passed, preserve an honest action-required tombstone.  Never represent an
  -- unknown external effect as revoked or silently drop it.
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where status = 'exchange_pending' and deadline_at <= now_at
  order by updated_at, cleanup_id for update skip locked limit 1;
  if found then
    update connected_app_private.provider_grant_cleanup_jobs set
      status = 'user_action_required', owner_id = null, connection_id = null,
      encrypted_record = null, finished_at = now_at, updated_at = now_at
    where cleanup_id = job.cleanup_id;
    return pg_catalog.jsonb_build_object('status', 'empty', 'record', null);
  end if;

  -- Exhaustion becomes a durable, secret-free operator/user action rather
  -- than an unclaimable row or a CHECK-constraint failure on attempt 33.
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where (status in ('cleanup_pending', 'retry') and attempts >= 32)
     or (status = 'claimed' and claim_expires_at <= now_at and attempts >= 32)
  order by updated_at, cleanup_id for update skip locked limit 1;
  if found then
    if job.claim_id is not null then
      insert into connected_app_private.provider_grant_cleanup_claim_history (
        claim_id, cleanup_id, source_binding_sha256, outcome, retired_at
      ) values (
        job.claim_id, job.cleanup_id, job.source_binding_sha256, 'expired', now_at
      ) on conflict (claim_id) do nothing;
    end if;
    update connected_app_private.provider_grant_cleanup_jobs set
      status = 'user_action_required', owner_id = null, connection_id = null,
      encrypted_record = null, claim_id = null, claim_expires_at = null,
      finished_at = now_at, updated_at = now_at
    where cleanup_id = job.cleanup_id;
    return pg_catalog.jsonb_build_object('status', 'empty', 'record', null);
  end if;
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where ((status in ('cleanup_pending', 'retry'))
     or (status = 'claimed' and claim_expires_at <= now_at))
    and attempts < 32
  order by updated_at, cleanup_id for update skip locked limit 1;
  if not found then
    return pg_catalog.jsonb_build_object('status', 'empty', 'record', null);
  end if;
  if job.status = 'claimed' then
    insert into connected_app_private.provider_grant_cleanup_claim_history (
      claim_id, cleanup_id, source_binding_sha256, outcome, retired_at
    ) values (
      job.claim_id, job.cleanup_id, job.source_binding_sha256, 'expired', now_at
    ) on conflict (claim_id) do nothing;
  end if;
  update connected_app_private.provider_grant_cleanup_jobs set
    status = 'claimed', claim_id = p_claim_id,
    claim_expires_at = now_at + pg_catalog.make_interval(secs => p_lease_seconds),
    attempts = attempts + 1, updated_at = now_at
  where cleanup_id = job.cleanup_id returning * into job;
  return pg_catalog.jsonb_build_object(
    'status', 'claimed', 'record', pg_catalog.jsonb_build_object(
      'cleanup_id', job.cleanup_id, 'provider', job.provider,
      'source_kind', job.source_kind,
      'source_binding_sha256', job.source_binding_sha256,
      'encrypted_record', job.encrypted_record,
      'claim_id', job.claim_id, 'claim_expires_at', job.claim_expires_at,
      'attempts', job.attempts
    )
  );
end;
$fn$;
comment on function public.connected_app_provider_cleanup_claim_v1(uuid,integer) is
  'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_CLAIM_V1_ONE_WINNER';

create or replace function public.connected_app_provider_cleanup_recover_v1(
  p_claim_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare job connected_app_private.provider_grant_cleanup_jobs%rowtype;
declare now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_claim_id is null then
    raise exception 'invalid provider cleanup recovery' using errcode = '22023';
  end if;
  if exists (
    select 1 from connected_app_private.provider_grant_cleanup_claim_history
    where claim_id = p_claim_id
  ) then
    return pg_catalog.jsonb_build_object('status', 'stale', 'record', null);
  end if;
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where claim_id = p_claim_id for update;
  if not found then
    return pg_catalog.jsonb_build_object('status', 'absent', 'record', null);
  end if;
  if job.status <> 'claimed' or job.claim_expires_at <= now_at then
    insert into connected_app_private.provider_grant_cleanup_claim_history (
      claim_id, cleanup_id, source_binding_sha256, outcome, retired_at
    ) values (
      job.claim_id, job.cleanup_id, job.source_binding_sha256, 'expired', now_at
    ) on conflict (claim_id) do nothing;
    update connected_app_private.provider_grant_cleanup_jobs set
      status = case when attempts >= 32 then 'user_action_required'
        else 'cleanup_pending' end,
      owner_id = case when attempts >= 32 then null else owner_id end,
      connection_id = case when attempts >= 32 then null else connection_id end,
      encrypted_record = case when attempts >= 32 then null else encrypted_record end,
      claim_id = null, claim_expires_at = null,
      finished_at = case when attempts >= 32 then now_at else null end,
      updated_at = now_at
    where cleanup_id = job.cleanup_id;
    return pg_catalog.jsonb_build_object('status', 'stale', 'record', null);
  end if;
  return pg_catalog.jsonb_build_object(
    'status', 'claimed', 'record', pg_catalog.jsonb_build_object(
      'cleanup_id', job.cleanup_id, 'provider', job.provider,
      'source_kind', job.source_kind,
      'source_binding_sha256', job.source_binding_sha256,
      'encrypted_record', job.encrypted_record,
      'claim_id', job.claim_id, 'claim_expires_at', job.claim_expires_at,
      'attempts', job.attempts
    )
  );
end;
$fn$;
comment on function public.connected_app_provider_cleanup_recover_v1(uuid) is
  'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_RECOVER_V1_EXACT_CLAIM_READBACK';

create or replace function public.connected_app_provider_cleanup_finish_v1(
  p_cleanup_id uuid, p_claim_id uuid, p_outcome text,
  p_provider_receipt_sha256 text
) returns jsonb language plpgsql security definer set search_path = '' as $fn$
declare job connected_app_private.provider_grant_cleanup_jobs%rowtype;
declare retired connected_app_private.provider_grant_cleanup_claim_history%rowtype;
declare now_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_outcome not in ('succeeded', 'retry', 'user_action_required')
     or (p_outcome = 'succeeded' and p_provider_receipt_sha256 is null)
     or (p_outcome <> 'succeeded' and p_provider_receipt_sha256 is not null)
     or (p_provider_receipt_sha256 is not null
         and p_provider_receipt_sha256 !~ '^[0-9a-f]{64}$') then
    raise exception 'invalid provider cleanup finish' using errcode = '22023';
  end if;
  select * into job from connected_app_private.provider_grant_cleanup_jobs
  where cleanup_id = p_cleanup_id for update;
  if not found then
    raise exception 'provider cleanup job absent' using errcode = '55000';
  end if;
  select * into retired
  from connected_app_private.provider_grant_cleanup_claim_history
  where claim_id = p_claim_id;
  if found then
    if retired.cleanup_id = p_cleanup_id
       and retired.source_binding_sha256 = job.source_binding_sha256
       and retired.outcome = p_outcome
       and job.status = p_outcome
       and job.provider_receipt_sha256 is not distinct from p_provider_receipt_sha256 then
      return pg_catalog.jsonb_build_object('status', job.status, 'cleanup_id', job.cleanup_id);
    end if;
    raise exception 'provider cleanup finish retired claim drifted' using errcode = '55000';
  end if;
  if job.status in ('succeeded', 'user_action_required') then
    if job.provider_receipt_sha256 is not distinct from p_provider_receipt_sha256
       and job.status = p_outcome then
      return pg_catalog.jsonb_build_object('status', job.status, 'cleanup_id', job.cleanup_id);
    end if;
    raise exception 'provider cleanup finish replay drifted' using errcode = '55000';
  end if;
  if job.status <> 'claimed' or job.claim_id <> p_claim_id
     or job.claim_expires_at <= now_at then
    raise exception 'provider cleanup claim drifted' using errcode = '55000';
  end if;
  insert into connected_app_private.provider_grant_cleanup_claim_history (
    claim_id, cleanup_id, source_binding_sha256, outcome, retired_at
  ) values (
    job.claim_id, job.cleanup_id, job.source_binding_sha256, p_outcome, now_at
  );
  update connected_app_private.provider_grant_cleanup_jobs set
    status = p_outcome,
    owner_id = case when p_outcome <> 'retry' then null else owner_id end,
    connection_id = case when p_outcome <> 'retry' then null else connection_id end,
    encrypted_record = case when p_outcome <> 'retry' then null else encrypted_record end,
    claim_id = null, claim_expires_at = null,
    provider_receipt_sha256 = p_provider_receipt_sha256,
    finished_at = case when p_outcome <> 'retry' then now_at else null end,
    updated_at = now_at
  where cleanup_id = p_cleanup_id returning * into job;
  return pg_catalog.jsonb_build_object('status', job.status, 'cleanup_id', job.cleanup_id);
end;
$fn$;
comment on function public.connected_app_provider_cleanup_finish_v1(uuid,uuid,text,text) is
  'ASK_CRUMP_CONNECTED_PROVIDER_CLEANUP_FINISH_V1_EXACT_ONE_USE_SETTLEMENT';

alter function connected_app_private.cleanup_digest_uuid_v1(uuid) owner to postgres;
alter function connected_app_private.queue_credential_cleanup_v1() owner to postgres;
alter function connected_app_private.queue_provisional_cleanup_v1() owner to postgres;
alter function connected_app_private.flag_owner_cleanup_v1() owner to postgres;
alter table connected_app_private.credential_refresh_lease_history owner to postgres;
alter table connected_app_private.provider_grant_cleanup_jobs owner to postgres;
alter table connected_app_private.provider_grant_cleanup_claim_history owner to postgres;

revoke all on table connected_app_private.credential_refresh_lease_history
  from public, anon, authenticated, service_role;
revoke all on table connected_app_private.provider_grant_cleanup_jobs
  from public, anon, authenticated, service_role;
revoke all on table connected_app_private.provider_grant_cleanup_claim_history
  from public, anon, authenticated, service_role;
revoke all on function public.connected_app_credential_claim_refresh_v1(text,text,uuid,integer)
  from service_role;
revoke all on function public.connected_app_credential_quarantine_refresh_v1(text,uuid,text)
  from service_role;
revoke all on function public.connected_app_credential_finish_refresh_v1(text,uuid)
  from service_role;

do $acl$
declare signature text;
begin
  foreach signature in array array[
    'public.connected_app_credential_claim_refresh_v2(text,text,uuid,integer)',
    'public.connected_app_credential_finish_refresh_v2(text,uuid,text)',
    'public.connected_app_credential_commit_refresh_v2(uuid,uuid,text,text,uuid,text,text,bigint,text,text,text,text,timestamp with time zone,bigint,timestamp with time zone,timestamp with time zone,text,text,text,text,text,text,text,text,text,uuid)',
    'public.connected_app_credential_quarantine_refresh_v2(text,uuid,text)',
    'public.connected_app_provider_cleanup_begin_v1(uuid,uuid,uuid,uuid,text,text,timestamp with time zone)',
    'public.connected_app_provider_cleanup_attach_v1(uuid,text,text,text,jsonb)',
    'public.connected_app_provider_cleanup_release_v1(uuid,text)',
    'public.connected_app_provider_cleanup_release_recover_v1(uuid,text)',
    'public.connected_app_provider_cleanup_claim_v1(uuid,integer)',
    'public.connected_app_provider_cleanup_recover_v1(uuid)',
    'public.connected_app_provider_cleanup_finish_v1(uuid,uuid,text,text)'
  ] loop
    execute 'alter function ' || signature || ' owner to postgres';
    execute 'revoke all on function ' || signature || ' from public, anon, authenticated';
    execute 'grant execute on function ' || signature || ' to service_role';
  end loop;

  foreach signature in array array[
    'connected_app_private.cleanup_digest_uuid_v1(uuid)',
    'connected_app_private.queue_credential_cleanup_v1()',
    'connected_app_private.queue_provisional_cleanup_v1()',
    'connected_app_private.flag_owner_cleanup_v1()'
  ] loop
    execute 'alter function ' || signature || ' owner to postgres';
    execute 'revoke all on function ' || signature
      || ' from public, anon, authenticated, service_role';
  end loop;
end;
$acl$;

do $postflight$
declare observed_target_fingerprint text;
begin
  if pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_credential_claim_refresh_v1(text,text,uuid,integer)',
       'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'service_role', 'public.connected_app_credential_finish_refresh_v1(text,uuid)',
       'EXECUTE'
     )
     or not pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_credential_claim_refresh_v2(text,text,uuid,integer)',
       'EXECUTE'
     )
     or not pg_catalog.has_function_privilege(
       'service_role', 'public.connected_app_provider_cleanup_claim_v1(uuid,integer)',
       'EXECUTE'
     )
     or not exists (
       select 1 from pg_catalog.pg_trigger
       where tgrelid = pg_catalog.to_regclass('public.users')
         and tgname = 'connected_cleanup_owner_before_delete' and not tgisinternal
     ) then
    raise exception 'connected cleanup/refresh postflight failed' using errcode = '55000';
  end if;
  observed_target_fingerprint := pg_temp.connected_cleanup_target_fingerprint();
  if observed_target_fingerprint is distinct from 'e90e794c75b45084d89d6b1247d3287e' then
    raise exception 'connected cleanup/refresh postflight fingerprint drifted: %',
      observed_target_fingerprint using errcode = '55000';
  end if;
end;
$postflight$;

commit;
