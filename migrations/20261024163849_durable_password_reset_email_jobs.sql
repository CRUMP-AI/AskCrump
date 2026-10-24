-- Durable password-reset-email queue for timing-uniform resend requests.
--
-- The queue stores a content-minimized, immutable delivery envelope. It never
-- stores a raw email address, bearer token, signed alias, rendered body,
-- signing secret, prompt, or customer content. Only SECURITY DEFINER RPCs are
-- callable by service_role; the table itself has no API-role privileges.

select pg_catalog.set_config(
  'askcrump.password_reset_email_queue_previous_search_path',
  pg_catalog.current_setting('search_path'),
  false
);
select pg_catalog.set_config('search_path', 'pg_catalog,public', false);

do $preflight$
declare
  queue_table regclass := pg_catalog.to_regclass('public.password_reset_email_jobs');
  users_table regclass := pg_catalog.to_regclass('public.users');
  users_email_index regclass := pg_catalog.to_regclass('public.users_email_lower_unique');
  users_reset_index regclass := pg_catalog.to_regclass(
    'public.users_password_reset_token_hash_unique'
  );
  consume_reset_oid oid := pg_catalog.to_regprocedure(
    'public.consume_password_reset_v1(text,text)'
  );
  signature text;
  function_oid oid;
  expected_signatures constant text[] := array[
    'public.enqueue_password_reset_email_job_v1(uuid,text,text,text,timestamp with time zone,text,text,text,text,text,text,text)',
    'public.claim_password_reset_email_job_v1(uuid,integer)',
    'public.stage_password_reset_email_job_v1(uuid,uuid)',
    'public.complete_password_reset_email_job_v1(uuid,uuid,text)',
    'public.release_password_reset_email_job_v1(uuid,uuid,text,boolean,integer)'
  ];
  expected_source_md5 constant text[] := array[
    '87e581a23206212e5849874678724fd8',
    '800d71fa7c64b0e68f07c07a983b8c2e',
    'cca37a6afc7cbfc5505c17d731e05604',
    'd2853f62a23039f871eb2acbc051ee27',
    '21451f26c3f9b26d1d1e73b59331f5ae'
  ];
  expected_columns constant text[] := array[
    '1:id:uuid:NO:',
    '2:delivery_mode:text:NO:',
    '3:user_id:uuid:YES:',
    '4:recipient_fingerprint:text:NO:',
    '5:password_reset_token_hash:text:NO:',
    '6:password_reset_expires:timestamptz:NO:',
    '7:alias_key_id:text:NO:',
    '8:alias_nonce:text:NO:',
    '9:status:text:NO:',
    '10:attempts:int4:NO:0',
    '11:next_attempt_at:timestamptz:NO:clock_timestamp()',
    '12:lease_token:uuid:YES:',
    '13:lease_expires_at:timestamptz:YES:',
    '14:template_version:text:NO:',
    '15:app_name:text:NO:',
    '16:app_url:text:NO:',
    '17:support_email:text:NO:',
    '18:from_email:text:NO:',
    '19:staged_at:timestamptz:YES:',
    '20:last_failure_code:text:YES:',
    '21:terminal_at:timestamptz:YES:',
    '22:created_at:timestamptz:NO:clock_timestamp()',
    '23:updated_at:timestamptz:NO:clock_timestamp()',
    '24:claim_token_history:_uuid:NO:''{}''::uuid[]'
  ];
  expected_constraints constant text[] := array[
    'password_reset_email_jobs_alias_key_id_check:c:CHECK (alias_key_id ~ ''^[A-Za-z0-9_-]{1,16}$''::text)',
    'password_reset_email_jobs_alias_nonce_check:c:CHECK (alias_nonce ~ ''^[A-Za-z0-9_-]{16,64}$''::text)',
    'password_reset_email_jobs_app_name_check:c:CHECK (length(app_name) >= 1 AND length(app_name) <= 120)',
    'password_reset_email_jobs_app_url_check:c:CHECK (length(app_url) >= 1 AND length(app_url) <= 500)',
    'password_reset_email_jobs_attempts_check:c:CHECK (attempts >= 0 AND attempts <= 6)',
    'password_reset_email_jobs_claim_token_history_check:c:CHECK (cardinality(claim_token_history) = attempts)',
    'password_reset_email_jobs_delivery_mode_check:c:CHECK (delivery_mode = ANY (ARRAY[''deliverable''::text, ''suppressed''::text]))',
    'password_reset_email_jobs_from_email_check:c:CHECK (length(from_email) >= 3 AND length(from_email) <= 320)',
    'password_reset_email_jobs_last_failure_code_check:c:CHECK (last_failure_code IS NULL OR (last_failure_code = ANY (ARRAY[''PROVIDER_TRANSPORT''::text, ''PROVIDER_THROTTLED''::text, ''PROVIDER_UNAVAILABLE''::text, ''PROVIDER_REJECTED''::text, ''SIGNING_KEY_UNAVAILABLE''::text, ''JOB_INTEGRITY_INVALID''::text, ''EMAIL_NOT_CONFIGURED''::text, ''WORKER_UNEXPECTED''::text])))',
    'password_reset_email_jobs_lease_state_check:c:CHECK (status = ''processing''::text AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL OR status <> ''processing''::text AND lease_token IS NULL AND lease_expires_at IS NULL)',
    'password_reset_email_jobs_mode_user_check:c:CHECK (delivery_mode = ''deliverable''::text AND user_id IS NOT NULL OR delivery_mode = ''suppressed''::text AND user_id IS NULL)',
    'password_reset_email_jobs_password_reset_token_hash_check:c:CHECK (password_reset_token_hash ~ ''^[0-9a-f]{64}$''::text)',
    'password_reset_email_jobs_pkey:p:PRIMARY KEY (id)',
    'password_reset_email_jobs_recipient_fingerprint_check:c:CHECK (recipient_fingerprint ~ ''^[0-9a-f]{64}$''::text)',
    'password_reset_email_jobs_status_check:c:CHECK (status = ANY (ARRAY[''queued''::text, ''processing''::text, ''provider_accepted''::text, ''suppressed''::text, ''failed_permanent''::text]))',
    'password_reset_email_jobs_support_email_check:c:CHECK (length(support_email) >= 3 AND length(support_email) <= 320)',
    'password_reset_email_jobs_template_version_check:c:CHECK (template_version = ''password-reset-v1''::text)',
    'password_reset_email_jobs_terminal_state_check:c:CHECK ((status = ANY (ARRAY[''provider_accepted''::text, ''suppressed''::text, ''failed_permanent''::text])) AND terminal_at IS NOT NULL OR (status = ANY (ARRAY[''queued''::text, ''processing''::text])) AND terminal_at IS NULL)',
    'password_reset_email_jobs_user_id_fkey:f:FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE'
  ];
  expected_indexes constant text[] := array[
    'password_reset_email_jobs_claim_token_history_idx:CREATE INDEX password_reset_email_jobs_claim_token_history_idx ON public.password_reset_email_jobs USING gin (claim_token_history)',
    'password_reset_email_jobs_expired_lease_idx:CREATE INDEX password_reset_email_jobs_expired_lease_idx ON public.password_reset_email_jobs USING btree (lease_expires_at, created_at, id) WHERE (status = ''processing''::text)',
    'password_reset_email_jobs_lease_token_unique:CREATE UNIQUE INDEX password_reset_email_jobs_lease_token_unique ON public.password_reset_email_jobs USING btree (lease_token) WHERE (lease_token IS NOT NULL)',
    'password_reset_email_jobs_pkey:CREATE UNIQUE INDEX password_reset_email_jobs_pkey ON public.password_reset_email_jobs USING btree (id)',
    'password_reset_email_jobs_ready_idx:CREATE INDEX password_reset_email_jobs_ready_idx ON public.password_reset_email_jobs USING btree (next_attempt_at, created_at, id) WHERE (status = ''queued''::text)',
    'password_reset_email_jobs_terminal_retention_idx:CREATE INDEX password_reset_email_jobs_terminal_retention_idx ON public.password_reset_email_jobs USING btree (terminal_at, id) WHERE (terminal_at IS NOT NULL)',
    'password_reset_email_jobs_user_idx:CREATE INDEX password_reset_email_jobs_user_idx ON public.password_reset_email_jobs USING btree (user_id) WHERE (user_id IS NOT NULL)'
  ];
