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
       'connected_loop_continuation_private.continuation_target_fingerprint_v1()'
     ) is not null then
    select connected_loop_continuation_private.continuation_target_fingerprint_v1()
      into target_fingerprint;
    if target_fingerprint <> '1fac1595981f5cd703aaabbc3d13c571' then
      raise exception 'connected multi-step continuation target drifted: %',
        target_fingerprint using errcode='55000';
    end if;
    return;
  end if;

  if pg_catalog.to_regprocedure(
       'connected_cancel_private.cancel_snapshot_target_fingerprint_v1()'
     ) is null then
    raise exception 'connected multi-step continuation predecessor is absent'
      using errcode='55000';
  end if;
  select connected_cancel_private.cancel_snapshot_target_fingerprint_v1()
    into predecessor_fingerprint;
  if predecessor_fingerprint <> '755dbb418bb4cef4d102f1587ee1c99a' then
    raise exception 'connected multi-step continuation predecessor drifted: %',
      predecessor_fingerprint using errcode='55000';
  end if;

  if pg_catalog.to_regclass('connected_loop_private.loops') is null
     or pg_catalog.to_regclass('connected_loop_private.steps') is null
     or pg_catalog.to_regclass('connected_chat_private.turns') is null
     or pg_catalog.to_regclass('connected_app_private.approval_reviews') is null
     or pg_catalog.to_regclass('connected_app_private.approvals') is null
     or pg_catalog.to_regclass('connected_app_private.action_ledger') is null
     or pg_catalog.to_regclass('public.user_chats') is null
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null
     or pg_catalog.to_regprocedure(
       'connected_loop_private.loop_view_v1(uuid,uuid)'
     ) is null then
    raise exception 'connected multi-step continuation predecessor is incomplete'
      using errcode='55000';
  end if;

  if pg_catalog.to_regnamespace('connected_loop_continuation_private') is not null
     or exists(
       select 1
       from pg_catalog.pg_proc as procedure
       join pg_catalog.pg_namespace as namespace
         on namespace.oid=procedure.pronamespace
       where namespace.nspname='public'
         and procedure.proname like 'connected_multi_step_continuation_%') then
    raise exception 'connected multi-step continuation target is partial'
      using errcode='55000';
  end if;

  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1
       from pg_catalog.pg_publication_namespace
       where pnnspid in (
         pg_catalog.to_regnamespace('connected_loop_private'),
         pg_catalog.to_regnamespace('connected_loop_continuation_private')))
     or exists(
       select 1
       from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row
         on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname in (
         'connected_loop_private','connected_loop_continuation_private')) then
    raise exception 'connected multi-step continuation publication exposure refused'
      using errcode='55000';
  end if;
end;
$preflight$;

create schema if not exists connected_loop_continuation_private authorization postgres;
comment on schema connected_loop_continuation_private is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_V1_PRIVATE_CONTENT_FREE_QUEUE';
revoke all on schema connected_loop_continuation_private
  from public,anon,authenticated,service_role;

create table if not exists connected_loop_continuation_private.jobs (
  loop_id uuid primary key
    references connected_loop_private.loops(loop_id) on delete cascade,
  owner_id uuid not null references public.users(id) on delete cascade,
  next_generation bigint not null default 0 check(next_generation>=0),
  current_claim_request_id uuid,
  available_at timestamptz not null,
  last_settlement_id uuid unique,
  last_outcome text check(last_outcome is null or last_outcome in (
    'waiting_approval','terminal','failed','cancelled','retryable')),
  last_result_revision bigint check(
    last_result_revision is null or last_result_revision>=1),
  updated_at timestamptz not null,
  unique(owner_id,loop_id),
  constraint connected_multi_step_continuation_job_settlement_shape check(
    (last_settlement_id is null and last_outcome is null
      and last_result_revision is null)
    or (last_settlement_id is not null and last_outcome is not null
      and last_result_revision is not null))
);
comment on table connected_loop_continuation_private.jobs is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_JOBS_V1_CONTENT_FREE';

create table if not exists connected_loop_continuation_private.claims (
  claim_request_id uuid primary key,
  claim_token uuid not null unique,
  loop_id uuid not null,
  owner_id uuid not null,
  generation bigint not null check(generation>=1),
  loop_revision bigint not null check(loop_revision>=1),
  kind text not null check(kind in ('active','approved_write')),
  approval_step_id uuid,
  action_id uuid,
  approval_id uuid,
  status text not null check(status in ('claimed','settled','superseded')),
  claimed_at timestamptz not null,
  claim_expires_at timestamptz not null,
  settlement_id uuid unique,
  outcome text check(outcome is null or outcome in (
    'waiting_approval','terminal','failed','cancelled','retryable')),
  result_revision bigint check(result_revision is null or result_revision>=1),
  settled_at timestamptz,
  updated_at timestamptz not null,
  constraint connected_multi_step_continuation_claim_loop_fk
    foreign key(owner_id,loop_id)
    references connected_loop_private.loops(owner_id,loop_id) on delete cascade,
  constraint connected_multi_step_continuation_claim_approval_shape check(
    (kind='active' and approval_step_id is null
      and action_id is null and approval_id is null)
    or (kind='approved_write' and approval_step_id is not null
      and action_id is not null and approval_id is not null)),
  constraint connected_multi_step_continuation_claim_time_shape check(
    claim_expires_at>claimed_at
      and claim_expires_at<=claimed_at+interval '2 minutes'),
  constraint connected_multi_step_continuation_claim_settlement_shape check(
    (status='claimed' and settlement_id is null and outcome is null
      and result_revision is null and settled_at is null)
    or (status='settled' and settlement_id is not null and outcome is not null
      and result_revision is not null and settled_at is not null)
    or (status='superseded' and settlement_id is null and outcome is null
      and result_revision is null and settled_at is null)),
  unique(loop_id,generation),
  unique(owner_id,claim_request_id)
);
comment on table connected_loop_continuation_private.claims is
  'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_CLAIMS_V1_CONTENT_FREE_ONE_USE';

