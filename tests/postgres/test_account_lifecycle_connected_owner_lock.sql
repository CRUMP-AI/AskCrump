-- Behavior and bounded two-connection concurrency coverage for the canonical
-- same-account owner advisory used by auth lifecycle RPCs and account deletion.
-- This file is intended only for the disposable PostgreSQL migration gate.

\set ON_ERROR_STOP on

create extension if not exists dblink;

create or replace function public.test_account_lifecycle_assert(
  p_condition boolean,
  p_message text
)
returns void
language plpgsql
set search_path = ''
as $function$
begin
  if p_condition is distinct from true then
    raise exception '%', p_message;
  end if;
end;
$function$;

create or replace function public.test_account_lifecycle_uuid(p_seed text)
returns uuid
language sql
immutable
strict
set search_path = ''
as $function$
  select (
    pg_catalog.substr(pg_catalog.md5(p_seed), 1, 8) || '-' ||
    pg_catalog.substr(pg_catalog.md5(p_seed), 9, 4) || '-' ||
    pg_catalog.substr(pg_catalog.md5(p_seed), 13, 4) || '-' ||
    pg_catalog.substr(pg_catalog.md5(p_seed), 17, 4) || '-' ||
    pg_catalog.substr(pg_catalog.md5(p_seed), 21, 12)
  )::uuid;
$function$;

create or replace function public.test_account_lifecycle_hash(p_seed text)
returns text
language sql
immutable
strict
set search_path = ''
as $function$
  select pg_catalog.encode(public.digest(p_seed, 'sha256'), 'hex');
$function$;

create or replace function public.test_account_lifecycle_seed(
  p_case text,
  p_user_id uuid
)
returns void
language plpgsql
set search_path = ''
as $function$
declare
  v_created_at timestamptz := pg_catalog.clock_timestamp() - interval '1 hour';
  v_existing_session_id uuid := public.test_account_lifecycle_uuid(
    p_case || ':existing-session:' || p_user_id::text
  );
  v_existing_session_hash text := public.test_account_lifecycle_hash(
    p_case || ':existing-session-token:' || p_user_id::text
  );
  v_project_id uuid := public.test_account_lifecycle_uuid(
    p_case || ':project:' || p_user_id::text
  );
  v_file_id uuid := public.test_account_lifecycle_uuid(
    p_case || ':file:' || p_user_id::text
  );
begin
  if p_case not in (
    'reset', 'login', 'registered_verify', 'guest_verify', 'setup'
  ) then
    raise exception 'Unknown account-lifecycle test case: %', p_case;
  end if;

  insert into public.users (
    id,
    email,
    password_hash,
    is_verified,
    is_guest,
    verification_token_hash,
    verification_token_expires,
    password_reset_token_hash,
    password_reset_expires,
    created_at,
    updated_at,
    registration_environment,
    registration_submitted_at,
    password_setup_required,
    password_inbox_bound_at
  ) values (
    p_user_id,
    p_case || '-' || p_user_id::text || '@example.test',
    case
      when p_case in ('registered_verify', 'guest_verify', 'setup')
        then '!pending-inbox-password-setup-v1!'
      else '$argon2id$account-lifecycle-owner-password-hash-v1'
    end,
    p_case in ('reset', 'login', 'setup'),
    p_case = 'guest_verify',
    case
      when p_case in ('registered_verify', 'guest_verify')
        then public.test_account_lifecycle_hash(
          p_case || ':verification:' || p_user_id::text
        )
      else null
    end,
    case
      when p_case in ('registered_verify', 'guest_verify')
        then pg_catalog.clock_timestamp() + interval '1 day'
      else null
    end,
    case
      when p_case = 'reset'
        then public.test_account_lifecycle_hash(
          p_case || ':reset:' || p_user_id::text
        )
      else null
    end,
    case
      when p_case = 'reset'
        then pg_catalog.clock_timestamp() + interval '1 day'
      else null
    end,
    v_created_at,
    v_created_at,
    'production',
    v_created_at,
    p_case = 'setup',
    case
      when p_case in ('reset', 'login') then v_created_at
      else null
    end
  );

  insert into public.sessions (
    id,
    user_id,
    token_hash,
    device_id,
    device_name,
    platform,
    device_info,
    created_at,
    last_activity,
    expires_at
  ) values (
    v_existing_session_id,
    p_user_id,
    v_existing_session_hash,
    'existing-' || p_case || '-' || p_user_id::text,
    'Existing account-lifecycle test session',
    'web',
    case
      when p_case = 'setup'
        then '{"passwordSetupProof":"inbox-verification-v1"}'::jsonb
      else '{}'::jsonb
    end,
    v_created_at,
    v_created_at,
    pg_catalog.clock_timestamp() + interval '1 day'
  );

  insert into public.usage_events (user_id, event_type)
  values (p_user_id, 'account-lifecycle-test');
  insert into public.user_chats (user_id, chat_id, title, messages)
  values (
    p_user_id,
    public.test_account_lifecycle_uuid(p_case || ':chat:' || p_user_id::text),
    'Account lifecycle test',
    '[]'::jsonb
  );
  insert into public.user_settings (user_id) values (p_user_id);
  insert into public.crump_chats (user_id) values (p_user_id);
  insert into public.devices (user_id) values (p_user_id);

  insert into public.chat_jobs (
    user_id, chat_id, message_id, status, response_data, updated_at
  ) values (
    p_user_id,
    public.test_account_lifecycle_uuid(p_case || ':job-chat:' || p_user_id::text),
    public.test_account_lifecycle_uuid(p_case || ':job-message:' || p_user_id::text),
    'completed',
    '{}'::jsonb,
    v_created_at
  );
  insert into public.projects (id, user_id, created_at)
  values (v_project_id, p_user_id, v_created_at);
  insert into public.project_chats (user_id, project_id, created_at)
  values (p_user_id, v_project_id, v_created_at);
  insert into public.user_files (
    id, user_id, kind, status, size_bytes, created_at
  ) values (
    v_file_id, p_user_id, 'document', 'ready', 1, v_created_at
  );
  insert into public.project_files (user_id, project_id, file_id, created_at)
  values (p_user_id, v_project_id, v_file_id, v_created_at);
