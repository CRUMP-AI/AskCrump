\set ON_ERROR_STOP on

create extension if not exists dblink;

create or replace function public.test_connected_lock_uuid(p_seed text)
returns uuid language sql immutable strict set search_path = ''
as $$
  select (
    substr(md5(p_seed),1,8)||'-'||substr(md5(p_seed),9,4)||'-'||
    substr(md5(p_seed),13,4)||'-'||substr(md5(p_seed),17,4)||'-'||
    substr(md5(p_seed),21,12)
  )::uuid
$$;

create or replace function public.test_connected_lock_hash(p_seed text)
returns text language sql immutable strict set search_path = ''
as $$ select encode(public.digest(p_seed,'sha256'),'hex') $$;

create or replace function public.test_connected_lock_assert(
  p_condition boolean, p_message text
)
returns void language plpgsql set search_path = ''
as $$
begin
  if p_condition is distinct from true then raise exception '%', p_message; end if;
end;
$$;

create or replace function public.test_connected_lock_seed(
  p_operation text, p_user_id uuid
)
returns void language plpgsql set search_path = ''
as $$
declare
  created timestamptz := clock_timestamp() - interval '1 hour';
begin
  insert into public.users(
    id,email,password_hash,is_verified,is_guest,created_at,updated_at,
    registration_environment,registration_submitted_at,
    password_setup_required,password_inbox_bound_at
  ) values (
    p_user_id,p_operation||'-'||p_user_id||'@example.test',
    '$argon2id$connected-lock-password-hash-v1',
    p_operation not like 'guest_%',p_operation like 'guest_%',
    created,created,'production',created,false,
    case when p_operation like 'guest_%' then null else created end
  );
  insert into public.sessions(
    id,user_id,token_hash,device_id,device_name,platform,device_info,
    created_at,last_activity,expires_at
  ) values (
    public.test_connected_lock_uuid(p_operation||':session:'||p_user_id),
    p_user_id,public.test_connected_lock_hash(p_operation||':token:'||p_user_id),
    'connected-lock-'||p_user_id,'Connected lock test','web','{}',
    created,created,clock_timestamp()+interval '1 hour'
  );

  -- Guest cases deliberately start with the target chat present so the race
  -- exercises guest-control -> owner advisory -> existing chat -> user.
  if p_operation like 'guest_%' then
    insert into public.user_chats(
      user_id,chat_id,title,messages,revision,created_at,updated_at
    ) values (
      p_user_id,
      public.test_connected_lock_uuid(p_operation||':chat:'||p_user_id),
      'Existing guest race chat','[]'::jsonb,0,created,created
    );
  end if;
end;
$$;

create or replace function public.test_connected_lock_call_writer(
  p_operation text, p_user_id uuid
)
returns table(applied boolean,error_sqlstate text,error_message text)
language plpgsql set search_path = ''
as $$
declare
  did_apply boolean := false;
  turn_id uuid;
  claim_token uuid;
  chat_id uuid := public.test_connected_lock_uuid(p_operation||':chat:'||p_user_id);
  message_id uuid := public.test_connected_lock_uuid(p_operation||':message:'||p_user_id);
  assistant_id uuid := public.test_connected_lock_uuid(p_operation||':assistant:'||p_user_id);
  response jsonb;
  err_state text;
  err_message text;
