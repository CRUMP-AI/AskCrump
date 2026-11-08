\set ON_ERROR_STOP on

begin;

select pg_catalog.set_config('search_path','pg_catalog,public',true);
select pg_catalog.set_config('quote_all_identifiers','off',true);

do $preflight$
declare
  observed_target text;
  observed_catalog text;
  fingerprint_oid oid;
  catalog_fingerprint_oid oid;
  transition_oid oid;
begin
  fingerprint_oid:=pg_catalog.to_regprocedure(
    'connected_readiness_private.runtime_readiness_target_fingerprint_v1()'
  );
  catalog_fingerprint_oid:=pg_catalog.to_regprocedure(
    'connected_readiness_private.runtime_readiness_catalog_fingerprint_v1()'
  );
  transition_oid:=pg_catalog.to_regprocedure(
    'public.connected_app_consume_approval_and_begin_effect_v1(uuid,uuid,uuid,uuid,bigint,text,text,uuid,timestamp with time zone)'
  );
  if fingerprint_oid is null then
    raise exception 'connected approval-effect predecessor is absent'
      using errcode='55000';
  end if;

  if transition_oid is null then
    if catalog_fingerprint_oid is not null
       or (select pg_catalog.count(*)
           from pg_catalog.pg_proc as proc_row
           join pg_catalog.pg_namespace as namespace_row
             on namespace_row.oid=proc_row.pronamespace
           where namespace_row.nspname='connected_readiness_private'
             and proc_row.proname in (
               'runtime_readiness_target_fingerprint_v1',
               'runtime_readiness_catalog_fingerprint_v1'))<>1
       or (select pg_catalog.md5(pg_catalog.pg_get_functiondef(proc_row.oid))<>
                    'fd14fc0ab96a67b31ae329f6686b98c4'
                  or pg_catalog.pg_get_userbyid(proc_row.proowner)<>'postgres'
                  or not proc_row.prosecdef or proc_row.provolatile<>'s'
                  or proc_row.proleakproof or proc_row.proretset
                  or proc_row.prokind<>'f' or language_row.lanname<>'sql'
                  or coalesce(proc_row.proconfig::text,'')<>
                     '{"search_path=\"\""}'
                  or coalesce(proc_row.proacl::text,'')<>
                     '{postgres=X/postgres}'
                  or coalesce(pg_catalog.obj_description(
                       proc_row.oid,'pg_proc'),'')<>
                     'ASK_CRUMP_CONNECTED_RUNTIME_READINESS_TARGET_FINGERPRINT_V1_FULL_STACK'
           from pg_catalog.pg_proc as proc_row
           join pg_catalog.pg_language as language_row
             on language_row.oid=proc_row.prolang
           where proc_row.oid=fingerprint_oid) then
      raise exception 'connected approval-effect predecessor fingerprint authority drifted'
        using errcode='55000';
    end if;
    select connected_readiness_private.runtime_readiness_target_fingerprint_v1()
      into observed_target;
    if observed_target<>'2e2bde8ec7137a2c5486532f48499f5a' then
      raise exception 'connected approval-effect predecessor drifted: %',
        observed_target using errcode='55000';
    end if;
  else
    if catalog_fingerprint_oid is null
       or (select pg_catalog.count(*)
           from pg_catalog.pg_proc as proc_row
           join pg_catalog.pg_namespace as namespace_row
             on namespace_row.oid=proc_row.pronamespace
           where namespace_row.nspname='connected_readiness_private'
             and proc_row.proname in (
               'runtime_readiness_target_fingerprint_v1',
               'runtime_readiness_catalog_fingerprint_v1'))<>2
       or (select pg_catalog.md5(pg_catalog.pg_get_functiondef(proc_row.oid))<>
                    '81801876eb127d22939d77fb2e2fa0e0'
                  or pg_catalog.pg_get_userbyid(proc_row.proowner)<>'postgres'
                  or not proc_row.prosecdef or proc_row.provolatile<>'s'
                  or proc_row.proleakproof or proc_row.proretset
                  or proc_row.prokind<>'f' or language_row.lanname<>'sql'
                  or coalesce(proc_row.proconfig::text,'')<>
                     '{"search_path=\"\""}'
                  or coalesce(proc_row.proacl::text,'')<>
                     '{postgres=X/postgres}'
                  or coalesce(pg_catalog.obj_description(
                       proc_row.oid,'pg_proc'),'')<>
                     'ASK_CRUMP_CONNECTED_APPROVAL_EFFECT_TARGET_FINGERPRINT_V1_FULL_STACK'
           from pg_catalog.pg_proc as proc_row
           join pg_catalog.pg_language as language_row
             on language_row.oid=proc_row.prolang
           where proc_row.oid=fingerprint_oid)
       or (select pg_catalog.md5(pg_catalog.pg_get_functiondef(proc_row.oid))<>
                    'b4b16acc52dac4d535742d359bebc632'
                  or pg_catalog.pg_get_userbyid(proc_row.proowner)<>'postgres'
                  or not proc_row.prosecdef or proc_row.provolatile<>'s'
                  or proc_row.proleakproof or proc_row.proretset
                  or proc_row.prokind<>'f' or language_row.lanname<>'sql'
                  or coalesce(proc_row.proconfig::text,'')<>
                     '{"search_path=\"\""}'
                  or coalesce(proc_row.proacl::text,'')<>
                     '{postgres=X/postgres}'
                  or coalesce(pg_catalog.obj_description(
                       proc_row.oid,'pg_proc'),'')<>
                     'ASK_CRUMP_CONNECTED_RUNTIME_READINESS_CATALOG_FINGERPRINT_V1_FULL_STACK'
           from pg_catalog.pg_proc as proc_row
           join pg_catalog.pg_language as language_row
             on language_row.oid=proc_row.prolang
           where proc_row.oid=catalog_fingerprint_oid) then
      raise exception 'connected approval-effect target fingerprint authority drifted'
        using errcode='55000';
    end if;
    select connected_readiness_private.runtime_readiness_catalog_fingerprint_v1()
      into observed_catalog;
    select connected_readiness_private.runtime_readiness_target_fingerprint_v1()
      into observed_target;
    if observed_catalog is distinct from observed_target
       or observed_target<>'c339945387929ed735b591d967f536dc' then
      raise exception 'connected approval-effect target drifted: %, %',
        observed_catalog,observed_target using errcode='55000';
    end if;
  end if;
  if pg_catalog.to_regprocedure(
       'public.connected_app_consume_approval_v1(uuid,uuid,uuid,uuid,bigint,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_begin_effect_v1(uuid,uuid,uuid,bigint,text,uuid,uuid,timestamp with time zone)'
     ) is null then
    raise exception 'connected approval-effect authority functions are absent'
      using errcode='55000';
  end if;
  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace as publication_schema
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=publication_schema.pnnspid
       where namespace_row.nspname like 'connected\_%\_private' escape '\')
     or exists(
       select 1 from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row
         on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname like 'connected\_%\_private' escape '\') then
    raise exception 'connected approval-effect publication exposure refused'
      using errcode='55000';
  end if;
end;
$preflight$;

create or replace function public.connected_app_consume_approval_and_begin_effect_v1(
  p_approval_id uuid,
  p_operation_id uuid,
  p_owner_id uuid,
  p_claim_id uuid,
  p_fencing_token bigint,
  p_approval_binding_sha256 text,
  p_granted_actions_sha256 text,
  p_effect_use_nonce uuid,
  p_credential_expires_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $fn$
declare
  result jsonb;
  action_row connected_app_private.action_ledger%rowtype;
  approval_row connected_app_private.approvals%rowtype;
begin
  if p_approval_id is null or p_operation_id is null or p_owner_id is null
     or p_claim_id is null or p_fencing_token<1
     or p_approval_binding_sha256 is null
     or p_approval_binding_sha256!~'^[0-9a-f]{64}$'
     or p_granted_actions_sha256 is null
     or p_granted_actions_sha256!~'^[0-9a-f]{64}$'
     or p_effect_use_nonce is null or p_credential_expires_at is null then
    raise exception 'connected approval-effect transition is invalid'
      using errcode='22023';
  end if;

  -- Both established functions take this same canonical transaction-scoped
  -- owner lock.  Calling them in one statement makes approval consumption and
  -- the effect_possible ledger transition one atomic commit boundary.
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select ledger.* into action_row
  from connected_app_private.action_ledger as ledger
  where ledger.operation_id=p_operation_id and ledger.owner_id=p_owner_id
  for update;
  if not found then
    raise exception 'action not found' using errcode='55000';
  end if;

  if action_row.status='effect_possible' then
    -- A response-loss retry reaches this explicit branch.  Prove the complete
    -- one-use identity tuple before delegating the remaining live authority,
    -- expiry, connection, grant, and resource checks to begin_effect_v1.
    select approval.* into approval_row
    from connected_app_private.approvals as approval
    where approval.approval_id=p_approval_id
    for update;
    if approval_row.approval_id is null
       or action_row.claim_id<>p_claim_id
       or action_row.fencing_token<>p_fencing_token
       or action_row.effect_use_nonce is distinct from p_effect_use_nonce
       or action_row.effect_credential_expires_at is distinct from
          p_credential_expires_at
       or approval_row.owner_id<>p_owner_id
       or approval_row.action_id<>action_row.action_id
       or approval_row.approval_binding_sha256<>p_approval_binding_sha256
       or approval_row.consumed_at is null
       or approval_row.consumed_by_operation_id is distinct from
          p_operation_id then
      raise exception 'effect replay authority changed' using errcode='55000';
    end if;
  elsif action_row.status='access_granted' then
    perform public.connected_app_consume_approval_v1(
      p_approval_id,p_operation_id,p_owner_id,p_claim_id,p_fencing_token,
      p_approval_binding_sha256
    );
  else
    raise exception 'approval-effect transition state changed'
      using errcode='55000';
  end if;
  result:=public.connected_app_begin_effect_v1(
    p_operation_id,p_owner_id,p_claim_id,p_fencing_token,
    p_granted_actions_sha256,p_approval_id,p_effect_use_nonce,
    p_credential_expires_at
  );
  return result;
end;
$fn$;
comment on function
  public.connected_app_consume_approval_and_begin_effect_v1(
    uuid,uuid,uuid,uuid,bigint,text,text,uuid,timestamptz
  ) is
  'ASK_CRUMP_CONNECTED_APPROVAL_EFFECT_V1_ATOMIC_ONE_USE_LINEARIZATION';
alter function
  public.connected_app_consume_approval_and_begin_effect_v1(
    uuid,uuid,uuid,uuid,bigint,text,text,uuid,timestamptz
  ) owner to postgres;
revoke all on function
  public.connected_app_consume_approval_and_begin_effect_v1(
    uuid,uuid,uuid,uuid,bigint,text,text,uuid,timestamptz
  ) from public,anon,authenticated,service_role;
grant execute on function
  public.connected_app_consume_approval_and_begin_effect_v1(
    uuid,uuid,uuid,uuid,bigint,text,text,uuid,timestamptz
  ) to service_role;

-- These primitives remain callable by postgres-owned SECURITY DEFINER
-- functions, but they are not application boundaries.  Leaving any one of
-- them directly executable by service_role would permit either authority
-- minting without a reviewed decision or reintroduce the non-atomic crash gap.
revoke all on function public.connected_app_create_approval_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,
  timestamptz,timestamptz
) from public,anon,authenticated,service_role;
revoke all on function public.connected_app_consume_approval_v1(
  uuid,uuid,uuid,uuid,bigint,text
) from public,anon,authenticated,service_role;
revoke all on function public.connected_app_begin_effect_v1(
  uuid,uuid,uuid,bigint,text,uuid,uuid,timestamptz
) from public,anon,authenticated,service_role;

-- Preserve the reviewed 69000 full-catalog manifest as a private helper, then
-- redefine the canonical readiness fingerprint as a small stable wrapper.
-- The helper's manifest includes both functions (and every connected private
-- catalog/ACL/RLS/column-ACL/policy/trigger/rule/publication object), so the
-- returned target attests the exact 69000 catalog plus this transition.
do $promote_fingerprint$
begin
  if pg_catalog.to_regprocedure(
       'connected_readiness_private.runtime_readiness_catalog_fingerprint_v1()'
     ) is null then
    if pg_catalog.to_regprocedure(
         'connected_readiness_private.runtime_readiness_target_fingerprint_v1()'
       ) is null then
      raise exception 'connected approval-effect fingerprint source is absent'
        using errcode='55000';
    end if;
    alter function
      connected_readiness_private.runtime_readiness_target_fingerprint_v1()
      rename to runtime_readiness_catalog_fingerprint_v1;
  end if;