end;
$function$;

create or replace function public.test_account_lifecycle_call_auth(
  p_case text,
  p_user_id uuid
)
returns table(
  applied boolean,
  error_sqlstate text,
  error_message text
)
language plpgsql
set search_path = ''
as $function$
declare
  v_applied boolean;
  v_error_sqlstate text;
  v_error_message text;
  v_existing_session_id uuid := public.test_account_lifecycle_uuid(
    p_case || ':existing-session:' || p_user_id::text
  );
  v_existing_session_hash text := public.test_account_lifecycle_hash(
    p_case || ':existing-session-token:' || p_user_id::text
  );
  v_new_session_id uuid := public.test_account_lifecycle_uuid(
    p_case || ':new-session:' || p_user_id::text
  );
  v_new_session_hash text := public.test_account_lifecycle_hash(
    p_case || ':new-session-token:' || p_user_id::text
  );
begin
  begin
    case p_case
      when 'reset' then
        select coalesce(pg_catalog.bool_or(result.reset_applied), false)
          into v_applied
          from public.consume_password_reset_v1(
            public.test_account_lifecycle_hash(
              p_case || ':reset:' || p_user_id::text
            ),
            '$argon2id$account-lifecycle-owner-reset-password-hash-v2'
          ) as result;
      when 'login' then
        select coalesce(pg_catalog.bool_or(result.login_applied), false)
          into v_applied
          from public.finalize_password_login_v1(
            p_user_id,
            '$argon2id$account-lifecycle-owner-password-hash-v1',
            null,
            v_new_session_id,
            v_new_session_hash,
            pg_catalog.clock_timestamp() + interval '1 day',
            'new-login-' || p_user_id::text,
            'Account lifecycle login',
            'web',
            '{}'::jsonb,
            '127.0.0.1',
            'account-lifecycle-owner-lock-test'
          ) as result;
      when 'registered_verify' then
        select coalesce(
          pg_catalog.bool_or(result.verification_applied), false
        )
          into v_applied
          from public.verify_registered_and_create_session_v1(
            p_user_id,
            public.test_account_lifecycle_hash(
              p_case || ':verification:' || p_user_id::text
            ),
            v_new_session_id,
            v_new_session_hash,
            pg_catalog.clock_timestamp() + interval '1 day',
            'new-registered-verify-' || p_user_id::text,
            'Account lifecycle registered verification',
            'web',
            '{}'::jsonb,
            '127.0.0.1',
            'account-lifecycle-owner-lock-test'
          ) as result;
      when 'guest_verify' then
        select coalesce(pg_catalog.bool_or(result.converted), false)
          into v_applied
          from public.verify_guest_and_create_session_v1(
            p_user_id,
            public.test_account_lifecycle_hash(
              p_case || ':verification:' || p_user_id::text
            ),
            v_new_session_id,
            v_new_session_hash,
            pg_catalog.clock_timestamp() + interval '1 day',
            'new-guest-verify-' || p_user_id::text,
            'Account lifecycle guest verification',
            'web',
            '{}'::jsonb,
            '127.0.0.1',
            'account-lifecycle-owner-lock-test'
          ) as result;
      when 'setup' then
        select coalesce(
          pg_catalog.bool_or(result.password_setup_applied), false
        )
          into v_applied
          from public.complete_initial_password_setup_v1(
            p_user_id,
            v_existing_session_id,
            v_existing_session_hash,
            '$argon2id$account-lifecycle-owner-setup-password-hash-v2'
          ) as result;
      else
        raise exception 'Unknown account-lifecycle test case: %', p_case;
    end case;

    return query select v_applied, null::text, null::text;
  exception when others then
    get stacked diagnostics
      v_error_sqlstate = returned_sqlstate,
      v_error_message = message_text;
    return query select null::boolean, v_error_sqlstate, v_error_message;
  end;
