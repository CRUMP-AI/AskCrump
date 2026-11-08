\set ON_ERROR_STOP on

begin;

select pg_catalog.set_config('search_path','pg_catalog,public',true);
select pg_catalog.set_config('quote_all_identifiers','off',true);

do $preflight$
declare
  predecessor_fingerprint text;
  target_fingerprint text;
begin
  if pg_catalog.to_regprocedure(
       'connected_retention_private.retention_target_fingerprint_v1()'
     ) is not null then
    select connected_retention_private.retention_target_fingerprint_v1()
      into target_fingerprint;
    if target_fingerprint <> '1578bda68f666f33ded70a8907274663' then
      raise exception 'connected ciphertext-retention target drifted: %',
        target_fingerprint using errcode='55000';
    end if;
    return;
  end if;

  if pg_catalog.to_regprocedure(
       'connected_loop_continuation_private.continuation_target_fingerprint_v1()'
     ) is null then
    raise exception 'connected ciphertext-retention predecessor is absent'
      using errcode='55000';
  end if;
  select connected_loop_continuation_private.continuation_target_fingerprint_v1()
    into predecessor_fingerprint;
  if predecessor_fingerprint <> '1fac1595981f5cd703aaabbc3d13c571' then
    raise exception 'connected ciphertext-retention predecessor drifted: %',
      predecessor_fingerprint using errcode='55000';
  end if;

  if pg_catalog.to_regclass('connected_app_private.payload_envelopes') is null
     or pg_catalog.to_regclass('connected_app_private.payload_tombstones') is null
     or pg_catalog.to_regclass('connected_app_private.read_results') is null
     or pg_catalog.to_regclass('connected_plan_private.operations') is null
     or pg_catalog.to_regclass('connected_plan_private.envelopes') is null
     or pg_catalog.to_regclass('connected_loop_private.loops') is null
     or pg_catalog.to_regclass('connected_loop_private.steps') is null
     or pg_catalog.to_regclass('connected_loop_private.envelopes') is null
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_payload_put_v1(uuid,uuid,uuid,uuid,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,text,text,text,text,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_plan_envelope_read_v1(uuid,uuid,uuid,text,uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_plan_envelope_delete_v1(uuid,uuid,uuid,text,uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_multi_step_put_envelope_v1(uuid,uuid,uuid,uuid,uuid,integer,text,text,text,text,timestamp with time zone,timestamp with time zone,text,text,text,text,text,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_multi_step_read_envelope_v1(uuid,uuid,uuid,uuid)'
     ) is null then
    raise exception 'connected ciphertext-retention predecessor is incomplete'
      using errcode='55000';
  end if;

  if pg_catalog.to_regnamespace('connected_retention_private') is not null
     or exists(
       select 1
       from pg_catalog.pg_proc as procedure
       join pg_catalog.pg_namespace as namespace
         on namespace.oid=procedure.pronamespace
       where namespace.nspname='public'
         and procedure.proname='connected_app_purge_expired_ciphertext_v1'
     ) then
    raise exception 'connected ciphertext-retention target is partial'
      using errcode='55000';
  end if;

  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1
       from pg_catalog.pg_publication_namespace
       where pnnspid in (
         pg_catalog.to_regnamespace('connected_app_private'),
         pg_catalog.to_regnamespace('connected_plan_private'),
         pg_catalog.to_regnamespace('connected_loop_private'),
         pg_catalog.to_regnamespace('connected_retention_private')
       )
     )
     or exists(
       select 1
       from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row
         on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname in (
        'connected_app_private','connected_plan_private','connected_loop_private',
         'connected_retention_private'
       )
     ) then
    raise exception 'connected ciphertext-retention publication exposure refused'
      using errcode='55000';
  end if;
end;
$preflight$;

create schema if not exists connected_retention_private authorization postgres;
comment on schema connected_retention_private is
  'ASK_CRUMP_CONNECTED_CIPHERTEXT_RETENTION_V1_PRIVATE_NO_CONTENT';
revoke all on schema connected_retention_private
  from public,anon,authenticated,service_role;

-- Put and purge now share the canonical owner -> payload advisory -> row order.
-- This prevents account deletion (owner first) from deadlocking an expiry pass.
create or replace function public.connected_app_payload_put_v1(
  p_payload_id uuid,
  p_owner_id uuid,
  p_connection_id uuid,
  p_action_id uuid,
  p_provider text,
  p_action text,
  p_commitment_key_id text,
  p_payload_sha256 text,
  p_created_at timestamptz,
  p_expires_at timestamptz,
  p_identity_sha256 text,
  p_reference_binding_sha256 text,
  p_key_id text,
  p_wrapped_key_nonce text,
  p_wrapped_key_ciphertext text,
  p_payload_nonce text,
  p_payload_ciphertext text,
  p_record_binding_sha256 text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.payload_envelopes%rowtype;
  tombstone connected_app_private.payload_tombstones%rowtype;
  connection_row connected_app_private.connections%rowtype;
begin
  perform connected_app_private.owner_lock_v1(p_owner_id);
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-payload:' || p_payload_id::text, 0)
  );
  select * into tombstone from connected_app_private.payload_tombstones
  where payload_id = p_payload_id;
  if found then
    if tombstone.identity_sha256 <> p_identity_sha256 then
      raise exception 'payload identity mismatch' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
  end if;
  select * into envelope from connected_app_private.payload_envelopes
  where payload_id = p_payload_id for update;
  if found then
    if envelope.identity_sha256 <> p_identity_sha256
       or envelope.owner_id <> p_owner_id then
      raise exception 'payload identity mismatch' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'status', 'present', 'record', pg_catalog.to_jsonb(envelope)
    );
  end if;
  select * into connection_row from connected_app_private.connections
  where owner_id = p_owner_id and id = p_connection_id for update;
  if not found or connection_row.provider <> p_provider
     or connection_row.authorization_state <> 'active'
     or connection_row.authorization_expires_at <= p_created_at
     or not (p_action = any(connection_row.granted_actions))
     or not exists (
       select 1 from connected_app_private.action_authority as authority
       where authority.action = p_action
     ) then
    raise exception 'payload authority mismatch' using errcode = '55000';
  end if;
  insert into connected_app_private.payload_envelopes (
    payload_id, owner_id, connection_id, action_id, provider, action,
    commitment_key_id, payload_sha256, created_at, expires_at,
    identity_sha256, reference_binding_sha256, key_id, wrapped_key_nonce,
    wrapped_key_ciphertext, payload_nonce, payload_ciphertext,
    record_binding_sha256
  ) values (
    p_payload_id, p_owner_id, p_connection_id, p_action_id, p_provider, p_action,
    p_commitment_key_id, p_payload_sha256, p_created_at, p_expires_at,
    p_identity_sha256, p_reference_binding_sha256, p_key_id, p_wrapped_key_nonce,
    p_wrapped_key_ciphertext, p_payload_nonce, p_payload_ciphertext,
    p_record_binding_sha256
  ) returning * into envelope;
  return pg_catalog.jsonb_build_object(
    'status', 'present', 'record', pg_catalog.to_jsonb(envelope)
  );
end;
$fn$;
comment on function public.connected_app_payload_put_v1(
  uuid,uuid,uuid,uuid,text,text,text,text,timestamptz,timestamptz,
  text,text,text,text,text,text,text,text
) is 'ASK_CRUMP_CONNECTED_PAYLOAD_PUT_V1_OWNER_THEN_PAYLOAD_LOCK';

-- Reads share the payload advisory fence with put/delete/purge.  The caller
-- cannot choose an owner, so this deliberately takes no owner lock and cannot
-- invert the canonical owner -> payload order used by mutating paths.
create or replace function public.connected_app_payload_read_v1(
  p_payload_id uuid,
  p_identity_sha256 text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  envelope connected_app_private.payload_envelopes%rowtype;
  tombstone connected_app_private.payload_tombstones%rowtype;
begin
  if p_identity_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid payload identity' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('connected-payload:' || p_payload_id::text, 0)
  );
  select * into tombstone
  from connected_app_private.payload_tombstones
  where payload_id = p_payload_id;
  if found then
    if tombstone.identity_sha256 <> p_identity_sha256 then
      raise exception 'payload identity mismatch' using errcode = '55000';
    end if;
    return pg_catalog.jsonb_build_object('status', 'erased', 'record', null);
  end if;
  select * into envelope
  from connected_app_private.payload_envelopes
  where payload_id = p_payload_id;
  if not found then
    return pg_catalog.jsonb_build_object('status', 'absent', 'record', null);
  end if;
  if envelope.identity_sha256 <> p_identity_sha256 then
    raise exception 'payload identity mismatch' using errcode = '55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'status', 'present', 'record', pg_catalog.to_jsonb(envelope)
  );
