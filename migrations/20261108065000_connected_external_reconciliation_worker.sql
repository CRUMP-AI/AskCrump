begin;

set local search_path = pg_catalog, public;
set local quote_all_identifiers = off;

create or replace function pg_temp.connected_external_reconciliation_target_fingerprint()
returns text
language sql
stable
set search_path = ''
as $fingerprint$
  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    pg_catalog.pg_get_functiondef(proc.oid),
    pg_catalog.obj_description(proc.oid, 'pg_proc'),
    pg_catalog.pg_get_userbyid(proc.proowner), proc.prosecdef::text,
    proc.proleakproof::text, proc.proisstrict::text, proc.proretset::text,
    proc.provolatile::text, proc.proparallel::text,
    proc.procost::text, proc.prorows::text,
    language.lanname, proc.proconfig::text, proc.proacl::text
  ))
  from pg_catalog.pg_proc proc
  join pg_catalog.pg_language language on language.oid = proc.prolang
  where proc.oid = pg_catalog.to_regprocedure(
    'public.connected_app_oauth_reconcile_expired_v1(integer)'
  )
$fingerprint$;

do $preflight$
declare
  helper_fingerprint text;
  target_fingerprint text;
  target_count integer;
begin
  if pg_catalog.to_regprocedure(
       'connected_app_private.oauth_operator_target_fingerprint_v1()'
     ) is null then
    raise exception 'connected external reconciliation predecessor is absent'
      using errcode = '55000';
  end if;
  select pg_catalog.md5(pg_catalog.concat_ws(E'\n',
    pg_catalog.pg_get_functiondef(proc.oid),
    pg_catalog.obj_description(proc.oid, 'pg_proc'),
    pg_catalog.pg_get_userbyid(proc.proowner), proc.prosecdef::text,
    proc.provolatile::text, proc.proconfig::text, proc.proacl::text
  )) into helper_fingerprint
  from pg_catalog.pg_proc proc
  where proc.oid = pg_catalog.to_regprocedure(
    'connected_app_private.oauth_operator_target_fingerprint_v1()'
  );
  select connected_app_private.oauth_operator_target_fingerprint_v1()
    into target_fingerprint;
  if helper_fingerprint <> '1bce6135686a0d64ec522a9217c9ea0c'
     or target_fingerprint <> '95612aca01e069376fb82aca32e286e9' then
    raise exception 'connected external reconciliation predecessor drifted'
      using errcode = '55000';
  end if;
  if exists (
       select 1 from pg_catalog.pg_publication publication_row
       where publication_row.puballtables
     ) or exists (
       select 1
       from pg_catalog.pg_publication_namespace publication_namespace
       where publication_namespace.pnnspid =
         pg_catalog.to_regnamespace('connected_app_private')
     ) or exists (
       select 1
       from pg_catalog.pg_publication_rel publication_relation
       join pg_catalog.pg_class class_row
         on class_row.oid = publication_relation.prrelid
       join pg_catalog.pg_namespace namespace_row
         on namespace_row.oid = class_row.relnamespace
       where namespace_row.nspname = 'connected_app_private'
     ) then
    raise exception 'connected external reconciliation publication exposure refused'
      using errcode = '55000';
  end if;
  select pg_catalog.count(*) into target_count
  from pg_catalog.pg_proc proc
  join pg_catalog.pg_namespace namespace_row
    on namespace_row.oid = proc.pronamespace
  where namespace_row.nspname = 'public'
    and proc.proname = 'connected_app_oauth_reconcile_expired_v1';
  if target_count not in (0, 1) then
    raise exception 'connected external reconciliation target is partial or overloaded'
      using errcode = '55000';
  end if;
  if target_count = 1 then
    if pg_catalog.to_regprocedure(
         'public.connected_app_oauth_reconcile_expired_v1(integer)'
       ) is null then
      raise exception 'connected external reconciliation target signature drifted'
        using errcode = '55000';
    end if;
    select pg_temp.connected_external_reconciliation_target_fingerprint()
      into target_fingerprint;
    if target_fingerprint <> '52629ef0c6f07fe7ac8eb4292bfc59aa' then
      raise exception 'connected external reconciliation target drifted: %',
        target_fingerprint using errcode = '55000';
    end if;
  end if;
end;
$preflight$;