end;
$function$;

create or replace function public.test_account_lifecycle_call_delete(
  p_user_id uuid
)
returns table(
  applied boolean,
  error_sqlstate text,
  error_message text
)
language plpgsql
set search_path = ''
as $function$
declare
  v_error_sqlstate text;
  v_error_message text;
begin
  begin
    perform public.delete_user_account(p_user_id, 'crump-files');
    return query select true, null::text, null::text;
  exception when others then
    get stacked diagnostics
      v_error_sqlstate = returned_sqlstate,
      v_error_message = message_text;
    return query select null::boolean, v_error_sqlstate, v_error_message;
  end;
end;
$function$;

create or replace function public.test_account_lifecycle_delay_auth()
returns trigger
language plpgsql
set search_path = ''
as $function$
begin
  if coalesce(
    pg_catalog.current_setting('askcrump.test_delay_auth_user', true), ''
  ) = new.id::text then
    perform pg_catalog.pg_sleep(0.75);
  end if;

  if coalesce(
    pg_catalog.current_setting('askcrump.test_reject_auth_user', true), ''
  ) = new.id::text then
    raise exception 'Synthetic auth rollback for %', new.id
      using errcode = 'P0001';
  end if;
  return new;
end;
$function$;

create trigger test_account_lifecycle_delay_auth_update
before update on public.users
for each row execute function public.test_account_lifecycle_delay_auth();

create or replace function public.test_account_lifecycle_delay_delete()
returns trigger
language plpgsql
set search_path = ''
as $function$
begin
  if coalesce(
    pg_catalog.current_setting('askcrump.test_delay_delete_user', true), ''
  ) = new.user_id::text then
    perform pg_catalog.pg_sleep(0.75);
  end if;

  if coalesce(
    pg_catalog.current_setting('askcrump.test_reject_delete_user', true), ''
  ) = new.user_id::text then
    raise exception 'Synthetic delete rollback for %', new.user_id
      using errcode = 'P0001';
  end if;
  return new;
end;
$function$;

create trigger test_account_lifecycle_delay_delete_job
before insert or update on public.account_storage_deletion_jobs
for each row execute function public.test_account_lifecycle_delay_delete();

create or replace function public.test_account_lifecycle_wait_for_advisory(
  p_application_name text,
  p_timeout interval default interval '3 seconds'
)
returns void
language plpgsql
set search_path = ''
as $function$
declare
  v_deadline timestamptz := pg_catalog.clock_timestamp() + p_timeout;
begin
  loop
    if exists (
      select 1
        from pg_catalog.pg_stat_activity as activity
        join pg_catalog.pg_locks as held_lock
          on held_lock.pid = activity.pid
       where activity.datname = pg_catalog.current_database()
         and activity.application_name = p_application_name
         and held_lock.locktype = 'advisory'
         and held_lock.mode = 'ExclusiveLock'
         and held_lock.granted is true
    ) then
      return;
    end if;

    if pg_catalog.clock_timestamp() >= v_deadline then
      raise exception 'Timed out waiting for advisory lock held by %',
        p_application_name using errcode = '57014';
    end if;
    perform pg_catalog.pg_sleep(0.01);
  end loop;