end;
$fn$;
comment on function public.connected_app_payload_read_v1(uuid,text)
  is 'ASK_CRUMP_CONNECTED_PAYLOAD_READ_V1_PAYLOAD_LOCKED';

drop function if exists public.connected_app_purge_expired_ciphertext_v1(
  integer,integer
);

create or replace function public.connected_app_purge_expired_ciphertext_v1(
  p_payload_maximum integer,
  p_plan_maximum integer,
  p_loop_maximum integer
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  now_at timestamptz := pg_catalog.clock_timestamp();
  candidate record;
  payload_row connected_app_private.payload_envelopes%rowtype;
  operation_row connected_plan_private.operations%rowtype;
  plan_row connected_plan_private.envelopes%rowtype;
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
  loop_envelope connected_loop_private.envelopes%rowtype;
  affected integer;
  payloads_purged integer := 0;
  plans_purged integer := 0;
  loop_envelopes_purged integer := 0;
begin
  if p_payload_maximum is null or p_plan_maximum is null
     or p_loop_maximum is null
     or p_payload_maximum not between 1 and 100
     or p_plan_maximum not between 1 and 100
     or p_loop_maximum not between 1 and 100 then
    raise exception 'invalid connected ciphertext-retention bounds'
      using errcode='22023';
  end if;

  for candidate in
    select envelope.payload_id,envelope.owner_id
    from connected_app_private.payload_envelopes as envelope
    where envelope.expires_at<=now_at
    order by envelope.expires_at,envelope.payload_id
    limit p_payload_maximum
  loop
    perform connected_app_private.owner_lock_v1(candidate.owner_id);
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(
        'connected-payload:' || candidate.payload_id::text,0
      )
    );
    select envelope.* into payload_row
    from connected_app_private.payload_envelopes as envelope
    where envelope.payload_id=candidate.payload_id
    for update;
    if found and payload_row.owner_id=candidate.owner_id
       and payload_row.expires_at<=now_at then
      delete from connected_app_private.payload_envelopes as envelope
      where envelope.payload_id=candidate.payload_id;
      get diagnostics affected = row_count;
      payloads_purged := payloads_purged + affected;
    end if;
  end loop;

  for candidate in
    select envelope.payload_id,envelope.owner_id,envelope.planning_id
    from connected_plan_private.envelopes as envelope
    where envelope.record_state='live' and envelope.expires_at<=now_at
    order by envelope.expires_at,envelope.payload_id
    limit p_plan_maximum
  loop
    perform connected_app_private.owner_lock_v1(candidate.owner_id);
    select operation.* into operation_row
    from connected_plan_private.operations as operation
    where operation.planning_id=candidate.planning_id
    for update;
    if not found or operation_row.owner_id<>candidate.owner_id
       or operation_row.payload_id<>candidate.payload_id then
      continue;
    end if;
    select envelope.* into plan_row
    from connected_plan_private.envelopes as envelope
    where envelope.payload_id=candidate.payload_id
    for update;
    if found and plan_row.owner_id=candidate.owner_id
       and plan_row.planning_id=candidate.planning_id
       and plan_row.record_state='live' and plan_row.expires_at<=now_at then
      update connected_plan_private.envelopes as envelope
      set record_state='deleted',commitment_key_id=null,payload_sha256=null,
          reference_binding_sha256=null,key_id=null,wrapped_key_nonce=null,
          wrapped_key_ciphertext=null,payload_nonce=null,payload_ciphertext=null,
          record_binding_sha256=null,deleted_at=now_at
      where envelope.payload_id=candidate.payload_id
        and envelope.record_state='live';
      get diagnostics affected = row_count;
      plans_purged := plans_purged + affected;
    end if;
  end loop;

  for candidate in
    select envelope.proposal_id,envelope.owner_id,envelope.loop_id,
           envelope.step_id
    from connected_loop_private.envelopes as envelope
    where envelope.expires_at<=now_at
    order by envelope.expires_at,envelope.proposal_id
    limit p_loop_maximum
  loop
    perform connected_app_private.owner_lock_v1(candidate.owner_id);
    select loop_value.* into loop_row
    from connected_loop_private.loops as loop_value
    where loop_value.loop_id=candidate.loop_id
      and loop_value.owner_id=candidate.owner_id
    for update;
    if not found or loop_row.expires_at>now_at then
      continue;
    end if;
    select step_value.* into step_row
    from connected_loop_private.steps as step_value
    where step_value.loop_id=candidate.loop_id
      and step_value.step_id=candidate.step_id
      and step_value.owner_id=candidate.owner_id
    for update;
    if not found then
      continue;
    end if;
    select envelope.* into loop_envelope
    from connected_loop_private.envelopes as envelope
    where envelope.proposal_id=candidate.proposal_id
    for update;
    if found and loop_envelope.owner_id=candidate.owner_id
       and loop_envelope.loop_id=candidate.loop_id
       and loop_envelope.step_id=candidate.step_id
       and loop_envelope.expires_at<=now_at then
      delete from connected_loop_private.envelopes as envelope
      where envelope.proposal_id=candidate.proposal_id;
      get diagnostics affected = row_count;
      loop_envelopes_purged:=loop_envelopes_purged+affected;
    end if;
  end loop;

  return pg_catalog.jsonb_build_object(
    'payloads_purged',payloads_purged,
    'plans_purged',plans_purged,
    'loop_envelopes_purged',loop_envelopes_purged
  );