end;
$promote_fingerprint$;

comment on function
  connected_readiness_private.runtime_readiness_catalog_fingerprint_v1() is
  'ASK_CRUMP_CONNECTED_RUNTIME_READINESS_CATALOG_FINGERPRINT_V1_FULL_STACK';
alter function
  connected_readiness_private.runtime_readiness_catalog_fingerprint_v1()
  owner to postgres;
revoke all on function
  connected_readiness_private.runtime_readiness_catalog_fingerprint_v1()
  from public,anon,authenticated,service_role;

create or replace function
  connected_readiness_private.runtime_readiness_target_fingerprint_v1()
returns text
language sql
stable
security definer
set search_path=''
as $fingerprint$
  select connected_readiness_private.runtime_readiness_catalog_fingerprint_v1()
$fingerprint$;
comment on function
  connected_readiness_private.runtime_readiness_target_fingerprint_v1() is
  'ASK_CRUMP_CONNECTED_APPROVAL_EFFECT_TARGET_FINGERPRINT_V1_FULL_STACK';
alter function
  connected_readiness_private.runtime_readiness_target_fingerprint_v1()
  owner to postgres;
revoke all on function
  connected_readiness_private.runtime_readiness_target_fingerprint_v1()
  from public,anon,authenticated,service_role;