end;
$function$;

create or replace function public.test_account_lifecycle_run_race(
  p_case text,
  p_user_id uuid,
  p_auth_first boolean
)
returns void
language plpgsql
set search_path = ''
as $function$
declare
  v_suffix text := pg_catalog.replace(p_user_id::text, '-', '');
  v_order text := case when p_auth_first then 'auth' else 'delete' end;
  v_auth_connection text := 'acl_auth_' || pg_catalog.substr(v_suffix, 1, 20);
  v_delete_connection text := 'acl_delete_' || pg_catalog.substr(v_suffix, 1, 20);
  v_auth_application text := 'acl-' || p_case || '-' || v_order || '-auth';
  v_delete_application text := 'acl-' || p_case || '-' || v_order || '-delete';
  v_auth_applied boolean;
  v_auth_sqlstate text;
  v_auth_message text;
  v_delete_applied boolean;
  v_delete_sqlstate text;
  v_delete_message text;
  v_job_id_before uuid;
  v_job_id_after uuid;
begin
  perform public.dblink_connect(
    v_auth_connection,
    pg_catalog.format(
      'host=%L port=%L dbname=%L user=%L application_name=%L',
      '127.0.0.1', pg_catalog.current_setting('port'),
      pg_catalog.current_database(), current_user, v_auth_application
    )
  );
  perform public.dblink_connect(
    v_delete_connection,
    pg_catalog.format(
      'host=%L port=%L dbname=%L user=%L application_name=%L',
      '127.0.0.1', pg_catalog.current_setting('port'),
      pg_catalog.current_database(), current_user, v_delete_application
    )
  );

  -- deadlock_timeout is superuser-only; set it before assuming the exact
  -- service_role used by the production RPC callers.
  perform public.dblink_exec(v_auth_connection, 'set deadlock_timeout = ''100ms''');
  perform public.dblink_exec(v_delete_connection, 'set deadlock_timeout = ''100ms''');
  perform public.dblink_exec(
    v_auth_connection, 'set statement_timeout = ''8s'''
  );
  perform public.dblink_exec(
    v_delete_connection, 'set statement_timeout = ''8s'''
  );
  perform public.dblink_exec(v_auth_connection, 'set lock_timeout = ''5s''');
  perform public.dblink_exec(v_delete_connection, 'set lock_timeout = ''5s''');
  perform public.dblink_exec(v_auth_connection, 'set role service_role');
  perform public.dblink_exec(v_delete_connection, 'set role service_role');

  if p_auth_first then
    perform public.dblink_exec(
      v_auth_connection,
      pg_catalog.format(
        'set askcrump.test_delay_auth_user = %L', p_user_id::text
      )
    );
    perform public.test_account_lifecycle_assert(
      public.dblink_send_query(
        v_auth_connection,
        pg_catalog.format(
          'select * from public.test_account_lifecycle_call_auth(%L, %L::uuid)',
          p_case, p_user_id::text
        )
      ) = 1,
      p_case || ' auth-first query was not dispatched.'
    );
    perform public.test_account_lifecycle_wait_for_advisory(v_auth_application);
    perform public.test_account_lifecycle_assert(
      public.dblink_send_query(
        v_delete_connection,
        pg_catalog.format(
          'select * from public.test_account_lifecycle_call_delete(%L::uuid)',
          p_user_id::text
        )
      ) = 1,
      p_case || ' auth-first delete query was not dispatched.'
    );

    select result.applied, result.error_sqlstate, result.error_message
      into v_auth_applied, v_auth_sqlstate, v_auth_message
      from public.dblink_get_result(v_auth_connection, true) as result(
        applied boolean, error_sqlstate text, error_message text
      );
    select result.applied, result.error_sqlstate, result.error_message
      into v_delete_applied, v_delete_sqlstate, v_delete_message
      from public.dblink_get_result(v_delete_connection, true) as result(
        applied boolean, error_sqlstate text, error_message text
      );
  else
    perform public.dblink_exec(
      v_delete_connection,
      pg_catalog.format(
        'set askcrump.test_delay_delete_user = %L', p_user_id::text
      )
    );
    perform public.test_account_lifecycle_assert(
      public.dblink_send_query(
        v_delete_connection,
        pg_catalog.format(
          'select * from public.test_account_lifecycle_call_delete(%L::uuid)',
          p_user_id::text
        )
      ) = 1,
      p_case || ' delete-first query was not dispatched.'
    );
    perform public.test_account_lifecycle_wait_for_advisory(v_delete_application);
    perform public.test_account_lifecycle_assert(
      public.dblink_send_query(
        v_auth_connection,
        pg_catalog.format(
          'select * from public.test_account_lifecycle_call_auth(%L, %L::uuid)',
          p_case, p_user_id::text
        )
      ) = 1,
      p_case || ' delete-first auth query was not dispatched.'
    );

    select result.applied, result.error_sqlstate, result.error_message
      into v_delete_applied, v_delete_sqlstate, v_delete_message
      from public.dblink_get_result(v_delete_connection, true) as result(
        applied boolean, error_sqlstate text, error_message text
      );
    select result.applied, result.error_sqlstate, result.error_message
      into v_auth_applied, v_auth_sqlstate, v_auth_message
      from public.dblink_get_result(v_auth_connection, true) as result(
        applied boolean, error_sqlstate text, error_message text
      );
  end if;

  perform public.dblink_disconnect(v_auth_connection);
  perform public.dblink_disconnect(v_delete_connection);

  perform public.test_account_lifecycle_assert(
    v_auth_sqlstate is null,
    pg_catalog.format(
      '%s %s-first auth raised SQLSTATE %s: %s',
      p_case, v_order, v_auth_sqlstate, v_auth_message
    )
  );
  perform public.test_account_lifecycle_assert(
    v_delete_sqlstate is null,
    pg_catalog.format(
      '%s %s-first delete raised SQLSTATE %s: %s',
      p_case, v_order, v_delete_sqlstate, v_delete_message
    )
  );
  perform public.test_account_lifecycle_assert(
    v_delete_applied is true,
    p_case || ' deletion did not complete.'
  );
  perform public.test_account_lifecycle_assert(
    v_auth_applied is not distinct from p_auth_first,
    pg_catalog.format(
      '%s %s-first result was not linearizable (auth applied=%s).',
      p_case, v_order, v_auth_applied
    )
  );

  select job.id
    into v_job_id_before
    from public.account_storage_deletion_jobs as job
   where job.user_id = p_user_id;
  perform public.test_account_lifecycle_assert(
    v_job_id_before is not null,
    p_case || ' deletion did not leave a durable storage job.'
  );

  -- A retry after either winner order is idempotent and preserves the same
  -- durable obligation rather than creating another job.
  perform public.delete_user_account(p_user_id, 'crump-files');
  select job.id
    into v_job_id_after
    from public.account_storage_deletion_jobs as job
   where job.user_id = p_user_id;
  perform public.test_account_lifecycle_assert(
    v_job_id_after = v_job_id_before,
    p_case || ' idempotent deletion retry changed the durable job identity.'
  );
  perform public.test_account_lifecycle_assert(
    (select pg_catalog.count(*) = 1
       from public.account_storage_deletion_jobs as job
      where job.user_id = p_user_id
        and job.status = 'pending'
        and job.bucket = 'crump-files'
        and job.owner_prefix = p_user_id::text || '/'),
    p_case || ' durable deletion job shape or cardinality drifted.'
  );

  perform public.test_account_lifecycle_assert(
    not exists (select 1 from public.users where id = p_user_id)
    and not exists (select 1 from public.sessions where user_id = p_user_id)
    and not exists (select 1 from public.usage_events where user_id = p_user_id)
    and not exists (select 1 from public.user_chats where user_id = p_user_id)
    and not exists (select 1 from public.user_settings where user_id = p_user_id)
    and not exists (select 1 from public.crump_chats where user_id = p_user_id)
    and not exists (select 1 from public.devices where user_id = p_user_id)
    and not exists (select 1 from public.chat_jobs where user_id = p_user_id)
    and not exists (select 1 from public.projects where user_id = p_user_id)
    and not exists (select 1 from public.project_chats where user_id = p_user_id)
    and not exists (select 1 from public.user_files where user_id = p_user_id)
    and not exists (select 1 from public.project_files where user_id = p_user_id),
    p_case || ' deletion left an account-owned row or orphan chat/session.'
  );