end;
$fn$;
comment on function public.connected_app_purge_expired_ciphertext_v1(
  integer,integer,integer
)
  is 'ASK_CRUMP_CONNECTED_CIPHERTEXT_RETENTION_V1_BOUNDED_PHYSICAL_ERASURE';

alter function public.connected_app_payload_put_v1(
  uuid,uuid,uuid,uuid,text,text,text,text,timestamptz,timestamptz,
  text,text,text,text,text,text,text,text
) owner to postgres;
alter function public.connected_app_payload_read_v1(uuid,text) owner to postgres;
alter function public.connected_app_purge_expired_ciphertext_v1(
  integer,integer,integer
)
  owner to postgres;
revoke all on function public.connected_app_payload_put_v1(
  uuid,uuid,uuid,uuid,text,text,text,text,timestamptz,timestamptz,
  text,text,text,text,text,text,text,text
) from public,anon,authenticated;
revoke all on function public.connected_app_payload_read_v1(uuid,text)
  from public,anon,authenticated;
revoke all on function public.connected_app_purge_expired_ciphertext_v1(
  integer,integer,integer
)
  from public,anon,authenticated;
grant execute on function public.connected_app_payload_put_v1(
  uuid,uuid,uuid,uuid,text,text,text,text,timestamptz,timestamptz,
  text,text,text,text,text,text,text,text
) to service_role;
grant execute on function public.connected_app_payload_read_v1(uuid,text)
  to service_role;