begin
  begin
    if p_operation = 'guest_reply' then
      select result.accepted into did_apply
      from public.persist_guest_chat_reply_v1(
        p_user_id,chat_id,'Guest reply race',
        jsonb_build_object('id',message_id,'role','user','content','race user'),
        jsonb_build_object(
          'id',assistant_id,'role','assistant','inReplyTo',message_id,
          'content','race assistant'
        )
      ) as result;
    elsif p_operation = 'guest_sync' then
      select result.accepted into did_apply
      from public.apply_guest_chat_sync_v2(
        p_user_id,chat_id,'Guest sync race','[]'::jsonb,
        clock_timestamp(),clock_timestamp(),null,1
      ) as result;
    elsif p_operation = 'connected' then
      select claimed.turn_id,claimed.claim_token
        into strict turn_id,claim_token
      from public.connected_chat_claim_turn_v1(
        p_user_id,chat_id,message_id,repeat('a',64),repeat('b',64)
      ) as claimed;
      response := public.connected_operator_complete_chat_v1(
        public.test_connected_lock_uuid(p_operation||':completion:'||p_user_id),
        p_user_id,
        public.test_connected_lock_uuid(p_operation||':session:'||p_user_id),
        turn_id,chat_id,message_id,assistant_id,claim_token,
        repeat('a',64),repeat('b',64),'delegated','chat-completion-key-1',
        repeat('c',64),'Connected completion race',
        jsonb_build_object('id',message_id,'role','user','content','race user'),
        jsonb_build_object(
          'id',assistant_id,'role','assistant','inReplyTo',message_id,
          'content','race assistant'
        ),
        jsonb_build_object('response','race assistant')
      );
      did_apply := response->>'completion_id' is not null;
    else
      raise exception 'unknown writer operation';
    end if;
    return query select did_apply,null::text,null::text;
  exception when others then
    get stacked diagnostics err_state=returned_sqlstate,err_message=message_text;
    return query select null::boolean,err_state,err_message;
  end;
end;
$$;

create or replace function public.test_connected_lock_call_delete(p_user_id uuid)
returns table(applied boolean,error_sqlstate text,error_message text)
language plpgsql set search_path = ''
as $$
declare err_state text; err_message text;
begin
  begin
    perform public.delete_user_account(p_user_id,'crump-files');
    return query select true,null::text,null::text;
  exception when others then
    get stacked diagnostics err_state=returned_sqlstate,err_message=message_text;
    return query select null::boolean,err_state,err_message;
  end;
end;
$$;

create or replace function public.test_connected_lock_delay_writer()
returns trigger language plpgsql set search_path = ''
as $$
begin
  if coalesce(current_setting('askcrump.test_delay_writer_user',true),'')
       = new.user_id::text then
    perform pg_sleep(0.65);
  end if;
  return new;
end;
$$;
create trigger test_connected_lock_delay_writer_trigger
before insert or update on public.user_chats
for each row execute function public.test_connected_lock_delay_writer();

create or replace function public.test_connected_lock_delay_delete()
returns trigger language plpgsql set search_path = ''
as $$
begin
  if coalesce(current_setting('askcrump.test_delay_delete_user',true),'')
       = new.user_id::text then
    perform pg_sleep(0.65);
  end if;
  return new;
end;
$$;
create trigger test_connected_lock_delay_delete_trigger
before insert or update on public.account_storage_deletion_jobs
for each row execute function public.test_connected_lock_delay_delete();

create or replace function public.test_connected_lock_wait(
  p_application text,p_timeout interval default interval '3 seconds'
)
returns void language plpgsql set search_path = ''
as $$
declare deadline timestamptz := clock_timestamp()+p_timeout;
begin
  loop
    if exists (
      select 1 from pg_stat_activity a join pg_locks l on l.pid=a.pid
      where a.datname=current_database() and a.application_name=p_application
        and l.locktype='advisory' and l.mode='ExclusiveLock' and l.granted
    ) then return; end if;
    if clock_timestamp()>=deadline then
      raise exception 'timed out waiting for %',p_application using errcode='57014';
    end if;
    perform pg_sleep(0.01);
  end loop;
end;
$$;

create or replace function public.test_connected_lock_run(
  p_operation text,p_user_id uuid,p_writer_first boolean
)
returns void language plpgsql set search_path = ''
as $$
declare
  suffix text := substr(replace(p_user_id::text,'-',''),1,18);
  writer_conn text := 'cl_writer_'||suffix;
  delete_conn text := 'cl_delete_'||suffix;
  writer_app text := 'connected-lock-'||p_operation||'-writer';
  delete_app text := 'connected-lock-'||p_operation||'-delete';
  writer_applied boolean; writer_state text; writer_message text;
  delete_applied boolean; delete_state text; delete_message text;
  job_before uuid; job_after uuid;