begin
  if users_table is null then
    raise exception 'password-reset-email queue requires public.users.' using errcode = '55000';
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'service_role')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'anon')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticated') then
    raise exception 'password-reset-email queue database roles are missing.' using errcode = '55000';
  end if;
  if (
    select pg_catalog.count(*)
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'users'
      and (
        (column_name = 'id' and data_type = 'uuid' and is_nullable = 'NO')
        or (column_name = 'email' and data_type = 'text' and is_nullable = 'NO')
        or (column_name = 'is_guest' and data_type = 'boolean'
            and is_nullable = 'NO' and column_default = 'false')
        or (column_name = 'deleted_at' and data_type = 'timestamp with time zone' and is_nullable = 'YES')
        or (column_name = 'password_reset_token_hash' and data_type = 'text'
            and is_nullable = 'YES' and column_default is null)
        or (column_name = 'password_reset_expires'
            and data_type = 'timestamp with time zone'
            and is_nullable = 'YES' and column_default is null)
        or (column_name = 'updated_at'
            and data_type = 'timestamp with time zone'
            and is_nullable in ('YES', 'NO')
            and column_default = 'now()')
      )
  ) <> 7 then
    raise exception 'unexpected users password-reset columns.' using errcode = '55000';
  end if;
  if users_email_index is null or not exists (
    select 1
    from pg_catalog.pg_index as index_row
    where index_row.indexrelid = users_email_index
      and index_row.indrelid = users_table
      and index_row.indisunique is true
      and index_row.indisvalid is true
      and index_row.indisready is true
      and pg_catalog.pg_get_indexdef(index_row.indexrelid)
           = 'CREATE UNIQUE INDEX users_email_lower_unique ON public.users USING btree (lower(email))'
  ) then
    raise exception 'users lower-email unique index drifted; refusing queue migration.' using errcode = '55000';
  end if;
  if users_reset_index is null or not exists (
    select 1
    from pg_catalog.pg_index as index_row
    where index_row.indexrelid = users_reset_index
      and index_row.indrelid = users_table
      and index_row.indisunique is true
      and index_row.indisvalid is true
      and index_row.indisready is true
      and index_row.indnkeyatts = 1
      and index_row.indnatts = 1
      and pg_catalog.pg_get_indexdef(index_row.indexrelid)
           = 'CREATE UNIQUE INDEX users_password_reset_token_hash_unique ON public.users USING btree (password_reset_token_hash) WHERE (password_reset_token_hash IS NOT NULL)'
  ) then
    raise exception 'password-reset unique index drifted; refusing queue migration.' using errcode = '55000';
  end if;
  if consume_reset_oid is null or (
    select pg_catalog.pg_get_userbyid(proc_row.proowner) <> 'postgres'
      or proc_row.prosecdef is not true
      or proc_row.provolatile <> 'v'
      or proc_row.proconfig is distinct from array['search_path=""']::text[]
      or pg_catalog.md5(proc_row.prosrc) <> '4d1195085da460fc77ad53fe8d5ff654'
      or pg_catalog.pg_get_function_result(proc_row.oid)
           <> 'TABLE(reset_applied boolean)'
      or pg_catalog.obj_description(proc_row.oid, 'pg_proc') is distinct from
           'Atomically consumes one password-reset token, updates its account, and revokes every active session.'
      or (
        select pg_catalog.count(*)
        from pg_catalog.aclexplode(
          coalesce(
            proc_row.proacl,
            pg_catalog.acldefault('f', proc_row.proowner)
          )
        )
      ) <> 2
      or exists (
        select 1
        from pg_catalog.aclexplode(
          coalesce(
            proc_row.proacl,
            pg_catalog.acldefault('f', proc_row.proowner)
          )
        ) as acl_row
        left join pg_catalog.pg_roles as role_row on role_row.oid = acl_row.grantee
        where acl_row.privilege_type <> 'EXECUTE'
           or acl_row.is_grantable
           or coalesce(role_row.rolname, '') not in ('postgres', 'service_role')
      )
      or not pg_catalog.has_function_privilege('service_role', consume_reset_oid, 'EXECUTE')
      or pg_catalog.has_function_privilege('anon', consume_reset_oid, 'EXECUTE')
      or pg_catalog.has_function_privilege('authenticated', consume_reset_oid, 'EXECUTE')
    from pg_catalog.pg_proc as proc_row
    where proc_row.oid = consume_reset_oid
  ) then
    raise exception 'atomic password-reset consumer drifted; refusing queue migration.' using errcode = '55000';
  end if;

  if queue_table is not null and (
    select class_row.relkind <> 'r'
      or class_row.relpersistence <> 'p'
      or pg_catalog.pg_get_userbyid(class_row.relowner) <> 'postgres'
      or class_row.relrowsecurity is not true
      or class_row.relforcerowsecurity is not true
      or coalesce(class_row.relacl::text, '') <> '{postgres=arwdDxtm/postgres}'
      or pg_catalog.obj_description(class_row.oid, 'pg_class')
           is distinct from 'ASK_CRUMP_PASSWORD_RESET_EMAIL_JOBS_V1'
    from pg_catalog.pg_class as class_row
    where class_row.oid = queue_table
  ) then
    raise exception 'password_reset_email_jobs drifted; refusing replacement.' using errcode = '55000';
  end if;
  if queue_table is not null and (
    select pg_catalog.array_agg(
      pg_catalog.format(
        '%s:%s:%s:%s:%s',
        ordinal_position,
        column_name,
        udt_name,
        is_nullable,
        coalesce(column_default, '')
      )
      order by ordinal_position
    )
    from information_schema.columns
    where table_schema = 'public' and table_name = 'password_reset_email_jobs'
  ) is distinct from expected_columns then
    raise exception 'password_reset_email_jobs column shape drifted.' using errcode = '55000';
  end if;
  if queue_table is not null and (
    select pg_catalog.array_agg(
      constraint_row.conname || ':' || constraint_row.contype::text || ':'
        || pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
      order by constraint_row.conname
    )
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid = queue_table
  ) is distinct from expected_constraints then
    raise exception 'password_reset_email_jobs constraint shape drifted.' using errcode = '55000';
  end if;
  if queue_table is not null and (
    exists (
      select 1
      from pg_catalog.pg_attribute as attribute_row
      where attribute_row.attrelid = queue_table
        and attribute_row.attnum > 0
        and attribute_row.attisdropped is not true
        and attribute_row.attacl is not null
    )
    or exists (
      select 1
      from pg_catalog.pg_policy as policy_row
      where policy_row.polrelid = queue_table
    )
  ) then
    raise exception 'password_reset_email_jobs column ACL or policy drifted.' using errcode = '55000';
  end if;
  if queue_table is not null and (
    select pg_catalog.count(*) <> 4
      or pg_catalog.count(*) filter (
        where trigger_row.tgenabled <> 'O' or trigger_row.tgisinternal is not true
      ) <> 0
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_constraint as constraint_row
      on constraint_row.oid = trigger_row.tgconstraint
    where constraint_row.conrelid = queue_table
      and constraint_row.conname = 'password_reset_email_jobs_user_id_fkey'
      and constraint_row.contype = 'f'
  ) then
    raise exception 'password_reset_email_jobs foreign-key triggers drifted.' using errcode = '55000';
  end if;
  if queue_table is not null and (
    (
      select pg_catalog.count(*) <> 2
        or pg_catalog.count(*) filter (
          where trigger_row.tgenabled <> 'O'
             or trigger_row.tgisinternal is not true
             or constraint_row.conname <> 'password_reset_email_jobs_user_id_fkey'
             or constraint_row.contype <> 'f'
        ) <> 0
      from pg_catalog.pg_trigger as trigger_row
      left join pg_catalog.pg_constraint as constraint_row
        on constraint_row.oid = trigger_row.tgconstraint
      where trigger_row.tgrelid = queue_table
    )
    or exists (
      select 1
      from pg_catalog.pg_rewrite as rewrite_row
      where rewrite_row.ev_class = queue_table
    )
  ) then
    raise exception 'password_reset_email_jobs trigger or rewrite-rule drifted.' using errcode = '55000';
  end if;
  if queue_table is not null and (
    select pg_catalog.array_agg(index_row.indexname || ':' || index_row.indexdef order by index_row.indexname)
    from pg_catalog.pg_indexes as index_row
    where index_row.schemaname = 'public'
      and index_row.tablename = 'password_reset_email_jobs'
  ) is distinct from expected_indexes then
    raise exception 'password_reset_email_jobs index shape drifted.' using errcode = '55000';
  end if;
  if queue_table is not null and exists (
    select 1
    from pg_catalog.pg_index as index_row
    where index_row.indrelid = queue_table
      and (index_row.indisvalid is not true or index_row.indisready is not true)
  ) then
    raise exception 'password_reset_email_jobs index state drifted.' using errcode = '55000';
  end if;

  foreach signature in array expected_signatures loop
    function_oid := pg_catalog.to_regprocedure(signature);
    if function_oid is not null and (
      select pg_catalog.pg_get_userbyid(proc_row.proowner) <> 'postgres'
        or proc_row.prosecdef is not true
        or proc_row.provolatile <> 'v'
        or proc_row.proconfig is distinct from array['search_path=""']::text[]
        or pg_catalog.strpos(proc_row.prosrc, 'ASK_CRUMP_PASSWORD_RESET_EMAIL_QUEUE_V1') = 0
        or pg_catalog.md5(proc_row.prosrc) <>
          expected_source_md5[pg_catalog.array_position(expected_signatures, signature)]
        or not pg_catalog.has_function_privilege('service_role', function_oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('anon', function_oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('authenticated', function_oid, 'EXECUTE')
        or exists (
          select 1
          from pg_catalog.aclexplode(
            coalesce(
              proc_row.proacl,
              pg_catalog.acldefault('f', proc_row.proowner)
            )
          ) as acl_row
          where acl_row.privilege_type <> 'EXECUTE'
             or acl_row.is_grantable
             or acl_row.grantee not in (
               proc_row.proowner,
               (select role_row.oid from pg_catalog.pg_roles as role_row
                where role_row.rolname = 'service_role')
             )
        )
        or not exists (
          select 1
          from pg_catalog.aclexplode(
            coalesce(
              proc_row.proacl,
              pg_catalog.acldefault('f', proc_row.proowner)
            )
          ) as acl_row
          where acl_row.grantee = proc_row.proowner
            and acl_row.privilege_type = 'EXECUTE'
            and not acl_row.is_grantable
        )
        or not exists (
          select 1
          from pg_catalog.aclexplode(
            coalesce(
              proc_row.proacl,
              pg_catalog.acldefault('f', proc_row.proowner)
            )
          ) as acl_row
          join pg_catalog.pg_roles as role_row on role_row.oid = acl_row.grantee
          where role_row.rolname = 'service_role'
            and acl_row.privilege_type = 'EXECUTE'
            and not acl_row.is_grantable
        )
      from pg_catalog.pg_proc as proc_row
      where proc_row.oid = function_oid
    ) then
      raise exception 'password-reset-email queue RPC drifted: %', signature using errcode = '55000';
    end if;
  end loop;

  if exists (
    select 1
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname in (
        'enqueue_password_reset_email_job_v1',
        'claim_password_reset_email_job_v1',
        'stage_password_reset_email_job_v1',
        'complete_password_reset_email_job_v1',
        'release_password_reset_email_job_v1'
      )
      and not proc_row.oid = any (
        pg_catalog.array_remove(
          array(
            select pg_catalog.to_regprocedure(item)
            from pg_catalog.unnest(expected_signatures) as item
          ),
          null
        )
      )
  ) then
    raise exception 'unexpected password-reset-email queue RPC overload.' using errcode = '55000';
  end if;
end;
$preflight$;

create table if not exists public.password_reset_email_jobs (
  id uuid primary key,
  delivery_mode text not null check (delivery_mode in ('deliverable', 'suppressed')),
  user_id uuid references public.users(id) on delete cascade,
  recipient_fingerprint text not null check (recipient_fingerprint ~ '^[0-9a-f]{64}$'),
  password_reset_token_hash text not null check (password_reset_token_hash ~ '^[0-9a-f]{64}$'),
  password_reset_expires timestamptz not null,
  alias_key_id text not null check (alias_key_id ~ '^[A-Za-z0-9_-]{1,16}$'),
  alias_nonce text not null check (alias_nonce ~ '^[A-Za-z0-9_-]{16,64}$'),
  status text not null check (status in ('queued', 'processing', 'provider_accepted', 'suppressed', 'failed_permanent')),
  attempts integer not null default 0 check (attempts between 0 and 6),
  next_attempt_at timestamptz not null default pg_catalog.clock_timestamp(),
  lease_token uuid,
  lease_expires_at timestamptz,
  template_version text not null check (template_version = 'password-reset-v1'),
  app_name text not null check (length(app_name) between 1 and 120),
  app_url text not null check (length(app_url) between 1 and 500),
  support_email text not null check (length(support_email) between 3 and 320),
  from_email text not null check (length(from_email) between 3 and 320),
  staged_at timestamptz,
  last_failure_code text check (last_failure_code is null or last_failure_code in (
    'PROVIDER_TRANSPORT', 'PROVIDER_THROTTLED', 'PROVIDER_UNAVAILABLE',
    'PROVIDER_REJECTED', 'SIGNING_KEY_UNAVAILABLE', 'JOB_INTEGRITY_INVALID',
    'EMAIL_NOT_CONFIGURED', 'WORKER_UNEXPECTED'
  )),
  terminal_at timestamptz,
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  updated_at timestamptz not null default pg_catalog.clock_timestamp(),
  claim_token_history uuid[] not null default '{}'::uuid[],
  constraint password_reset_email_jobs_claim_token_history_check check (
    pg_catalog.cardinality(claim_token_history) = attempts
  ),
  constraint password_reset_email_jobs_mode_user_check check (
    (delivery_mode = 'deliverable' and user_id is not null)
    or (delivery_mode = 'suppressed' and user_id is null)
  ),
  constraint password_reset_email_jobs_lease_state_check check (
    (status = 'processing' and lease_token is not null and lease_expires_at is not null)
    or (status <> 'processing' and lease_token is null and lease_expires_at is null)
  ),
  constraint password_reset_email_jobs_terminal_state_check check (
    (status in ('provider_accepted', 'suppressed', 'failed_permanent') and terminal_at is not null)
    or (status in ('queued', 'processing') and terminal_at is null)
  )
);

alter table public.password_reset_email_jobs owner to postgres;
comment on table public.password_reset_email_jobs is 'ASK_CRUMP_PASSWORD_RESET_EMAIL_JOBS_V1';
alter table public.password_reset_email_jobs enable row level security;
alter table public.password_reset_email_jobs force row level security;
revoke all on table public.password_reset_email_jobs from public, anon, authenticated, service_role;

create unique index if not exists password_reset_email_jobs_lease_token_unique
  on public.password_reset_email_jobs(lease_token) where lease_token is not null;
create index if not exists password_reset_email_jobs_claim_token_history_idx
  on public.password_reset_email_jobs using gin (claim_token_history);
create index if not exists password_reset_email_jobs_user_idx
  on public.password_reset_email_jobs(user_id) where user_id is not null;
create index if not exists password_reset_email_jobs_ready_idx
  on public.password_reset_email_jobs(next_attempt_at, created_at, id) where status = 'queued';
create index if not exists password_reset_email_jobs_expired_lease_idx
  on public.password_reset_email_jobs(lease_expires_at, created_at, id) where status = 'processing';
create index if not exists password_reset_email_jobs_terminal_retention_idx
  on public.password_reset_email_jobs(terminal_at, id) where terminal_at is not null;

create or replace function public.enqueue_password_reset_email_job_v1(
  p_job_id uuid,
  p_normalized_email text,
  p_recipient_fingerprint text,
  p_replacement_token_hash text,
  p_replacement_expires_at timestamptz,
  p_alias_key_id text,
  p_alias_nonce text,
  p_template_version text,
  p_app_name text,
  p_app_url text,
  p_support_email text,
  p_from_email text
)
returns table (accepted boolean, job_id uuid)
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  -- ASK_CRUMP_PASSWORD_RESET_EMAIL_QUEUE_V1
  v_now timestamptz := pg_catalog.clock_timestamp();
  v_user public.users%rowtype;
  v_mode text := 'suppressed';
  v_status text := 'suppressed';
  v_anchor text := pg_catalog.lower(pg_catalog.btrim(p_replacement_token_hash));
  v_expiry timestamptz := p_replacement_expires_at;
  v_existing public.password_reset_email_jobs%rowtype;
begin
  if p_job_id is null
     or p_normalized_email is null
     or length(p_normalized_email) not between 3 and 320
     or p_normalized_email <> pg_catalog.lower(pg_catalog.btrim(p_normalized_email))
     or pg_catalog.strpos(p_normalized_email, '@') < 2
     or p_recipient_fingerprint is null
     or p_recipient_fingerprint !~ '^[0-9a-f]{64}$'
     or p_replacement_token_hash is null
     or v_anchor !~ '^[0-9a-f]{64}$'
     or p_replacement_expires_at is null
     or v_expiry <= v_now + interval '5 minutes'
     or v_expiry > v_now + interval '65 minutes'
     or p_alias_key_id is null
     or p_alias_key_id !~ '^[A-Za-z0-9_-]{1,16}$'
     or p_alias_nonce is null
     or p_alias_nonce !~ '^[A-Za-z0-9_-]{16,64}$'
     or p_template_version is null
     or p_template_version <> 'password-reset-v1'
     or p_app_name is null
     or length(p_app_name) not between 1 and 120
     or p_app_name ~ '[[:cntrl:]]'
     or p_app_url is null
     or length(p_app_url) not between 1 and 500
     or p_app_url !~ '^https?://'
     or p_app_url ~ '[[:cntrl:]]'
     or p_support_email is null
     or length(p_support_email) not between 3 and 320
     or pg_catalog.strpos(p_support_email, '@') < 2
     or p_support_email ~ '[[:cntrl:]]'
     or p_from_email is null
     or length(p_from_email) not between 3 and 320
     or pg_catalog.strpos(p_from_email, '@') < 2
     or p_from_email ~ '[[:cntrl:]]' then
    raise exception 'invalid password-reset-email queue envelope.' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(1179014993, pg_catalog.hashtext(p_job_id::text));

  select job.* into v_existing
  from public.password_reset_email_jobs as job
  where job.id = p_job_id;
  if found then
    if v_existing.recipient_fingerprint <> pg_catalog.lower(p_recipient_fingerprint)
       or v_existing.alias_key_id <> p_alias_key_id
       or v_existing.alias_nonce <> p_alias_nonce
       or v_existing.template_version <> p_template_version
       or v_existing.app_name <> p_app_name
       or v_existing.app_url <> p_app_url
       or v_existing.support_email <> p_support_email
       or v_existing.from_email <> p_from_email then
      raise exception 'password-reset-email queue job replay mismatch.' using errcode = '23505';
    end if;
    return query select true, p_job_id;
    return;
  end if;

  select account.* into v_user
  from public.users as account
  where pg_catalog.lower(account.email) = p_normalized_email
    and account.is_guest is not true
    and account.deleted_at is null
  order by account.id
  for update
  limit 1;

  -- The account lock may have blocked behind a concurrent reset or enqueue.
  -- Refresh the security clock before deciding whether the locked generation
  -- is still usable or whether the replacement candidate is still fresh.
  v_now := pg_catalog.clock_timestamp();
  if v_expiry <= v_now + interval '5 minutes'
     or v_expiry > v_now + interval '65 minutes' then
    raise exception 'invalid password-reset-email queue envelope.' using errcode = '22023';
  end if;

  if found then
    if coalesce(v_user.password_reset_token_hash, '') ~ '^[0-9a-f]{64}$'
       and v_user.password_reset_expires > v_now then
      v_anchor := pg_catalog.lower(v_user.password_reset_token_hash);
      v_expiry := v_user.password_reset_expires;
    else
      update public.users as account
      set password_reset_token_hash = v_anchor,
          password_reset_expires = v_expiry,
          updated_at = v_now
      where account.id = v_user.id
        and account.is_guest is not true
        and account.deleted_at is null;
    end if;
    v_mode := 'deliverable';
    v_status := 'queued';
  end if;

  insert into public.password_reset_email_jobs (
    id, delivery_mode, user_id, recipient_fingerprint,
    password_reset_token_hash, password_reset_expires, alias_key_id,
    alias_nonce, status, next_attempt_at,
    template_version, app_name, app_url, support_email, from_email,
    terminal_at, created_at, updated_at
  ) values (
    p_job_id, v_mode, case when v_mode = 'deliverable' then v_user.id else null end,
    pg_catalog.lower(p_recipient_fingerprint), v_anchor, v_expiry,
    p_alias_key_id, p_alias_nonce, v_status, v_now,
    p_template_version, p_app_name, p_app_url, p_support_email, p_from_email,
    case when v_status = 'suppressed' then v_now else null end, v_now, v_now
  ) on conflict (id) do nothing;

  return query select true, p_job_id;
end;
$$;

create or replace function public.claim_password_reset_email_job_v1(
  p_claim_token uuid,
  p_lease_seconds integer default 120
)
returns table (job_id uuid, lease_token uuid, attempts integer)
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  -- ASK_CRUMP_PASSWORD_RESET_EMAIL_QUEUE_V1
  v_now timestamptz;
  v_lease_seconds integer := least(240, greatest(60, coalesce(p_lease_seconds, 120)));
begin
  if p_claim_token is null then
    raise exception 'claim token is required.' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    1179014994,
    pg_catalog.hashtext(p_claim_token::text)
  );
  v_now := pg_catalog.clock_timestamp();

  -- Claim tokens are durable one-shot fencing values for the retained life of
  -- the queue row. A live replay returns the existing lease; an expired or
  -- completed replay returns no row and cannot consume another job.
  if exists (
    select 1
    from public.password_reset_email_jobs as job
    where job.claim_token_history @> array[p_claim_token]
  ) then
    return query
    select job.id, job.lease_token, job.attempts
    from public.password_reset_email_jobs as job
    where job.claim_token_history @> array[p_claim_token]
      and job.status = 'processing'
      and job.lease_token = p_claim_token
      and job.lease_expires_at > v_now
    order by job.id
    limit 1;
    return;
  end if;

  with stale as (
    select job.id
    from public.password_reset_email_jobs as job
    where (
        job.status = 'queued'
        or (job.status = 'processing' and job.lease_expires_at <= v_now)
      )
      and (
        job.attempts >= 6
        or job.password_reset_expires <= v_now
          + pg_catalog.make_interval(secs => v_lease_seconds)
        or job.created_at <= v_now - interval '55 minutes'
      )
    order by job.created_at, job.id
    for update skip locked
    limit 100
  )
  update public.password_reset_email_jobs as job
  set status = 'failed_permanent',
      last_failure_code = 'JOB_INTEGRITY_INVALID',
      terminal_at = v_now,
      lease_token = null,
      lease_expires_at = null,
      updated_at = v_now
  where job.id in (select stale.id from stale);

  with expired as (
    select job.id
    from public.password_reset_email_jobs as job
    where job.status in ('provider_accepted', 'suppressed', 'failed_permanent')
      and job.terminal_at < v_now - interval '7 days'
    order by job.terminal_at, job.id
    for update skip locked
    limit 100
  )
  delete from public.password_reset_email_jobs as job
  where job.id in (select expired.id from expired);

  return query
  with candidate as (
    select job.id
    from public.password_reset_email_jobs as job
    where (
        (job.status = 'queued' and job.next_attempt_at <= v_now)
        or (job.status = 'processing' and job.lease_expires_at <= v_now)
      )
      and job.attempts < 6
      and job.password_reset_expires > v_now
        + pg_catalog.make_interval(secs => v_lease_seconds)
      and job.created_at > v_now - interval '55 minutes'
    order by job.next_attempt_at, job.created_at, job.id
    for update skip locked
    limit 1
  ), claimed as (
    update public.password_reset_email_jobs as job
    set status = 'processing',
        attempts = least(6, job.attempts + 1),
        lease_token = p_claim_token,
        lease_expires_at = v_now + pg_catalog.make_interval(secs => v_lease_seconds),
        claim_token_history = pg_catalog.array_append(job.claim_token_history, p_claim_token),
        staged_at = null,
        updated_at = v_now
    where job.id = (select candidate.id from candidate)
    returning job.id, job.lease_token, job.attempts
  )
  select claimed.id, claimed.lease_token, claimed.attempts from claimed;
end;
$$;

create or replace function public.stage_password_reset_email_job_v1(
  p_job_id uuid,
  p_lease_token uuid
)
returns table (
  disposition text,
  job_id uuid,
  lease_token uuid,
  user_id uuid,
  recipient_email text,
  recipient_fingerprint text,
  password_reset_token_hash text,
  password_reset_expires timestamptz,
  alias_key_id text,
  alias_nonce text,
  template_version text,
  app_name text,
  app_url text,
  support_email text,
  from_email text,
  attempts integer
)
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  -- ASK_CRUMP_PASSWORD_RESET_EMAIL_QUEUE_V1
  v_now timestamptz;
  v_user_id uuid;
  v_job public.password_reset_email_jobs%rowtype;
  v_user public.users%rowtype;
begin
  select job.user_id into v_user_id
  from public.password_reset_email_jobs as job
  where job.id = p_job_id;

  if v_user_id is not null then
    select account.* into v_user
    from public.users as account
    where account.id = v_user_id
    for update;
  end if;

  select job.* into v_job
  from public.password_reset_email_jobs as job
  where job.id = p_job_id
    and job.status = 'processing'
    and job.lease_token = p_lease_token
  for update;

  if not found then
    return query select 'lease_lost', p_job_id, p_lease_token, null::uuid,
      null::text, null::text, null::text, null::timestamptz,
      null::text, null::text, null::text, null::text,
      null::text, null::text, null::text, null::integer;
    return;
  end if;

  -- Both account and job locks can wait. Sample the security clock only after
  -- acquiring them so an expired lease or reset generation cannot be staged.
  v_now := pg_catalog.clock_timestamp();
  if v_job.lease_expires_at <= v_now then
    return query select 'lease_lost', p_job_id, p_lease_token, null::uuid,
      null::text, null::text, null::text, null::timestamptz,
      null::text, null::text, null::text, null::text,
      null::text, null::text, null::text, null::integer;
    return;
  end if;

  if v_job.delivery_mode <> 'deliverable'
     or v_user.id is null
     or v_user.deleted_at is not null
     or v_user.is_guest is true
     or pg_catalog.lower(coalesce(v_user.password_reset_token_hash, '')) <> v_job.password_reset_token_hash
     or v_user.password_reset_expires is distinct from v_job.password_reset_expires
     or v_job.password_reset_expires <= v_now + interval '30 seconds' then
    return query select 'suppress', v_job.id, v_job.lease_token, null::uuid,
      null::text, null::text, null::text, null::timestamptz,
      null::text, null::text, null::text, null::text,
      null::text, null::text, null::text, v_job.attempts;
    return;
  end if;

  update public.password_reset_email_jobs as job
  set staged_at = coalesce(job.staged_at, v_now), updated_at = v_now
  where job.id = v_job.id
    and job.status = 'processing'
    and job.lease_token = p_lease_token
    and job.lease_expires_at > v_now;
  if not found then
    return query select 'lease_lost', p_job_id, p_lease_token, null::uuid,
      null::text, null::text, null::text, null::timestamptz,
      null::text, null::text, null::text, null::text,
      null::text, null::text, null::text, null::integer;
    return;
  end if;

  return query select 'deliver', v_job.id, v_job.lease_token, v_job.user_id,
    v_user.email, v_job.recipient_fingerprint, v_job.password_reset_token_hash,
    v_job.password_reset_expires, v_job.alias_key_id, v_job.alias_nonce,
    v_job.template_version, v_job.app_name, v_job.app_url,
    v_job.support_email, v_job.from_email, v_job.attempts;
end;
$$;

create or replace function public.complete_password_reset_email_job_v1(
  p_job_id uuid,
  p_lease_token uuid,
  p_outcome text
)
returns text
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  -- ASK_CRUMP_PASSWORD_RESET_EMAIL_QUEUE_V1
  v_status text;
  v_now timestamptz := pg_catalog.clock_timestamp();
begin
  if p_outcome is null or p_outcome not in ('provider_accepted', 'suppressed') then
    raise exception 'invalid password-reset-email completion.' using errcode = '22023';
  end if;
  update public.password_reset_email_jobs as job
  set status = p_outcome,
      terminal_at = v_now,
      lease_token = null,
      lease_expires_at = null,
      updated_at = v_now
  where job.id = p_job_id
    and job.status = 'processing'
    and job.lease_token = p_lease_token
    and job.lease_expires_at > pg_catalog.clock_timestamp()
    and (
      p_outcome <> 'provider_accepted'
      or (job.delivery_mode = 'deliverable' and job.staged_at is not null)
    )
  returning job.status into v_status;
  if v_status is not null then return v_status; end if;
  select job.status into v_status from public.password_reset_email_jobs as job where job.id = p_job_id;
  if v_status = p_outcome then return v_status; end if;
  return 'lease_lost';
end;
$$;

create or replace function public.release_password_reset_email_job_v1(
  p_job_id uuid,
  p_lease_token uuid,
  p_failure_code text,
  p_retryable boolean,
  p_retry_after_seconds integer default null
)
returns text
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  -- ASK_CRUMP_PASSWORD_RESET_EMAIL_QUEUE_V1
  v_job public.password_reset_email_jobs%rowtype;
  v_now timestamptz;
  v_backoff integer;
  v_next timestamptz;
begin
  if p_failure_code is null or p_failure_code not in (
    'PROVIDER_TRANSPORT', 'PROVIDER_THROTTLED', 'PROVIDER_UNAVAILABLE',
    'PROVIDER_REJECTED', 'SIGNING_KEY_UNAVAILABLE', 'JOB_INTEGRITY_INVALID',
    'EMAIL_NOT_CONFIGURED', 'WORKER_UNEXPECTED'
  ) then
    raise exception 'invalid password-reset-email failure class.' using errcode = '22023';
  end if;

  select job.* into v_job
  from public.password_reset_email_jobs as job
  where job.id = p_job_id
    and job.status = 'processing'
    and job.lease_token = p_lease_token
  for update;
  if not found then return 'lease_lost'; end if;

  v_now := pg_catalog.clock_timestamp();
  if v_job.lease_expires_at <= v_now then return 'lease_lost'; end if;

  v_backoff := least(3600, greatest(
    coalesce(p_retry_after_seconds, 0),
    (30 * pg_catalog.power(2::numeric, greatest(0, least(v_job.attempts - 1, 6))))::integer
  ));
  v_next := v_now + pg_catalog.make_interval(secs => v_backoff);

  if p_retryable is not true
     or v_job.attempts >= 6
     or v_next + interval '2 minutes' >= v_job.password_reset_expires
     or v_next >= v_job.created_at + interval '55 minutes' then
    update public.password_reset_email_jobs as job
    set status = 'failed_permanent', last_failure_code = p_failure_code,
        terminal_at = v_now, lease_token = null, lease_expires_at = null,
        updated_at = v_now
    where job.id = v_job.id
      and job.status = 'processing'
      and job.lease_token = p_lease_token
      and job.lease_expires_at > v_now;
    if not found then return 'lease_lost'; end if;
    return 'failed_permanent';
  end if;

  update public.password_reset_email_jobs as job
  set status = 'queued', next_attempt_at = v_next,
      last_failure_code = p_failure_code, lease_token = null,
      lease_expires_at = null, updated_at = v_now
  where job.id = v_job.id
    and job.status = 'processing'
    and job.lease_token = p_lease_token
    and job.lease_expires_at > v_now;
  if not found then return 'lease_lost'; end if;
  return 'retry_scheduled';
end;
$$;

alter function public.enqueue_password_reset_email_job_v1(uuid,text,text,text,timestamptz,text,text,text,text,text,text,text) owner to postgres;
alter function public.claim_password_reset_email_job_v1(uuid,integer) owner to postgres;
alter function public.stage_password_reset_email_job_v1(uuid,uuid) owner to postgres;
alter function public.complete_password_reset_email_job_v1(uuid,uuid,text) owner to postgres;
alter function public.release_password_reset_email_job_v1(uuid,uuid,text,boolean,integer) owner to postgres;

revoke all on function public.enqueue_password_reset_email_job_v1(uuid,text,text,text,timestamptz,text,text,text,text,text,text,text) from public, anon, authenticated, service_role;
revoke all on function public.claim_password_reset_email_job_v1(uuid,integer) from public, anon, authenticated, service_role;
revoke all on function public.stage_password_reset_email_job_v1(uuid,uuid) from public, anon, authenticated, service_role;
revoke all on function public.complete_password_reset_email_job_v1(uuid,uuid,text) from public, anon, authenticated, service_role;
revoke all on function public.release_password_reset_email_job_v1(uuid,uuid,text,boolean,integer) from public, anon, authenticated, service_role;

grant execute on function public.enqueue_password_reset_email_job_v1(uuid,text,text,text,timestamptz,text,text,text,text,text,text,text) to service_role;
grant execute on function public.claim_password_reset_email_job_v1(uuid,integer) to service_role;
grant execute on function public.stage_password_reset_email_job_v1(uuid,uuid) to service_role;
grant execute on function public.complete_password_reset_email_job_v1(uuid,uuid,text) to service_role;
grant execute on function public.release_password_reset_email_job_v1(uuid,uuid,text,boolean,integer) to service_role;

do $postflight$
declare
  queue_table regclass := 'public.password_reset_email_jobs'::regclass;
  signature text;
  function_oid oid;
  expected_signatures constant text[] := array[
    'public.enqueue_password_reset_email_job_v1(uuid,text,text,text,timestamp with time zone,text,text,text,text,text,text,text)',
    'public.claim_password_reset_email_job_v1(uuid,integer)',
    'public.stage_password_reset_email_job_v1(uuid,uuid)',
    'public.complete_password_reset_email_job_v1(uuid,uuid,text)',
    'public.release_password_reset_email_job_v1(uuid,uuid,text,boolean,integer)'
  ];
  expected_source_md5 constant text[] := array[
    '87e581a23206212e5849874678724fd8',
    '800d71fa7c64b0e68f07c07a983b8c2e',
    'cca37a6afc7cbfc5505c17d731e05604',
    'd2853f62a23039f871eb2acbc051ee27',
    '21451f26c3f9b26d1d1e73b59331f5ae'
  ];
  expected_indexes constant text[] := array[
    'password_reset_email_jobs_claim_token_history_idx:CREATE INDEX password_reset_email_jobs_claim_token_history_idx ON public.password_reset_email_jobs USING gin (claim_token_history)',
    'password_reset_email_jobs_expired_lease_idx:CREATE INDEX password_reset_email_jobs_expired_lease_idx ON public.password_reset_email_jobs USING btree (lease_expires_at, created_at, id) WHERE (status = ''processing''::text)',
    'password_reset_email_jobs_lease_token_unique:CREATE UNIQUE INDEX password_reset_email_jobs_lease_token_unique ON public.password_reset_email_jobs USING btree (lease_token) WHERE (lease_token IS NOT NULL)',
    'password_reset_email_jobs_pkey:CREATE UNIQUE INDEX password_reset_email_jobs_pkey ON public.password_reset_email_jobs USING btree (id)',
    'password_reset_email_jobs_ready_idx:CREATE INDEX password_reset_email_jobs_ready_idx ON public.password_reset_email_jobs USING btree (next_attempt_at, created_at, id) WHERE (status = ''queued''::text)',
    'password_reset_email_jobs_terminal_retention_idx:CREATE INDEX password_reset_email_jobs_terminal_retention_idx ON public.password_reset_email_jobs USING btree (terminal_at, id) WHERE (terminal_at IS NOT NULL)',
    'password_reset_email_jobs_user_idx:CREATE INDEX password_reset_email_jobs_user_idx ON public.password_reset_email_jobs USING btree (user_id) WHERE (user_id IS NOT NULL)'
  ];
begin
  if (
       select class_row.relkind <> 'r'
         or class_row.relpersistence <> 'p'
         or pg_catalog.pg_get_userbyid(class_row.relowner) <> 'postgres'
         or class_row.relrowsecurity is not true
         or class_row.relforcerowsecurity is not true
         or coalesce(class_row.relacl::text, '') <> '{postgres=arwdDxtm/postgres}'
         or pg_catalog.obj_description(class_row.oid, 'pg_class')
              is distinct from 'ASK_CRUMP_PASSWORD_RESET_EMAIL_JOBS_V1'
       from pg_catalog.pg_class as class_row
       where class_row.oid = queue_table
     )
     or pg_catalog.has_table_privilege('service_role', queue_table, 'SELECT')
     or pg_catalog.has_table_privilege('service_role', queue_table, 'INSERT')
     or pg_catalog.has_table_privilege('service_role', queue_table, 'UPDATE')
     or pg_catalog.has_table_privilege('service_role', queue_table, 'DELETE')
     or pg_catalog.has_table_privilege('anon', queue_table, 'SELECT')
     or pg_catalog.has_table_privilege('authenticated', queue_table, 'SELECT')
     or exists (
       select 1
       from pg_catalog.pg_attribute as attribute_row
       where attribute_row.attrelid = queue_table
         and attribute_row.attnum > 0
         and attribute_row.attisdropped is not true
         and attribute_row.attacl is not null
     )
     or exists (
       select 1
       from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid = queue_table
     ) then
    raise exception 'password-reset-email queue table ACL is unsafe.' using errcode = '55000';
  end if;
  if (
    select pg_catalog.count(*) <> 4
      or pg_catalog.count(*) filter (
        where trigger_row.tgenabled <> 'O' or trigger_row.tgisinternal is not true
      ) <> 0
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_constraint as constraint_row
      on constraint_row.oid = trigger_row.tgconstraint
    where constraint_row.conrelid = queue_table
      and constraint_row.conname = 'password_reset_email_jobs_user_id_fkey'
      and constraint_row.contype = 'f'
  ) then
    raise exception 'password-reset-email queue foreign-key trigger contract failed.' using errcode = '55000';
  end if;
  if (
    (
      select pg_catalog.count(*) <> 2
        or pg_catalog.count(*) filter (
          where trigger_row.tgenabled <> 'O'
             or trigger_row.tgisinternal is not true
             or constraint_row.conname <> 'password_reset_email_jobs_user_id_fkey'
             or constraint_row.contype <> 'f'
        ) <> 0
      from pg_catalog.pg_trigger as trigger_row
      left join pg_catalog.pg_constraint as constraint_row
        on constraint_row.oid = trigger_row.tgconstraint
      where trigger_row.tgrelid = queue_table
    )
    or exists (
      select 1
      from pg_catalog.pg_rewrite as rewrite_row
      where rewrite_row.ev_class = queue_table
    )
  ) then
    raise exception 'password-reset-email queue trigger or rewrite-rule contract failed.' using errcode = '55000';
  end if;
  if (
    select pg_catalog.array_agg(index_class.relname || ':' || pg_catalog.pg_get_indexdef(index_row.indexrelid) order by index_class.relname)
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as index_class on index_class.oid = index_row.indexrelid
    where index_row.indrelid = queue_table
  ) is distinct from expected_indexes
     or exists (
       select 1
       from pg_catalog.pg_index as index_row
       where index_row.indrelid = queue_table
         and (index_row.indisvalid is not true or index_row.indisready is not true)
     ) then
    raise exception 'password-reset-email queue index contract is incomplete.' using errcode = '55000';
  end if;

  foreach signature in array expected_signatures loop
    function_oid := pg_catalog.to_regprocedure(signature);
    if function_oid is null or (
      select pg_catalog.pg_get_userbyid(proc_row.proowner) <> 'postgres'
        or proc_row.prosecdef is not true
        or proc_row.provolatile <> 'v'
        or proc_row.proconfig is distinct from array['search_path=""']::text[]
        or pg_catalog.md5(proc_row.prosrc) <>
          expected_source_md5[pg_catalog.array_position(expected_signatures, signature)]
        or (
          select pg_catalog.count(*)
          from pg_catalog.aclexplode(
            coalesce(
              proc_row.proacl,
              pg_catalog.acldefault('f', proc_row.proowner)
            )
          )
        ) <> 2
        or pg_catalog.has_function_privilege('anon', function_oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('authenticated', function_oid, 'EXECUTE')
        or exists (
          select 1
          from pg_catalog.aclexplode(
            coalesce(
              proc_row.proacl,
              pg_catalog.acldefault('f', proc_row.proowner)
            )
          ) as acl_row
          left join pg_catalog.pg_roles as role_row on role_row.oid = acl_row.grantee
          where acl_row.privilege_type <> 'EXECUTE'
             or acl_row.is_grantable
             or coalesce(role_row.rolname, '') not in ('postgres', 'service_role')
        )
        or not pg_catalog.has_function_privilege('service_role', function_oid, 'EXECUTE')
      from pg_catalog.pg_proc as proc_row
      where proc_row.oid = function_oid
    ) then
      raise exception 'password-reset-email queue RPC postflight failed: %', signature using errcode = '55000';
    end if;
  end loop;
end;
$postflight$;

select pg_catalog.set_config(
  'search_path',
  pg_catalog.current_setting('askcrump.password_reset_email_queue_previous_search_path'),
  false
);
reset askcrump.password_reset_email_queue_previous_search_path;