do $job_current_claim_fk$
begin
  if not exists(
    select 1
    from pg_catalog.pg_constraint as constraint_row
    where constraint_row.conrelid=
      'connected_loop_continuation_private.jobs'::pg_catalog.regclass
      and constraint_row.conname=
        'connected_multi_step_continuation_job_current_claim_fk'
  ) then
    alter table connected_loop_continuation_private.jobs
      add constraint connected_multi_step_continuation_job_current_claim_fk
      foreign key(current_claim_request_id)
      references connected_loop_continuation_private.claims(claim_request_id)
      on delete set null;
  end if;
end;
$job_current_claim_fk$;

create index if not exists connected_multi_step_continuation_jobs_ready_idx
  on connected_loop_continuation_private.jobs(available_at,loop_id);
create index if not exists connected_multi_step_continuation_claims_live_idx
  on connected_loop_continuation_private.claims(claim_expires_at,loop_id)
  where status='claimed';
create index if not exists connected_multi_step_continuation_claims_owner_idx
  on connected_loop_continuation_private.claims(owner_id,loop_id,generation desc);

alter table connected_loop_continuation_private.jobs enable row level security;
alter table connected_loop_continuation_private.jobs force row level security;
alter table connected_loop_continuation_private.claims enable row level security;
alter table connected_loop_continuation_private.claims force row level security;

create or replace function connected_loop_continuation_private.approved_write_v1(
  p_owner_id uuid,p_loop_id uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'approval_step_id',step_row.step_id,
    'action_id',step_row.action_id,
    'approval_id',step_row.approval_id,
    'result_binding_sha256',ledger_row.terminal_binding_sha256)
  from connected_loop_private.loops as loop_row
  join connected_loop_private.steps as step_row
    on step_row.loop_id=loop_row.loop_id
   and step_row.owner_id=loop_row.owner_id
   and step_row.step_index=loop_row.current_step-1
  join connected_app_private.approval_reviews as review_row
    on review_row.owner_id=loop_row.owner_id
   and review_row.approval_id=step_row.approval_id
   and review_row.action_id=step_row.action_id
  join connected_app_private.approvals as approval_row
    on approval_row.owner_id=loop_row.owner_id
   and approval_row.approval_id=step_row.approval_id
   and approval_row.action_id=step_row.action_id
  join connected_app_private.action_ledger as ledger_row
    on ledger_row.owner_id=loop_row.owner_id
   and ledger_row.operation_id=step_row.action_id
  where loop_row.owner_id=p_owner_id and loop_row.loop_id=p_loop_id
    and loop_row.status='waiting_approval'
    and loop_row.pending_approval_id=step_row.approval_id
    and step_row.state='settled' and step_row.proposal_kind='action'
    and step_row.action_id is not null and step_row.approval_id is not null
    and review_row.status='approved' and review_row.decided_at is not null
    and approval_row.approval_binding_sha256=review_row.approval_binding_sha256
    and approval_row.parameters_sha256=review_row.parameters_sha256
    and approval_row.consumed_at is not null
    and approval_row.consumed_by_operation_id=step_row.action_id
    and ledger_row.status='terminal' and ledger_row.terminal_outcome='succeeded'
    and ledger_row.terminal_binding_sha256 is not null
    and ledger_row.terminal_at is not null
$fn$;
comment on function connected_loop_continuation_private.approved_write_v1(uuid,uuid)
  is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_APPROVED_WRITE_V1_DATABASE_PROOF';

create or replace function connected_loop_continuation_private.claim_view_v1(
  p_claim_request_id uuid,p_claim_token uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'claim_request_id',claim_row.claim_request_id,
    'claim_token',claim_row.claim_token,
    'claim_generation',claim_row.generation,
    'loop_revision',claim_row.loop_revision,
    'claim_expires_at',claim_row.claim_expires_at,
    'claim_state',claim_row.status,
    'kind',claim_row.kind,
    'loop_id',loop_row.loop_id,'owner_id',loop_row.owner_id,
    'session_id',loop_row.session_id,
    'session_binding_sha256',loop_row.session_binding_sha256,
    'chat_id',loop_row.chat_id,'message_id',loop_row.message_id,
    'turn_id',loop_row.turn_id,'turn_claim_token',loop_row.turn_claim_token,
    'time_zone',loop_row.time_zone,
    'request_binding_sha256',loop_row.request_binding_sha256,
    'requested_at',loop_row.requested_at,'expires_at',loop_row.expires_at,
    'max_steps',loop_row.max_steps,
    'approval_step_id',claim_row.approval_step_id,
    'action_id',claim_row.action_id,'approval_id',claim_row.approval_id)
  from connected_loop_continuation_private.claims as claim_row
  join connected_loop_private.loops as loop_row
    on loop_row.owner_id=claim_row.owner_id and loop_row.loop_id=claim_row.loop_id
  where claim_row.claim_request_id=p_claim_request_id
    and claim_row.claim_token=p_claim_token
$fn$;
comment on function connected_loop_continuation_private.claim_view_v1(uuid,uuid)
  is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_CLAIM_VIEW_V1_CONTENT_FREE';

