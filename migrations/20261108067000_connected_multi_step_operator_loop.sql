\set ON_ERROR_STOP on

begin;

select pg_catalog.set_config('search_path','pg_catalog,public',true);
select pg_catalog.set_config('quote_all_identifiers','off',true);

do $preflight$
declare
  predecessor_fingerprint text;
  existing_target_fingerprint text;
  exact_target boolean := false;
begin
  if pg_catalog.to_regprocedure(
       'connected_loop_private.multi_step_target_fingerprint_v1()'
     ) is not null then
    select connected_loop_private.multi_step_target_fingerprint_v1()
      into existing_target_fingerprint;
    if existing_target_fingerprint <> 'a63bd463531f048bac9024b17d5823c1' then
      raise exception 'connected multi-step existing target drifted: %',
        existing_target_fingerprint using errcode='55000';
    end if;
    exact_target := true;
  else
    if pg_catalog.to_regprocedure(
         'connected_schedule_private.schedule_approval_target_fingerprint_v1()'
       ) is null then
      raise exception 'connected multi-step predecessor is absent'
        using errcode='55000';
    end if;
    select connected_schedule_private.schedule_approval_target_fingerprint_v1()
      into predecessor_fingerprint;
    if predecessor_fingerprint <> 'fd7caa733d4112ade452de4755f39a45' then
      raise exception 'connected multi-step predecessor drifted: %',
        predecessor_fingerprint using errcode='55000';
    end if;
  end if;

  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace
       where pnnspid in (
         pg_catalog.to_regnamespace('connected_app_private'),
         pg_catalog.to_regnamespace('connected_chat_private'),
         pg_catalog.to_regnamespace('connected_loop_private')))
     or exists(
       select 1 from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row
         on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname in (
         'connected_app_private','connected_chat_private','connected_loop_private')) then
    raise exception 'connected multi-step publication exposure refused'
      using errcode='55000';
  end if;

  if not exact_target and (
       pg_catalog.to_regnamespace('connected_loop_private') is not null
       or exists(
         select 1 from pg_catalog.pg_proc as proc_row
         join pg_catalog.pg_namespace as namespace_row
           on namespace_row.oid=proc_row.pronamespace
         where namespace_row.nspname='public'
           and proc_row.proname like 'connected_multi_step_%')) then
    raise exception 'connected multi-step target is partial' using errcode='55000';
  end if;
end;
$preflight$;

create schema if not exists connected_loop_private authorization postgres;
comment on schema connected_loop_private is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_V1_PRIVATE_CONTENT_FREE_CONTROL_AND_CIPHERTEXT';
revoke all on schema connected_loop_private from public,anon,authenticated,service_role;

create table if not exists connected_loop_private.loops (
  loop_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  session_id uuid not null,
  session_binding_sha256 text not null
    check(session_binding_sha256~'^[0-9a-f]{64}$'),
  chat_id uuid not null,
  message_id uuid not null,
  turn_id uuid not null references connected_chat_private.turns(turn_id) on delete cascade,
  turn_claim_token uuid not null,
  time_zone text not null check(length(time_zone) between 1 and 128),
  request_binding_sha256 text not null
    check(request_binding_sha256~'^[0-9a-f]{64}$'),
  status text not null default 'active' check(status in (
    'active','waiting_approval','clarification','completed','failed',
    'cancelled','expired','effect_unknown','limit_reached')),
  current_step integer not null default 0 check(current_step between 0 and 8),
  max_steps integer not null default 8 check(max_steps=8),
  task_state_revision bigint not null default 1 check(task_state_revision>=1),
  pending_approval_id uuid,
  last_result_reference_id uuid,
  last_result_binding_sha256 text
    check(last_result_binding_sha256 is null
      or last_result_binding_sha256~'^[0-9a-f]{64}$'),
  requested_at timestamptz not null,
  expires_at timestamptz not null,
  updated_at timestamptz not null,
  constraint connected_multi_step_loop_time_shape check(
    expires_at>requested_at and expires_at<=requested_at+interval '30 minutes'),
  constraint connected_multi_step_loop_result_shape check(
    (last_result_reference_id is null)=(last_result_binding_sha256 is null)),
  constraint connected_multi_step_loop_approval_shape check(
    (status='waiting_approval' and pending_approval_id is not null)
    or (status<>'waiting_approval' and pending_approval_id is null)),
  unique(owner_id,turn_id),
  unique(owner_id,loop_id),
  unique(owner_id,turn_id,turn_claim_token)
);
comment on table connected_loop_private.loops is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_LOOPS_V1_CONTENT_FREE_MAX_EIGHT';
create index if not exists connected_multi_step_loops_active_idx
  on connected_loop_private.loops(status,expires_at,loop_id)
  where status in ('active','waiting_approval');
create index if not exists connected_multi_step_loops_owner_idx
  on connected_loop_private.loops(owner_id,updated_at desc,loop_id);

create table if not exists connected_loop_private.steps (
  step_id uuid primary key,
  loop_id uuid not null references connected_loop_private.loops(loop_id) on delete cascade,
  owner_id uuid not null references public.users(id) on delete cascade,
  step_index integer not null check(step_index between 0 and 7),
  state text not null check(state in (
    'claimed','invoked','settled','effect_unknown','cancelled')),
  claim_request_id uuid not null,
  claim_token uuid not null,
  planning_binding_sha256 text not null
    check(planning_binding_sha256~'^[0-9a-f]{64}$'),
  lease_expires_at timestamptz not null,
  invocation_id uuid,
  invocation_expires_at timestamptz,
  proposal_id uuid unique,
  proposal_sha256 text check(proposal_sha256 is null
    or proposal_sha256~'^[0-9a-f]{64}$'),
  proposal_binding_sha256 text check(proposal_binding_sha256 is null
    or proposal_binding_sha256~'^[0-9a-f]{64}$'),
  proposal_kind text check(proposal_kind is null
    or proposal_kind in ('complete','clarify','action')),
  connection_id uuid,
  provider text check(provider is null or provider in ('google','microsoft')),
  resource text check(resource is null or resource in ('mail','calendar')),
  action text,
  authorization_revision bigint check(authorization_revision is null
    or authorization_revision>=1),
  authorization_snapshot_sha256 text
    check(authorization_snapshot_sha256 is null
      or authorization_snapshot_sha256~'^[0-9a-f]{64}$'),
  action_id uuid,
  approval_id uuid,
  result_reference_id uuid,
  result_binding_sha256 text check(result_binding_sha256 is null
    or result_binding_sha256~'^[0-9a-f]{64}$'),
  settled_at timestamptz,
  updated_at timestamptz not null,
  constraint connected_multi_step_step_invocation_shape check(
    (invocation_id is null)=(invocation_expires_at is null)),
  constraint connected_multi_step_step_proposal_shape check(
    (proposal_id is null and proposal_sha256 is null
      and proposal_binding_sha256 is null and proposal_kind is null)
    or (proposal_id is not null and proposal_sha256 is not null
      and proposal_binding_sha256 is not null and proposal_kind is not null)),
  constraint connected_multi_step_step_authority_shape check(
    (proposal_kind='action' and connection_id is not null and provider is not null
      and resource is not null and action is not null
      and authorization_revision is not null
      and authorization_snapshot_sha256 is not null)
    or (proposal_kind is distinct from 'action' and connection_id is null
      and provider is null and resource is null and action is null
      and authorization_revision is null
      and authorization_snapshot_sha256 is null)),
  constraint connected_multi_step_step_result_shape check(
    (result_reference_id is null)=(result_binding_sha256 is null)),
  constraint connected_multi_step_step_settled_shape check(
    (state='settled' and settled_at is not null and proposal_id is not null)
    or (state<>'settled' and settled_at is null)),
  unique(loop_id,step_index),
  unique(loop_id,step_id),
  unique(owner_id,step_id),
  unique(loop_id,claim_request_id)
);
comment on table connected_loop_private.steps is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_STEPS_V1_CONTENT_FREE_ONE_MODEL_ONE_ACTION';
create index if not exists connected_multi_step_steps_loop_idx
  on connected_loop_private.steps(loop_id,step_index,step_id);
create index if not exists connected_multi_step_steps_invoked_idx
  on connected_loop_private.steps(invocation_expires_at,step_id)
  where state='invoked' and proposal_id is null;