grant execute on function public.connected_app_purge_expired_ciphertext_v1(
  integer,integer,integer
)
  to service_role;

create or replace function connected_retention_private.retention_target_fingerprint_v1()
returns text language sql stable security definer set search_path='' as $fingerprint$
  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
  from (
    select pg_catalog.concat_ws('|','schema',namespace_row.nspname,
      pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text,''),coalesce(description.description,''))
      as item
    from pg_catalog.pg_namespace as namespace_row
    left join pg_catalog.pg_description as description
      on description.objoid=namespace_row.oid and description.objsubid=0
    where namespace_row.nspname='connected_retention_private'
    union all
    select pg_catalog.concat_ws('|','relation',namespace_row.nspname,
      class_row.relname,class_row.relkind,class_row.relrowsecurity,
      class_row.relforcerowsecurity,pg_catalog.pg_get_userbyid(class_row.relowner),
      coalesce(class_row.relacl::text,''),coalesce(description.description,''))
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_description as description
      on description.objoid=class_row.oid and description.objsubid=0
    where (namespace_row.nspname,class_row.relname) in (
      ('connected_app_private','payload_envelopes'),
      ('connected_app_private','payload_tombstones'),
      ('connected_app_private','read_results'),
      ('connected_plan_private','operations'),
      ('connected_plan_private','envelopes'),
      ('connected_loop_private','loops'),
      ('connected_loop_private','steps'),
      ('connected_loop_private','envelopes'))
    union all
    select pg_catalog.concat_ws('|','function',
      procedure.oid::pg_catalog.regprocedure::text,
      pg_catalog.pg_get_userbyid(procedure.proowner),procedure.prosecdef,
      procedure.provolatile,coalesce(procedure.proconfig::text,''),
      coalesce(procedure.proacl::text,''),coalesce(description.description,''),
      pg_catalog.md5(pg_catalog.pg_get_functiondef(procedure.oid)))
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=procedure.pronamespace
    left join pg_catalog.pg_description as description
      on description.objoid=procedure.oid and description.objsubid=0
    where (namespace_row.nspname,procedure.proname) in (
      ('connected_app_private','owner_lock_v1'),
      ('connected_app_private','payload_tombstone_before_delete_v1'),
      ('public','connected_app_payload_put_v1'),
      ('public','connected_app_payload_read_v1'),
      ('public','connected_app_payload_reference_get_v1'),
      ('public','connected_app_payload_delete_v1'),
      ('public','connected_app_purge_expired_ciphertext_v1'),
      ('public','connected_plan_envelope_put_v1'),
      ('public','connected_plan_envelope_read_v1'),
      ('public','connected_plan_envelope_delete_v1'),
      ('public','connected_multi_step_put_envelope_v1'),
      ('public','connected_multi_step_read_envelope_v1'))
    union all
    select pg_catalog.concat_ws('|','trigger',namespace_row.nspname,
      class_row.relname,trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid=trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where not trigger_row.tgisinternal
      and (namespace_row.nspname,class_row.relname) in (
        ('connected_app_private','payload_envelopes'),
        ('connected_plan_private','envelopes'),
        ('connected_loop_private','loops'),
        ('connected_loop_private','steps'),
        ('connected_loop_private','envelopes'))
    union all
    select pg_catalog.concat_ws('|','rule',namespace_row.nspname,
      class_row.relname,rule_row.rulename,
      pg_catalog.pg_get_ruledef(rule_row.oid,true))
    from pg_catalog.pg_rewrite as rule_row
    join pg_catalog.pg_class as class_row on class_row.oid=rule_row.ev_class
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where rule_row.rulename<>'_RETURN'
      and (namespace_row.nspname,class_row.relname) in (
        ('connected_app_private','payload_envelopes'),
        ('connected_plan_private','envelopes'),
        ('connected_loop_private','loops'),
        ('connected_loop_private','steps'),
        ('connected_loop_private','envelopes'))
    union all
    select pg_catalog.concat_ws('|','publication',publication_row.pubname,
      publication_row.puballtables,coalesce(namespace_row.nspname,''),
      coalesce(class_row.relname,''))
    from pg_catalog.pg_publication as publication_row
    left join pg_catalog.pg_publication_rel as publication_relation
      on publication_relation.prpubid=publication_row.oid
    left join pg_catalog.pg_class as class_row
      on class_row.oid=publication_relation.prrelid
    left join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where publication_row.puballtables
       or namespace_row.nspname in (
         'connected_app_private','connected_plan_private','connected_loop_private',
         'connected_retention_private')
  ) as manifest(item)