begin
  perform public.dblink_connect(writer_conn,format(
    'host=%L port=%L dbname=%L user=%L application_name=%L',
    '127.0.0.1',current_setting('port'),current_database(),current_user,writer_app
  ));
  perform public.dblink_connect(delete_conn,format(
    'host=%L port=%L dbname=%L user=%L application_name=%L',
    '127.0.0.1',current_setting('port'),current_database(),current_user,delete_app
  ));
  perform public.dblink_exec(writer_conn,'set deadlock_timeout=''100ms''');
  perform public.dblink_exec(delete_conn,'set deadlock_timeout=''100ms''');
  perform public.dblink_exec(writer_conn,'set statement_timeout=''8s''');
  perform public.dblink_exec(delete_conn,'set statement_timeout=''8s''');
  perform public.dblink_exec(writer_conn,'set lock_timeout=''5s''');
  perform public.dblink_exec(delete_conn,'set lock_timeout=''5s''');
  perform public.dblink_exec(writer_conn,'set role service_role');
  perform public.dblink_exec(delete_conn,'set role service_role');

  if p_writer_first then
    perform public.dblink_exec(writer_conn,format(
      'set askcrump.test_delay_writer_user=%L',p_user_id::text
    ));
    perform public.test_connected_lock_assert(
      public.dblink_send_query(writer_conn,format(
        'select * from public.test_connected_lock_call_writer(%L,%L::uuid)',
        p_operation,p_user_id::text
      ))=1,'writer query was not dispatched'
    );
    perform public.test_connected_lock_wait(writer_app);
    perform public.test_connected_lock_assert(
      public.dblink_send_query(delete_conn,format(
        'select * from public.test_connected_lock_call_delete(%L::uuid)',
        p_user_id::text
      ))=1,'delete query was not dispatched'
    );
    select * into writer_applied,writer_state,writer_message
      from public.dblink_get_result(writer_conn,true)
      as r(applied boolean,error_sqlstate text,error_message text);
    select * into delete_applied,delete_state,delete_message
      from public.dblink_get_result(delete_conn,true)
      as r(applied boolean,error_sqlstate text,error_message text);
  else
    perform public.dblink_exec(delete_conn,format(
      'set askcrump.test_delay_delete_user=%L',p_user_id::text
    ));
    perform public.test_connected_lock_assert(
      public.dblink_send_query(delete_conn,format(
        'select * from public.test_connected_lock_call_delete(%L::uuid)',
        p_user_id::text
      ))=1,'delete query was not dispatched'
    );
    perform public.test_connected_lock_wait(delete_app);
    perform public.test_connected_lock_assert(
      public.dblink_send_query(writer_conn,format(
        'select * from public.test_connected_lock_call_writer(%L,%L::uuid)',
        p_operation,p_user_id::text
      ))=1,'writer query was not dispatched'
    );
    select * into delete_applied,delete_state,delete_message
      from public.dblink_get_result(delete_conn,true)
      as r(applied boolean,error_sqlstate text,error_message text);
    select * into writer_applied,writer_state,writer_message
      from public.dblink_get_result(writer_conn,true)
      as r(applied boolean,error_sqlstate text,error_message text);
  end if;

  perform public.dblink_disconnect(writer_conn);
  perform public.dblink_disconnect(delete_conn);

  perform public.test_connected_lock_assert(
    writer_state is distinct from '40P01' and delete_state is distinct from '40P01',
    format('%s race deadlocked: writer=%s delete=%s',p_operation,writer_state,delete_state)
  );
  perform public.test_connected_lock_assert(
    delete_state is null and delete_applied,
    format('%s deletion failed: %s %s',p_operation,delete_state,delete_message)
  );
  if p_writer_first then
    perform public.test_connected_lock_assert(
      writer_state is null and writer_applied,
      format('%s writer-first did not commit: %s %s',p_operation,writer_state,writer_message)
    );
  else
    perform public.test_connected_lock_assert(
      writer_applied is not true,
      format('%s delete-first writer was not safely refused: %s %s',
        p_operation,writer_state,writer_message)
    );
  end if;

  select id into job_before from public.account_storage_deletion_jobs
   where user_id=p_user_id;
  perform public.delete_user_account(p_user_id,'crump-files');
  select id into job_after from public.account_storage_deletion_jobs
   where user_id=p_user_id;
  perform public.test_connected_lock_assert(
    job_before is not null and job_after=job_before,
    p_operation||' deletion job was not durable/idempotent'
  );
  perform public.test_connected_lock_assert(
    not exists(select 1 from public.users where id=p_user_id)
    and not exists(select 1 from public.sessions where user_id=p_user_id)
    and not exists(select 1 from public.user_chats where user_id=p_user_id)
    and not exists(select 1 from public.chat_jobs where user_id=p_user_id)
    and not exists(
      select 1 from connected_chat_private.turns where owner_id=p_user_id
    )
    and not exists(
      select 1 from connected_chat_completion_private.completions
      where owner_id=p_user_id
    ),
    p_operation||' deletion left an account-owned row'
  );