create table if not exists connected_loop_private.envelopes (
  proposal_id uuid primary key,
  loop_id uuid not null,
  step_id uuid not null,
  owner_id uuid not null,
  turn_id uuid not null,
  step_index integer not null check(step_index between 0 and 7),
  planning_binding_sha256 text not null
    check(planning_binding_sha256~'^[0-9a-f]{64}$'),
  commitment_key_id text not null
    check(commitment_key_id~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'),
  proposal_sha256 text not null check(proposal_sha256~'^[0-9a-f]{64}$'),
  reference_binding_sha256 text not null
    check(reference_binding_sha256~'^[0-9a-f]{64}$'),
  created_at timestamptz not null,
  expires_at timestamptz not null,
  key_id text not null check(key_id~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'),
  wrapped_key_nonce text not null check(length(wrapped_key_nonce) between 16 and 256),
  wrapped_key_ciphertext text not null
    check(length(wrapped_key_ciphertext) between 32 and 2048),
  payload_nonce text not null check(length(payload_nonce) between 16 and 256),
  payload_ciphertext text not null
    check(length(payload_ciphertext) between 32 and 65536),
  record_binding_sha256 text not null
    check(record_binding_sha256~'^[0-9a-f]{64}$'),
  constraint connected_multi_step_envelope_time_shape check(expires_at>created_at),
  constraint connected_multi_step_envelope_step_fk foreign key(loop_id,step_id)
    references connected_loop_private.steps(loop_id,step_id) on delete cascade,
  constraint connected_multi_step_envelope_owner_fk foreign key(owner_id,step_id)
    references connected_loop_private.steps(owner_id,step_id) on delete cascade,
  unique(loop_id,step_id),
  unique(owner_id,proposal_id),
  unique(reference_binding_sha256),
  unique(record_binding_sha256)
);
comment on table connected_loop_private.envelopes is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_ENVELOPES_V1_ENCRYPTED_PROPOSALS_ONLY';

alter table connected_loop_private.loops enable row level security;
alter table connected_loop_private.loops force row level security;
alter table connected_loop_private.steps enable row level security;
alter table connected_loop_private.steps force row level security;
alter table connected_loop_private.envelopes enable row level security;
alter table connected_loop_private.envelopes force row level security;

create or replace function connected_loop_private.loop_view_v1(
  p_owner_id uuid,p_loop_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'loop_id',loop_row.loop_id,'owner_id',loop_row.owner_id,
    'session_id',loop_row.session_id,
    'session_binding_sha256',loop_row.session_binding_sha256,
    'chat_id',loop_row.chat_id,'message_id',loop_row.message_id,
    'turn_id',loop_row.turn_id,'turn_claim_token',loop_row.turn_claim_token,
    'time_zone',loop_row.time_zone,
    'request_binding_sha256',loop_row.request_binding_sha256,
    'status',loop_row.status,'current_step',loop_row.current_step,
    'max_steps',loop_row.max_steps,
    'task_state_revision',loop_row.task_state_revision,
    'pending_approval_id',loop_row.pending_approval_id,
    'last_result_reference_id',loop_row.last_result_reference_id,
    'last_result_binding_sha256',loop_row.last_result_binding_sha256,
    'expires_at',loop_row.expires_at,'updated_at',loop_row.updated_at)
  from connected_loop_private.loops as loop_row
  where loop_row.owner_id=p_owner_id and loop_row.loop_id=p_loop_id
$fn$;
comment on function connected_loop_private.loop_view_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_LOOP_VIEW_V1_CONTENT_FREE';

create or replace function connected_loop_private.loop_public_view_v1(
  p_owner_id uuid,p_loop_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'loop_id',loop_row.loop_id,'chat_id',loop_row.chat_id,
    'turn_id',loop_row.turn_id,'status',loop_row.status,
    'current_step',loop_row.current_step,'max_steps',loop_row.max_steps,
    'task_state_revision',loop_row.task_state_revision,
    'pending_approval_id',loop_row.pending_approval_id,
    'last_result_reference_id',loop_row.last_result_reference_id,
    'expires_at',loop_row.expires_at,'updated_at',loop_row.updated_at)
  from connected_loop_private.loops as loop_row
  where loop_row.owner_id=p_owner_id and loop_row.loop_id=p_loop_id
$fn$;
comment on function connected_loop_private.loop_public_view_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_PUBLIC_VIEW_V1_OWNER_SCOPED_CONTENT_FREE';

create or replace function connected_loop_private.step_view_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid,p_invoke_permitted boolean
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select case when step_row.state='settled' then pg_catalog.jsonb_build_object(
    'kind','settlement','loop',connected_loop_private.loop_view_v1(p_owner_id,p_loop_id),
    'step_id',step_row.step_id,'step_index',step_row.step_index,
    'proposal_id',step_row.proposal_id,'proposal_sha256',step_row.proposal_sha256,
    'proposal_binding_sha256',step_row.proposal_binding_sha256,
    'action_id',step_row.action_id,'approval_id',step_row.approval_id,
    'result_reference_id',step_row.result_reference_id,
    'result_binding_sha256',step_row.result_binding_sha256)
  else pg_catalog.jsonb_build_object(
    'kind','claim','loop',connected_loop_private.loop_view_v1(p_owner_id,p_loop_id),
    'step_id',step_row.step_id,'step_index',step_row.step_index,
    'state',step_row.state,'claim_request_id',step_row.claim_request_id,
    'claim_token',step_row.claim_token,
    'planning_binding_sha256',step_row.planning_binding_sha256,
    'lease_expires_at',step_row.lease_expires_at,
    'invocation_id',step_row.invocation_id,
    'invocation_expires_at',step_row.invocation_expires_at,
    'proposal_id',step_row.proposal_id,'proposal_sha256',step_row.proposal_sha256,
    'proposal_binding_sha256',step_row.proposal_binding_sha256,
    'proposal_kind',step_row.proposal_kind,'connection_id',step_row.connection_id,
    'provider',step_row.provider,'resource',step_row.resource,'action',step_row.action,
    'authorization_revision',step_row.authorization_revision,
    'authorization_snapshot_sha256',step_row.authorization_snapshot_sha256,
    'invoke_permitted',p_invoke_permitted)
  end
  from connected_loop_private.steps as step_row
  where step_row.owner_id=p_owner_id and step_row.loop_id=p_loop_id
    and step_row.step_id=p_step_id
$fn$;
comment on function connected_loop_private.step_view_v1(uuid,uuid,uuid,boolean) is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_STEP_VIEW_V1_CONTENT_FREE';

create or replace function connected_loop_private.envelope_view_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid,p_proposal_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'proposal_id',envelope.proposal_id,'loop_id',envelope.loop_id,
    'step_id',envelope.step_id,'owner_id',envelope.owner_id,
    'turn_id',envelope.turn_id,'step_index',envelope.step_index,
    'planning_binding_sha256',envelope.planning_binding_sha256,
    'commitment_key_id',envelope.commitment_key_id,
    'proposal_sha256',envelope.proposal_sha256,
    'reference_binding_sha256',envelope.reference_binding_sha256,
    'created_at',envelope.created_at,'expires_at',envelope.expires_at,
    'key_id',envelope.key_id,'wrapped_key_nonce',envelope.wrapped_key_nonce,
    'wrapped_key_ciphertext',envelope.wrapped_key_ciphertext,
    'payload_nonce',envelope.payload_nonce,
    'payload_ciphertext',envelope.payload_ciphertext,
    'record_binding_sha256',envelope.record_binding_sha256)
  from connected_loop_private.envelopes as envelope
  where envelope.owner_id=p_owner_id and envelope.loop_id=p_loop_id
    and envelope.step_id=p_step_id and envelope.proposal_id=p_proposal_id
$fn$;
comment on function connected_loop_private.envelope_view_v1(uuid,uuid,uuid,uuid) is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_ENVELOPE_VIEW_V1_CIPHERTEXT_ONLY';

create or replace function public.connected_multi_step_start_v1(
  p_loop_id uuid,p_owner_id uuid,p_session_id uuid,
  p_session_binding_sha256 text,p_chat_id uuid,p_message_id uuid,
  p_turn_id uuid,p_turn_claim_token uuid,p_time_zone text,
  p_request_binding_sha256 text,p_requested_at timestamptz,
  p_expires_at timestamptz,p_max_steps integer
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  session_row public.sessions%rowtype;
  job_row public.chat_jobs%rowtype;
  turn_row connected_chat_private.turns%rowtype;
  loop_row connected_loop_private.loops%rowtype;
begin
  if p_loop_id is null or p_owner_id is null or p_session_id is null
     or p_chat_id is null or p_message_id is null or p_turn_id is null
     or p_turn_claim_token is null or p_max_steps<>8
     or p_session_binding_sha256!~'^[0-9a-f]{64}$'
     or p_request_binding_sha256!~'^[0-9a-f]{64}$'
     or p_time_zone is null or length(p_time_zone) not between 1 and 128
     or not exists(select 1 from pg_catalog.pg_timezone_names
       where name=p_time_zone)
     or p_requested_at<now_at-interval '5 minutes'
     or p_requested_at>now_at+interval '1 minute'
     or p_expires_at<=now_at or p_expires_at<=p_requested_at
     or p_expires_at>p_requested_at+interval '30 minutes' then
    raise exception 'invalid connected multi-step start binding' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select session.* into session_row from public.sessions as session
  where session.id=p_session_id and session.user_id=p_owner_id for share;
  if not found or session_row.revoked_at is not null or session_row.expires_at<=now_at
     or session_row.expires_at<p_expires_at then
    raise exception 'connected multi-step session authority changed'
      using errcode='55000';
  end if;
  select job.* into job_row from public.chat_jobs as job
  where job.user_id=p_owner_id and job.message_id=p_message_id for update;
  if not found or job_row.chat_id<>p_chat_id or job_row.status<>'processing'
     or job_row.claim_token<>p_turn_claim_token then
    raise exception 'connected multi-step chat claim changed' using errcode='55000';
  end if;
  select turn.* into turn_row from connected_chat_private.turns as turn
  where turn.turn_id=p_turn_id and turn.job_id=job_row.id for update;
  if not found or turn_row.owner_id<>p_owner_id or turn_row.chat_id<>p_chat_id
     or turn_row.message_id<>p_message_id
     or turn_row.origin_session_binding_sha256<>p_session_binding_sha256
     or turn_row.request_binding_sha256<>p_request_binding_sha256 then
    raise exception 'connected multi-step turn binding changed' using errcode='55000';
  end if;
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.loop_id=p_loop_id or (
    loop_value.owner_id=p_owner_id and loop_value.turn_id=p_turn_id) for update;
  if found then
    if loop_row.loop_id<>p_loop_id or loop_row.owner_id<>p_owner_id
       or loop_row.session_id<>p_session_id
       or loop_row.session_binding_sha256<>p_session_binding_sha256
       or loop_row.chat_id<>p_chat_id or loop_row.message_id<>p_message_id
       or loop_row.turn_id<>p_turn_id
       or loop_row.turn_claim_token<>p_turn_claim_token
       or loop_row.time_zone<>p_time_zone
       or loop_row.request_binding_sha256<>p_request_binding_sha256
       or loop_row.requested_at<>p_requested_at or loop_row.expires_at<>p_expires_at
       or loop_row.max_steps<>p_max_steps
       or turn_row.planning_id is distinct from p_loop_id
       or turn_row.planning_binding_sha256 is distinct from p_request_binding_sha256 then
      raise exception 'connected multi-step start replay drifted' using errcode='55000';
    end if;
    return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
  end if;
  if turn_row.stage<>'claimed' or turn_row.planning_id is not null
     or turn_row.planning_binding_sha256 is not null then
    raise exception 'connected multi-step turn is unavailable' using errcode='55000';
  end if;
  insert into connected_loop_private.loops(
    loop_id,owner_id,session_id,session_binding_sha256,chat_id,message_id,
    turn_id,turn_claim_token,time_zone,request_binding_sha256,status,
    current_step,max_steps,task_state_revision,requested_at,expires_at,updated_at)
  values(p_loop_id,p_owner_id,p_session_id,p_session_binding_sha256,p_chat_id,
    p_message_id,p_turn_id,p_turn_claim_token,p_time_zone,p_request_binding_sha256,
    'active',0,8,1,p_requested_at,p_expires_at,now_at);
  update connected_chat_private.turns as turn set stage='planning',
    planning_id=p_loop_id,planning_binding_sha256=p_request_binding_sha256,
    updated_at=now_at
  where turn.turn_id=p_turn_id and turn.stage='claimed'
    and turn.planning_id is null and turn.planning_binding_sha256 is null;
  if not found then
    raise exception 'connected multi-step lost its turn fence' using errcode='55000';
  end if;
  return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
end;
$fn$;
comment on function public.connected_multi_step_start_v1(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,timestamptz,timestamptz,integer
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_START_V1_EXACT_AUTHENTICATED_TURN';

create or replace function public.connected_multi_step_read_loop_v1(
  p_owner_id uuid,p_loop_id uuid
) returns jsonb language plpgsql security definer set search_path='' as $fn$
begin
  if p_owner_id is null or p_loop_id is null then
    raise exception 'invalid connected multi-step read key' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
end;
$fn$;
comment on function public.connected_multi_step_read_loop_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_READ_LOOP_V1_CONTENT_FREE';

create or replace function public.connected_multi_step_list_v1(
  p_owner_id uuid,p_limit integer
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  result jsonb;
begin
  if p_owner_id is null or p_limit not between 1 and 100 then
    raise exception 'invalid connected multi-step list key' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select coalesce(pg_catalog.jsonb_agg(
      connected_loop_private.loop_public_view_v1(p_owner_id,ordered_loop.loop_id)
      order by ordered_loop.updated_at desc,ordered_loop.loop_id),
    '[]'::pg_catalog.jsonb)
  into result
  from (
    select loop_row.loop_id,loop_row.updated_at
    from connected_loop_private.loops as loop_row
    where loop_row.owner_id=p_owner_id
    order by loop_row.updated_at desc,loop_row.loop_id
    limit p_limit
  ) as ordered_loop;
  return result;
end;
$fn$;
comment on function public.connected_multi_step_list_v1(uuid,integer) is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_LIST_V1_OWNER_SCOPED_CONTENT_FREE';

create or replace function public.connected_multi_step_owner_status_v1(
  p_owner_id uuid,p_loop_id uuid
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare loop_row connected_loop_private.loops%rowtype;
begin
  if p_owner_id is null or p_loop_id is null then
    raise exception 'invalid connected multi-step owner status key'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select item.* into loop_row from connected_loop_private.loops as item
  where item.owner_id=p_owner_id and item.loop_id=p_loop_id for share;
  if not found then
    return null;
  end if;
  return connected_loop_private.loop_public_view_v1(p_owner_id,p_loop_id);
end;
$fn$;
comment on function public.connected_multi_step_owner_status_v1(uuid,uuid) is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_OWNER_STATUS_V1_SAFE_PUBLIC_PROJECTION';

create or replace function public.connected_multi_step_cancel_owner_v1(
  p_owner_id uuid,p_loop_id uuid,p_expected_revision bigint,p_now timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
begin
  if p_owner_id is null or p_loop_id is null or p_expected_revision<1
     or p_now<now_at-interval '1 minute' or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step owner cancel key'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select item.* into loop_row from connected_loop_private.loops as item
  where item.owner_id=p_owner_id and item.loop_id=p_loop_id for update;
  if not found then
    raise exception 'connected multi-step owner cancel loop is absent'
      using errcode='55000';
  end if;
  if loop_row.status='cancelled' then
    if loop_row.task_state_revision not in (
      p_expected_revision,p_expected_revision+1) then
      raise exception 'connected multi-step owner cancel replay drifted'
        using errcode='55000';
    end if;
    return connected_loop_private.loop_public_view_v1(p_owner_id,p_loop_id);
  end if;
  if loop_row.status not in ('active','waiting_approval')
     or loop_row.task_state_revision<>p_expected_revision then
    raise exception 'connected multi-step owner cancel revision changed'
      using errcode='55000';
  end if;
  update connected_loop_private.loops set status='cancelled',
    task_state_revision=task_state_revision+1,pending_approval_id=null,
    updated_at=now_at
  where owner_id=p_owner_id and loop_id=p_loop_id
    and task_state_revision=p_expected_revision
    and status in ('active','waiting_approval');
  if not found then
    raise exception 'connected multi-step owner cancel lost revision fence'
      using errcode='55000';
  end if;
  update connected_loop_private.steps set state='cancelled',updated_at=now_at
  where owner_id=p_owner_id and loop_id=p_loop_id
    and state in ('claimed','invoked');
  return connected_loop_private.loop_public_view_v1(p_owner_id,p_loop_id);
end;
$fn$;
comment on function public.connected_multi_step_cancel_owner_v1(
  uuid,uuid,bigint,timestamptz
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CANCEL_OWNER_V1_EXACT_REVISION_SAFE_PROJECTION';

create or replace function public.connected_multi_step_claim_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid,p_expected_revision bigint,
  p_claim_request_id uuid,p_claim_token uuid,p_planning_binding_sha256 text,
  p_now timestamptz,p_lease_seconds integer
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
begin
  if p_owner_id is null or p_loop_id is null or p_step_id is null
     or p_claim_request_id is null or p_claim_token is null
     or p_expected_revision<1
     or p_planning_binding_sha256!~'^[0-9a-f]{64}$'
     or p_lease_seconds not between 5 and 120
     or p_now<now_at-interval '1 minute' or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step claim' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for update;
  if not found then
    raise exception 'connected multi-step loop is absent' using errcode='55000';
  end if;
  select step_value.* into step_row from connected_loop_private.steps as step_value
  where step_value.loop_id=p_loop_id and (
    step_value.step_id=p_step_id or step_value.step_index=loop_row.current_step
    or step_value.claim_request_id=p_claim_request_id) for update;
  if found then
    if step_row.step_id<>p_step_id or step_row.owner_id<>p_owner_id
       or step_row.step_index<>loop_row.current_step
       or step_row.claim_request_id<>p_claim_request_id
       or step_row.claim_token<>p_claim_token
       or step_row.planning_binding_sha256<>p_planning_binding_sha256 then
      raise exception 'connected multi-step claim replay drifted' using errcode='55000';
    end if;
    return connected_loop_private.step_view_v1(
      p_owner_id,p_loop_id,p_step_id,false);
  end if;
  if loop_row.status<>'active' or loop_row.expires_at<=now_at
     or loop_row.current_step>=loop_row.max_steps
     or loop_row.task_state_revision<>p_expected_revision then
    raise exception 'connected multi-step claim fence changed' using errcode='55000';
  end if;
  update connected_loop_private.loops as loop_value
  set task_state_revision=task_state_revision+1,updated_at=now_at
  where loop_value.loop_id=p_loop_id and loop_value.owner_id=p_owner_id
    and loop_value.task_state_revision=p_expected_revision and loop_value.status='active';
  if not found then
    raise exception 'connected multi-step claim lost revision fence' using errcode='55000';
  end if;
  insert into connected_loop_private.steps(
    step_id,loop_id,owner_id,step_index,state,claim_request_id,claim_token,
    planning_binding_sha256,lease_expires_at,updated_at)
  values(p_step_id,p_loop_id,p_owner_id,loop_row.current_step,'claimed',
    p_claim_request_id,p_claim_token,p_planning_binding_sha256,
    now_at+pg_catalog.make_interval(secs=>p_lease_seconds),now_at);
  return connected_loop_private.step_view_v1(p_owner_id,p_loop_id,p_step_id,false);
end;
$fn$;
comment on function public.connected_multi_step_claim_v1(
  uuid,uuid,uuid,bigint,uuid,uuid,text,timestamptz,integer
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CLAIM_V1_OWNER_SERIAL_EXACTLY_ONE';

create or replace function public.connected_multi_step_mark_invoked_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid,p_step_index integer,
  p_expected_revision bigint,p_claim_request_id uuid,p_claim_token uuid,
  p_planning_binding_sha256 text,p_invocation_id uuid,p_now timestamptz,
  p_invocation_seconds integer
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
begin
  if p_owner_id is null or p_loop_id is null or p_step_id is null
     or p_step_index not between 0 and 7 or p_expected_revision<1
     or p_claim_request_id is null or p_claim_token is null or p_invocation_id is null
     or p_planning_binding_sha256!~'^[0-9a-f]{64}$'
     or p_invocation_seconds not between 5 and 120
     or p_now<now_at-interval '1 minute' or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step invocation' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for update;
  select step_value.* into step_row from connected_loop_private.steps as step_value
  where step_value.owner_id=p_owner_id and step_value.loop_id=p_loop_id
    and step_value.step_id=p_step_id for update;
  if not found or loop_row.status<>'active' or loop_row.expires_at<=now_at
     or step_row.step_index<>p_step_index
     or step_row.claim_request_id<>p_claim_request_id
     or step_row.claim_token<>p_claim_token
     or step_row.planning_binding_sha256<>p_planning_binding_sha256 then
    raise exception 'connected multi-step invocation binding changed'
      using errcode='55000';
  end if;
  if step_row.state='invoked' then
    if step_row.invocation_id<>p_invocation_id
       or step_row.invocation_expires_at<=now_at then
      raise exception 'connected multi-step invocation is unavailable'
        using errcode='55000';
    end if;
    return connected_loop_private.step_view_v1(
      p_owner_id,p_loop_id,p_step_id,true);
  end if;
  if step_row.state<>'claimed' or loop_row.task_state_revision<>p_expected_revision then
    raise exception 'connected multi-step invocation fence changed' using errcode='55000';
  end if;
  update connected_loop_private.loops set
    task_state_revision=task_state_revision+1,updated_at=now_at
  where loop_id=p_loop_id and owner_id=p_owner_id
    and task_state_revision=p_expected_revision and status='active';
  if not found then
    raise exception 'connected multi-step invocation lost revision fence'
      using errcode='55000';
  end if;
  update connected_loop_private.steps set state='invoked',
    invocation_id=p_invocation_id,
    invocation_expires_at=now_at+pg_catalog.make_interval(secs=>p_invocation_seconds),
    updated_at=now_at
  where step_id=p_step_id and state='claimed';
  if not found then
    raise exception 'connected multi-step invocation lost step fence'
      using errcode='55000';
  end if;
  return connected_loop_private.step_view_v1(p_owner_id,p_loop_id,p_step_id,true);
end;
$fn$;
comment on function public.connected_multi_step_mark_invoked_v1(
  uuid,uuid,uuid,integer,bigint,uuid,uuid,text,uuid,timestamptz,integer
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_MARK_INVOKED_V1_EXACT_RESPONSE_LOSS_RECOVERY';

create or replace function public.connected_multi_step_put_envelope_v1(
  p_proposal_id uuid,p_loop_id uuid,p_step_id uuid,p_owner_id uuid,
  p_turn_id uuid,p_step_index integer,p_planning_binding_sha256 text,
  p_commitment_key_id text,p_proposal_sha256 text,
  p_reference_binding_sha256 text,p_created_at timestamptz,
  p_expires_at timestamptz,p_key_id text,p_wrapped_key_nonce text,
  p_wrapped_key_ciphertext text,p_payload_nonce text,p_payload_ciphertext text,
  p_record_binding_sha256 text
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
  envelope_row connected_loop_private.envelopes%rowtype;
begin
  if p_proposal_id is null or p_loop_id is null or p_step_id is null
     or p_owner_id is null or p_turn_id is null
     or p_step_index not between 0 and 7
     or p_planning_binding_sha256!~'^[0-9a-f]{64}$'
     or p_commitment_key_id!~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'
     or p_proposal_sha256!~'^[0-9a-f]{64}$'
     or p_reference_binding_sha256!~'^[0-9a-f]{64}$'
     or p_key_id!~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'
     or length(p_wrapped_key_nonce) not between 16 and 256
     or length(p_wrapped_key_ciphertext) not between 32 and 2048
     or length(p_payload_nonce) not between 16 and 256
     or length(p_payload_ciphertext) not between 32 and 65536
     or p_record_binding_sha256!~'^[0-9a-f]{64}$'
     or p_created_at<now_at-interval '1 minute'
     or p_created_at>now_at+interval '1 minute'
     or p_expires_at<=now_at or p_expires_at<=p_created_at then
    raise exception 'invalid connected multi-step encrypted envelope'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for share;
  select step_value.* into step_row from connected_loop_private.steps as step_value
  where step_value.owner_id=p_owner_id and step_value.loop_id=p_loop_id
    and step_value.step_id=p_step_id for update;
  if loop_row.loop_id is null or not found or loop_row.turn_id<>p_turn_id
     or loop_row.status<>'active' or loop_row.expires_at<=now_at
     or p_expires_at<>loop_row.expires_at
     or step_row.step_index<>p_step_index or step_row.state<>'invoked'
     or step_row.planning_binding_sha256<>p_planning_binding_sha256
     or step_row.proposal_id is not null then
    raise exception 'connected multi-step envelope binding changed'
      using errcode='55000';
  end if;
  select envelope.* into envelope_row
  from connected_loop_private.envelopes as envelope
  where envelope.proposal_id=p_proposal_id or envelope.step_id=p_step_id
    or envelope.reference_binding_sha256=p_reference_binding_sha256
    or envelope.record_binding_sha256=p_record_binding_sha256
  for update;
  if found then
    if envelope_row.proposal_id<>p_proposal_id or envelope_row.loop_id<>p_loop_id
       or envelope_row.step_id<>p_step_id or envelope_row.owner_id<>p_owner_id
       or envelope_row.turn_id<>p_turn_id or envelope_row.step_index<>p_step_index
       or envelope_row.planning_binding_sha256<>p_planning_binding_sha256
       or envelope_row.commitment_key_id<>p_commitment_key_id
       or envelope_row.proposal_sha256<>p_proposal_sha256
       or envelope_row.reference_binding_sha256<>p_reference_binding_sha256
       or envelope_row.created_at<>p_created_at or envelope_row.expires_at<>p_expires_at
       or envelope_row.key_id<>p_key_id
       or envelope_row.wrapped_key_nonce<>p_wrapped_key_nonce
       or envelope_row.wrapped_key_ciphertext<>p_wrapped_key_ciphertext
       or envelope_row.payload_nonce<>p_payload_nonce
       or envelope_row.payload_ciphertext<>p_payload_ciphertext
       or envelope_row.record_binding_sha256<>p_record_binding_sha256 then
      raise exception 'connected multi-step envelope replay drifted'
        using errcode='55000';
    end if;
    return connected_loop_private.envelope_view_v1(
      p_owner_id,p_loop_id,p_step_id,p_proposal_id);
  end if;
  insert into connected_loop_private.envelopes(
    proposal_id,loop_id,step_id,owner_id,turn_id,step_index,
    planning_binding_sha256,commitment_key_id,proposal_sha256,
    reference_binding_sha256,created_at,expires_at,key_id,wrapped_key_nonce,
    wrapped_key_ciphertext,payload_nonce,payload_ciphertext,record_binding_sha256)
  values(p_proposal_id,p_loop_id,p_step_id,p_owner_id,p_turn_id,p_step_index,
    p_planning_binding_sha256,p_commitment_key_id,p_proposal_sha256,
    p_reference_binding_sha256,p_created_at,p_expires_at,p_key_id,
    p_wrapped_key_nonce,p_wrapped_key_ciphertext,p_payload_nonce,
    p_payload_ciphertext,p_record_binding_sha256);
  return connected_loop_private.envelope_view_v1(
    p_owner_id,p_loop_id,p_step_id,p_proposal_id);
end;
$fn$;
comment on function public.connected_multi_step_put_envelope_v1(
  uuid,uuid,uuid,uuid,uuid,integer,text,text,text,text,timestamptz,timestamptz,
  text,text,text,text,text,text
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_PUT_ENVELOPE_V1_CIPHERTEXT_EXACT_REPLAY';

create or replace function public.connected_multi_step_read_envelope_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid,p_proposal_id uuid
) returns jsonb language plpgsql security definer set search_path='' as $fn$
begin
  if p_owner_id is null or p_loop_id is null or p_step_id is null
     or p_proposal_id is null then
    raise exception 'invalid connected multi-step envelope read key'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  return connected_loop_private.envelope_view_v1(
    p_owner_id,p_loop_id,p_step_id,p_proposal_id);
end;
$fn$;
comment on function public.connected_multi_step_read_envelope_v1(
  uuid,uuid,uuid,uuid
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_READ_ENVELOPE_V1_CIPHERTEXT_ONLY';

create or replace function public.connected_multi_step_attach_proposal_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid,p_step_index integer,
  p_expected_revision bigint,p_claim_request_id uuid,p_claim_token uuid,
  p_planning_binding_sha256 text,p_invocation_id uuid,p_proposal_id uuid,
  p_proposal_sha256 text,p_proposal_binding_sha256 text,p_proposal_kind text,
  p_connection_id uuid,p_provider text,p_resource text,p_action text,
  p_authorization_revision bigint,p_authorization_snapshot_sha256 text,
  p_now timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
  envelope_row connected_loop_private.envelopes%rowtype;
  connection_row connected_app_private.connections%rowtype;
  authority_row connected_app_private.action_authority%rowtype;
begin
  if p_owner_id is null or p_loop_id is null or p_step_id is null
     or p_step_index not between 0 and 7 or p_expected_revision<1
     or p_claim_request_id is null or p_claim_token is null
     or p_invocation_id is null or p_proposal_id is null
     or p_planning_binding_sha256!~'^[0-9a-f]{64}$'
     or p_proposal_sha256!~'^[0-9a-f]{64}$'
     or p_proposal_binding_sha256!~'^[0-9a-f]{64}$'
     or p_proposal_kind not in ('complete','clarify','action')
     or p_now<now_at-interval '1 minute' or p_now>now_at+interval '1 minute'
     or ((p_proposal_kind='action')<>(p_connection_id is not null
       and p_provider is not null and p_resource is not null and p_action is not null
       and p_authorization_revision is not null
       and p_authorization_snapshot_sha256 is not null))
     or (p_authorization_snapshot_sha256 is not null
       and p_authorization_snapshot_sha256!~'^[0-9a-f]{64}$') then
    raise exception 'invalid connected multi-step proposal attachment'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for update;
  select step_value.* into step_row from connected_loop_private.steps as step_value
  where step_value.owner_id=p_owner_id and step_value.loop_id=p_loop_id
    and step_value.step_id=p_step_id for update;
  if loop_row.loop_id is null or not found or loop_row.status<>'active'
     or loop_row.expires_at<=now_at or step_row.step_index<>p_step_index
     or step_row.claim_request_id<>p_claim_request_id
     or step_row.claim_token<>p_claim_token
     or step_row.planning_binding_sha256<>p_planning_binding_sha256
     or step_row.invocation_id<>p_invocation_id then
    raise exception 'connected multi-step proposal attachment binding changed'
      using errcode='55000';
  end if;
  if step_row.proposal_id is not null then
    if step_row.proposal_id<>p_proposal_id
       or step_row.proposal_sha256<>p_proposal_sha256
       or step_row.proposal_binding_sha256<>p_proposal_binding_sha256
       or step_row.proposal_kind<>p_proposal_kind
       or step_row.connection_id is distinct from p_connection_id
       or step_row.provider is distinct from p_provider
       or step_row.resource is distinct from p_resource
       or step_row.action is distinct from p_action
       or step_row.authorization_revision is distinct from p_authorization_revision
       or step_row.authorization_snapshot_sha256
          is distinct from p_authorization_snapshot_sha256 then
      raise exception 'connected multi-step proposal attachment replay drifted'
        using errcode='55000';
    end if;
    return connected_loop_private.step_view_v1(
      p_owner_id,p_loop_id,p_step_id,false);
  end if;
  if step_row.state<>'invoked' or step_row.invocation_expires_at<=now_at
     or loop_row.task_state_revision<>p_expected_revision then
    raise exception 'connected multi-step proposal attachment fence changed'
      using errcode='55000';
  end if;
  select envelope.* into envelope_row from connected_loop_private.envelopes as envelope
  where envelope.proposal_id=p_proposal_id and envelope.loop_id=p_loop_id
    and envelope.step_id=p_step_id and envelope.owner_id=p_owner_id for share;
  if not found or envelope_row.step_index<>p_step_index
     or envelope_row.planning_binding_sha256<>p_planning_binding_sha256
     or envelope_row.proposal_sha256<>p_proposal_sha256
     or envelope_row.reference_binding_sha256<>p_proposal_binding_sha256
     or envelope_row.expires_at<>loop_row.expires_at then
    raise exception 'connected multi-step encrypted proposal is absent or drifted'
      using errcode='55000';
  end if;
  if p_proposal_kind='action' then
    select connection.* into connection_row from connected_app_private.connections as connection
    where connection.owner_id=p_owner_id and connection.id=p_connection_id for update;
    select authority.* into authority_row from connected_app_private.action_authority as authority
    where authority.action=p_action;
    if connection_row.id is null or authority_row.action is null
       or connection_row.authorization_state<>'active'
       or connection_row.provider<>p_provider or connection_row.resource<>p_resource
       or connection_row.authorization_revision<>p_authorization_revision
       or connection_row.authorization_snapshot_sha256<>p_authorization_snapshot_sha256
       or connection_row.authorization_expires_at is null
       or connection_row.authorization_expires_at<=now_at
       or not (p_action=any(connection_row.granted_actions))
       or authority_row.resource<>p_resource then
      raise exception 'connected multi-step proposal cannot grant authority'
        using errcode='55000';
    end if;
  end if;
  update connected_loop_private.loops set
    task_state_revision=task_state_revision+1,updated_at=now_at
  where loop_id=p_loop_id and owner_id=p_owner_id
    and task_state_revision=p_expected_revision and status='active';
  if not found then
    raise exception 'connected multi-step proposal lost revision fence'
      using errcode='55000';
  end if;
  update connected_loop_private.steps set proposal_id=p_proposal_id,
    proposal_sha256=p_proposal_sha256,
    proposal_binding_sha256=p_proposal_binding_sha256,
    proposal_kind=p_proposal_kind,connection_id=p_connection_id,
    provider=p_provider,resource=p_resource,action=p_action,
    authorization_revision=p_authorization_revision,
    authorization_snapshot_sha256=p_authorization_snapshot_sha256,
    updated_at=now_at
  where step_id=p_step_id and proposal_id is null and state='invoked';
  if not found then
    raise exception 'connected multi-step proposal lost step fence'
      using errcode='55000';
  end if;
  return connected_loop_private.step_view_v1(p_owner_id,p_loop_id,p_step_id,false);
end;
$fn$;
comment on function public.connected_multi_step_attach_proposal_v1(
  uuid,uuid,uuid,integer,bigint,uuid,uuid,text,uuid,uuid,text,text,text,
  uuid,text,text,text,bigint,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_ATTACH_PROPOSAL_V1_NO_MODEL_AUTHORITY';

create or replace function public.connected_multi_step_prepare_action_v1(
  p_owner_id uuid,p_session_id uuid,p_chat_id uuid,p_message_id uuid,
  p_turn_id uuid,p_turn_claim_token uuid,p_session_binding_sha256 text,
  p_request_binding_sha256 text,p_loop_id uuid,p_step_id uuid,
  p_step_index integer,p_loop_revision bigint,p_planning_binding_sha256 text,
  p_proposal_id uuid,p_proposal_sha256 text,p_proposal_binding_sha256 text,
  p_request_id uuid,p_command_binding_sha256 text,p_grant_id uuid,
  p_action_id uuid,p_task_id uuid,p_connection_id uuid,p_provider text,
  p_resource text,p_action text,p_authorization_revision bigint,
  p_authorization_snapshot_sha256 text,p_granted_actions_sha256 text,
  p_granted_scopes_sha256 text,p_task_state_revision bigint,
  p_parameters_payload_id uuid,p_parameters_reference_binding_sha256 text,
  p_parameters_sha256 text,p_resource_version_sha256 text,p_policy_version text,
  p_approval_id uuid,p_approval_binding_sha256 text,p_preview_payload_id uuid,
  p_preview_reference_binding_sha256 text,p_preview_sha256 text,
  p_requested_at timestamptz,p_expires_at timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  session_row public.sessions%rowtype;
  job_row public.chat_jobs%rowtype;
  turn_row connected_chat_private.turns%rowtype;
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
  preparation jsonb;
begin
  if p_owner_id is null or p_session_id is null or p_chat_id is null
     or p_message_id is null or p_turn_id is null or p_turn_claim_token is null
     or p_loop_id is null or p_step_id is null or p_step_index not between 0 and 7
     or p_loop_revision<1 or p_task_state_revision<>p_loop_revision
     or p_proposal_id is null or p_request_id is null or p_action_id is null
     or p_session_binding_sha256!~'^[0-9a-f]{64}$'
     or p_request_binding_sha256!~'^[0-9a-f]{64}$'
     or p_planning_binding_sha256!~'^[0-9a-f]{64}$'
     or p_proposal_sha256!~'^[0-9a-f]{64}$'
     or p_proposal_binding_sha256!~'^[0-9a-f]{64}$' then
    raise exception 'invalid connected multi-step action preparation binding'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select session.* into session_row from public.sessions as session
  where session.id=p_session_id and session.user_id=p_owner_id for share;
  if not found or session_row.revoked_at is not null or session_row.expires_at<=now_at then
    raise exception 'connected multi-step action session changed' using errcode='55000';
  end if;
  select job.* into job_row from public.chat_jobs as job
  where job.user_id=p_owner_id and job.message_id=p_message_id for update;
  if not found or job_row.chat_id<>p_chat_id or job_row.status<>'processing'
     or job_row.claim_token<>p_turn_claim_token then
    raise exception 'connected multi-step action claim changed' using errcode='55000';
  end if;
  select turn.* into turn_row from connected_chat_private.turns as turn
  where turn.turn_id=p_turn_id and turn.job_id=job_row.id for update;
  if not found or turn_row.owner_id<>p_owner_id or turn_row.chat_id<>p_chat_id
     or turn_row.message_id<>p_message_id
     or turn_row.origin_session_binding_sha256<>p_session_binding_sha256
     or turn_row.request_binding_sha256<>p_request_binding_sha256
     or turn_row.planning_id<>p_loop_id
     or turn_row.stage not in ('planning','planned','prepared','executing') then
    raise exception 'connected multi-step action turn changed' using errcode='55000';
  end if;
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for update;
  select step_value.* into step_row from connected_loop_private.steps as step_value
  where step_value.owner_id=p_owner_id and step_value.loop_id=p_loop_id
    and step_value.step_id=p_step_id for update;
  if loop_row.loop_id is null or not found or loop_row.session_id<>p_session_id
     or loop_row.session_binding_sha256<>p_session_binding_sha256
     or loop_row.chat_id<>p_chat_id or loop_row.message_id<>p_message_id
     or loop_row.turn_id<>p_turn_id or loop_row.turn_claim_token<>p_turn_claim_token
     or loop_row.request_binding_sha256<>p_request_binding_sha256
     or loop_row.status<>'active' or loop_row.expires_at<=now_at
     or loop_row.task_state_revision<>p_loop_revision
     or loop_row.current_step<>p_step_index
     or step_row.step_index<>p_step_index or step_row.state<>'invoked'
     or step_row.planning_binding_sha256<>p_planning_binding_sha256
     or step_row.proposal_id<>p_proposal_id
     or step_row.proposal_sha256<>p_proposal_sha256
     or step_row.proposal_binding_sha256<>p_proposal_binding_sha256
     or step_row.proposal_kind<>'action'
     or step_row.connection_id<>p_connection_id or step_row.provider<>p_provider
     or step_row.resource<>p_resource or step_row.action<>p_action
     or step_row.authorization_revision<>p_authorization_revision
     or step_row.authorization_snapshot_sha256<>p_authorization_snapshot_sha256
     or p_expires_at>loop_row.expires_at then
    raise exception 'connected multi-step attached action changed'
      using errcode='55000';
  end if;
  preparation:=public.connected_app_operator_prepare_action_v1(
    p_request_id,p_owner_id,p_session_id,p_session_binding_sha256,
    p_command_binding_sha256,p_grant_id,p_action_id,p_task_id,p_turn_id,
    p_connection_id,p_provider,p_resource,p_action,p_authorization_revision,
    p_authorization_snapshot_sha256,p_granted_actions_sha256,
    p_granted_scopes_sha256,p_task_state_revision,p_parameters_payload_id,
    p_parameters_reference_binding_sha256,p_parameters_sha256,
    p_resource_version_sha256,p_policy_version,p_approval_id,
    p_approval_binding_sha256,p_preview_payload_id,
    p_preview_reference_binding_sha256,p_preview_sha256,
    p_requested_at,p_expires_at);
  if preparation->>'request_id'<>p_request_id::text
     or preparation->>'action_id'<>p_action_id::text
     or preparation->>'turn_id'<>p_turn_id::text
     or preparation->>'connection_id'<>p_connection_id::text
     or preparation->>'command_binding_sha256'<>p_command_binding_sha256 then
    raise exception 'connected multi-step action preparation result drifted'
      using errcode='55000';
  end if;
  update connected_chat_private.turns as turn set stage='prepared',
    preparation_request_id=p_request_id,action_id=p_action_id,
    execution_request_id=null,updated_at=now_at
  where turn.turn_id=p_turn_id and turn.owner_id=p_owner_id
    and turn.planning_id=p_loop_id
    and turn.stage in ('planning','planned','prepared','executing');
  if not found then
    raise exception 'connected multi-step action lost turn fence' using errcode='55000';
  end if;
  return preparation;
end;
$fn$;
comment on function public.connected_multi_step_prepare_action_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,integer,bigint,text,uuid,text,text,
  uuid,text,uuid,uuid,uuid,uuid,text,text,text,bigint,text,text,text,bigint,uuid,text,
  text,text,text,uuid,text,uuid,text,text,timestamptz,timestamptz
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_PREPARE_ACTION_V1_EXACT_ATTACHED_STEP';

create or replace function public.connected_multi_step_begin_read_v1(
  p_owner_id uuid,p_session_id uuid,p_chat_id uuid,p_message_id uuid,
  p_turn_id uuid,p_turn_claim_token uuid,p_session_binding_sha256 text,
  p_request_binding_sha256 text,p_loop_id uuid,p_step_id uuid,
  p_step_index integer,p_loop_revision bigint,p_planning_binding_sha256 text,
  p_proposal_id uuid,p_proposal_sha256 text,p_proposal_binding_sha256 text,
  p_execution_request_id uuid,p_preparation_request_id uuid,p_action_id uuid,
  p_command_binding_sha256 text
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  session_row public.sessions%rowtype;
  job_row public.chat_jobs%rowtype;
  turn_row connected_chat_private.turns%rowtype;
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
  preparation_row connected_app_private.action_preparations%rowtype;
begin
  if p_owner_id is null or p_session_id is null or p_chat_id is null
     or p_message_id is null or p_turn_id is null or p_turn_claim_token is null
     or p_loop_id is null or p_step_id is null or p_step_index not between 0 and 7
     or p_loop_revision<1 or p_proposal_id is null
     or p_execution_request_id is null or p_preparation_request_id is null
     or p_action_id is null or p_session_binding_sha256!~'^[0-9a-f]{64}$'
     or p_request_binding_sha256!~'^[0-9a-f]{64}$'
     or p_planning_binding_sha256!~'^[0-9a-f]{64}$'
     or p_proposal_sha256!~'^[0-9a-f]{64}$'
     or p_proposal_binding_sha256!~'^[0-9a-f]{64}$'
     or p_command_binding_sha256!~'^[0-9a-f]{64}$' then
    raise exception 'invalid connected multi-step read execution binding'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select session.* into session_row from public.sessions as session
  where session.id=p_session_id and session.user_id=p_owner_id for share;
  if not found or session_row.revoked_at is not null or session_row.expires_at<=now_at then
    raise exception 'connected multi-step read session changed' using errcode='55000';
  end if;
  select job.* into job_row from public.chat_jobs as job
  where job.user_id=p_owner_id and job.message_id=p_message_id for update;
  select turn.* into turn_row from connected_chat_private.turns as turn
  where turn.turn_id=p_turn_id and turn.job_id=job_row.id for update;
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for update;
  select step_value.* into step_row from connected_loop_private.steps as step_value
  where step_value.owner_id=p_owner_id and step_value.loop_id=p_loop_id
    and step_value.step_id=p_step_id for update;
  select preparation.* into preparation_row
  from connected_app_private.action_preparations as preparation
  where preparation.owner_id=p_owner_id
    and preparation.request_id=p_preparation_request_id for update;
  if session_row.id is null or job_row.id is null or turn_row.turn_id is null
     or loop_row.loop_id is null or step_row.step_id is null
     or preparation_row.request_id is null
     or job_row.chat_id<>p_chat_id or job_row.status<>'processing'
     or job_row.claim_token<>p_turn_claim_token
     or turn_row.owner_id<>p_owner_id or turn_row.chat_id<>p_chat_id
     or turn_row.message_id<>p_message_id
     or turn_row.origin_session_binding_sha256<>p_session_binding_sha256
     or turn_row.request_binding_sha256<>p_request_binding_sha256
     or turn_row.planning_id<>p_loop_id or turn_row.stage<>'prepared'
     or turn_row.preparation_request_id<>p_preparation_request_id
     or turn_row.action_id<>p_action_id
     or loop_row.session_id<>p_session_id or loop_row.turn_id<>p_turn_id
     or loop_row.turn_claim_token<>p_turn_claim_token
     or loop_row.status<>'active' or loop_row.expires_at<=now_at
     or loop_row.task_state_revision<>p_loop_revision
     or loop_row.current_step<>p_step_index
     or step_row.step_index<>p_step_index or step_row.state<>'invoked'
     or step_row.planning_binding_sha256<>p_planning_binding_sha256
     or step_row.proposal_id<>p_proposal_id
     or step_row.proposal_sha256<>p_proposal_sha256
     or step_row.proposal_binding_sha256<>p_proposal_binding_sha256
     or step_row.proposal_kind<>'action' or step_row.action_id is not null
     or preparation_row.action_id<>p_action_id
     or preparation_row.turn_id<>p_turn_id
     or preparation_row.command_binding_sha256<>p_command_binding_sha256
     or preparation_row.status<>'ready' or preparation_row.mutates_external_state
     or preparation_row.connection_id<>step_row.connection_id
     or preparation_row.action<>step_row.action
     or preparation_row.expires_at<=now_at then
    raise exception 'connected multi-step read execution binding changed'
      using errcode='55000';
  end if;
  update connected_chat_private.turns set stage='executing',
    execution_request_id=p_execution_request_id,updated_at=now_at
  where turn_id=p_turn_id and stage='prepared'
    and preparation_request_id=p_preparation_request_id and action_id=p_action_id;
  if not found then
    raise exception 'connected multi-step read lost turn fence' using errcode='55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'stage','executing','execution_request_id',p_execution_request_id,
    'preparation_request_id',p_preparation_request_id,'action_id',p_action_id,
    'updated_at',now_at);
end;
$fn$;
comment on function public.connected_multi_step_begin_read_v1(
  uuid,uuid,uuid,uuid,uuid,uuid,text,text,uuid,uuid,integer,bigint,text,uuid,text,text,
  uuid,uuid,uuid,text
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_BEGIN_READ_V1_NO_PROVIDER_EFFECT';

create or replace function public.connected_multi_step_settle_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid,p_step_index integer,
  p_expected_revision bigint,p_claim_request_id uuid,p_claim_token uuid,
  p_planning_binding_sha256 text,p_invocation_id uuid,p_proposal_id uuid,
  p_proposal_sha256 text,p_proposal_binding_sha256 text,p_status text,
  p_execution_kind text,p_action_id uuid,p_approval_id uuid,
  p_result_reference_id uuid,p_result_binding_sha256 text,p_now timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
  preparation_row connected_app_private.action_preparations%rowtype;
  review_row connected_app_private.approval_reviews%rowtype;
  read_row connected_app_private.read_results%rowtype;
  ledger_row connected_app_private.action_ledger%rowtype;
  next_step integer;
  expected_status text;
begin
  if p_owner_id is null or p_loop_id is null or p_step_id is null
     or p_step_index not between 0 and 7 or p_expected_revision<1
     or p_claim_request_id is null or p_claim_token is null
     or p_invocation_id is null or p_proposal_id is null
     or p_planning_binding_sha256!~'^[0-9a-f]{64}$'
     or p_proposal_sha256!~'^[0-9a-f]{64}$'
     or p_proposal_binding_sha256!~'^[0-9a-f]{64}$'
     or p_status not in (
       'active','waiting_approval','clarification','completed','limit_reached')
     or (p_execution_kind is not null and p_execution_kind not in (
       'read_complete','pending_approval','action_complete'))
     or (p_result_binding_sha256 is not null
       and p_result_binding_sha256!~'^[0-9a-f]{64}$')
     or (p_result_reference_id is null)<>(p_result_binding_sha256 is null)
     or p_now<now_at-interval '1 minute' or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step settlement' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for update;
  select step_value.* into step_row from connected_loop_private.steps as step_value
  where step_value.owner_id=p_owner_id and step_value.loop_id=p_loop_id
    and step_value.step_id=p_step_id for update;
  if loop_row.loop_id is null or not found or step_row.step_index<>p_step_index
     or step_row.claim_request_id<>p_claim_request_id
     or step_row.claim_token<>p_claim_token
     or step_row.planning_binding_sha256<>p_planning_binding_sha256
     or step_row.invocation_id<>p_invocation_id
     or step_row.proposal_id<>p_proposal_id
     or step_row.proposal_sha256<>p_proposal_sha256
     or step_row.proposal_binding_sha256<>p_proposal_binding_sha256 then
    raise exception 'connected multi-step settlement binding changed'
      using errcode='55000';
  end if;
  if step_row.state='settled' then
    if step_row.action_id is distinct from p_action_id
       or step_row.approval_id is distinct from p_approval_id
       or step_row.result_reference_id is distinct from p_result_reference_id
       or step_row.result_binding_sha256 is distinct from p_result_binding_sha256 then
      raise exception 'connected multi-step settlement replay drifted'
        using errcode='55000';
    end if;
    return connected_loop_private.step_view_v1(
      p_owner_id,p_loop_id,p_step_id,false);
  end if;
  if loop_row.status<>'active' or loop_row.expires_at<=now_at
     or loop_row.task_state_revision<>p_expected_revision
     or loop_row.current_step<>p_step_index or step_row.state<>'invoked' then
    raise exception 'connected multi-step settlement fence changed'
      using errcode='55000';
  end if;

  if step_row.proposal_kind='complete' then
    if p_status<>'completed' or p_execution_kind is not null
       or p_action_id is not null or p_approval_id is not null
       or p_result_reference_id is not null then
      raise exception 'connected multi-step completion shape drifted'
        using errcode='55000';
    end if;
    next_step:=loop_row.current_step;
  elsif step_row.proposal_kind='clarify' then
    if p_status<>'clarification' or p_execution_kind is not null
       or p_action_id is not null or p_approval_id is not null
       or p_result_reference_id is not null then
      raise exception 'connected multi-step clarification shape drifted'
        using errcode='55000';
    end if;
    next_step:=loop_row.current_step;
  elsif step_row.proposal_kind='action' then
    if p_action_id is null then
      raise exception 'connected multi-step action settlement lacks action'
        using errcode='55000';
    end if;
    select preparation.* into preparation_row
    from connected_app_private.action_preparations as preparation
    where preparation.owner_id=p_owner_id and preparation.action_id=p_action_id
    for update;
    if not found or preparation_row.turn_id<>loop_row.turn_id
       or preparation_row.connection_id<>step_row.connection_id
       or preparation_row.provider<>step_row.provider
       or preparation_row.resource<>step_row.resource
       or preparation_row.action<>step_row.action
       or preparation_row.authorization_revision<>step_row.authorization_revision
       or preparation_row.authorization_snapshot_sha256
          <>step_row.authorization_snapshot_sha256
       or preparation_row.task_state_revision<>p_expected_revision
       or preparation_row.expires_at<=now_at then
      raise exception 'connected multi-step action preparation changed'
        using errcode='55000';
    end if;
    next_step:=loop_row.current_step+1;
    expected_status:=case when next_step>=loop_row.max_steps
      then 'limit_reached' else 'active' end;
    if p_execution_kind='pending_approval' then
      if p_status<>'waiting_approval' or p_approval_id is null
         or p_result_reference_id is not null
         or preparation_row.status<>'pending_approval'
         or not preparation_row.mutates_external_state
         or preparation_row.approval_id<>p_approval_id then
        raise exception 'connected multi-step write must await a fresh approval'
          using errcode='55000';
      end if;
      select review.* into review_row
      from connected_app_private.approval_reviews as review
      where review.owner_id=p_owner_id and review.approval_id=p_approval_id
        and review.action_id=p_action_id for update;
      if not found or review_row.status<>'pending'
         or review_row.expires_at<=now_at or review_row.decided_at is not null then
        raise exception 'connected multi-step fresh approval review changed'
          using errcode='55000';
      end if;
    elsif p_execution_kind='read_complete' then
      if p_status<>expected_status or p_approval_id is not null
         or p_result_reference_id is null or preparation_row.status<>'ready'
         or preparation_row.mutates_external_state then
        raise exception 'connected multi-step read settlement shape drifted'
          using errcode='55000';
      end if;
      select result.* into read_row from connected_app_private.read_results as result
      where result.owner_id=p_owner_id and result.operation_id=p_action_id
        and result.result_payload_id=p_result_reference_id for share;
      select ledger.* into ledger_row from connected_app_private.action_ledger as ledger
      where ledger.owner_id=p_owner_id and ledger.operation_id=p_action_id for share;
      if read_row.completion_id is null or ledger_row.operation_id is null
         or read_row.action_id<>p_action_id
         or read_row.connection_id<>step_row.connection_id
         or read_row.provider<>step_row.provider or read_row.resource<>step_row.resource
         or read_row.action<>step_row.action or ledger_row.status<>'terminal'
         or ledger_row.terminal_outcome<>'read'
         or ledger_row.terminal_binding_sha256<>read_row.terminal_binding_sha256 then
        raise exception 'connected multi-step read result is absent or drifted'
          using errcode='55000';
      end if;
    else
      raise exception 'connected multi-step action execution kind is invalid'
        using errcode='55000';
    end if;
  else
    raise exception 'connected multi-step proposal is unavailable'
      using errcode='55000';
  end if;

  update connected_loop_private.loops set status=p_status,current_step=next_step,
    task_state_revision=task_state_revision+1,
    pending_approval_id=case when p_status='waiting_approval'
      then p_approval_id else null end,
    last_result_reference_id=p_result_reference_id,
    last_result_binding_sha256=p_result_binding_sha256,updated_at=now_at
  where loop_id=p_loop_id and owner_id=p_owner_id
    and status='active' and task_state_revision=p_expected_revision;
  if not found then
    raise exception 'connected multi-step settlement lost revision fence'
      using errcode='55000';
  end if;
  update connected_loop_private.steps set state='settled',action_id=p_action_id,
    approval_id=p_approval_id,result_reference_id=p_result_reference_id,
    result_binding_sha256=p_result_binding_sha256,settled_at=now_at,updated_at=now_at
  where step_id=p_step_id and state='invoked';
  if not found then
    raise exception 'connected multi-step settlement lost step fence'
      using errcode='55000';
  end if;
  if step_row.proposal_kind='clarify' then
    update connected_chat_private.turns set stage='planned',
      preparation_request_id=null,action_id=null,execution_request_id=null,
      updated_at=now_at
    where turn_id=loop_row.turn_id and owner_id=p_owner_id
      and stage in ('planning','planned','prepared','executing');
    if not found then
      raise exception 'connected multi-step clarification lost turn fence'
        using errcode='55000';
    end if;
  end if;
  return connected_loop_private.step_view_v1(p_owner_id,p_loop_id,p_step_id,false);
end;
$fn$;
comment on function public.connected_multi_step_settle_v1(
  uuid,uuid,uuid,integer,bigint,uuid,uuid,text,uuid,uuid,text,text,text,text,
  uuid,uuid,uuid,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_SETTLE_V1_TYPED_ONE_ACTION_FRESH_WRITE_APPROVAL';

create or replace function public.connected_multi_step_read_step_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid
) returns jsonb language plpgsql security definer set search_path='' as $fn$
begin
  if p_owner_id is null or p_loop_id is null or p_step_id is null then
    raise exception 'invalid connected multi-step read-step key' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  return connected_loop_private.step_view_v1(
    p_owner_id,p_loop_id,p_step_id,false);
end;
$fn$;
comment on function public.connected_multi_step_read_step_v1(uuid,uuid,uuid) is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_READ_STEP_V1_CONTENT_FREE';

create or replace function public.connected_multi_step_mark_unknown_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid,p_step_index integer,
  p_expected_revision bigint,p_claim_request_id uuid,p_claim_token uuid,
  p_planning_binding_sha256 text,p_invocation_id uuid,p_now timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
begin
  if p_owner_id is null or p_loop_id is null or p_step_id is null
     or p_step_index not between 0 and 7 or p_expected_revision<1
     or p_claim_request_id is null or p_claim_token is null
     or p_planning_binding_sha256!~'^[0-9a-f]{64}$'
     or p_now<now_at-interval '1 minute' or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step unknown binding' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for update;
  select step_value.* into step_row from connected_loop_private.steps as step_value
  where step_value.owner_id=p_owner_id and step_value.loop_id=p_loop_id
    and step_value.step_id=p_step_id for update;
  if loop_row.loop_id is null or not found or step_row.step_index<>p_step_index
     or step_row.claim_request_id<>p_claim_request_id
     or step_row.claim_token<>p_claim_token
     or step_row.planning_binding_sha256<>p_planning_binding_sha256
     or step_row.invocation_id is distinct from p_invocation_id then
    raise exception 'connected multi-step unknown binding changed'
      using errcode='55000';
  end if;
  if loop_row.status='effect_unknown' and step_row.state='effect_unknown' then
    return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
  end if;
  if loop_row.status<>'active' or loop_row.task_state_revision<>p_expected_revision
     or step_row.state not in ('claimed','invoked') then
    raise exception 'connected multi-step unknown fence changed' using errcode='55000';
  end if;
  update connected_loop_private.loops set status='effect_unknown',
    task_state_revision=task_state_revision+1,pending_approval_id=null,updated_at=now_at
  where loop_id=p_loop_id and owner_id=p_owner_id
    and status='active' and task_state_revision=p_expected_revision;
  update connected_loop_private.steps set state='effect_unknown',updated_at=now_at
  where step_id=p_step_id and state in ('claimed','invoked');
  update connected_chat_private.turns set stage='effect_unknown',updated_at=now_at
  where turn_id=loop_row.turn_id and owner_id=p_owner_id
    and stage not in ('terminal','effect_unknown');
  return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
end;
$fn$;
comment on function public.connected_multi_step_mark_unknown_v1(
  uuid,uuid,uuid,integer,bigint,uuid,uuid,text,uuid,timestamptz
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_MARK_UNKNOWN_V1_FAIL_CLOSED';

create or replace function public.connected_multi_step_stop_v1(
  p_loop_id uuid,p_owner_id uuid,p_session_id uuid,
  p_session_binding_sha256 text,p_chat_id uuid,p_message_id uuid,
  p_turn_id uuid,p_turn_claim_token uuid,p_time_zone text,
  p_request_binding_sha256 text,p_requested_at timestamptz,
  p_expires_at timestamptz,p_max_steps integer,p_expected_revision bigint,
  p_status text,p_now timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
begin
  if p_loop_id is null or p_owner_id is null or p_session_id is null
     or p_chat_id is null or p_message_id is null or p_turn_id is null
     or p_turn_claim_token is null or p_max_steps<>8 or p_expected_revision<1
     or p_session_binding_sha256!~'^[0-9a-f]{64}$'
     or p_request_binding_sha256!~'^[0-9a-f]{64}$'
     or p_status not in ('failed','cancelled','expired')
     or p_now<now_at-interval '1 minute' or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step stop binding' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for update;
  if not found then
    raise exception 'connected multi-step stop loop is absent' using errcode='55000';
  end if;
  if loop_row.session_id<>p_session_id
     or loop_row.session_binding_sha256<>p_session_binding_sha256
     or loop_row.chat_id<>p_chat_id or loop_row.message_id<>p_message_id
     or loop_row.turn_id<>p_turn_id or loop_row.turn_claim_token<>p_turn_claim_token
     or loop_row.time_zone<>p_time_zone
     or loop_row.request_binding_sha256<>p_request_binding_sha256
     or loop_row.requested_at<>p_requested_at or loop_row.expires_at<>p_expires_at
     or loop_row.max_steps<>p_max_steps then
    raise exception 'connected multi-step stop binding changed' using errcode='55000';
  end if;
  if loop_row.status=p_status then
    return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
  end if;
  if loop_row.status not in ('active','waiting_approval')
     or loop_row.task_state_revision<>p_expected_revision
     or (p_status='expired' and now_at<p_expires_at) then
    raise exception 'connected multi-step stop fence changed' using errcode='55000';
  end if;
  update connected_loop_private.loops set status=p_status,
    task_state_revision=task_state_revision+1,pending_approval_id=null,updated_at=now_at
  where loop_id=p_loop_id and owner_id=p_owner_id
    and task_state_revision=p_expected_revision
    and status in ('active','waiting_approval');
  if not found then
    raise exception 'connected multi-step stop lost revision fence' using errcode='55000';
  end if;
  update connected_loop_private.steps set state='cancelled',updated_at=now_at
  where loop_id=p_loop_id and owner_id=p_owner_id
    and state in ('claimed','invoked');
  return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
end;
$fn$;
comment on function public.connected_multi_step_stop_v1(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,timestamptz,timestamptz,
  integer,bigint,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_STOP_V1_CANCEL_DEADLINE_REVISION_FENCE';

create or replace function public.connected_multi_step_read_write_result_v1(
  p_owner_id uuid,p_loop_id uuid,p_step_id uuid,p_action_id uuid,p_approval_id uuid
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
  review_row connected_app_private.approval_reviews%rowtype;
  approval_row connected_app_private.approvals%rowtype;
  ledger_row connected_app_private.action_ledger%rowtype;
begin
  if p_owner_id is null or p_loop_id is null or p_step_id is null
     or p_action_id is null or p_approval_id is null then
    raise exception 'invalid connected multi-step write-result key' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for share;
  select step_value.* into step_row from connected_loop_private.steps as step_value
  where step_value.owner_id=p_owner_id and step_value.loop_id=p_loop_id
    and step_value.step_id=p_step_id for share;
  select review.* into review_row from connected_app_private.approval_reviews as review
  where review.owner_id=p_owner_id and review.approval_id=p_approval_id
    and review.action_id=p_action_id for share;
  select approval.* into approval_row from connected_app_private.approvals as approval
  where approval.owner_id=p_owner_id and approval.approval_id=p_approval_id
    and approval.action_id=p_action_id for share;
  select ledger.* into ledger_row from connected_app_private.action_ledger as ledger
  where ledger.owner_id=p_owner_id and ledger.operation_id=p_action_id for share;
  if loop_row.loop_id is null or step_row.step_id is null or review_row.approval_id is null
     or approval_row.approval_id is null or ledger_row.operation_id is null
     or step_row.state<>'settled' or step_row.action_id<>p_action_id
     or step_row.approval_id<>p_approval_id
     or review_row.status<>'approved'
     or approval_row.consumed_at is null
     or approval_row.consumed_by_operation_id<>p_action_id
     or ledger_row.status<>'terminal' or ledger_row.terminal_outcome<>'succeeded'
     or ledger_row.terminal_binding_sha256 is null or ledger_row.terminal_at is null
     or not (
       (loop_row.status='waiting_approval'
        and loop_row.pending_approval_id=p_approval_id
        and step_row.result_reference_id is null
        and step_row.result_binding_sha256 is null)
       or
       (loop_row.status in ('active','limit_reached')
        and loop_row.pending_approval_id is null
        and loop_row.last_result_reference_id=p_action_id
        and loop_row.last_result_binding_sha256=ledger_row.terminal_binding_sha256
        and step_row.result_reference_id=p_action_id
        and step_row.result_binding_sha256=ledger_row.terminal_binding_sha256)
     ) then
    raise exception 'connected multi-step write result is not authoritative'
      using errcode='55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'version',1,'owner_id',p_owner_id,'loop_id',p_loop_id,'step_id',p_step_id,
    'action_id',p_action_id,'approval_id',p_approval_id,
    'result_reference_id',p_action_id,
    'result_binding_sha256',ledger_row.terminal_binding_sha256,
    'terminal_at',ledger_row.terminal_at,'status','succeeded');
end;
$fn$;
comment on function public.connected_multi_step_read_write_result_v1(
  uuid,uuid,uuid,uuid,uuid
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_WRITE_RESULT_V1_DATABASE_AUTHORED_CONTENT_FREE';

create or replace function public.connected_multi_step_resume_approved_v1(
  p_loop_id uuid,p_owner_id uuid,p_session_id uuid,
  p_session_binding_sha256 text,p_chat_id uuid,p_message_id uuid,
  p_turn_id uuid,p_turn_claim_token uuid,p_time_zone text,
  p_request_binding_sha256 text,p_requested_at timestamptz,
  p_expires_at timestamptz,p_max_steps integer,p_expected_revision bigint,
  p_step_id uuid,p_action_id uuid,p_approval_id uuid,p_result_reference_id uuid,
  p_result_binding_sha256 text,p_now timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  step_row connected_loop_private.steps%rowtype;
  review_row connected_app_private.approval_reviews%rowtype;
  approval_row connected_app_private.approvals%rowtype;
  ledger_row connected_app_private.action_ledger%rowtype;
  next_status text;
begin
  if p_loop_id is null or p_owner_id is null or p_session_id is null
     or p_chat_id is null or p_message_id is null or p_turn_id is null
     or p_turn_claim_token is null or p_max_steps<>8 or p_expected_revision<1
     or p_step_id is null or p_action_id is null or p_approval_id is null
     or p_result_reference_id is null
     or p_session_binding_sha256!~'^[0-9a-f]{64}$'
     or p_request_binding_sha256!~'^[0-9a-f]{64}$'
     or p_result_binding_sha256!~'^[0-9a-f]{64}$'
     or p_now<now_at-interval '1 minute' or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step approval resume binding'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for update;
  select step_value.* into step_row from connected_loop_private.steps as step_value
  where step_value.owner_id=p_owner_id and step_value.loop_id=p_loop_id
    and step_value.step_id=p_step_id for update;
  select review.* into review_row from connected_app_private.approval_reviews as review
  where review.owner_id=p_owner_id and review.approval_id=p_approval_id
    and review.action_id=p_action_id for share;
  select approval.* into approval_row from connected_app_private.approvals as approval
  where approval.owner_id=p_owner_id and approval.approval_id=p_approval_id
    and approval.action_id=p_action_id for share;
  select ledger.* into ledger_row from connected_app_private.action_ledger as ledger
  where ledger.owner_id=p_owner_id and ledger.operation_id=p_action_id for share;
  if loop_row.loop_id is null or step_row.step_id is null
     or review_row.approval_id is null or approval_row.approval_id is null
     or ledger_row.operation_id is null
     or loop_row.session_id<>p_session_id
     or loop_row.session_binding_sha256<>p_session_binding_sha256
     or loop_row.chat_id<>p_chat_id or loop_row.message_id<>p_message_id
     or loop_row.turn_id<>p_turn_id or loop_row.turn_claim_token<>p_turn_claim_token
     or loop_row.time_zone<>p_time_zone
     or loop_row.request_binding_sha256<>p_request_binding_sha256
     or loop_row.requested_at<>p_requested_at or loop_row.expires_at<>p_expires_at
     or loop_row.max_steps<>p_max_steps
     or step_row.state<>'settled' or step_row.action_id<>p_action_id
     or step_row.approval_id<>p_approval_id
     or review_row.status<>'approved' or review_row.decided_at is null
     or approval_row.approval_binding_sha256<>review_row.approval_binding_sha256
     or approval_row.parameters_sha256<>review_row.parameters_sha256
     or approval_row.consumed_at is null
     or approval_row.consumed_by_operation_id<>p_action_id
     or ledger_row.status<>'terminal' or ledger_row.terminal_outcome<>'succeeded'
     or ledger_row.terminal_binding_sha256<>p_result_binding_sha256
     or p_result_reference_id<>p_action_id then
    raise exception 'connected multi-step fresh approval execution is not proven'
      using errcode='55000';
  end if;
  next_status:=case when loop_row.current_step>=loop_row.max_steps
    then 'limit_reached' else 'active' end;
  if loop_row.status=next_status
     and loop_row.last_result_reference_id=p_result_reference_id
     and loop_row.last_result_binding_sha256=p_result_binding_sha256
     and step_row.approval_id=p_approval_id
     and step_row.result_reference_id=p_result_reference_id
     and step_row.result_binding_sha256=p_result_binding_sha256 then
    return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
  end if;
  if loop_row.status<>'waiting_approval'
     or loop_row.pending_approval_id<>p_approval_id
     or loop_row.task_state_revision<>p_expected_revision then
    raise exception 'connected multi-step approval resume fence changed'
      using errcode='55000';
  end if;
  update connected_loop_private.loops set status=next_status,
    task_state_revision=task_state_revision+1,pending_approval_id=null,
    last_result_reference_id=p_result_reference_id,
    last_result_binding_sha256=p_result_binding_sha256,updated_at=now_at
  where loop_id=p_loop_id and owner_id=p_owner_id
    and status='waiting_approval' and task_state_revision=p_expected_revision
    and pending_approval_id=p_approval_id;
  if not found then
    raise exception 'connected multi-step approval resume lost revision fence'
      using errcode='55000';
  end if;
  update connected_loop_private.steps set result_reference_id=p_result_reference_id,
    result_binding_sha256=p_result_binding_sha256,updated_at=now_at
  where step_id=p_step_id and action_id=p_action_id and approval_id=p_approval_id;
  if not found then
    raise exception 'connected multi-step approval resume lost step fence'
      using errcode='55000';
  end if;
  return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
end;
$fn$;
comment on function public.connected_multi_step_resume_approved_v1(
  uuid,uuid,uuid,text,uuid,uuid,uuid,uuid,text,text,timestamptz,timestamptz,integer,
  bigint,uuid,uuid,uuid,uuid,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_RESUME_APPROVED_V1_FRESH_CONSUMED_APPROVAL_ONLY';

create or replace function connected_loop_private.multi_step_target_fingerprint_v1()
returns text language sql stable security definer set search_path='' as $fn$
  select pg_catalog.md5(pg_catalog.string_agg(
    item.value::text,
    E'\n' order by item.value::text collate pg_catalog."C"
  ))
  from (
    select pg_catalog.jsonb_build_array(
      'schema',namespace_row.nspname,
      pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text,''),
      pg_catalog.obj_description(namespace_row.oid,'pg_namespace')) as value
    from pg_catalog.pg_namespace as namespace_row
    where namespace_row.nspname='connected_loop_private'
    union all
    select pg_catalog.jsonb_build_array(
      'relation',namespace_row.nspname,class_row.relname,class_row.relkind,
      class_row.relpersistence,class_row.relrowsecurity,class_row.relforcerowsecurity,
      class_row.relreplident,pg_catalog.pg_get_userbyid(class_row.relowner),
      coalesce(class_row.relacl::text,''),coalesce(class_row.reloptions::text,''),
      pg_catalog.obj_description(class_row.oid,'pg_class'))
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_loop_private'
      and class_row.relname in ('loops','steps','envelopes')
    union all
    select pg_catalog.jsonb_build_array(
      'column',namespace_row.nspname,class_row.relname,attribute_row.attnum,
      attribute_row.attname,
      pg_catalog.format_type(attribute_row.atttypid,attribute_row.atttypmod),
      attribute_row.attnotnull,attribute_row.attidentity,attribute_row.attgenerated,
      attribute_row.attstorage,attribute_row.attcompression,
      coalesce(attribute_row.attoptions::text,''),
      coalesce(pg_catalog.pg_get_expr(default_row.adbin,default_row.adrelid),''),
      coalesce(attribute_row.attacl::text,''),
      pg_catalog.col_description(class_row.oid,attribute_row.attnum))
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row on class_row.oid=attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_attrdef as default_row
      on default_row.adrelid=attribute_row.attrelid
      and default_row.adnum=attribute_row.attnum
    where namespace_row.nspname='connected_loop_private'
      and class_row.relname in ('loops','steps','envelopes')
      and attribute_row.attnum>0 and not attribute_row.attisdropped
    union all
    select pg_catalog.jsonb_build_array(
      'constraint',namespace_row.nspname,class_row.relname,constraint_row.conname,
      constraint_row.contype,constraint_row.condeferrable,constraint_row.condeferred,
      constraint_row.convalidated,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    join pg_catalog.pg_class as class_row on class_row.oid=constraint_row.conrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_loop_private'
      and class_row.relname in ('loops','steps','envelopes')
    union all
    select pg_catalog.jsonb_build_array(
      'index',namespace_row.nspname,class_row.relname,index_class.relname,
      index_row.indisunique,index_row.indisprimary,index_row.indisvalid,
      index_row.indisready,pg_catalog.pg_get_indexdef(index_row.indexrelid))
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as class_row on class_row.oid=index_row.indrelid
    join pg_catalog.pg_class as index_class on index_class.oid=index_row.indexrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_loop_private'
      and class_row.relname in ('loops','steps','envelopes')
    union all
    select pg_catalog.jsonb_build_array(
      'trigger',namespace_row.nspname,class_row.relname,trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid=trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_loop_private'
      and class_row.relname in ('loops','steps','envelopes')
      and not trigger_row.tgisinternal
    union all
    select pg_catalog.jsonb_build_array(
      'rule',namespace_row.nspname,class_row.relname,rewrite_row.rulename,
      pg_catalog.pg_get_ruledef(rewrite_row.oid,true))
    from pg_catalog.pg_rewrite as rewrite_row
    join pg_catalog.pg_class as class_row on class_row.oid=rewrite_row.ev_class
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_loop_private'
      and class_row.relname in ('loops','steps','envelopes')
      and rewrite_row.rulename<>'_RETURN'
    union all
    select pg_catalog.jsonb_build_array(
      'function',namespace_row.nspname,proc_row.proname,
      pg_catalog.pg_get_function_identity_arguments(proc_row.oid),
      pg_catalog.pg_get_functiondef(proc_row.oid),
      pg_catalog.pg_get_userbyid(proc_row.proowner),proc_row.prosecdef,
      proc_row.proleakproof,proc_row.proisstrict,proc_row.proretset,
      proc_row.provolatile,proc_row.proparallel,proc_row.procost,proc_row.prorows,
      language_row.lanname,coalesce(proc_row.proconfig::text,''),
      coalesce(proc_row.proacl::text,''),
      pg_catalog.obj_description(proc_row.oid,'pg_proc'))
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=proc_row.pronamespace
    join pg_catalog.pg_language as language_row on language_row.oid=proc_row.prolang
    where (namespace_row.nspname='connected_loop_private'
        and proc_row.proname in (
          'loop_view_v1','loop_public_view_v1','step_view_v1','envelope_view_v1',
          'multi_step_target_fingerprint_v1'))
       or (namespace_row.nspname='public'
        and proc_row.proname in (
          'connected_multi_step_start_v1','connected_multi_step_read_loop_v1',
          'connected_multi_step_list_v1',
          'connected_multi_step_owner_status_v1',
          'connected_multi_step_cancel_owner_v1',
          'connected_multi_step_claim_v1','connected_multi_step_mark_invoked_v1',
          'connected_multi_step_put_envelope_v1',
          'connected_multi_step_read_envelope_v1',
          'connected_multi_step_attach_proposal_v1',
          'connected_multi_step_prepare_action_v1',
          'connected_multi_step_begin_read_v1','connected_multi_step_settle_v1',
          'connected_multi_step_read_step_v1','connected_multi_step_mark_unknown_v1',
          'connected_multi_step_stop_v1',
          'connected_multi_step_read_write_result_v1',
          'connected_multi_step_resume_approved_v1'))
  ) as item
$fn$;
comment on function connected_loop_private.multi_step_target_fingerprint_v1() is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_TARGET_FINGERPRINT_V1_EXACT_CATALOG';

alter schema connected_loop_private owner to postgres;
alter table connected_loop_private.loops owner to postgres;
alter table connected_loop_private.steps owner to postgres;
alter table connected_loop_private.envelopes owner to postgres;
revoke all on table connected_loop_private.loops from public,anon,authenticated,service_role;
revoke all on table connected_loop_private.steps from public,anon,authenticated,service_role;
revoke all on table connected_loop_private.envelopes from public,anon,authenticated,service_role;

do $function_acl$
declare
  proc_row record;
  identity text;
begin
  for proc_row in
    select namespace_row.nspname,proc.proname,
      pg_catalog.pg_get_function_identity_arguments(proc.oid) as arguments
    from pg_catalog.pg_proc as proc
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=proc.pronamespace
    where (namespace_row.nspname='connected_loop_private'
      and proc.proname in (
        'loop_view_v1','loop_public_view_v1','step_view_v1','envelope_view_v1',
        'multi_step_target_fingerprint_v1'))
      or (namespace_row.nspname='public' and proc.proname like 'connected_multi_step_%')
  loop
    identity:=pg_catalog.format('%I.%I(%s)',proc_row.nspname,proc_row.proname,
      proc_row.arguments);
    execute 'alter function '||identity||' owner to postgres';
    execute 'revoke all on function '||identity||' from public';
    execute 'revoke all on function '||identity||' from anon';
    execute 'revoke all on function '||identity||' from authenticated';
    execute 'revoke all on function '||identity||' from service_role';
    if proc_row.nspname='public' then
      execute 'grant execute on function '||identity||' to service_role';
    end if;
  end loop;
end;
$function_acl$;

do $postflight$
declare
  target_fingerprint text;
  target_function_count integer;
begin
  select connected_loop_private.multi_step_target_fingerprint_v1()
    into target_fingerprint;
  if length('a63bd463531f048bac9024b17d5823c1')=32
     and target_fingerprint<>'a63bd463531f048bac9024b17d5823c1' then
    raise exception 'connected multi-step target drifted: %',target_fingerprint
      using errcode='55000';
  end if;
  select count(*) into target_function_count
  from pg_catalog.pg_proc as proc_row
  join pg_catalog.pg_namespace as namespace_row
    on namespace_row.oid=proc_row.pronamespace
  where namespace_row.nspname='public'
    and proc_row.proname like 'connected_multi_step_%';
  if length('a63bd463531f048bac9024b17d5823c1')=32 and (target_function_count<>18
     or exists(
       select 1 from pg_catalog.pg_class as class_row
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname='connected_loop_private'
         and class_row.relname in ('loops','steps','envelopes')
         and (not class_row.relrowsecurity or not class_row.relforcerowsecurity
           or pg_catalog.pg_get_userbyid(class_row.relowner)<>'postgres'
           or pg_catalog.has_table_privilege('anon',class_row.oid,
             'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
           or pg_catalog.has_table_privilege('authenticated',class_row.oid,
             'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
           or pg_catalog.has_table_privilege('service_role',class_row.oid,
             'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')))
     or exists(
       select 1 from pg_catalog.pg_policy as policy_row
       where policy_row.polrelid in (
         'connected_loop_private.loops'::pg_catalog.regclass,
         'connected_loop_private.steps'::pg_catalog.regclass,
         'connected_loop_private.envelopes'::pg_catalog.regclass))
     or exists(
       select 1 from pg_catalog.pg_proc as proc_row
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=proc_row.pronamespace
       where namespace_row.nspname='public'
         and proc_row.proname like 'connected_multi_step_%'
         and (not proc_row.prosecdef
           or proc_row.proconfig<>array['search_path=""']::text[]
           or not pg_catalog.has_function_privilege(
             'service_role',proc_row.oid,'EXECUTE')
           or pg_catalog.has_function_privilege('anon',proc_row.oid,'EXECUTE')
           or pg_catalog.has_function_privilege('authenticated',proc_row.oid,'EXECUTE')))
     or exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace
       where pnnspid=pg_catalog.to_regnamespace('connected_loop_private'))
     or exists(
       select 1 from pg_catalog.pg_publication_rel as publication_relation
       where publication_relation.prrelid in (
         'connected_loop_private.loops'::pg_catalog.regclass,
         'connected_loop_private.steps'::pg_catalog.regclass,
         'connected_loop_private.envelopes'::pg_catalog.regclass))) then
    raise exception 'connected multi-step authority or privacy postflight failed'
      using errcode='55000';
  end if;
end;
$postflight$;

commit;