exception when others then
  if v_auth_connection = any(
    coalesce(public.dblink_get_connections(), array[]::text[])
  ) then
    perform public.dblink_disconnect(v_auth_connection);
  end if;
  if v_delete_connection = any(
    coalesce(public.dblink_get_connections(), array[]::text[])
  ) then
    perform public.dblink_disconnect(v_delete_connection);
  end if;
  raise;
end;
$function$;

create or replace function public.test_account_lifecycle_run_rollback(
  p_operation text,
  p_user_id uuid
)
returns void
language plpgsql
set search_path = ''
as $function$
declare
  v_connection text := 'acl_rollback_' || pg_catalog.substr(
    pg_catalog.replace(p_user_id::text, '-', ''), 1, 20
  );
  v_application text := 'acl-rollback-' || p_operation;
  v_applied boolean;
  v_sqlstate text;
  v_message text;
  v_lock_available boolean;
begin
  perform public.dblink_connect(
    v_connection,
    pg_catalog.format(
      'host=%L port=%L dbname=%L user=%L application_name=%L',
      '127.0.0.1', pg_catalog.current_setting('port'),
      pg_catalog.current_database(), current_user, v_application
    )
  );
  perform public.dblink_exec(v_connection, 'set role service_role');
  perform public.dblink_exec(v_connection, 'set statement_timeout = ''8s''');
  perform public.dblink_exec(v_connection, 'set lock_timeout = ''5s''');

  if p_operation = 'auth' then
    perform public.dblink_exec(
      v_connection,
      pg_catalog.format(
        'set askcrump.test_reject_auth_user = %L', p_user_id::text
      )
    );
    select result.applied, result.error_sqlstate, result.error_message
      into v_applied, v_sqlstate, v_message
      from public.dblink(
        v_connection,
        pg_catalog.format(
          'select * from public.test_account_lifecycle_call_auth(''reset'', %L::uuid)',
          p_user_id::text
        ),
        true
      ) as result(
        applied boolean, error_sqlstate text, error_message text
      );
  elsif p_operation = 'delete' then
    perform public.dblink_exec(
      v_connection,
      pg_catalog.format(
        'set askcrump.test_reject_delete_user = %L', p_user_id::text
      )
    );
    select result.applied, result.error_sqlstate, result.error_message
      into v_applied, v_sqlstate, v_message
      from public.dblink(
        v_connection,
        pg_catalog.format(
          'select * from public.test_account_lifecycle_call_delete(%L::uuid)',
          p_user_id::text
        ),
        true
      ) as result(
        applied boolean, error_sqlstate text, error_message text
      );
  else
    raise exception 'Unknown rollback operation: %', p_operation;
  end if;

  perform public.dblink_disconnect(v_connection);
  perform public.test_account_lifecycle_assert(
    v_applied is null and v_sqlstate = 'P0001',
    pg_catalog.format(
      '%s rollback did not surface the synthetic P0001 boundary: %s %s',
      p_operation, v_sqlstate, v_message
    )
  );

  v_lock_available := pg_catalog.pg_try_advisory_xact_lock(
    pg_catalog.hashtextextended(p_user_id::text, 606232723337443413::bigint)
  );
  perform public.test_account_lifecycle_assert(
    v_lock_available,
    p_operation || ' rollback leaked the account advisory lock.'
  );
  perform public.test_account_lifecycle_assert(
    exists (select 1 from public.users where id = p_user_id)
    and exists (select 1 from public.sessions where user_id = p_user_id)
    and exists (select 1 from public.user_chats where user_id = p_user_id)
    and exists (select 1 from public.crump_chats where user_id = p_user_id)
    and not exists (
      select 1
        from public.account_storage_deletion_jobs
       where user_id = p_user_id
    ),
    p_operation || ' rollback did not restore account-owned state.'
  );

  if p_operation = 'auth' then
    perform public.test_account_lifecycle_assert(
      exists (
        select 1
          from public.users as account
         where account.id = p_user_id
           and account.password_reset_token_hash =
             public.test_account_lifecycle_hash(
               'reset:reset:' || p_user_id::text
             )
      ),
      'Auth rollback consumed or changed the password-reset token.'
    );
  end if;
