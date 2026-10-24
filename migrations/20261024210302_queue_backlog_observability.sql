-- Privacy-safe aggregate observability for the two durable email queues.
--
-- The migration runner owns transaction control. This migration exposes one
-- fixed aggregate-only row to service_role. It adds no table grants, policy,
-- view, materialized state, trigger, counter, identifier, timestamp, status
-- breakdown, failure detail, or customer content.

select pg_catalog.set_config(
  'askcrump.email_queue_backlog_previous_search_path',
  pg_catalog.current_setting('search_path'),
  false
);
select pg_catalog.set_config(
  'askcrump.email_queue_backlog_previous_quote_all_identifiers',
  pg_catalog.current_setting('quote_all_identifiers'),
  false
);
select pg_catalog.set_config('search_path', 'pg_catalog,public', false);
select pg_catalog.set_config('quote_all_identifiers', 'off', false);

do $preflight$
declare
  verification_table regclass := pg_catalog.to_regclass(
    'public.verification_email_jobs'
  );
  password_reset_table regclass := pg_catalog.to_regclass(
    'public.password_reset_email_jobs'
  );
  verification_claim oid := pg_catalog.to_regprocedure(
    'public.claim_verification_email_job_v1(uuid,integer)'
  );
  password_reset_claim oid := pg_catalog.to_regprocedure(
    'public.claim_password_reset_email_job_v1(uuid,integer)'
  );
  backlog_function oid := pg_catalog.to_regprocedure(
    'public.read_email_queue_backlog_v1()'
  );
  function_oid oid;
  signature text;
  source_md5 text;
  source_marker text;
  verification_fingerprint text;
  password_reset_fingerprint text;
  expected_backlog_source_md5 constant text := 'efae7a5f9fb838ddcfbcdc4385f0b745';
  expected_backlog_result constant text :=
    'TABLE(verification_active_depth bigint, verification_eligible_depth bigint, verification_oldest_eligible_job_age_seconds bigint, password_reset_active_depth bigint, password_reset_eligible_depth bigint, password_reset_oldest_eligible_job_age_seconds bigint)';
  claim_signatures constant text[] := array[
    'public.claim_verification_email_job_v1(uuid,integer)',
    'public.claim_password_reset_email_job_v1(uuid,integer)'
  ];
  claim_source_md5 constant text[] := array[
    'd6dd16c8e13ef88708663ec6b076f9ef',
    '800d71fa7c64b0e68f07c07a983b8c2e'
  ];
  claim_source_markers constant text[] := array[
    'ASK_CRUMP_VERIFICATION_EMAIL_QUEUE_V1',
    'ASK_CRUMP_PASSWORD_RESET_EMAIL_QUEUE_V1'
  ];
  verification_columns constant text[] := array[
    '1:id:uuid:NO:',
    '2:delivery_mode:text:NO:',
    '3:user_id:uuid:YES:',
    '4:recipient_fingerprint:text:NO:',
    '5:verification_token_hash:text:NO:',
    '6:verification_token_expires:timestamptz:NO:',
    '7:alias_key_id:text:NO:',
    '8:alias_nonce:text:NO:',
    '9:intent:text:YES:',
    '10:plan:text:YES:',
    '11:status:text:NO:',
    '12:attempts:int4:NO:0',
    '13:next_attempt_at:timestamptz:NO:clock_timestamp()',
    '14:lease_token:uuid:YES:',
    '15:lease_expires_at:timestamptz:YES:',
    '16:template_version:text:NO:',
    '17:app_name:text:NO:',
    '18:app_url:text:NO:',
    '19:support_email:text:NO:',
    '20:from_email:text:NO:',
    '21:staged_at:timestamptz:YES:',
    '22:last_failure_code:text:YES:',
    '23:terminal_at:timestamptz:YES:',
    '24:created_at:timestamptz:NO:clock_timestamp()',
    '25:updated_at:timestamptz:NO:clock_timestamp()',
    '26:claim_token_history:_uuid:NO:''{}''::uuid[]'
  ];
  verification_constraints constant text[] := array[
    'verification_email_jobs_alias_key_id_check:c:CHECK (alias_key_id ~ ''^[A-Za-z0-9_-]{1,16}$''::text)',
    'verification_email_jobs_alias_nonce_check:c:CHECK (alias_nonce ~ ''^[A-Za-z0-9_-]{16,64}$''::text)',
    'verification_email_jobs_app_name_check:c:CHECK (length(app_name) >= 1 AND length(app_name) <= 120)',
    'verification_email_jobs_app_url_check:c:CHECK (length(app_url) >= 1 AND length(app_url) <= 500)',
    'verification_email_jobs_attempts_check:c:CHECK (attempts >= 0 AND attempts <= 6)',
    'verification_email_jobs_claim_token_history_check:c:CHECK (cardinality(claim_token_history) = attempts)',
    'verification_email_jobs_delivery_mode_check:c:CHECK (delivery_mode = ANY (ARRAY[''deliverable''::text, ''suppressed''::text]))',
    'verification_email_jobs_from_email_check:c:CHECK (length(from_email) >= 3 AND length(from_email) <= 320)',
    'verification_email_jobs_intent_check:c:CHECK (intent IS NULL OR (intent = ANY (ARRAY[''document''::text, ''image''::text, ''presentation''::text, ''resume''::text, ''video''::text, ''projects''::text])))',
    'verification_email_jobs_last_failure_code_check:c:CHECK (last_failure_code IS NULL OR (last_failure_code = ANY (ARRAY[''PROVIDER_TRANSPORT''::text, ''PROVIDER_THROTTLED''::text, ''PROVIDER_UNAVAILABLE''::text, ''PROVIDER_REJECTED''::text, ''SIGNING_KEY_UNAVAILABLE''::text, ''JOB_INTEGRITY_INVALID''::text, ''EMAIL_NOT_CONFIGURED''::text, ''WORKER_UNEXPECTED''::text])))',
    'verification_email_jobs_lease_state_check:c:CHECK (status = ''processing''::text AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL OR status <> ''processing''::text AND lease_token IS NULL AND lease_expires_at IS NULL)',
    'verification_email_jobs_mode_user_check:c:CHECK (delivery_mode = ''deliverable''::text AND user_id IS NOT NULL OR delivery_mode = ''suppressed''::text AND user_id IS NULL)',
    'verification_email_jobs_pkey:p:PRIMARY KEY (id)',
    'verification_email_jobs_plan_check:c:CHECK (plan IS NULL OR (plan = ANY (ARRAY[''professional''::text, ''enterprise''::text])))',
    'verification_email_jobs_recipient_fingerprint_check:c:CHECK (recipient_fingerprint ~ ''^[0-9a-f]{64}$''::text)',
    'verification_email_jobs_status_check:c:CHECK (status = ANY (ARRAY[''queued''::text, ''processing''::text, ''provider_accepted''::text, ''suppressed''::text, ''failed_permanent''::text]))',
    'verification_email_jobs_support_email_check:c:CHECK (length(support_email) >= 3 AND length(support_email) <= 320)',
    'verification_email_jobs_template_version_check:c:CHECK (template_version = ''verification-v1''::text)',
    'verification_email_jobs_terminal_state_check:c:CHECK ((status = ANY (ARRAY[''provider_accepted''::text, ''suppressed''::text, ''failed_permanent''::text])) AND terminal_at IS NOT NULL OR (status = ANY (ARRAY[''queued''::text, ''processing''::text])) AND terminal_at IS NULL)',
    'verification_email_jobs_user_id_fkey:f:FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE',
    'verification_email_jobs_verification_token_hash_check:c:CHECK (verification_token_hash ~ ''^[0-9a-f]{64}$''::text)'
  ];
  verification_indexes constant text[] := array[
    'verification_email_jobs_claim_token_history_idx:CREATE INDEX verification_email_jobs_claim_token_history_idx ON public.verification_email_jobs USING gin (claim_token_history)',
    'verification_email_jobs_expired_lease_idx:CREATE INDEX verification_email_jobs_expired_lease_idx ON public.verification_email_jobs USING btree (lease_expires_at, created_at, id) WHERE (status = ''processing''::text)',
    'verification_email_jobs_lease_token_unique:CREATE UNIQUE INDEX verification_email_jobs_lease_token_unique ON public.verification_email_jobs USING btree (lease_token) WHERE (lease_token IS NOT NULL)',
    'verification_email_jobs_pkey:CREATE UNIQUE INDEX verification_email_jobs_pkey ON public.verification_email_jobs USING btree (id)',
    'verification_email_jobs_ready_idx:CREATE INDEX verification_email_jobs_ready_idx ON public.verification_email_jobs USING btree (next_attempt_at, created_at, id) WHERE (status = ''queued''::text)',
    'verification_email_jobs_terminal_retention_idx:CREATE INDEX verification_email_jobs_terminal_retention_idx ON public.verification_email_jobs USING btree (terminal_at, id) WHERE (terminal_at IS NOT NULL)',
    'verification_email_jobs_user_idx:CREATE INDEX verification_email_jobs_user_idx ON public.verification_email_jobs USING btree (user_id) WHERE (user_id IS NOT NULL)'
  ];
  password_reset_columns constant text[] := array[
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
  password_reset_constraints constant text[] := array[
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
  password_reset_indexes constant text[] := array[
    'password_reset_email_jobs_claim_token_history_idx:CREATE INDEX password_reset_email_jobs_claim_token_history_idx ON public.password_reset_email_jobs USING gin (claim_token_history)',
    'password_reset_email_jobs_expired_lease_idx:CREATE INDEX password_reset_email_jobs_expired_lease_idx ON public.password_reset_email_jobs USING btree (lease_expires_at, created_at, id) WHERE (status = ''processing''::text)',
    'password_reset_email_jobs_lease_token_unique:CREATE UNIQUE INDEX password_reset_email_jobs_lease_token_unique ON public.password_reset_email_jobs USING btree (lease_token) WHERE (lease_token IS NOT NULL)',
    'password_reset_email_jobs_pkey:CREATE UNIQUE INDEX password_reset_email_jobs_pkey ON public.password_reset_email_jobs USING btree (id)',
    'password_reset_email_jobs_ready_idx:CREATE INDEX password_reset_email_jobs_ready_idx ON public.password_reset_email_jobs USING btree (next_attempt_at, created_at, id) WHERE (status = ''queued''::text)',
    'password_reset_email_jobs_terminal_retention_idx:CREATE INDEX password_reset_email_jobs_terminal_retention_idx ON public.password_reset_email_jobs USING btree (terminal_at, id) WHERE (terminal_at IS NOT NULL)',
    'password_reset_email_jobs_user_idx:CREATE INDEX password_reset_email_jobs_user_idx ON public.password_reset_email_jobs USING btree (user_id) WHERE (user_id IS NOT NULL)'
  ];
begin
  if verification_table is null or password_reset_table is null then
    raise exception 'email queue backlog requires both durable queue tables.'
      using errcode = '55000';
  end if;
  if not exists (select 1 from pg_catalog.pg_roles where rolname = 'service_role')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'anon')
     or not exists (select 1 from pg_catalog.pg_roles where rolname = 'authenticated') then
    raise exception 'email queue backlog database roles are missing.'
      using errcode = '55000';
  end if;

  if (
    select class_row.relkind <> 'r'
      or class_row.relpersistence <> 'p'
      or pg_catalog.pg_get_userbyid(class_row.relowner) <> 'postgres'
      or class_row.relrowsecurity is not true
      or class_row.relforcerowsecurity is not true
      or coalesce(class_row.relacl::text, '') <> '{postgres=arwdDxtm/postgres}'
      or pg_catalog.obj_description(class_row.oid, 'pg_class')
           is distinct from 'ASK_CRUMP_VERIFICATION_EMAIL_JOBS_V1'
    from pg_catalog.pg_class as class_row
    where class_row.oid = verification_table
  ) then
    raise exception 'verification_email_jobs backlog prerequisite drifted.'
      using errcode = '55000';
  end if;
  if (
    select pg_catalog.array_agg(
      pg_catalog.format(
        '%s:%s:%s:%s:%s', ordinal_position, column_name, udt_name,
        is_nullable, coalesce(column_default, '')
      ) order by ordinal_position
    )
    from information_schema.columns
    where table_schema = 'public' and table_name = 'verification_email_jobs'
  ) is distinct from verification_columns then
    raise exception 'verification_email_jobs backlog column drifted.'
      using errcode = '55000';
  end if;
  if (
    select pg_catalog.array_agg(
      constraint_row.conname || ':' || constraint_row.contype::text || ':'
        || pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
      order by constraint_row.conname
    )
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid = verification_table
  ) is distinct from verification_constraints then
    raise exception 'verification_email_jobs backlog constraint drifted.'
      using errcode = '55000';
  end if;
  if (
    select pg_catalog.array_agg(
      index_row.indexname || ':' || index_row.indexdef order by index_row.indexname
    )
    from pg_catalog.pg_indexes as index_row
    where index_row.schemaname = 'public'
      and index_row.tablename = 'verification_email_jobs'
  ) is distinct from verification_indexes
     or exists (
       select 1
       from pg_catalog.pg_index as index_row
       where index_row.indrelid = verification_table
         and (index_row.indisvalid is not true or index_row.indisready is not true)
     ) then
    raise exception 'verification_email_jobs backlog index drifted.'
      using errcode = '55000';
  end if;
  if exists (
       select 1
       from pg_catalog.pg_attribute as attribute_row
       where attribute_row.attrelid = verification_table
         and attribute_row.attnum > 0
         and attribute_row.attisdropped is not true
         and attribute_row.attacl is not null
     )
     or exists (
       select 1 from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid = verification_table
     )
     or exists (
       select 1 from pg_catalog.pg_rewrite as rewrite_row
       where rewrite_row.ev_class = verification_table
     )
     or (
       select pg_catalog.count(*) <> 2
         or pg_catalog.count(*) filter (
           where trigger_row.tgenabled <> 'O'
              or trigger_row.tgisinternal is not true
              or constraint_row.conname <> 'verification_email_jobs_user_id_fkey'
              or constraint_row.contype <> 'f'
         ) <> 0
       from pg_catalog.pg_trigger as trigger_row
       left join pg_catalog.pg_constraint as constraint_row
         on constraint_row.oid = trigger_row.tgconstraint
       where trigger_row.tgrelid = verification_table
     ) then
    raise exception 'verification_email_jobs backlog ACL, policy, trigger, or rule drifted.'
      using errcode = '55000';
  end if;
  if (
    select pg_catalog.count(*) <> 4
      or pg_catalog.count(*) filter (
        where trigger_row.tgenabled <> 'O' or trigger_row.tgisinternal is not true
      ) <> 0
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_constraint as constraint_row
      on constraint_row.oid = trigger_row.tgconstraint
    where constraint_row.conrelid = verification_table
      and constraint_row.conname = 'verification_email_jobs_user_id_fkey'
      and constraint_row.contype = 'f'
  ) then
    raise exception 'verification_email_jobs backlog foreign-key trigger drifted.'
      using errcode = '55000';
  end if;

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
    where class_row.oid = password_reset_table
  ) then
    raise exception 'password_reset_email_jobs backlog prerequisite drifted.'
      using errcode = '55000';
  end if;
  if (
    select pg_catalog.array_agg(
      pg_catalog.format(
        '%s:%s:%s:%s:%s', ordinal_position, column_name, udt_name,
        is_nullable, coalesce(column_default, '')
      ) order by ordinal_position
    )
    from information_schema.columns
    where table_schema = 'public' and table_name = 'password_reset_email_jobs'
  ) is distinct from password_reset_columns then
    raise exception 'password_reset_email_jobs backlog column drifted.'
      using errcode = '55000';
  end if;
  if (
    select pg_catalog.array_agg(
      constraint_row.conname || ':' || constraint_row.contype::text || ':'
        || pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
      order by constraint_row.conname
    )
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid = password_reset_table
  ) is distinct from password_reset_constraints then
    raise exception 'password_reset_email_jobs backlog constraint drifted.'
      using errcode = '55000';
  end if;
  if (
    select pg_catalog.array_agg(
      index_row.indexname || ':' || index_row.indexdef order by index_row.indexname
    )
    from pg_catalog.pg_indexes as index_row
    where index_row.schemaname = 'public'
      and index_row.tablename = 'password_reset_email_jobs'
  ) is distinct from password_reset_indexes
     or exists (
       select 1
       from pg_catalog.pg_index as index_row
       where index_row.indrelid = password_reset_table
         and (index_row.indisvalid is not true or index_row.indisready is not true)
     ) then
    raise exception 'password_reset_email_jobs backlog index drifted.'
      using errcode = '55000';
  end if;
  if exists (
       select 1
       from pg_catalog.pg_attribute as attribute_row
       where attribute_row.attrelid = password_reset_table
         and attribute_row.attnum > 0
         and attribute_row.attisdropped is not true
         and attribute_row.attacl is not null
     )
     or exists (
       select 1 from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid = password_reset_table
     )
     or exists (
       select 1 from pg_catalog.pg_rewrite as rewrite_row
       where rewrite_row.ev_class = password_reset_table
     )
     or (
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
       where trigger_row.tgrelid = password_reset_table
     ) then
    raise exception 'password_reset_email_jobs backlog ACL, policy, trigger, or rule drifted.'
      using errcode = '55000';
  end if;
  if (
    select pg_catalog.count(*) <> 4
      or pg_catalog.count(*) filter (
        where trigger_row.tgenabled <> 'O' or trigger_row.tgisinternal is not true
      ) <> 0
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_constraint as constraint_row
      on constraint_row.oid = trigger_row.tgconstraint
    where constraint_row.conrelid = password_reset_table
      and constraint_row.conname = 'password_reset_email_jobs_user_id_fkey'
      and constraint_row.contype = 'f'
  ) then
    raise exception 'password_reset_email_jobs backlog foreign-key trigger drifted.'
      using errcode = '55000';
  end if;

  foreach signature in array claim_signatures loop
    function_oid := pg_catalog.to_regprocedure(signature);
    source_md5 := claim_source_md5[pg_catalog.array_position(claim_signatures, signature)];
    source_marker := claim_source_markers[pg_catalog.array_position(claim_signatures, signature)];
    if function_oid is null or (
      select pg_catalog.pg_get_userbyid(proc_row.proowner) <> 'postgres'
        or language_row.lanname <> 'plpgsql'
        or proc_row.prokind <> 'f'
        or proc_row.prosecdef is not true
        or proc_row.proleakproof is true
        or proc_row.provolatile <> 'v'
        or proc_row.proparallel <> 'u'
        or proc_row.proretset is not true
        or proc_row.pronargs <> 2
        or proc_row.proconfig is distinct from array['search_path=""']::text[]
        or proc_row.pronargdefaults <> 1
        or pg_catalog.pg_get_expr(proc_row.proargdefaults, 0) is distinct from '120'
        or pg_catalog.pg_get_function_arguments(proc_row.oid)
             is distinct from 'p_claim_token uuid, p_lease_seconds integer DEFAULT 120'
        or pg_catalog.pg_get_function_result(proc_row.oid)
             is distinct from 'TABLE(job_id uuid, lease_token uuid, attempts integer)'
        or pg_catalog.strpos(proc_row.prosrc, source_marker) = 0
        or pg_catalog.md5(proc_row.prosrc) <> source_md5
        or (
          select pg_catalog.count(*) <> 2
            or pg_catalog.count(*) filter (
              where grantee_role.rolname = 'postgres'
                and grantor_role.rolname = 'postgres'
                and acl_row.privilege_type = 'EXECUTE'
                and acl_row.is_grantable is false
            ) <> 1
            or pg_catalog.count(*) filter (
              where grantee_role.rolname = 'service_role'
                and grantor_role.rolname = 'postgres'
                and acl_row.privilege_type = 'EXECUTE'
                and acl_row.is_grantable is false
            ) <> 1
          from pg_catalog.aclexplode(
            coalesce(proc_row.proacl, pg_catalog.acldefault('f', proc_row.proowner))
          ) as acl_row
          left join pg_catalog.pg_roles as grantee_role on grantee_role.oid = acl_row.grantee
          left join pg_catalog.pg_roles as grantor_role on grantor_role.oid = acl_row.grantor
        )
        or not pg_catalog.has_function_privilege('service_role', proc_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('anon', proc_row.oid, 'EXECUTE')
        or pg_catalog.has_function_privilege('authenticated', proc_row.oid, 'EXECUTE')
      from pg_catalog.pg_proc as proc_row
      join pg_catalog.pg_language as language_row on language_row.oid = proc_row.prolang
      where proc_row.oid = function_oid
    ) then
      raise exception 'email queue backlog claim prerequisite drifted: %', signature
        using errcode = '55000';
    end if;
  end loop;
  if exists (
    select 1
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname in (
        'claim_verification_email_job_v1',
        'claim_password_reset_email_job_v1'
      )
      and proc_row.oid not in (verification_claim, password_reset_claim)
  ) then
    raise exception 'unexpected email queue claim RPC overload.'
      using errcode = '55000';
  end if;

  if pg_catalog.to_regclass('public.read_email_queue_backlog_v1') is not null then
    raise exception 'email queue backlog relation-name collision.'
      using errcode = '55000';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname = 'read_email_queue_backlog_v1'
      and proc_row.oid is distinct from backlog_function
  ) then
    raise exception 'unexpected email queue backlog RPC overload.'
      using errcode = '55000';
  end if;
  if backlog_function is not null and (
    select pg_catalog.pg_get_userbyid(proc_row.proowner) <> 'postgres'
      or language_row.lanname <> 'sql'
      or proc_row.prokind <> 'f'
      or proc_row.prosecdef is not true
      or proc_row.proleakproof is true
      or proc_row.provolatile <> 's'
      or proc_row.proparallel <> 'u'
      or proc_row.proretset is not true
      or proc_row.pronargs <> 0
      or proc_row.pronargdefaults <> 0
      or proc_row.proconfig is distinct from array['search_path=""']::text[]
      or pg_catalog.pg_get_function_result(proc_row.oid) is distinct from expected_backlog_result
      or pg_catalog.strpos(proc_row.prosrc, 'ASK_CRUMP_EMAIL_QUEUE_BACKLOG_V1') = 0
      or pg_catalog.md5(proc_row.prosrc) <> expected_backlog_source_md5
      or pg_catalog.obj_description(proc_row.oid, 'pg_proc') is distinct from
           'ASK_CRUMP_EMAIL_QUEUE_BACKLOG_V1 aggregate-only service-role observability.'
      or (
        select pg_catalog.count(*) <> 2
          or pg_catalog.count(*) filter (
            where grantee_role.rolname = 'postgres'
              and grantor_role.rolname = 'postgres'
              and acl_row.privilege_type = 'EXECUTE'
              and acl_row.is_grantable is false
          ) <> 1
          or pg_catalog.count(*) filter (
            where grantee_role.rolname = 'service_role'
              and grantor_role.rolname = 'postgres'
              and acl_row.privilege_type = 'EXECUTE'
              and acl_row.is_grantable is false
          ) <> 1
        from pg_catalog.aclexplode(
          coalesce(proc_row.proacl, pg_catalog.acldefault('f', proc_row.proowner))
        ) as acl_row
        left join pg_catalog.pg_roles as grantee_role on grantee_role.oid = acl_row.grantee
        left join pg_catalog.pg_roles as grantor_role on grantor_role.oid = acl_row.grantor
      )
      or not pg_catalog.has_function_privilege('service_role', proc_row.oid, 'EXECUTE')
      or pg_catalog.has_function_privilege('anon', proc_row.oid, 'EXECUTE')
      or pg_catalog.has_function_privilege('authenticated', proc_row.oid, 'EXECUTE')
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_language as language_row on language_row.oid = proc_row.prolang
    where proc_row.oid = backlog_function
  ) then
    raise exception 'existing email queue backlog RPC drifted.'
      using errcode = '55000';
  end if;

  select pg_catalog.md5(pg_catalog.concat_ws(
    E'\n',
    (select class_row.relkind::text || ':' || class_row.relpersistence::text || ':'
       || class_row.relowner::text || ':' || class_row.relrowsecurity::text || ':'
       || class_row.relforcerowsecurity::text || ':' || coalesce(class_row.relacl::text, '')
       || ':' || coalesce(pg_catalog.obj_description(class_row.oid, 'pg_class'), '')
     from pg_catalog.pg_class as class_row where class_row.oid = verification_table),
    verification_columns::text,
    verification_constraints::text,
    verification_indexes::text,
    (select pg_catalog.array_agg(
       index_row.indexrelid::regclass::text || ':' || index_row.indisvalid::text
         || ':' || index_row.indisready::text order by index_row.indexrelid::regclass::text
     )::text from pg_catalog.pg_index as index_row
     where index_row.indrelid = verification_table),
    (select pg_catalog.array_agg(
       attribute_row.attname || ':' || attribute_row.attacl::text
       order by attribute_row.attnum
     )::text from pg_catalog.pg_attribute as attribute_row
     where attribute_row.attrelid = verification_table
       and attribute_row.attnum > 0 and not attribute_row.attisdropped
       and attribute_row.attacl is not null),
    (select pg_catalog.array_agg(policy_row.polname order by policy_row.polname)::text
     from pg_catalog.pg_policy as policy_row
     where policy_row.polrelid = verification_table),
    (select pg_catalog.array_agg(rewrite_row.rulename order by rewrite_row.rulename)::text
     from pg_catalog.pg_rewrite as rewrite_row
     where rewrite_row.ev_class = verification_table),
    (select pg_catalog.array_agg(
       trigger_row.tgrelid::regclass::text || ':' || trigger_row.tgname || ':'
         || trigger_row.tgenabled::text || ':' || trigger_row.tgisinternal::text
       order by trigger_row.tgrelid::regclass::text, trigger_row.tgname
     )::text
     from pg_catalog.pg_trigger as trigger_row
     join pg_catalog.pg_constraint as constraint_row
       on constraint_row.oid = trigger_row.tgconstraint
     where constraint_row.conrelid = verification_table
       and constraint_row.conname = 'verification_email_jobs_user_id_fkey'
       and constraint_row.contype = 'f'),
    (select pg_catalog.array_agg(
       trigger_row.tgname || ':' || trigger_row.tgenabled::text || ':'
         || trigger_row.tgisinternal::text || ':'
         || coalesce(constraint_row.conname, '') || ':'
         || coalesce(constraint_row.contype::text, '') order by trigger_row.tgname
     )::text from pg_catalog.pg_trigger as trigger_row
     left join pg_catalog.pg_constraint as constraint_row
       on constraint_row.oid = trigger_row.tgconstraint
     where trigger_row.tgrelid = verification_table)
  )) into verification_fingerprint;
  select pg_catalog.md5(pg_catalog.concat_ws(
    E'\n',
    (select class_row.relkind::text || ':' || class_row.relpersistence::text || ':'
       || class_row.relowner::text || ':' || class_row.relrowsecurity::text || ':'
       || class_row.relforcerowsecurity::text || ':' || coalesce(class_row.relacl::text, '')
       || ':' || coalesce(pg_catalog.obj_description(class_row.oid, 'pg_class'), '')
     from pg_catalog.pg_class as class_row where class_row.oid = password_reset_table),
    password_reset_columns::text,
    password_reset_constraints::text,
    password_reset_indexes::text,
    (select pg_catalog.array_agg(
       index_row.indexrelid::regclass::text || ':' || index_row.indisvalid::text
         || ':' || index_row.indisready::text order by index_row.indexrelid::regclass::text
     )::text from pg_catalog.pg_index as index_row
     where index_row.indrelid = password_reset_table),
    (select pg_catalog.array_agg(
       attribute_row.attname || ':' || attribute_row.attacl::text
       order by attribute_row.attnum
     )::text from pg_catalog.pg_attribute as attribute_row
     where attribute_row.attrelid = password_reset_table
       and attribute_row.attnum > 0 and not attribute_row.attisdropped
       and attribute_row.attacl is not null),
    (select pg_catalog.array_agg(policy_row.polname order by policy_row.polname)::text
     from pg_catalog.pg_policy as policy_row
     where policy_row.polrelid = password_reset_table),
    (select pg_catalog.array_agg(rewrite_row.rulename order by rewrite_row.rulename)::text
     from pg_catalog.pg_rewrite as rewrite_row
     where rewrite_row.ev_class = password_reset_table),
    (select pg_catalog.array_agg(
       trigger_row.tgrelid::regclass::text || ':' || trigger_row.tgname || ':'
         || trigger_row.tgenabled::text || ':' || trigger_row.tgisinternal::text
       order by trigger_row.tgrelid::regclass::text, trigger_row.tgname
     )::text
     from pg_catalog.pg_trigger as trigger_row
     join pg_catalog.pg_constraint as constraint_row
       on constraint_row.oid = trigger_row.tgconstraint
     where constraint_row.conrelid = password_reset_table
       and constraint_row.conname = 'password_reset_email_jobs_user_id_fkey'
       and constraint_row.contype = 'f'),
    (select pg_catalog.array_agg(
       trigger_row.tgname || ':' || trigger_row.tgenabled::text || ':'
         || trigger_row.tgisinternal::text || ':'
         || coalesce(constraint_row.conname, '') || ':'
         || coalesce(constraint_row.contype::text, '') order by trigger_row.tgname
     )::text from pg_catalog.pg_trigger as trigger_row
     left join pg_catalog.pg_constraint as constraint_row
       on constraint_row.oid = trigger_row.tgconstraint
     where trigger_row.tgrelid = password_reset_table)
  )) into password_reset_fingerprint;
  perform pg_catalog.set_config(
    'askcrump.email_queue_backlog_verification_fingerprint',
    verification_fingerprint,
    false
  );
  perform pg_catalog.set_config(
    'askcrump.email_queue_backlog_password_reset_fingerprint',
    password_reset_fingerprint,
    false
  );