exception when others then
  if writer_conn=any(coalesce(public.dblink_get_connections(),array[]::text[]))
    then perform public.dblink_disconnect(writer_conn); end if;
  if delete_conn=any(coalesce(public.dblink_get_connections(),array[]::text[]))
    then perform public.dblink_disconnect(delete_conn); end if;
  raise;
end;
$$;

select public.test_connected_lock_seed(
  'guest_reply',public.test_connected_lock_uuid('guest-reply-writer-first')
);
select public.test_connected_lock_run(
  'guest_reply',public.test_connected_lock_uuid('guest-reply-writer-first'),true
);
select public.test_connected_lock_seed(
  'guest_reply',public.test_connected_lock_uuid('guest-reply-delete-first')
);
select public.test_connected_lock_run(
  'guest_reply',public.test_connected_lock_uuid('guest-reply-delete-first'),false
);
select public.test_connected_lock_seed(
  'guest_sync',public.test_connected_lock_uuid('guest-sync-writer-first')
);
select public.test_connected_lock_run(
  'guest_sync',public.test_connected_lock_uuid('guest-sync-writer-first'),true
);
select public.test_connected_lock_seed(
  'guest_sync',public.test_connected_lock_uuid('guest-sync-delete-first')
);
select public.test_connected_lock_run(
  'guest_sync',public.test_connected_lock_uuid('guest-sync-delete-first'),false
);
select public.test_connected_lock_seed(
  'connected',public.test_connected_lock_uuid('connected-writer-first')
);
select public.test_connected_lock_run(
  'connected',public.test_connected_lock_uuid('connected-writer-first'),true
);
select public.test_connected_lock_seed(
  'connected',public.test_connected_lock_uuid('connected-delete-first')
);
select public.test_connected_lock_run(
  'connected',public.test_connected_lock_uuid('connected-delete-first'),false
);

drop trigger test_connected_lock_delay_writer_trigger on public.user_chats;
drop trigger test_connected_lock_delay_delete_trigger
  on public.account_storage_deletion_jobs;
drop function public.test_connected_lock_delay_writer();
drop function public.test_connected_lock_delay_delete();
drop function public.test_connected_lock_run(text,uuid,boolean);
drop function public.test_connected_lock_wait(text,interval);
drop function public.test_connected_lock_call_delete(uuid);
drop function public.test_connected_lock_call_writer(text,uuid);
drop function public.test_connected_lock_seed(text,uuid);
drop function public.test_connected_lock_assert(boolean,text);
drop function public.test_connected_lock_hash(text);
drop function public.test_connected_lock_uuid(text);

select 'guest and connected completion owner-lock races passed' as result;