do $postflight$
declare
  observed_target text;
  observed_catalog text;
  procedure_oid oid;
  fingerprint_oid oid;
  catalog_fingerprint_oid oid;
  create_approval_oid oid;
  consume_approval_oid oid;
  begin_effect_oid oid;
  decide_approval_oid oid;
begin
  procedure_oid:=pg_catalog.to_regprocedure(
    'public.connected_app_consume_approval_and_begin_effect_v1(uuid,uuid,uuid,uuid,bigint,text,text,uuid,timestamp with time zone)'
  );
  fingerprint_oid:=pg_catalog.to_regprocedure(
    'connected_readiness_private.runtime_readiness_target_fingerprint_v1()'
  );
  catalog_fingerprint_oid:=pg_catalog.to_regprocedure(
    'connected_readiness_private.runtime_readiness_catalog_fingerprint_v1()'
  );
  create_approval_oid:=pg_catalog.to_regprocedure(
    'public.connected_app_create_approval_v1(uuid,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,text,text,timestamp with time zone,timestamp with time zone)'
  );
  consume_approval_oid:=pg_catalog.to_regprocedure(
    'public.connected_app_consume_approval_v1(uuid,uuid,uuid,uuid,bigint,text)'
  );
  begin_effect_oid:=pg_catalog.to_regprocedure(
    'public.connected_app_begin_effect_v1(uuid,uuid,uuid,bigint,text,uuid,uuid,timestamp with time zone)'
  );
  decide_approval_oid:=pg_catalog.to_regprocedure(
    'public.connected_app_operator_decide_approval_v1(uuid,uuid,text,uuid,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,bigint,text,text,text,text,text,timestamp with time zone)'
  );
  if procedure_oid is null or fingerprint_oid is null
     or catalog_fingerprint_oid is null or create_approval_oid is null
     or consume_approval_oid is null or begin_effect_oid is null
     or decide_approval_oid is null
     or (select pg_catalog.pg_get_userbyid(proc_row.proowner)<>'postgres'
         or not proc_row.prosecdef
         or proc_row.provolatile<>'v'
         or proc_row.proleakproof
         or proc_row.proretset
         or proc_row.prokind<>'f'
         or language_row.lanname<>'plpgsql'
         or coalesce(proc_row.proconfig::text,'')<>'{"search_path=\"\""}'
       from pg_catalog.pg_proc as proc_row
       join pg_catalog.pg_language as language_row
         on language_row.oid=proc_row.prolang
       where proc_row.oid=procedure_oid)
     or not pg_catalog.has_function_privilege(
       'service_role',procedure_oid,'execute')
     or pg_catalog.has_function_privilege('public',procedure_oid,'execute')
     or pg_catalog.has_function_privilege('anon',procedure_oid,'execute')
     or pg_catalog.has_function_privilege('authenticated',procedure_oid,'execute')
     or (select pg_catalog.count(*)
         from pg_catalog.pg_proc as proc_row
         join pg_catalog.pg_namespace as namespace_row
           on namespace_row.oid=proc_row.pronamespace
         where namespace_row.nspname='public'
           and proc_row.proname=
             'connected_app_consume_approval_and_begin_effect_v1')<>1
     or (select pg_catalog.count(*)
         from pg_catalog.pg_proc as proc_row
         join pg_catalog.pg_namespace as namespace_row
           on namespace_row.oid=proc_row.pronamespace
         where namespace_row.nspname='connected_readiness_private'
           and proc_row.proname in (
             'runtime_readiness_target_fingerprint_v1',
             'runtime_readiness_catalog_fingerprint_v1'))<>2
     or (select pg_catalog.md5(pg_catalog.pg_get_functiondef(proc_row.oid))<>
                  '81801876eb127d22939d77fb2e2fa0e0'
                or pg_catalog.pg_get_userbyid(proc_row.proowner)<>'postgres'
                or not proc_row.prosecdef or proc_row.provolatile<>'s'
                or proc_row.proleakproof or proc_row.proretset
                or proc_row.prokind<>'f' or language_row.lanname<>'sql'
                or coalesce(proc_row.proconfig::text,'')<>
                   '{"search_path=\"\""}'
                or coalesce(proc_row.proacl::text,'')<>
                   '{postgres=X/postgres}'
                or coalesce(pg_catalog.obj_description(
                     proc_row.oid,'pg_proc'),'')<>
                   'ASK_CRUMP_CONNECTED_APPROVAL_EFFECT_TARGET_FINGERPRINT_V1_FULL_STACK'
         from pg_catalog.pg_proc as proc_row
         join pg_catalog.pg_language as language_row
           on language_row.oid=proc_row.prolang
         where proc_row.oid=fingerprint_oid)
     or (select pg_catalog.md5(pg_catalog.pg_get_functiondef(proc_row.oid))<>
                  'b4b16acc52dac4d535742d359bebc632'
                or pg_catalog.pg_get_userbyid(proc_row.proowner)<>'postgres'
                or not proc_row.prosecdef or proc_row.provolatile<>'s'
                or proc_row.proleakproof or proc_row.proretset
                or proc_row.prokind<>'f' or language_row.lanname<>'sql'
                or coalesce(proc_row.proconfig::text,'')<>
                   '{"search_path=\"\""}'
                or coalesce(proc_row.proacl::text,'')<>
                   '{postgres=X/postgres}'
                or coalesce(pg_catalog.obj_description(
                     proc_row.oid,'pg_proc'),'')<>
                   'ASK_CRUMP_CONNECTED_RUNTIME_READINESS_CATALOG_FINGERPRINT_V1_FULL_STACK'
         from pg_catalog.pg_proc as proc_row
         join pg_catalog.pg_language as language_row
           on language_row.oid=proc_row.prolang
         where proc_row.oid=catalog_fingerprint_oid)
     or pg_catalog.has_function_privilege(
       'service_role',fingerprint_oid,'execute')
     or pg_catalog.has_function_privilege(
       'service_role',catalog_fingerprint_oid,'execute') then
    raise exception 'connected approval-effect function authority drifted'
      using errcode='55000',
        detail=pg_catalog.format(
          'target_helper=%s catalog_helper=%s',
          (select pg_catalog.md5(pg_catalog.pg_get_functiondef(proc_row.oid))
           from pg_catalog.pg_proc as proc_row
           where proc_row.oid=fingerprint_oid),
          (select pg_catalog.md5(pg_catalog.pg_get_functiondef(proc_row.oid))
           from pg_catalog.pg_proc as proc_row
           where proc_row.oid=catalog_fingerprint_oid)
        );
  end if;
  if pg_catalog.has_function_privilege(
       'service_role',create_approval_oid,'execute')
     or pg_catalog.has_function_privilege(
       'service_role',consume_approval_oid,'execute')
     or pg_catalog.has_function_privilege(
       'service_role',begin_effect_oid,'execute')
     or pg_catalog.has_function_privilege('public',create_approval_oid,'execute')
     or pg_catalog.has_function_privilege('public',consume_approval_oid,'execute')
     or pg_catalog.has_function_privilege('public',begin_effect_oid,'execute')
     or pg_catalog.has_function_privilege('anon',create_approval_oid,'execute')
     or pg_catalog.has_function_privilege('anon',consume_approval_oid,'execute')
     or pg_catalog.has_function_privilege('anon',begin_effect_oid,'execute')
     or pg_catalog.has_function_privilege(
       'authenticated',create_approval_oid,'execute')
     or pg_catalog.has_function_privilege(
       'authenticated',consume_approval_oid,'execute')
     or pg_catalog.has_function_privilege(
       'authenticated',begin_effect_oid,'execute')
     or not pg_catalog.has_function_privilege(
       'service_role',decide_approval_oid,'execute') then
    raise exception 'connected approval-effect primitive ACL drifted'
      using errcode='55000';
  end if;
  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace as publication_schema
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=publication_schema.pnnspid
       where namespace_row.nspname like 'connected\_%\_private' escape '\')
     or exists(
       select 1 from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row
         on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname like 'connected\_%\_private' escape '\') then
    raise exception 'connected approval-effect publication exposure failed'
      using errcode='55000';
  end if;
  select connected_readiness_private.runtime_readiness_catalog_fingerprint_v1()
    into observed_catalog;
  select connected_readiness_private.runtime_readiness_target_fingerprint_v1()
    into observed_target;
  if observed_catalog is distinct from observed_target
     or observed_target<>'c339945387929ed735b591d967f536dc' then
    raise exception 'connected approval-effect postflight drifted: %, %',
      observed_catalog,observed_target using errcode='55000';
  end if;
end;
$postflight$;

commit;