create or replace function connected_loop_continuation_private.settlement_view_v1(
  p_settlement_id uuid,p_claim_request_id uuid,p_claim_token uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select pg_catalog.jsonb_build_object(
    'settlement_id',claim_row.settlement_id,
    'claim_request_id',claim_row.claim_request_id,
    'claim_token',claim_row.claim_token,
    'owner_id',claim_row.owner_id,'loop_id',claim_row.loop_id,
    'claim_generation',claim_row.generation,
    'outcome',claim_row.outcome,
    'result_revision',claim_row.result_revision,
    'settled_at',claim_row.settled_at)
  from connected_loop_continuation_private.claims as claim_row
  where claim_row.settlement_id=p_settlement_id
    and claim_row.claim_request_id=p_claim_request_id
    and claim_row.claim_token=p_claim_token
    and claim_row.status='settled'
$fn$;
comment on function connected_loop_continuation_private.settlement_view_v1(uuid,uuid,uuid)
  is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_SETTLEMENT_VIEW_V1_CONTENT_FREE';

create or replace function public.connected_multi_step_continuation_list_v1(
  p_maximum integer,p_now timestamptz
) returns setof jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  if p_maximum is null or p_maximum<1 or p_maximum>32
     or p_now is null or p_now<now_at-interval '1 minute'
     or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step continuation list request'
      using errcode='22023';
  end if;
  return query
  select pg_catalog.jsonb_build_object(
    'owner_id',loop_row.owner_id,'loop_id',loop_row.loop_id,
    'task_state_revision',loop_row.task_state_revision,
    'kind',case when loop_row.status='active' then 'active'
      else 'approved_write' end,
    'expires_at',loop_row.expires_at)
  from connected_loop_private.loops as loop_row
  left join connected_loop_continuation_private.jobs as job_row
    on job_row.loop_id=loop_row.loop_id and job_row.owner_id=loop_row.owner_id
  left join connected_loop_continuation_private.claims as current_claim
    on current_claim.claim_request_id=job_row.current_claim_request_id
  where loop_row.expires_at>now_at
    and (
      loop_row.status='active'
      or (loop_row.status='waiting_approval'
        and connected_loop_continuation_private.approved_write_v1(
          loop_row.owner_id,loop_row.loop_id) is not null))
    and (job_row.available_at is null or job_row.available_at<=now_at)
    and (current_claim.claim_request_id is null
      or current_claim.status<>'claimed'
      or current_claim.claim_expires_at<=now_at)
  order by loop_row.updated_at,loop_row.loop_id
  limit p_maximum;
end;
$fn$;
comment on function public.connected_multi_step_continuation_list_v1(integer,timestamptz)
  is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_LIST_V1_CONTENT_FREE_RUNNABLE_ONLY';

create or replace function public.connected_multi_step_continuation_claim_v1(
  p_owner_id uuid,p_loop_id uuid,p_expected_revision bigint,
  p_claim_request_id uuid,p_claim_token uuid,p_now timestamptz,
  p_lease_seconds integer
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  job_row connected_loop_continuation_private.jobs%rowtype;
  claim_row connected_loop_continuation_private.claims%rowtype;
  proof jsonb;
  next_kind text;
  new_generation bigint;
  lease_until timestamptz;
begin
  if p_owner_id is null or p_loop_id is null or p_expected_revision<1
     or p_claim_request_id is null or p_claim_token is null
     or p_lease_seconds<5 or p_lease_seconds>120
     or p_now is null or p_now<now_at-interval '1 minute'
     or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step continuation claim request'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row
  from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id
  for update;
  if loop_row.loop_id is null or loop_row.task_state_revision<>p_expected_revision
     or loop_row.expires_at<=now_at
     or loop_row.status not in ('active','waiting_approval') then
    raise exception 'connected multi-step continuation loop fence changed'
      using errcode='55000';
  end if;
  if loop_row.status='waiting_approval' then
    proof:=connected_loop_continuation_private.approved_write_v1(
      p_owner_id,p_loop_id);
    if proof is null then
      raise exception 'connected multi-step continuation approval is not executable'
        using errcode='55000';
    end if;
    next_kind:='approved_write';
  else
    proof:=null;
    next_kind:='active';
  end if;

  select claim_value.* into claim_row
  from connected_loop_continuation_private.claims as claim_value
  where claim_value.claim_request_id=p_claim_request_id for update;
  if claim_row.claim_request_id is not null then
    if claim_row.owner_id<>p_owner_id or claim_row.loop_id<>p_loop_id
       or claim_row.claim_token<>p_claim_token
       or claim_row.loop_revision<>p_expected_revision
       or claim_row.kind<>next_kind then
      raise exception 'connected multi-step continuation claim identity collision'
        using errcode='55000';
    end if;
    return connected_loop_continuation_private.claim_view_v1(
      p_claim_request_id,p_claim_token);
  end if;
  if exists(
    select 1 from connected_loop_continuation_private.claims
    where claim_token=p_claim_token) then
    raise exception 'connected multi-step continuation claim token collision'
      using errcode='55000';
  end if;

  insert into connected_loop_continuation_private.jobs(
    loop_id,owner_id,next_generation,current_claim_request_id,
    available_at,updated_at)
  values(p_loop_id,p_owner_id,0,null,now_at,now_at)
  on conflict(loop_id) do nothing;
  select job_value.* into job_row
  from connected_loop_continuation_private.jobs as job_value
  where job_value.owner_id=p_owner_id and job_value.loop_id=p_loop_id
  for update;
  if job_row.loop_id is null or job_row.available_at>now_at then
    raise exception 'connected multi-step continuation job is not available'
      using errcode='55P03';
  end if;
  if job_row.current_claim_request_id is not null then
    select claim_value.* into claim_row
    from connected_loop_continuation_private.claims as claim_value
    where claim_value.claim_request_id=job_row.current_claim_request_id
    for update;
    if claim_row.status='claimed' and claim_row.claim_expires_at>now_at then
      raise exception 'connected multi-step continuation job is already claimed'
        using errcode='55P03';
    end if;
    if claim_row.status='claimed' then
      update connected_loop_continuation_private.claims
      set status='superseded',updated_at=now_at
      where claim_request_id=claim_row.claim_request_id and status='claimed';
    end if;
  end if;
  new_generation:=job_row.next_generation+1;
  lease_until:=least(
    loop_row.expires_at,now_at+pg_catalog.make_interval(secs=>p_lease_seconds));
  if lease_until<=now_at then
    raise exception 'connected multi-step continuation lease is expired'
      using errcode='55000';
  end if;
  insert into connected_loop_continuation_private.claims(
    claim_request_id,claim_token,loop_id,owner_id,generation,loop_revision,kind,
    approval_step_id,action_id,approval_id,status,claimed_at,
    claim_expires_at,updated_at)
  values(
    p_claim_request_id,p_claim_token,p_loop_id,p_owner_id,new_generation,
    p_expected_revision,next_kind,
    case when proof is null then null else (proof->>'approval_step_id')::uuid end,
    case when proof is null then null else (proof->>'action_id')::uuid end,
    case when proof is null then null else (proof->>'approval_id')::uuid end,
    'claimed',now_at,lease_until,now_at);
  update connected_loop_continuation_private.jobs
  set next_generation=new_generation,
      current_claim_request_id=p_claim_request_id,updated_at=now_at
  where loop_id=p_loop_id and owner_id=p_owner_id;
  return connected_loop_continuation_private.claim_view_v1(
    p_claim_request_id,p_claim_token);
end;
$fn$;
comment on function public.connected_multi_step_continuation_claim_v1(
  uuid,uuid,bigint,uuid,uuid,timestamptz,integer
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_CLAIM_V1_ONE_USE_CRASH_RECOVERABLE';

create or replace function public.connected_multi_step_continuation_read_claim_v1(
  p_claim_request_id uuid,p_claim_token uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_loop_continuation_private.claim_view_v1(
    p_claim_request_id,p_claim_token)
$fn$;
comment on function public.connected_multi_step_continuation_read_claim_v1(uuid,uuid)
  is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_READ_CLAIM_V1_RESPONSE_LOSS';

create or replace function public.connected_multi_step_continuation_renew_v1(
  p_owner_id uuid,p_loop_id uuid,p_claim_request_id uuid,p_claim_token uuid,
  p_claim_generation bigint,p_expected_revision bigint,p_now timestamptz,
  p_lease_seconds integer
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  job_row connected_loop_continuation_private.jobs%rowtype;
  claim_row connected_loop_continuation_private.claims%rowtype;
  lease_until timestamptz;
begin
  if p_owner_id is null or p_loop_id is null or p_claim_request_id is null
     or p_claim_token is null or p_claim_generation<1 or p_expected_revision<1
     or p_lease_seconds<5 or p_lease_seconds>120
     or p_now is null or p_now<now_at-interval '1 minute'
     or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step continuation renewal'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for share;
  select job_value.* into job_row
  from connected_loop_continuation_private.jobs as job_value
  where job_value.owner_id=p_owner_id and job_value.loop_id=p_loop_id for update;
  select claim_value.* into claim_row
  from connected_loop_continuation_private.claims as claim_value
  where claim_value.claim_request_id=p_claim_request_id for update;
  if loop_row.loop_id is null or job_row.loop_id is null
     or claim_row.claim_request_id is null
     or loop_row.task_state_revision<>p_expected_revision
     or loop_row.status<>'active' or loop_row.expires_at<=now_at
     or job_row.current_claim_request_id<>p_claim_request_id
     or claim_row.owner_id<>p_owner_id or claim_row.loop_id<>p_loop_id
     or claim_row.claim_token<>p_claim_token
     or claim_row.generation<>p_claim_generation
     or claim_row.status<>'claimed' or claim_row.claim_expires_at<=now_at then
    raise exception 'connected multi-step continuation renewal fence changed'
      using errcode='55000';
  end if;
  lease_until:=least(
    loop_row.expires_at,now_at+pg_catalog.make_interval(secs=>p_lease_seconds));
  if lease_until<=now_at then
    raise exception 'connected multi-step continuation renewal expired'
      using errcode='55000';
  end if;
  update connected_loop_continuation_private.claims
  set loop_revision=p_expected_revision,claim_expires_at=lease_until,updated_at=now_at
  where claim_request_id=p_claim_request_id and claim_token=p_claim_token
    and generation=p_claim_generation and status='claimed';
  if not found then
    raise exception 'connected multi-step continuation renewal lost claim'
      using errcode='55000';
  end if;
  return connected_loop_continuation_private.claim_view_v1(
    p_claim_request_id,p_claim_token);
end;
$fn$;
comment on function public.connected_multi_step_continuation_renew_v1(
  uuid,uuid,uuid,uuid,bigint,bigint,timestamptz,integer
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_RENEW_V1_REVISION_DEADLINE_FENCE';

create or replace function public.connected_multi_step_continuation_settle_v1(
  p_owner_id uuid,p_loop_id uuid,p_claim_request_id uuid,p_claim_token uuid,
  p_claim_generation bigint,p_settlement_id uuid,p_outcome text,
  p_result_revision bigint,p_now timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  job_row connected_loop_continuation_private.jobs%rowtype;
  claim_row connected_loop_continuation_private.claims%rowtype;
begin
  if p_owner_id is null or p_loop_id is null or p_claim_request_id is null
     or p_claim_token is null or p_claim_generation<1 or p_settlement_id is null
     or p_result_revision<1 or p_outcome not in (
       'waiting_approval','terminal','failed','cancelled','retryable')
     or p_now is null or p_now<now_at-interval '1 minute'
     or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step continuation settlement'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for share;
  select job_value.* into job_row
  from connected_loop_continuation_private.jobs as job_value
  where job_value.owner_id=p_owner_id and job_value.loop_id=p_loop_id for update;
  select claim_value.* into claim_row
  from connected_loop_continuation_private.claims as claim_value
  where claim_value.claim_request_id=p_claim_request_id for update;
  if claim_row.status='settled' then
    if claim_row.owner_id<>p_owner_id or claim_row.loop_id<>p_loop_id
       or claim_row.claim_token<>p_claim_token
       or claim_row.generation<>p_claim_generation
       or claim_row.settlement_id<>p_settlement_id
       or claim_row.outcome<>p_outcome
       or claim_row.result_revision<>p_result_revision then
      raise exception 'connected multi-step continuation settlement replay drifted'
        using errcode='55000';
    end if;
    return connected_loop_continuation_private.settlement_view_v1(
      p_settlement_id,p_claim_request_id,p_claim_token);
  end if;
  if loop_row.loop_id is null or job_row.loop_id is null
     or claim_row.claim_request_id is null
     or loop_row.task_state_revision<>p_result_revision
     or job_row.current_claim_request_id<>p_claim_request_id
     or claim_row.owner_id<>p_owner_id or claim_row.loop_id<>p_loop_id
     or claim_row.claim_token<>p_claim_token
     or claim_row.generation<>p_claim_generation
     or claim_row.status<>'claimed' or claim_row.claim_expires_at<=now_at then
    raise exception 'connected multi-step continuation settlement fence changed'
      using errcode='55000';
  end if;
  if (p_outcome='waiting_approval' and loop_row.status<>'waiting_approval')
     or (p_outcome='retryable' and loop_row.status<>'active')
     or (p_outcome='failed' and loop_row.status<>'failed')
     or (p_outcome='cancelled' and loop_row.status<>'cancelled')
     or (p_outcome='terminal' and loop_row.status not in (
       'clarification','completed','expired','effect_unknown','limit_reached')) then
    raise exception 'connected multi-step continuation settlement outcome drifted'
      using errcode='55000';
  end if;
  update connected_loop_continuation_private.claims
  set status='settled',settlement_id=p_settlement_id,outcome=p_outcome,
      result_revision=p_result_revision,settled_at=now_at,updated_at=now_at
  where claim_request_id=p_claim_request_id and claim_token=p_claim_token
    and generation=p_claim_generation and status='claimed';
  if not found then
    raise exception 'connected multi-step continuation settlement lost claim'
      using errcode='55000';
  end if;
  update connected_loop_continuation_private.jobs
  set current_claim_request_id=null,last_settlement_id=p_settlement_id,
      last_outcome=p_outcome,last_result_revision=p_result_revision,
      available_at=case when p_outcome='retryable'
        then now_at+interval '5 seconds'
        when p_outcome='waiting_approval' then now_at
        else loop_row.expires_at end,
      updated_at=now_at
  where loop_id=p_loop_id and owner_id=p_owner_id
    and current_claim_request_id=p_claim_request_id;
  if not found then
    raise exception 'connected multi-step continuation settlement lost job'
      using errcode='55000';
  end if;
  return connected_loop_continuation_private.settlement_view_v1(
    p_settlement_id,p_claim_request_id,p_claim_token);
end;
$fn$;
comment on function public.connected_multi_step_continuation_settle_v1(
  uuid,uuid,uuid,uuid,bigint,uuid,text,bigint,timestamptz
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_SETTLE_V1_EXACT_RESPONSE_RECOVERY';

create or replace function public.connected_multi_step_continuation_read_settlement_v1(
  p_settlement_id uuid,p_claim_request_id uuid,p_claim_token uuid
) returns jsonb language sql stable security definer set search_path='' as $fn$
  select connected_loop_continuation_private.settlement_view_v1(
    p_settlement_id,p_claim_request_id,p_claim_token)
$fn$;
comment on function public.connected_multi_step_continuation_read_settlement_v1(
  uuid,uuid,uuid
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_READ_SETTLEMENT_V1_RESPONSE_LOSS';

create or replace function public.connected_multi_step_continuation_instruction_v1(
  p_owner_id uuid,p_loop_id uuid,p_claim_request_id uuid,p_claim_token uuid,
  p_claim_generation bigint,p_now timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  turn_row connected_chat_private.turns%rowtype;
  chat_job_row public.chat_jobs%rowtype;
  job_row connected_loop_continuation_private.jobs%rowtype;
  claim_row connected_loop_continuation_private.claims%rowtype;
  instruction text;
  matches bigint;
begin
  if p_owner_id is null or p_loop_id is null or p_claim_request_id is null
     or p_claim_token is null or p_claim_generation<1
     or p_now is null or p_now<now_at-interval '1 minute'
     or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step continuation instruction request'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for share;
  select turn_value.* into turn_row from connected_chat_private.turns as turn_value
  where turn_value.owner_id=p_owner_id and turn_value.turn_id=loop_row.turn_id for share;
  select chat_job_value.* into chat_job_row from public.chat_jobs as chat_job_value
  where chat_job_value.id=turn_row.job_id and chat_job_value.user_id=p_owner_id
  for share;
  select job_value.* into job_row
  from connected_loop_continuation_private.jobs as job_value
  where job_value.owner_id=p_owner_id and job_value.loop_id=p_loop_id for share;
  select claim_value.* into claim_row
  from connected_loop_continuation_private.claims as claim_value
  where claim_value.claim_request_id=p_claim_request_id for share;
  if loop_row.loop_id is null or turn_row.turn_id is null
     or chat_job_row.id is null or job_row.loop_id is null
     or claim_row.claim_request_id is null
     or loop_row.expires_at<=now_at
     or loop_row.status not in ('active','waiting_approval')
     or (claim_row.kind='active' and loop_row.status<>'active')
     or (claim_row.kind='approved_write' and loop_row.status<>'waiting_approval')
     or turn_row.chat_id<>loop_row.chat_id
     or turn_row.message_id<>loop_row.message_id
     or chat_job_row.chat_id<>loop_row.chat_id
     or chat_job_row.message_id<>loop_row.message_id
     or chat_job_row.claim_token<>loop_row.turn_claim_token
     or turn_row.origin_session_binding_sha256<>loop_row.session_binding_sha256
     or turn_row.request_binding_sha256<>loop_row.request_binding_sha256
     or job_row.current_claim_request_id<>p_claim_request_id
     or claim_row.owner_id<>p_owner_id or claim_row.loop_id<>p_loop_id
     or claim_row.claim_token<>p_claim_token
     or claim_row.generation<>p_claim_generation
     or claim_row.status<>'claimed' or claim_row.claim_expires_at<=now_at then
    raise exception 'connected multi-step continuation instruction fence changed'
      using errcode='55000';
  end if;
  select pg_catalog.count(*),pg_catalog.min(expanded.message_item->>'content')
    into matches,instruction
  from public.user_chats as chat_row
  cross join lateral pg_catalog.jsonb_array_elements(chat_row.messages)
    as expanded(message_item)
  where chat_row.user_id=p_owner_id and chat_row.chat_id=loop_row.chat_id
    and chat_row.deleted_at is null
    and pg_catalog.jsonb_typeof(expanded.message_item)='object'
    and expanded.message_item->>'id'=loop_row.message_id::text
    and expanded.message_item->>'role'='user'
    and pg_catalog.jsonb_typeof(expanded.message_item->'content')='string';
  if matches<>1 or instruction is null or instruction=''
     or pg_catalog.octet_length(instruction)>12000 then
    return pg_catalog.jsonb_build_object(
      'version',1,'owner_id',p_owner_id,'loop_id',p_loop_id,
      'chat_id',loop_row.chat_id,'message_id',loop_row.message_id,
      'instruction',null);
  end if;
  return pg_catalog.jsonb_build_object(
    'version',1,'owner_id',p_owner_id,'loop_id',p_loop_id,
    'chat_id',loop_row.chat_id,'message_id',loop_row.message_id,
    'instruction',instruction);
end;
$fn$;
comment on function public.connected_multi_step_continuation_instruction_v1(
  uuid,uuid,uuid,uuid,bigint,timestamptz
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_INSTRUCTION_V1_LIVE_CLAIM_BOUND_CONTENT';

create or replace function public.connected_multi_step_continuation_fail_v1(
  p_owner_id uuid,p_loop_id uuid,p_claim_request_id uuid,p_claim_token uuid,
  p_claim_generation bigint,p_expected_revision bigint,p_reason text,
  p_now timestamptz
) returns jsonb language plpgsql security definer set search_path='' as $fn$
declare
  now_at timestamptz:=pg_catalog.clock_timestamp();
  loop_row connected_loop_private.loops%rowtype;
  job_row connected_loop_continuation_private.jobs%rowtype;
  claim_row connected_loop_continuation_private.claims%rowtype;
  proof jsonb;
begin
  if p_owner_id is null or p_loop_id is null or p_claim_request_id is null
     or p_claim_token is null or p_claim_generation<1 or p_expected_revision<1
     or p_reason not in (
       'instruction_missing','instruction_invalid',
       'connections_missing','connections_invalid')
     or p_now is null or p_now<now_at-interval '1 minute'
     or p_now>now_at+interval '1 minute' then
    raise exception 'invalid connected multi-step continuation failure'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select loop_value.* into loop_row from connected_loop_private.loops as loop_value
  where loop_value.owner_id=p_owner_id and loop_value.loop_id=p_loop_id for update;
  select job_value.* into job_row
  from connected_loop_continuation_private.jobs as job_value
  where job_value.owner_id=p_owner_id and job_value.loop_id=p_loop_id for update;
  select claim_value.* into claim_row
  from connected_loop_continuation_private.claims as claim_value
  where claim_value.claim_request_id=p_claim_request_id for update;
  if loop_row.status='failed' and loop_row.task_state_revision=p_expected_revision+1 then
    return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
  end if;
  if loop_row.status='cancelled' then
    return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
  end if;
  if loop_row.loop_id is null or job_row.loop_id is null
     or claim_row.claim_request_id is null
     or loop_row.task_state_revision<>p_expected_revision
     or loop_row.status not in ('active','waiting_approval')
     or loop_row.expires_at<=now_at
     or job_row.current_claim_request_id<>p_claim_request_id
     or claim_row.owner_id<>p_owner_id or claim_row.loop_id<>p_loop_id
     or claim_row.claim_token<>p_claim_token
     or claim_row.generation<>p_claim_generation
     or claim_row.status<>'claimed' or claim_row.claim_expires_at<=now_at then
    raise exception 'connected multi-step continuation failure fence changed'
      using errcode='55000';
  end if;
  if loop_row.status='waiting_approval' then
    proof:=connected_loop_continuation_private.approved_write_v1(
      p_owner_id,p_loop_id);
    if proof is null
       or (proof->>'approval_step_id')::uuid<>claim_row.approval_step_id
       or (proof->>'action_id')::uuid<>claim_row.action_id
       or (proof->>'approval_id')::uuid<>claim_row.approval_id then
      raise exception 'connected multi-step continuation failure lost write proof'
        using errcode='55000';
    end if;
    update connected_loop_private.steps
    set result_reference_id=claim_row.action_id,
        result_binding_sha256=proof->>'result_binding_sha256',updated_at=now_at
    where step_id=claim_row.approval_step_id and loop_id=p_loop_id
      and owner_id=p_owner_id and action_id=claim_row.action_id
      and approval_id=claim_row.approval_id and state='settled';
    if not found then
      raise exception 'connected multi-step continuation failure lost step proof'
        using errcode='55000';
    end if;
  end if;
  update connected_loop_private.loops
  set status='failed',task_state_revision=task_state_revision+1,
      pending_approval_id=null,
      last_result_reference_id=case when proof is null
        then last_result_reference_id else claim_row.action_id end,
      last_result_binding_sha256=case when proof is null
        then last_result_binding_sha256 else proof->>'result_binding_sha256' end,
      updated_at=now_at
  where owner_id=p_owner_id and loop_id=p_loop_id
    and task_state_revision=p_expected_revision
    and status in ('active','waiting_approval');
  if not found then
    raise exception 'connected multi-step continuation failure lost loop fence'
      using errcode='55000';
  end if;
  return connected_loop_private.loop_view_v1(p_owner_id,p_loop_id);
end;
$fn$;
comment on function public.connected_multi_step_continuation_fail_v1(
  uuid,uuid,uuid,uuid,bigint,bigint,text,timestamptz
) is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_FAIL_V1_DETERMINISTIC_NO_LOOP';

alter table connected_loop_continuation_private.jobs owner to postgres;
alter table connected_loop_continuation_private.claims owner to postgres;
alter function connected_loop_continuation_private.approved_write_v1(uuid,uuid)
  owner to postgres;
alter function connected_loop_continuation_private.claim_view_v1(uuid,uuid)
  owner to postgres;
alter function connected_loop_continuation_private.settlement_view_v1(uuid,uuid,uuid)
  owner to postgres;
alter function public.connected_multi_step_continuation_list_v1(integer,timestamptz)
  owner to postgres;
alter function public.connected_multi_step_continuation_claim_v1(
  uuid,uuid,bigint,uuid,uuid,timestamptz,integer
) owner to postgres;
alter function public.connected_multi_step_continuation_read_claim_v1(uuid,uuid)
  owner to postgres;
alter function public.connected_multi_step_continuation_renew_v1(
  uuid,uuid,uuid,uuid,bigint,bigint,timestamptz,integer
) owner to postgres;
alter function public.connected_multi_step_continuation_settle_v1(
  uuid,uuid,uuid,uuid,bigint,uuid,text,bigint,timestamptz
) owner to postgres;
alter function public.connected_multi_step_continuation_read_settlement_v1(
  uuid,uuid,uuid
) owner to postgres;
alter function public.connected_multi_step_continuation_instruction_v1(
  uuid,uuid,uuid,uuid,bigint,timestamptz
) owner to postgres;
alter function public.connected_multi_step_continuation_fail_v1(
  uuid,uuid,uuid,uuid,bigint,bigint,text,timestamptz
) owner to postgres;

revoke all on table connected_loop_continuation_private.jobs
  from public,anon,authenticated,service_role;
revoke all on table connected_loop_continuation_private.claims
  from public,anon,authenticated,service_role;
revoke all on function connected_loop_continuation_private.approved_write_v1(uuid,uuid)
  from public,anon,authenticated,service_role;
revoke all on function connected_loop_continuation_private.claim_view_v1(uuid,uuid)
  from public,anon,authenticated,service_role;
revoke all on function connected_loop_continuation_private.settlement_view_v1(
  uuid,uuid,uuid
) from public,anon,authenticated,service_role;
revoke all on function public.connected_multi_step_continuation_list_v1(
  integer,timestamptz
) from public,anon,authenticated;
revoke all on function public.connected_multi_step_continuation_claim_v1(
  uuid,uuid,bigint,uuid,uuid,timestamptz,integer
) from public,anon,authenticated;
revoke all on function public.connected_multi_step_continuation_read_claim_v1(uuid,uuid)
  from public,anon,authenticated;
revoke all on function public.connected_multi_step_continuation_renew_v1(
  uuid,uuid,uuid,uuid,bigint,bigint,timestamptz,integer
) from public,anon,authenticated;
revoke all on function public.connected_multi_step_continuation_settle_v1(
  uuid,uuid,uuid,uuid,bigint,uuid,text,bigint,timestamptz
) from public,anon,authenticated;
revoke all on function public.connected_multi_step_continuation_read_settlement_v1(
  uuid,uuid,uuid
) from public,anon,authenticated;
revoke all on function public.connected_multi_step_continuation_instruction_v1(
  uuid,uuid,uuid,uuid,bigint,timestamptz
) from public,anon,authenticated;
revoke all on function public.connected_multi_step_continuation_fail_v1(
  uuid,uuid,uuid,uuid,bigint,bigint,text,timestamptz
) from public,anon,authenticated;

grant execute on function public.connected_multi_step_continuation_list_v1(
  integer,timestamptz
) to service_role;
grant execute on function public.connected_multi_step_continuation_claim_v1(
  uuid,uuid,bigint,uuid,uuid,timestamptz,integer
) to service_role;
grant execute on function public.connected_multi_step_continuation_read_claim_v1(uuid,uuid)
  to service_role;
grant execute on function public.connected_multi_step_continuation_renew_v1(
  uuid,uuid,uuid,uuid,bigint,bigint,timestamptz,integer
) to service_role;
grant execute on function public.connected_multi_step_continuation_settle_v1(
  uuid,uuid,uuid,uuid,bigint,uuid,text,bigint,timestamptz
) to service_role;
grant execute on function public.connected_multi_step_continuation_read_settlement_v1(
  uuid,uuid,uuid
) to service_role;
grant execute on function public.connected_multi_step_continuation_instruction_v1(
  uuid,uuid,uuid,uuid,bigint,timestamptz
) to service_role;
grant execute on function public.connected_multi_step_continuation_fail_v1(
  uuid,uuid,uuid,uuid,bigint,bigint,text,timestamptz
) to service_role;

create or replace function connected_loop_continuation_private.continuation_target_fingerprint_v1()
returns text language sql stable security definer set search_path='' as $fingerprint$
  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
  from (
    select pg_catalog.concat_ws('|','schema',namespace_row.nspname,
      pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text,''),coalesce(description.description,'')) as item
    from pg_catalog.pg_namespace as namespace_row
    left join pg_catalog.pg_description as description
      on description.objoid=namespace_row.oid and description.objsubid=0
    where namespace_row.nspname='connected_loop_continuation_private'
    union all
    select pg_catalog.concat_ws('|','relation',class_row.relname,class_row.relkind,
      class_row.relrowsecurity,class_row.relforcerowsecurity,
      pg_catalog.pg_get_userbyid(class_row.relowner),
      coalesce(class_row.relacl::text,''),coalesce(description.description,''))
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_description as description
      on description.objoid=class_row.oid and description.objsubid=0
    where namespace_row.nspname='connected_loop_continuation_private'
      and class_row.relname in ('jobs','claims')
    union all
    select pg_catalog.concat_ws('|','column',class_row.relname,attribute.attnum,
      attribute.attname,pg_catalog.format_type(attribute.atttypid,attribute.atttypmod),
      attribute.attnotnull,coalesce(
        pg_catalog.pg_get_expr(default_value.adbin,default_value.adrelid),''),
      coalesce(pg_catalog.col_description(attribute.attrelid,attribute.attnum),''))
    from pg_catalog.pg_attribute as attribute
    join pg_catalog.pg_class as class_row on class_row.oid=attribute.attrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_attrdef as default_value
      on default_value.adrelid=attribute.attrelid
     and default_value.adnum=attribute.attnum
    where namespace_row.nspname='connected_loop_continuation_private'
      and class_row.relname in ('jobs','claims')
      and attribute.attnum>0 and not attribute.attisdropped
    union all
    select pg_catalog.concat_ws('|','constraint',class_row.relname,
      constraint_row.conname,constraint_row.contype,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    join pg_catalog.pg_class as class_row on class_row.oid=constraint_row.conrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_loop_continuation_private'
      and class_row.relname in ('jobs','claims')
    union all
    select pg_catalog.concat_ws('|','index',table_class.relname,index_class.relname,
      pg_catalog.pg_get_indexdef(index_class.oid))
    from pg_catalog.pg_class as index_class
    join pg_catalog.pg_index as index_row
      on index_row.indexrelid=index_class.oid
    join pg_catalog.pg_class as table_class on table_class.oid=index_row.indrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=table_class.relnamespace
    where namespace_row.nspname='connected_loop_continuation_private'
      and table_class.relname in ('jobs','claims')
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
    where (namespace_row.nspname='connected_loop_continuation_private'
      and procedure.proname in (
        'approved_write_v1','claim_view_v1','settlement_view_v1'))
       or (namespace_row.nspname='public'
      and procedure.proname in (
        'connected_multi_step_continuation_list_v1',
        'connected_multi_step_continuation_claim_v1',
        'connected_multi_step_continuation_read_claim_v1',
        'connected_multi_step_continuation_renew_v1',
        'connected_multi_step_continuation_settle_v1',
        'connected_multi_step_continuation_read_settlement_v1',
        'connected_multi_step_continuation_instruction_v1',
        'connected_multi_step_continuation_fail_v1'))
    union all
    select pg_catalog.concat_ws('|','trigger',class_row.relname,trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid=trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_loop_continuation_private'
      and class_row.relname in ('jobs','claims') and not trigger_row.tgisinternal
    union all
    select pg_catalog.concat_ws('|','rule',class_row.relname,rule_row.rulename,
      pg_catalog.pg_get_ruledef(rule_row.oid,true))
    from pg_catalog.pg_rewrite as rule_row
    join pg_catalog.pg_class as class_row on class_row.oid=rule_row.ev_class
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_loop_continuation_private'
      and class_row.relname in ('jobs','claims') and rule_row.rulename<>'_RETURN'
    union all
    select pg_catalog.concat_ws('|','publication',publication_row.pubname,
      publication_row.puballtables,coalesce(namespace_row.nspname,''),
      coalesce(class_row.relname,''))
    from pg_catalog.pg_publication as publication_row
    left join pg_catalog.pg_publication_rel as publication_rel
      on publication_rel.prpubid=publication_row.oid
    left join pg_catalog.pg_class as class_row
      on class_row.oid=publication_rel.prrelid
    left join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where publication_row.puballtables
       or namespace_row.nspname='connected_loop_continuation_private'
  ) as manifest(item)
$fingerprint$;
comment on function connected_loop_continuation_private.continuation_target_fingerprint_v1()
  is 'ASK_CRUMP_CONNECTED_MULTI_STEP_CONTINUATION_TARGET_FINGERPRINT_V1';
alter function connected_loop_continuation_private.continuation_target_fingerprint_v1()
  owner to postgres;
revoke all on function connected_loop_continuation_private.continuation_target_fingerprint_v1()
  from public,anon,authenticated,service_role;

do $postflight$
declare
  target_fingerprint text;
  function_name text;
begin
  select connected_loop_continuation_private.continuation_target_fingerprint_v1()
    into target_fingerprint;
  if target_fingerprint <> '1fac1595981f5cd703aaabbc3d13c571' then
    raise exception 'connected multi-step continuation postflight drifted: %',
      target_fingerprint using errcode='55000';
  end if;
  foreach function_name in array array[
    'public.connected_multi_step_continuation_list_v1(integer,timestamp with time zone)',
    'public.connected_multi_step_continuation_claim_v1(uuid,uuid,bigint,uuid,uuid,timestamp with time zone,integer)',
    'public.connected_multi_step_continuation_read_claim_v1(uuid,uuid)',
    'public.connected_multi_step_continuation_renew_v1(uuid,uuid,uuid,uuid,bigint,bigint,timestamp with time zone,integer)',
    'public.connected_multi_step_continuation_settle_v1(uuid,uuid,uuid,uuid,bigint,uuid,text,bigint,timestamp with time zone)',
    'public.connected_multi_step_continuation_read_settlement_v1(uuid,uuid,uuid)',
    'public.connected_multi_step_continuation_instruction_v1(uuid,uuid,uuid,uuid,bigint,timestamp with time zone)',
    'public.connected_multi_step_continuation_fail_v1(uuid,uuid,uuid,uuid,bigint,bigint,text,timestamp with time zone)'
  ] loop
    if pg_catalog.has_function_privilege('public',function_name,'execute')
       or pg_catalog.has_function_privilege('anon',function_name,'execute')
       or pg_catalog.has_function_privilege('authenticated',function_name,'execute')
       or not pg_catalog.has_function_privilege('service_role',function_name,'execute') then
      raise exception 'connected multi-step continuation function ACL drifted: %',
        function_name using errcode='55000';
    end if;
  end loop;
  if pg_catalog.has_schema_privilege(
       'service_role','connected_loop_continuation_private','usage')
     or pg_catalog.has_table_privilege(
       'service_role','connected_loop_continuation_private.jobs','select')
     or pg_catalog.has_table_privilege(
       'service_role','connected_loop_continuation_private.claims','select')
     or exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row
         on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname='connected_loop_continuation_private') then
    raise exception 'connected multi-step continuation private boundary drifted'
      using errcode='55000';
  end if;
end;
$postflight$;

commit;