exception when others then
  if v_connection = any(
    coalesce(public.dblink_get_connections(), array[]::text[])
  ) then
    perform public.dblink_disconnect(v_connection);
  end if;
  raise;
end;
$function$;

-- Five auth lifecycle RPCs, each exercised against deletion with both the auth
-- transition and deletion winning the canonical advisory first.
select public.test_account_lifecycle_seed(
  'reset', public.test_account_lifecycle_uuid('reset-auth-first')
);
select public.test_account_lifecycle_run_race(
  'reset', public.test_account_lifecycle_uuid('reset-auth-first'), true
);
select public.test_account_lifecycle_seed(
  'reset', public.test_account_lifecycle_uuid('reset-delete-first')
);
select public.test_account_lifecycle_run_race(
  'reset', public.test_account_lifecycle_uuid('reset-delete-first'), false
);

select public.test_account_lifecycle_seed(
  'login', public.test_account_lifecycle_uuid('login-auth-first')
);
select public.test_account_lifecycle_run_race(
  'login', public.test_account_lifecycle_uuid('login-auth-first'), true
);
select public.test_account_lifecycle_seed(
  'login', public.test_account_lifecycle_uuid('login-delete-first')
);
select public.test_account_lifecycle_run_race(
  'login', public.test_account_lifecycle_uuid('login-delete-first'), false
);