end;
$preflight$;

create or replace function public.read_email_queue_backlog_v1()
returns table (
  verification_active_depth bigint,
  verification_eligible_depth bigint,
  verification_oldest_eligible_job_age_seconds bigint,
  password_reset_active_depth bigint,
  password_reset_eligible_depth bigint,
  password_reset_oldest_eligible_job_age_seconds bigint
)
language sql
stable
security definer
set search_path = ''
as $function$
  -- ASK_CRUMP_EMAIL_QUEUE_BACKLOG_V1
  with sampled_clock as materialized (
    select pg_catalog.statement_timestamp() as sampled_at
  ),
  verification_active_rows as (
    select 1 as marker
    from public.verification_email_jobs as job
    where job.status = 'queued'
    union all
    select 1 as marker
    from public.verification_email_jobs as job
    where job.status = 'processing'
  ),
  verification_active as (
    select pg_catalog.count(*) as depth
    from verification_active_rows
  ),
  verification_eligible_rows as (
    select job.created_at
    from public.verification_email_jobs as job
    cross join sampled_clock as clock
    where job.status = 'queued'
      and job.next_attempt_at <= clock.sampled_at
      and job.attempts < 6
      and job.verification_token_expires
            > clock.sampled_at + interval '5 minutes'
      and job.created_at > clock.sampled_at - interval '23 hours'
    union all
    select job.created_at
    from public.verification_email_jobs as job
    cross join sampled_clock as clock
    where job.status = 'processing'
      and job.lease_expires_at <= clock.sampled_at
      and job.attempts < 6
      and job.verification_token_expires
            > clock.sampled_at + interval '5 minutes'
      and job.created_at > clock.sampled_at - interval '23 hours'
  ),
  verification_eligible as (
    select
      pg_catalog.count(eligible.created_at) as depth,
      case
        when pg_catalog.min(eligible.created_at) is null then null::bigint
        else greatest(
          0::numeric,
          pg_catalog.floor(extract(
            epoch from (clock.sampled_at - pg_catalog.min(eligible.created_at))
          ))
        )::bigint
      end as oldest_age_seconds
    from sampled_clock as clock
    left join verification_eligible_rows as eligible on true
    group by clock.sampled_at
  ),
  password_reset_active_rows as (
    select 1 as marker
    from public.password_reset_email_jobs as job
    where job.status = 'queued'
    union all
    select 1 as marker
    from public.password_reset_email_jobs as job
    where job.status = 'processing'
  ),
  password_reset_active as (
    select pg_catalog.count(*) as depth
    from password_reset_active_rows
  ),
  password_reset_eligible_rows as (
    select job.created_at
    from public.password_reset_email_jobs as job
    cross join sampled_clock as clock
    where job.status = 'queued'
      and job.next_attempt_at <= clock.sampled_at
      and job.attempts < 6
      and job.password_reset_expires
            > clock.sampled_at + pg_catalog.make_interval(secs => 120)
      and job.created_at > clock.sampled_at - interval '55 minutes'
    union all
    select job.created_at
    from public.password_reset_email_jobs as job
    cross join sampled_clock as clock
    where job.status = 'processing'
      and job.lease_expires_at <= clock.sampled_at
      and job.attempts < 6
      and job.password_reset_expires
            > clock.sampled_at + pg_catalog.make_interval(secs => 120)
      and job.created_at > clock.sampled_at - interval '55 minutes'
  ),
  password_reset_eligible as (
    select
      pg_catalog.count(eligible.created_at) as depth,
      case
        when pg_catalog.min(eligible.created_at) is null then null::bigint
        else greatest(
          0::numeric,
          pg_catalog.floor(extract(
            epoch from (clock.sampled_at - pg_catalog.min(eligible.created_at))
          ))
        )::bigint
      end as oldest_age_seconds
    from sampled_clock as clock
    left join password_reset_eligible_rows as eligible on true
    group by clock.sampled_at
  )
  select
    verification_active.depth,
    verification_eligible.depth,
    verification_eligible.oldest_age_seconds,
    password_reset_active.depth,
    password_reset_eligible.depth,
    password_reset_eligible.oldest_age_seconds
  from verification_active
  cross join verification_eligible
  cross join password_reset_active
  cross join password_reset_eligible;
