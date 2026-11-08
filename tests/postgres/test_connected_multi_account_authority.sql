\set ON_ERROR_STOP on

begin;

insert into public.users(
  id,email,password_hash,is_verified,is_guest,created_at,updated_at,
  registration_environment,registration_submitted_at,
  password_setup_required,password_inbox_bound_at
) values(
  '10000000-0000-4000-8000-000000006891',
  'multi-account-owner@example.test','$argon2id$multi-account',true,false,
  pg_catalog.clock_timestamp()-interval '1 day',pg_catalog.clock_timestamp(),
  'production',pg_catalog.clock_timestamp()-interval '1 day',false,
  pg_catalog.clock_timestamp()-interval '1 day'
);

create or replace function public.connected_multi_account_seed_active_v1(
  p_connection_id uuid,p_account_kind text,p_resource text,p_seed text
) returns void language plpgsql set search_path='' as $fn$
begin
  insert into connected_app_private.connections(
    id,owner_id,provider,resource,account_kind,connection_incarnation_id,
    authorization_revision,authorization_state,authorization_snapshot_sha256,
    granted_actions,granted_actions_sha256,granted_scopes_sha256,
    external_account_id_sha256,broker_credential_ref,credential_ref_sha256,
    authorization_issued_at,authorization_expires_at,created_at,updated_at
  ) values(
    p_connection_id,'10000000-0000-4000-8000-000000006891','microsoft',
    p_resource,p_account_kind,pg_catalog.gen_random_uuid(),1,'active',
    pg_catalog.md5(p_seed||':snapshot')||pg_catalog.md5(p_seed||':snapshot:2'),
    case when p_resource='mail' then array['mail.get'] else array['calendar.get'] end,
    pg_catalog.md5(p_seed||':actions')||pg_catalog.md5(p_seed||':actions:2'),
    pg_catalog.md5(p_seed||':scopes')||pg_catalog.md5(p_seed||':scopes:2'),
    pg_catalog.md5(p_seed||':external')||pg_catalog.md5(p_seed||':external:2'),
    pg_catalog.gen_random_uuid(),
    pg_catalog.md5(p_seed||':credential')||pg_catalog.md5(p_seed||':credential:2'),
    pg_catalog.clock_timestamp(),pg_catalog.clock_timestamp()+interval '1 hour',
    pg_catalog.clock_timestamp(),pg_catalog.clock_timestamp()
  );
end;
$fn$;

select public.connected_multi_account_seed_active_v1(
  '20000000-0000-4000-8000-000000006891','personal','mail','personal-mail'
);
select public.connected_multi_account_seed_active_v1(
  '20000000-0000-4000-8000-000000006892','work_school','mail','work-mail'
);
select public.connected_multi_account_seed_active_v1(
  '20000000-0000-4000-8000-000000006893','personal','calendar','personal-calendar'
);
select public.connected_multi_account_seed_active_v1(
  '20000000-0000-4000-8000-000000006894','work_school','calendar','work-calendar'
);

do $behavior$
declare
  listed jsonb;
  selected jsonb;
begin
  select public.connected_app_operator_list_connections_v1(
    '10000000-0000-4000-8000-000000006891'
  ) into listed;
  if pg_catalog.jsonb_array_length(listed)<>4
     or (select pg_catalog.count(distinct (
          (item->>'provider')||':'||(item->>'account_kind')||':'||
          (item->>'resource')))
         from pg_catalog.jsonb_array_elements(listed) as item)<>4 then
    raise exception 'Microsoft account-kind connection list collapsed: %',listed;
  end if;

  select public.connected_app_operator_get_connection_authority_v1(
    '10000000-0000-4000-8000-000000006891',
    '20000000-0000-4000-8000-000000006892'
  ) into selected;
  if selected->>'connection_id'<>'20000000-0000-4000-8000-000000006892'
     or selected->>'provider'<>'microsoft'
     or selected->>'resource'<>'mail' then
    raise exception 'explicit connection authority selection drifted: %',selected;
  end if;

  begin
    perform public.connected_multi_account_seed_active_v1(
      '20000000-0000-4000-8000-000000006895','personal','mail',
      'duplicate-personal-mail'
    );
    raise exception 'duplicate same-kind resource unexpectedly activated';
  exception when unique_violation then
    null;
  end;

  if (select pg_catalog.count(*)
      from connected_app_private.connections
      where owner_id='10000000-0000-4000-8000-000000006891'
        and authorization_state='active')<>4 then
    raise exception 'duplicate refusal changed existing authorities';
  end if;
end;
$behavior$;

set local role service_role;
select public.delete_user_account(
  '10000000-0000-4000-8000-000000006891','crump-files'
);
reset role;

do $deletion$
begin
  if exists(
       select 1 from connected_app_private.connections
       where owner_id='10000000-0000-4000-8000-000000006891'
     )
     or exists(
       select 1 from connected_app_private.oauth_flows
       where owner_id='10000000-0000-4000-8000-000000006891'
     ) then
    raise exception 'multi-account deletion left connected-app orphans';
  end if;
end;
$deletion$;

rollback;

select 'CONNECTED_MULTI_ACCOUNT_AUTHORITY_BEHAVIOR_OK' as result;