select public.test_account_lifecycle_seed(
  'registered_verify',
  public.test_account_lifecycle_uuid('registered-verify-auth-first')
);
select public.test_account_lifecycle_run_race(
  'registered_verify',
  public.test_account_lifecycle_uuid('registered-verify-auth-first'),
  true
);
select public.test_account_lifecycle_seed(
  'registered_verify',
  public.test_account_lifecycle_uuid('registered-verify-delete-first')
);
select public.test_account_lifecycle_run_race(
  'registered_verify',
  public.test_account_lifecycle_uuid('registered-verify-delete-first'),
  false
);

select public.test_account_lifecycle_seed(
  'guest_verify',
  public.test_account_lifecycle_uuid('guest-verify-auth-first')
);
select public.test_account_lifecycle_run_race(
  'guest_verify',
  public.test_account_lifecycle_uuid('guest-verify-auth-first'),
  true
);
select public.test_account_lifecycle_seed(
  'guest_verify',
  public.test_account_lifecycle_uuid('guest-verify-delete-first')
);
select public.test_account_lifecycle_run_race(
  'guest_verify',
  public.test_account_lifecycle_uuid('guest-verify-delete-first'),
  false
);

select public.test_account_lifecycle_seed(
  'setup', public.test_account_lifecycle_uuid('setup-auth-first')
);
select public.test_account_lifecycle_run_race(
  'setup', public.test_account_lifecycle_uuid('setup-auth-first'), true
);
select public.test_account_lifecycle_seed(
  'setup', public.test_account_lifecycle_uuid('setup-delete-first')
);
select public.test_account_lifecycle_run_race(
  'setup', public.test_account_lifecycle_uuid('setup-delete-first'), false
);

-- Rollback of either side must release the transaction-scoped advisory and
-- preserve the pre-transaction account state.
select public.test_account_lifecycle_seed(
  'reset', public.test_account_lifecycle_uuid('rollback-auth')
);
select public.test_account_lifecycle_run_rollback(
  'auth', public.test_account_lifecycle_uuid('rollback-auth')
);
select public.test_account_lifecycle_seed(
  'login', public.test_account_lifecycle_uuid('rollback-delete')
);
select public.test_account_lifecycle_run_rollback(
  'delete', public.test_account_lifecycle_uuid('rollback-delete')
);

drop trigger test_account_lifecycle_delay_auth_update on public.users;
drop trigger test_account_lifecycle_delay_delete_job
  on public.account_storage_deletion_jobs;
drop function public.test_account_lifecycle_delay_auth();
drop function public.test_account_lifecycle_delay_delete();
drop function public.test_account_lifecycle_run_rollback(text, uuid);
drop function public.test_account_lifecycle_run_race(text, uuid, boolean);
drop function public.test_account_lifecycle_wait_for_advisory(text, interval);
drop function public.test_account_lifecycle_call_delete(uuid);
drop function public.test_account_lifecycle_call_auth(text, uuid);
drop function public.test_account_lifecycle_seed(text, uuid);
drop function public.test_account_lifecycle_hash(text);
drop function public.test_account_lifecycle_uuid(text);
drop function public.test_account_lifecycle_assert(boolean, text);

select 'account lifecycle owner-lock concurrency checks passed' as result;