$function$;

alter function public.read_email_queue_backlog_v1() owner to postgres;
revoke all on function public.read_email_queue_backlog_v1()
  from public, anon, authenticated, service_role;
grant execute on function public.read_email_queue_backlog_v1() to service_role;
comment on function public.read_email_queue_backlog_v1() is
  'ASK_CRUMP_EMAIL_QUEUE_BACKLOG_V1 aggregate-only service-role observability.';

do $postflight$
declare
  verification_table regclass := 'public.verification_email_jobs'::regclass;
  password_reset_table regclass := 'public.password_reset_email_jobs'::regclass;
  function_oid oid := pg_catalog.to_regprocedure(
    'public.read_email_queue_backlog_v1()'
  );
  current_fingerprint text;
  expected_source_md5 constant text := 'efae7a5f9fb838ddcfbcdc4385f0b745';
  expected_result constant text :=
    'TABLE(verification_active_depth bigint, verification_eligible_depth bigint, verification_oldest_eligible_job_age_seconds bigint, password_reset_active_depth bigint, password_reset_eligible_depth bigint, password_reset_oldest_eligible_job_age_seconds bigint)';
begin
  if function_oid is null or (
    select pg_catalog.pg_get_userbyid(proc_row.proowner) <> 'postgres'
      or language_row.lanname <> 'sql'
      or proc_row.prokind <> 'f'
      or proc_row.prosecdef is not true
      or proc_row.proleakproof is true
      or proc_row.provolatile <> 's'
      or proc_row.proparallel <> 'u'
      or proc_row.proretset is not true
      or proc_row.pronargs <> 0
      or proc_row.pronargdefaults <> 0
      or proc_row.proconfig is distinct from array['search_path=""']::text[]
      or pg_catalog.pg_get_function_result(proc_row.oid) is distinct from expected_result
      or pg_catalog.strpos(proc_row.prosrc, 'ASK_CRUMP_EMAIL_QUEUE_BACKLOG_V1') = 0
      or pg_catalog.md5(proc_row.prosrc) <> expected_source_md5
      or pg_catalog.obj_description(proc_row.oid, 'pg_proc') is distinct from
           'ASK_CRUMP_EMAIL_QUEUE_BACKLOG_V1 aggregate-only service-role observability.'
      or (
        select pg_catalog.count(*) <> 2
          or pg_catalog.count(*) filter (
            where grantee_role.rolname = 'postgres'
              and grantor_role.rolname = 'postgres'
              and acl_row.privilege_type = 'EXECUTE'
              and acl_row.is_grantable is false
          ) <> 1
          or pg_catalog.count(*) filter (
            where grantee_role.rolname = 'service_role'
              and grantor_role.rolname = 'postgres'
              and acl_row.privilege_type = 'EXECUTE'
              and acl_row.is_grantable is false
          ) <> 1
        from pg_catalog.aclexplode(
          coalesce(proc_row.proacl, pg_catalog.acldefault('f', proc_row.proowner))
        ) as acl_row
        left join pg_catalog.pg_roles as grantee_role on grantee_role.oid = acl_row.grantee
        left join pg_catalog.pg_roles as grantor_role on grantor_role.oid = acl_row.grantor
      )
      or not pg_catalog.has_function_privilege('service_role', proc_row.oid, 'EXECUTE')
      or pg_catalog.has_function_privilege('anon', proc_row.oid, 'EXECUTE')
      or pg_catalog.has_function_privilege('authenticated', proc_row.oid, 'EXECUTE')
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_language as language_row on language_row.oid = proc_row.prolang
    where proc_row.oid = function_oid
  ) then
    raise exception 'email queue backlog RPC postflight failed.'
      using errcode = '55000';
  end if;
  if exists (
    select 1
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid = proc_row.pronamespace
    where namespace_row.nspname = 'public'
      and proc_row.proname = 'read_email_queue_backlog_v1'
      and proc_row.oid <> function_oid
  ) then
    raise exception 'unexpected email queue backlog RPC overload after create.'
      using errcode = '55000';
  end if;

  select pg_catalog.md5(pg_catalog.concat_ws(
    E'\n',
    (select class_row.relkind::text || ':' || class_row.relpersistence::text || ':'
       || class_row.relowner::text || ':' || class_row.relrowsecurity::text || ':'
       || class_row.relforcerowsecurity::text || ':' || coalesce(class_row.relacl::text, '')
       || ':' || coalesce(pg_catalog.obj_description(class_row.oid, 'pg_class'), '')
     from pg_catalog.pg_class as class_row where class_row.oid = verification_table),
    (select pg_catalog.array_agg(
       pg_catalog.format(
         '%s:%s:%s:%s:%s', ordinal_position, column_name, udt_name,
         is_nullable, coalesce(column_default, '')
       ) order by ordinal_position
     )::text from information_schema.columns
     where table_schema = 'public' and table_name = 'verification_email_jobs'),
    (select pg_catalog.array_agg(
       constraint_row.conname || ':' || constraint_row.contype::text || ':'
         || pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
       order by constraint_row.conname
     )::text from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = verification_table),
    (select pg_catalog.array_agg(
       index_row.indexname || ':' || index_row.indexdef order by index_row.indexname
     )::text from pg_catalog.pg_indexes as index_row
     where index_row.schemaname = 'public'
       and index_row.tablename = 'verification_email_jobs'),
    (select pg_catalog.array_agg(
       index_row.indexrelid::regclass::text || ':' || index_row.indisvalid::text
         || ':' || index_row.indisready::text order by index_row.indexrelid::regclass::text
     )::text from pg_catalog.pg_index as index_row
     where index_row.indrelid = verification_table),
    (select pg_catalog.array_agg(
       attribute_row.attname || ':' || attribute_row.attacl::text
       order by attribute_row.attnum
     )::text from pg_catalog.pg_attribute as attribute_row
     where attribute_row.attrelid = verification_table
       and attribute_row.attnum > 0 and not attribute_row.attisdropped
       and attribute_row.attacl is not null),
    (select pg_catalog.array_agg(policy_row.polname order by policy_row.polname)::text
     from pg_catalog.pg_policy as policy_row
     where policy_row.polrelid = verification_table),
    (select pg_catalog.array_agg(rewrite_row.rulename order by rewrite_row.rulename)::text
     from pg_catalog.pg_rewrite as rewrite_row
     where rewrite_row.ev_class = verification_table),
    (select pg_catalog.array_agg(
       trigger_row.tgrelid::regclass::text || ':' || trigger_row.tgname || ':'
         || trigger_row.tgenabled::text || ':' || trigger_row.tgisinternal::text
       order by trigger_row.tgrelid::regclass::text, trigger_row.tgname
     )::text
     from pg_catalog.pg_trigger as trigger_row
     join pg_catalog.pg_constraint as constraint_row
       on constraint_row.oid = trigger_row.tgconstraint
     where constraint_row.conrelid = verification_table
       and constraint_row.conname = 'verification_email_jobs_user_id_fkey'
       and constraint_row.contype = 'f'),
    (select pg_catalog.array_agg(
       trigger_row.tgname || ':' || trigger_row.tgenabled::text || ':'
         || trigger_row.tgisinternal::text || ':'
         || coalesce(constraint_row.conname, '') || ':'
         || coalesce(constraint_row.contype::text, '') order by trigger_row.tgname
     )::text from pg_catalog.pg_trigger as trigger_row
     left join pg_catalog.pg_constraint as constraint_row
       on constraint_row.oid = trigger_row.tgconstraint
     where trigger_row.tgrelid = verification_table)
  )) into current_fingerprint;
  if current_fingerprint <> pg_catalog.current_setting(
       'askcrump.email_queue_backlog_verification_fingerprint'
     ) then
    raise exception 'verification_email_jobs changed during backlog migration.'
      using errcode = '55000';
  end if;

  select pg_catalog.md5(pg_catalog.concat_ws(
    E'\n',
    (select class_row.relkind::text || ':' || class_row.relpersistence::text || ':'
       || class_row.relowner::text || ':' || class_row.relrowsecurity::text || ':'
       || class_row.relforcerowsecurity::text || ':' || coalesce(class_row.relacl::text, '')
       || ':' || coalesce(pg_catalog.obj_description(class_row.oid, 'pg_class'), '')
     from pg_catalog.pg_class as class_row where class_row.oid = password_reset_table),
    (select pg_catalog.array_agg(
       pg_catalog.format(
         '%s:%s:%s:%s:%s', ordinal_position, column_name, udt_name,
         is_nullable, coalesce(column_default, '')
       ) order by ordinal_position
     )::text from information_schema.columns
     where table_schema = 'public' and table_name = 'password_reset_email_jobs'),
    (select pg_catalog.array_agg(
       constraint_row.conname || ':' || constraint_row.contype::text || ':'
         || pg_catalog.pg_get_constraintdef(constraint_row.oid, true)
       order by constraint_row.conname
     )::text from pg_catalog.pg_constraint as constraint_row
     where constraint_row.conrelid = password_reset_table),
    (select pg_catalog.array_agg(
       index_row.indexname || ':' || index_row.indexdef order by index_row.indexname
     )::text from pg_catalog.pg_indexes as index_row
     where index_row.schemaname = 'public'
       and index_row.tablename = 'password_reset_email_jobs'),
    (select pg_catalog.array_agg(
       index_row.indexrelid::regclass::text || ':' || index_row.indisvalid::text
         || ':' || index_row.indisready::text order by index_row.indexrelid::regclass::text
     )::text from pg_catalog.pg_index as index_row
     where index_row.indrelid = password_reset_table),
    (select pg_catalog.array_agg(
       attribute_row.attname || ':' || attribute_row.attacl::text
       order by attribute_row.attnum
     )::text from pg_catalog.pg_attribute as attribute_row
     where attribute_row.attrelid = password_reset_table
       and attribute_row.attnum > 0 and not attribute_row.attisdropped
       and attribute_row.attacl is not null),
    (select pg_catalog.array_agg(policy_row.polname order by policy_row.polname)::text
     from pg_catalog.pg_policy as policy_row
     where policy_row.polrelid = password_reset_table),
    (select pg_catalog.array_agg(rewrite_row.rulename order by rewrite_row.rulename)::text
     from pg_catalog.pg_rewrite as rewrite_row
     where rewrite_row.ev_class = password_reset_table),
    (select pg_catalog.array_agg(
       trigger_row.tgrelid::regclass::text || ':' || trigger_row.tgname || ':'
         || trigger_row.tgenabled::text || ':' || trigger_row.tgisinternal::text
       order by trigger_row.tgrelid::regclass::text, trigger_row.tgname
     )::text
     from pg_catalog.pg_trigger as trigger_row
     join pg_catalog.pg_constraint as constraint_row
       on constraint_row.oid = trigger_row.tgconstraint
     where constraint_row.conrelid = password_reset_table
       and constraint_row.conname = 'password_reset_email_jobs_user_id_fkey'
       and constraint_row.contype = 'f'),
    (select pg_catalog.array_agg(
       trigger_row.tgname || ':' || trigger_row.tgenabled::text || ':'
         || trigger_row.tgisinternal::text || ':'
         || coalesce(constraint_row.conname, '') || ':'
         || coalesce(constraint_row.contype::text, '') order by trigger_row.tgname
     )::text from pg_catalog.pg_trigger as trigger_row
     left join pg_catalog.pg_constraint as constraint_row
       on constraint_row.oid = trigger_row.tgconstraint
     where trigger_row.tgrelid = password_reset_table)
  )) into current_fingerprint;
  if current_fingerprint <> pg_catalog.current_setting(
       'askcrump.email_queue_backlog_password_reset_fingerprint'
     ) then
    raise exception 'password_reset_email_jobs changed during backlog migration.'
      using errcode = '55000';
  end if;
end;
$postflight$;

select pg_catalog.set_config(
  'search_path',
  pg_catalog.current_setting('askcrump.email_queue_backlog_previous_search_path'),
  false
);
select pg_catalog.set_config(
  'quote_all_identifiers',
  pg_catalog.current_setting(
    'askcrump.email_queue_backlog_previous_quote_all_identifiers'
  ),
  false
);
reset askcrump.email_queue_backlog_previous_search_path;
reset askcrump.email_queue_backlog_previous_quote_all_identifiers;
reset askcrump.email_queue_backlog_verification_fingerprint;
reset askcrump.email_queue_backlog_password_reset_fingerprint;