$fingerprint$;
comment on function connected_retention_private.retention_target_fingerprint_v1()
  is 'ASK_CRUMP_CONNECTED_CIPHERTEXT_RETENTION_TARGET_FINGERPRINT_V1';
alter function connected_retention_private.retention_target_fingerprint_v1()
  owner to postgres;
revoke all on function connected_retention_private.retention_target_fingerprint_v1()
  from public,anon,authenticated,service_role;

do $postflight$
declare
  target_fingerprint text;
begin
  select connected_retention_private.retention_target_fingerprint_v1()
    into target_fingerprint;
  if target_fingerprint<>'1578bda68f666f33ded70a8907274663' then
    raise exception 'connected ciphertext-retention postflight drifted: %',
      target_fingerprint using errcode='55000';
  end if;
  if pg_catalog.has_function_privilege(
       'public','public.connected_app_purge_expired_ciphertext_v1(integer,integer,integer)','execute')
     or pg_catalog.has_function_privilege(
       'anon','public.connected_app_purge_expired_ciphertext_v1(integer,integer,integer)','execute')
     or pg_catalog.has_function_privilege(
       'authenticated','public.connected_app_purge_expired_ciphertext_v1(integer,integer,integer)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_purge_expired_ciphertext_v1(integer,integer,integer)','execute')
     or pg_catalog.has_schema_privilege(
       'service_role','connected_retention_private','usage')
     or exists(select 1 from pg_catalog.pg_publication where puballtables) then
    raise exception 'connected ciphertext-retention authority drifted'
      using errcode='55000';
  end if;
end;
$postflight$;

commit;