create or replace function public.connected_app_oauth_reconcile_expired_v1(
  p_limit integer
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  flow_row record;
  provisional_row record;
  expired_flow_count integer := 0;
  expired_provisional_count integer := 0;
  reference_at timestamptz := pg_catalog.clock_timestamp();
begin
  if p_limit is null or p_limit < 1 or p_limit > 100 then
    raise exception 'connected OAuth reconciliation limit is invalid'
      using errcode = '22023';
  end if;

  for flow_row in
    select secret.flow_id, secret.flow_binding_sha256, secret.owner_id
    from connected_app_private.oauth_secret_custody secret
    where secret.expires_at <= reference_at
      and secret.status in ('pending', 'attempt_fenced', 'deadline_expired')
    order by secret.expires_at, secret.flow_id
    limit p_limit
  loop
    -- Take the same owner advisory lock as every OAuth lifecycle mutation
    -- before any row lock.  The nonblocking form lets several authenticated
    -- workers divide work without recreating an owner/row lock inversion.
    continue when not pg_catalog.pg_try_advisory_xact_lock(
      pg_catalog.hashtextextended(
        flow_row.owner_id::text, 606232723337443413::bigint
      )
    );
    perform 1
    from connected_app_private.oauth_secret_custody secret
    where secret.flow_id = flow_row.flow_id
      and secret.flow_binding_sha256 = flow_row.flow_binding_sha256
      and secret.owner_id = flow_row.owner_id
      and secret.expires_at <= reference_at
      and secret.status in ('pending', 'attempt_fenced', 'deadline_expired')
    for update skip locked;
    continue when not found;
    perform public.connected_app_oauth_secret_abort_v1(
      flow_row.flow_id, flow_row.flow_binding_sha256, 'expired'
    );
    expired_flow_count := expired_flow_count + 1;
  end loop;

  for provisional_row in
    select provisional.provisional_id, provisional.owner_id,
      provisional.credential_handle_sha256, provisional.record_binding_sha256
    from connected_app_private.oauth_provisional_credentials provisional
    where provisional.expires_at <= reference_at
    order by provisional.expires_at, provisional.provisional_id
    limit p_limit
  loop
    continue when not pg_catalog.pg_try_advisory_xact_lock(
      pg_catalog.hashtextextended(
        provisional_row.owner_id::text, 606232723337443413::bigint
      )
    );
    delete from connected_app_private.oauth_provisional_credentials provisional
    where provisional.provisional_id = provisional_row.provisional_id
      and provisional.owner_id = provisional_row.owner_id
      and provisional.credential_handle_sha256 =
        provisional_row.credential_handle_sha256
      and provisional.record_binding_sha256 =
        provisional_row.record_binding_sha256
      and provisional.expires_at <= reference_at;
    if found then
      expired_provisional_count := expired_provisional_count + 1;
    end if;
  end loop;

  return pg_catalog.jsonb_build_object(
    'expired_flows', expired_flow_count,
    'expired_provisionals', expired_provisional_count
  );
end;
$function$;

comment on function public.connected_app_oauth_reconcile_expired_v1(integer) is
  'ASK_CRUMP_CONNECTED_OAUTH_RECONCILE_EXPIRED_V1_BOUNDED_SKIP_LOCKED_CONTENT_FREE';
alter function public.connected_app_oauth_reconcile_expired_v1(integer)
  owner to postgres;
revoke all on function public.connected_app_oauth_reconcile_expired_v1(integer)
  from public, anon, authenticated;
grant execute on function public.connected_app_oauth_reconcile_expired_v1(integer)
  to service_role;

do $postflight$
declare
  target_fingerprint text;
begin
  if pg_catalog.to_regprocedure(
       'public.connected_app_oauth_reconcile_expired_v1(integer)'
     ) is null
     or pg_catalog.pg_get_userbyid((
       select proc.proowner from pg_catalog.pg_proc proc
       where proc.oid = pg_catalog.to_regprocedure(
         'public.connected_app_oauth_reconcile_expired_v1(integer)'
       )
     )) <> 'postgres'
     or not pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_oauth_reconcile_expired_v1(integer)',
       'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'anon',
       'public.connected_app_oauth_reconcile_expired_v1(integer)',
       'EXECUTE'
     )
     or pg_catalog.has_function_privilege(
       'authenticated',
       'public.connected_app_oauth_reconcile_expired_v1(integer)',
       'EXECUTE'
     ) then
    raise exception 'connected external reconciliation authority drifted'
      using errcode = '55000';
  end if;
  select pg_temp.connected_external_reconciliation_target_fingerprint()
    into target_fingerprint;
  if target_fingerprint <> '52629ef0c6f07fe7ac8eb4292bfc59aa' then
    raise exception 'connected external reconciliation exact target failed: %',
      target_fingerprint using errcode = '55000';
  end if;
end;
$postflight$;

commit;
