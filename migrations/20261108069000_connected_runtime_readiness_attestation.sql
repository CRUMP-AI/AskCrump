\set ON_ERROR_STOP on

begin;

select pg_catalog.set_config('search_path','pg_catalog,public',true);
select pg_catalog.set_config('quote_all_identifiers','off',true);

do $preflight$
declare
  predecessor_fingerprint text;
  existing_target_fingerprint text;
begin
  if pg_catalog.to_regprocedure(
       'connected_readiness_private.runtime_readiness_target_fingerprint_v1()'
     ) is not null then
    if not exists(
      select 1
      from pg_catalog.pg_proc as proc_row
      join pg_catalog.pg_language as language_row
        on language_row.oid=proc_row.prolang
      where proc_row.oid=
        'connected_readiness_private.runtime_readiness_target_fingerprint_v1()'
          ::pg_catalog.regprocedure
        and pg_catalog.pg_get_userbyid(proc_row.proowner)='postgres'
        and language_row.lanname='sql'
        and proc_row.prokind='f'
        and proc_row.provolatile='s'
        and proc_row.proisstrict is false
        and proc_row.prosecdef is true
        and proc_row.proleakproof is false
        and proc_row.proparallel='u'
        and proc_row.proretset is false
        and proc_row.prorettype='pg_catalog.text'::pg_catalog.regtype
        and proc_row.pronargs=0
        and pg_catalog.md5(proc_row.prosrc)=
          'd9060896d2e302e6476949dac7702125'
        and proc_row.proconfig=
          array['search_path=""']::pg_catalog.text[]
        and proc_row.proacl::text='{postgres=X/postgres}'
        and pg_catalog.obj_description(proc_row.oid,'pg_proc')=
          'ASK_CRUMP_CONNECTED_RUNTIME_READINESS_TARGET_FINGERPRINT_V1_FULL_STACK'
    ) then
      raise exception 'connected runtime readiness target attestor drifted'
        using errcode='55000';
    end if;
    select connected_readiness_private.runtime_readiness_target_fingerprint_v1()
      into existing_target_fingerprint;
    if existing_target_fingerprint<>'59714dce4c61f8140eddc1a2c8606b70' then
      raise exception 'connected runtime readiness target drifted: %',
        existing_target_fingerprint using errcode='55000';
    end if;
  else
    if pg_catalog.to_regprocedure(
         'connected_multi_account_private.multi_account_target_fingerprint_v1()'
       ) is null then
      raise exception 'connected runtime readiness predecessor is absent'
        using errcode='55000';
    end if;
    select connected_multi_account_private.multi_account_target_fingerprint_v1()
      into predecessor_fingerprint;
    if predecessor_fingerprint<>'bf14a3339a25e4e2cdab12ef18523599' then
      raise exception 'connected runtime readiness predecessor drifted: %',
        predecessor_fingerprint using errcode='55000';
    end if;
    if pg_catalog.to_regnamespace('connected_readiness_private') is not null
       or pg_catalog.to_regprocedure(
         'public.connected_app_claim_release_preview_ceremony_v1(uuid,uuid,text,text,text,text,text)'
       ) is not null
       or pg_catalog.to_regprocedure(
         'public.connected_app_release_preview_begin_v1(uuid,text,text,text,text,text,jsonb,text,text,text,text,text,text,text,text)'
       ) is not null
       or pg_catalog.to_regprocedure(
         'public.connected_app_issue_provider_smoke_challenge_v1(text,text,text,text,text,text,text,text,text,text,text,uuid,text)'
       ) is not null
       or pg_catalog.to_regprocedure(
         'public.connected_app_record_provider_smoke_v1(text,text,text,text,text,text,text,text,text,text,text,uuid,text,uuid,text)'
       ) is not null
       or pg_catalog.to_regprocedure(
         'public.connected_app_runtime_readiness_v1(text,text,text,text,text,text,text,text,text)'
       ) is not null
       or pg_catalog.to_regprocedure(
         'public.connected_app_release_preview_retire_connection_v1(uuid,uuid,uuid,bigint,text,text,text,uuid,text)'
       ) is not null
       or pg_catalog.to_regprocedure(
         'public.connected_app_release_preview_authority_v1(uuid,text,text,bigint,text,text,text)'
       ) is not null
       or pg_catalog.to_regprocedure(
         'public.connected_app_release_preview_fail_v1(uuid)'
       ) is not null then
      raise exception 'connected runtime readiness target is partial'
        using errcode='55000';
    end if;
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
    raise exception 'connected runtime readiness publication exposure refused'
      using errcode='55000';
  end if;
end;
$preflight$;

create schema if not exists connected_readiness_private authorization postgres;
comment on schema connected_readiness_private is
  'ASK_CRUMP_CONNECTED_RUNTIME_READINESS_V1_PRIVATE_CONTENT_FREE_ATTESTATION';
revoke all on schema connected_readiness_private
  from public,anon,authenticated,service_role;

create table if not exists connected_readiness_private.release_preview_ceremony (
  invocation_id uuid primary key,
  claim_id uuid not null unique,
  owner_id uuid not null references public.users(id) on delete cascade,
  session_binding_sha256 text not null
    check(session_binding_sha256~'^[0-9a-f]{64}$'),
  confirmation_sha256 text not null
    check(confirmation_sha256~'^[0-9a-f]{64}$'),
  deployment_id text not null check(deployment_id~'^dpl_[A-Za-z0-9]{8,}$'),
  commit_sha text not null check(commit_sha~'^[0-9a-f]{40}$'),
  host_configuration_ciphertext_sha256 text not null
    check(host_configuration_ciphertext_sha256~'^[0-9a-f]{64}$'),
  status text not null check(status in ('running','succeeded','failed')),
  recovery_count integer not null default 0 check(recovery_count between 0 and 100),
  issued_at timestamptz not null,
  expires_at timestamptz not null,
  completed_at timestamptz,
  constraint connected_release_preview_ceremony_lifetime check(
    expires_at>issued_at and expires_at<=issued_at+interval '15 minutes'),
  constraint connected_release_preview_ceremony_terminal check(
    (status='running' and completed_at is null)
    or (status in ('succeeded','failed') and completed_at is not null))
);
comment on table connected_readiness_private.release_preview_ceremony is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_CEREMONY_V1_CONTENT_FREE_ONE_USE_RECOVERABLE';
alter table connected_readiness_private.release_preview_ceremony enable row level security;
alter table connected_readiness_private.release_preview_ceremony force row level security;
revoke all on table connected_readiness_private.release_preview_ceremony
  from public,anon,authenticated,service_role;
create unique index if not exists
  connected_release_preview_ceremony_one_running_idx
  on connected_readiness_private.release_preview_ceremony((true))
  where status='running';

create table if not exists connected_readiness_private.release_preview_invocation (
  invocation_id uuid primary key references
    connected_readiness_private.release_preview_ceremony(invocation_id)
    on delete cascade,
  composition_manifest_sha256 text not null
    check(composition_manifest_sha256~'^[0-9a-f]{64}$'),
  database_contract_sha256 text not null
    check(database_contract_sha256~'^[0-9a-f]{64}$'),
  database_target_fingerprint text not null
    check(database_target_fingerprint~'^[0-9a-f]{32}$'),
  provider_contract_sha256 text not null
    check(provider_contract_sha256~'^[0-9a-f]{64}$'),
  deployment_id text not null check(deployment_id~'^dpl_[A-Za-z0-9]{8,}$'),
  commit_sha text not null check(commit_sha~'^[0-9a-f]{40}$'),
  host_configuration_ciphertext_sha256 text not null
    check(host_configuration_ciphertext_sha256~'^[0-9a-f]{64}$'),
  root_key_id text not null
    check(root_key_id~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$'),
  release_preview_contract_sha256 text not null
    check(release_preview_contract_sha256~'^[0-9a-f]{64}$'),
  descriptor_matrix_sha256 text not null
    check(descriptor_matrix_sha256~'^[0-9a-f]{64}$'),
  dedicated_account_attestation_sha256 text not null
    check(dedicated_account_attestation_sha256~'^[0-9a-f]{64}$'),
  effect_manifest_sha256 text not null
    check(effect_manifest_sha256~'^[0-9a-f]{64}$'),
  google_account_kind text not null
    check(google_account_kind in ('personal','work_school')),
  status text not null check(status in ('running','settled','attested','failed')),
  created_at timestamptz not null,
  settled_at timestamptz,
  attested_at timestamptz,
  constraint connected_release_preview_invocation_state check(
    (status='running' and settled_at is null and attested_at is null)
    or (status='settled' and settled_at is not null and attested_at is null)
    or (status='attested' and settled_at is not null and attested_at is not null)
    or (status='failed' and attested_at is null))
);
comment on table connected_readiness_private.release_preview_invocation is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_INVOCATION_V1_EXACT_DEPLOYMENT_CONTENT_FREE';
alter table connected_readiness_private.release_preview_invocation enable row level security;
alter table connected_readiness_private.release_preview_invocation force row level security;
revoke all on table connected_readiness_private.release_preview_invocation
  from public,anon,authenticated,service_role;

create table if not exists connected_readiness_private.release_preview_effect (
  effect_id uuid primary key,
  invocation_id uuid not null references
    connected_readiness_private.release_preview_invocation(invocation_id)
    on delete cascade,
  provider text not null check(provider in ('google','microsoft')),
  account_kind text not null check(account_kind in ('personal','work_school')),
  resource text not null check(resource in ('mail','calendar')),
  marker_sha256 text not null check(marker_sha256~'^[0-9a-f]{64}$'),
  phase text not null check(phase in (
    'pending','dispatched','observed','cleanup','clean',
    'retained_test_artifact','effect_unknown')),
  revision bigint not null default 0 check(revision>=0),
  artifact_id_sha256 text check(artifact_id_sha256~'^[0-9a-f]{64}$'),
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(invocation_id,provider,account_kind,resource),
  unique(invocation_id,marker_sha256),
  constraint connected_release_preview_effect_account_matrix check(
    (provider='google') or (provider='microsoft'))
);
comment on table connected_readiness_private.release_preview_effect is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_EFFECT_V1_CONTENT_FREE_CRASH_RECOVERY';
alter table connected_readiness_private.release_preview_effect enable row level security;
alter table connected_readiness_private.release_preview_effect force row level security;
revoke all on table connected_readiness_private.release_preview_effect
  from public,anon,authenticated,service_role;

create table if not exists connected_readiness_private.release_preview_authority (
  invocation_id uuid not null references
    connected_readiness_private.release_preview_invocation(invocation_id)
    on delete cascade,
  provider text not null check(provider in ('google','microsoft')),
  account_kind text not null check(account_kind in ('personal','work_school')),
  phase text not null check(phase in (
    'pending','revocation_dispatched','revocation_attested','local_retired')),
  revision bigint not null default 0 check(revision>=0),
  provider_receipt_sha256 text
    check(provider_receipt_sha256~'^[0-9a-f]{64}$'),
  created_at timestamptz not null,
  updated_at timestamptz not null,
  primary key(invocation_id,provider,account_kind),
  constraint connected_release_preview_authority_provider_truth check(
    (provider='google' and (
      (phase in ('pending','revocation_dispatched')
       and provider_receipt_sha256 is null)
      or (phase in ('revocation_attested','local_retired')
          and provider_receipt_sha256 is not null)))
    or (provider='microsoft' and phase in ('pending','local_retired')
        and provider_receipt_sha256 is null))
);
comment on table connected_readiness_private.release_preview_authority is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_AUTHORITY_V1_CRASH_RECOVERABLE_REVOCATION_AND_RETIREMENT';
alter table connected_readiness_private.release_preview_authority
  enable row level security;
alter table connected_readiness_private.release_preview_authority
  force row level security;
revoke all on table connected_readiness_private.release_preview_authority
  from public,anon,authenticated,service_role;

create table if not exists connected_readiness_private.provider_smoke_challenge (
  singleton boolean primary key default true check(singleton),
  challenge_id uuid not null unique,
  composition_manifest_sha256 text not null
    check(composition_manifest_sha256~'^[0-9a-f]{64}$'),
  database_contract_sha256 text not null
    check(database_contract_sha256~'^[0-9a-f]{64}$'),
  database_target_fingerprint text not null
    check(database_target_fingerprint~'^[0-9a-f]{32}$'),
  provider_contract_sha256 text not null
    check(provider_contract_sha256~'^[0-9a-f]{64}$'),
  deployment_id text not null
    check(deployment_id~'^dpl_[A-Za-z0-9]{8,}$'),
  commit_sha text not null check(commit_sha~'^[0-9a-f]{40}$'),
  host_configuration_ciphertext_sha256 text not null
    check(host_configuration_ciphertext_sha256~'^[0-9a-f]{64}$'),
  root_key_id text not null
    check(root_key_id~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$'),
  release_preview_contract_sha256 text not null
    check(release_preview_contract_sha256~'^[0-9a-f]{64}$'),
  release_preview_descriptor_matrix_sha256 text not null
    check(release_preview_descriptor_matrix_sha256~'^[0-9a-f]{64}$'),
  release_preview_dedicated_account_attestation_sha256 text not null
    check(release_preview_dedicated_account_attestation_sha256~'^[0-9a-f]{64}$'),
  release_preview_invocation_id uuid not null,
  release_preview_effect_manifest_sha256 text not null
    check(release_preview_effect_manifest_sha256~'^[0-9a-f]{64}$'),
  issued_at timestamptz not null,
  expires_at timestamptz not null,
  constraint connected_provider_smoke_challenge_lifetime check(
    expires_at>issued_at and expires_at<=issued_at+interval '15 minutes')
);
comment on table connected_readiness_private.provider_smoke_challenge is
  'ASK_CRUMP_CONNECTED_PROVIDER_SMOKE_CHALLENGE_V1_CONTENT_FREE_ONE_USE';
alter table connected_readiness_private.provider_smoke_challenge
  enable row level security;
alter table connected_readiness_private.provider_smoke_challenge
  force row level security;
revoke all on table connected_readiness_private.provider_smoke_challenge
  from public,anon,authenticated,service_role;

create table if not exists connected_readiness_private.provider_smoke (
  singleton boolean primary key default true check(singleton),
  challenge_id uuid not null unique,
  challenge_issued_at timestamptz not null,
  composition_manifest_sha256 text not null
    check(composition_manifest_sha256~'^[0-9a-f]{64}$'),
  database_contract_sha256 text not null
    check(database_contract_sha256~'^[0-9a-f]{64}$'),
  database_target_fingerprint text not null
    check(database_target_fingerprint~'^[0-9a-f]{32}$'),
  provider_contract_sha256 text not null
    check(provider_contract_sha256~'^[0-9a-f]{64}$'),
  deployment_id text not null
    check(deployment_id~'^dpl_[A-Za-z0-9]{8,}$'),
  commit_sha text not null check(commit_sha~'^[0-9a-f]{40}$'),
  host_configuration_ciphertext_sha256 text not null
    check(host_configuration_ciphertext_sha256~'^[0-9a-f]{64}$'),
  root_key_id text not null
    check(root_key_id~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$'),
  release_preview_contract_sha256 text not null
    check(release_preview_contract_sha256~'^[0-9a-f]{64}$'),
  release_preview_descriptor_matrix_sha256 text not null
    check(release_preview_descriptor_matrix_sha256~'^[0-9a-f]{64}$'),
  release_preview_dedicated_account_attestation_sha256 text not null
    check(release_preview_dedicated_account_attestation_sha256~'^[0-9a-f]{64}$'),
  release_preview_invocation_id uuid not null,
  release_preview_effect_manifest_sha256 text not null
    check(release_preview_effect_manifest_sha256~'^[0-9a-f]{64}$'),
  provider_smoke_attestation_sha256 text not null
    check(provider_smoke_attestation_sha256~'^[0-9a-f]{64}$'),
  checked_at timestamptz not null
);
comment on table connected_readiness_private.provider_smoke is
  'ASK_CRUMP_CONNECTED_PROVIDER_SMOKE_V1_CONTENT_FREE_DURABLE_EXACT_DEPLOYMENT';
alter table connected_readiness_private.provider_smoke enable row level security;
alter table connected_readiness_private.provider_smoke force row level security;
revoke all on table connected_readiness_private.provider_smoke
  from public,anon,authenticated,service_role;

create or replace function public.connected_app_claim_release_preview_ceremony_v1(
  p_claim_id uuid,
  p_owner_id uuid,
  p_session_binding_sha256 text,
  p_confirmation_sha256 text,
  p_deployment_id text,
  p_commit_sha text,
  p_host_configuration_ciphertext_sha256 text
)
returns table(
  invocation_id uuid,
  issued_at timestamptz,
  expires_at timestamptz,
  recovery boolean,
  deployment_id text,
  commit_sha text,
  host_configuration_ciphertext_sha256 text
)
language plpgsql volatile security definer set search_path='' as $fn$
declare
  reference timestamptz:=pg_catalog.statement_timestamp();
  ceremony connected_readiness_private.release_preview_ceremony%rowtype;
  is_recovery boolean:=false;
begin
  if p_claim_id is null or p_owner_id is null
     or p_session_binding_sha256!~'^[0-9a-f]{64}$'
     or p_confirmation_sha256!~'^[0-9a-f]{64}$'
     or p_deployment_id!~'^dpl_[A-Za-z0-9]{8,}$'
     or p_commit_sha!~'^[0-9a-f]{40}$'
     or p_host_configuration_ciphertext_sha256!~'^[0-9a-f]{64}$' then
    raise exception 'connected release preview claim is invalid'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  perform connected_app_private.owner_lock_v1(
    '00000000-0000-4000-8000-000000000069'::uuid);
  select * into ceremony
  from connected_readiness_private.release_preview_ceremony
  where status='running' for update;
  if not found then
    if exists(
      select 1
      from connected_readiness_private.release_preview_ceremony as history
      where history.owner_id<>p_owner_id
    ) then
      raise exception 'connected release preview history owner drifted'
        using errcode='55000';
    end if;
    if exists(
      select 1
      from connected_readiness_private.release_preview_ceremony as history
      where history.owner_id=p_owner_id
        and history.status in ('succeeded','failed')
        and history.deployment_id=p_deployment_id
        and history.commit_sha=p_commit_sha
        and history.host_configuration_ciphertext_sha256=
          p_host_configuration_ciphertext_sha256
    ) then
      raise exception 'connected release preview ceremony is terminal'
        using errcode='55000';
    end if;
    insert into connected_readiness_private.release_preview_ceremony(
      invocation_id,claim_id,owner_id,session_binding_sha256,
      confirmation_sha256,deployment_id,commit_sha,
      host_configuration_ciphertext_sha256,status,recovery_count,
      issued_at,expires_at,completed_at)
    values(
      pg_catalog.gen_random_uuid(),p_claim_id,p_owner_id,
      p_session_binding_sha256,p_confirmation_sha256,p_deployment_id,
      p_commit_sha,p_host_configuration_ciphertext_sha256,'running',0,
      reference,reference+interval '15 minutes',null)
    returning * into ceremony;
  else
    if ceremony.owner_id<>p_owner_id
       or ceremony.session_binding_sha256<>p_session_binding_sha256
       or ceremony.confirmation_sha256<>p_confirmation_sha256
       or ceremony.deployment_id<>p_deployment_id
       or ceremony.commit_sha<>p_commit_sha
       or ceremony.host_configuration_ciphertext_sha256<>
          p_host_configuration_ciphertext_sha256 then
      raise exception 'connected release preview claim tuple drifted'
        using errcode='55000';
    end if;
    if ceremony.expires_at>reference then
      if ceremony.claim_id<>p_claim_id then
        raise exception 'connected release preview ceremony is already claimed'
          using errcode='55P03';
      end if;
    else
      if ceremony.recovery_count>=100 then
        raise exception 'connected release preview recovery limit reached'
          using errcode='55000';
      end if;
      update connected_readiness_private.release_preview_ceremony
      set claim_id=p_claim_id,issued_at=reference,
          expires_at=reference+interval '15 minutes',
          recovery_count=recovery_count+1
      where invocation_id=ceremony.invocation_id
      returning * into ceremony;
      is_recovery:=true;
    end if;
  end if;
  return query select ceremony.invocation_id,ceremony.issued_at,
    ceremony.expires_at,is_recovery,ceremony.deployment_id,
    ceremony.commit_sha,ceremony.host_configuration_ciphertext_sha256;
end;
$fn$;
comment on function public.connected_app_claim_release_preview_ceremony_v1(
  uuid,uuid,text,text,text,text,text) is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_CLAIM_V1_ONE_USE_FRESH_RECOVERY_LEASE';

create or replace function public.connected_app_read_release_preview_ceremony_v1(
  p_claim_id uuid,
  p_owner_id uuid,
  p_session_binding_sha256 text,
  p_confirmation_sha256 text,
  p_deployment_id text,
  p_commit_sha text,
  p_host_configuration_ciphertext_sha256 text
)
returns table(
  invocation_id uuid,
  issued_at timestamptz,
  expires_at timestamptz,
  recovery boolean,
  deployment_id text,
  commit_sha text,
  host_configuration_ciphertext_sha256 text
)
language sql stable security definer set search_path='' as $fn$
  select ceremony.invocation_id,ceremony.issued_at,ceremony.expires_at,
    ceremony.recovery_count>0,ceremony.deployment_id,ceremony.commit_sha,
    ceremony.host_configuration_ciphertext_sha256
  from connected_readiness_private.release_preview_ceremony as ceremony
  where ceremony.claim_id=p_claim_id
    and ceremony.owner_id=p_owner_id
    and ceremony.session_binding_sha256=p_session_binding_sha256
    and ceremony.confirmation_sha256=p_confirmation_sha256
    and ceremony.deployment_id=p_deployment_id
    and ceremony.commit_sha=p_commit_sha
    and ceremony.host_configuration_ciphertext_sha256=
      p_host_configuration_ciphertext_sha256
    and ceremony.status='running'
    and ceremony.expires_at>pg_catalog.statement_timestamp()
$fn$;
comment on function public.connected_app_read_release_preview_ceremony_v1(
  uuid,uuid,text,text,text,text,text) is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_READ_CLAIM_V1_EXACT_CURRENT_CLAIM';

create or replace function public.connected_app_release_preview_begin_v1(
  p_invocation_id uuid,
  p_release_preview_contract_sha256 text,
  p_descriptor_matrix_sha256 text,
  p_dedicated_account_attestation_sha256 text,
  p_effect_manifest_sha256 text,
  p_google_account_kind text,
  p_effects jsonb,
  p_composition_manifest_sha256 text,
  p_database_contract_sha256 text,
  p_database_target_fingerprint text,
  p_provider_contract_sha256 text,
  p_deployment_id text,
  p_commit_sha text,
  p_host_configuration_ciphertext_sha256 text,
  p_root_key_id text
)
returns jsonb
language plpgsql volatile security definer set search_path='' as $fn$
declare
  reference timestamptz:=pg_catalog.statement_timestamp();
  ceremony connected_readiness_private.release_preview_ceremony%rowtype;
  existing connected_readiness_private.release_preview_invocation%rowtype;
  effect_count integer;
  distinct_count integer;
  matrix_count integer;
begin
  if p_invocation_id is null
     or p_release_preview_contract_sha256!~'^[0-9a-f]{64}$'
     or p_descriptor_matrix_sha256!~'^[0-9a-f]{64}$'
     or p_dedicated_account_attestation_sha256!~'^[0-9a-f]{64}$'
     or p_effect_manifest_sha256!~'^[0-9a-f]{64}$'
     or p_google_account_kind not in ('personal','work_school')
     or pg_catalog.jsonb_typeof(p_effects)<>'array'
     or pg_catalog.jsonb_array_length(p_effects)<>6
     or p_composition_manifest_sha256!~'^[0-9a-f]{64}$'
     or p_database_contract_sha256<>
       '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a'
     or p_database_target_fingerprint!~'^[0-9a-f]{32}$'
     or p_provider_contract_sha256<>
       'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6'
     or p_deployment_id!~'^dpl_[A-Za-z0-9]{8,}$'
     or p_commit_sha!~'^[0-9a-f]{40}$'
     or p_host_configuration_ciphertext_sha256!~'^[0-9a-f]{64}$'
     or p_root_key_id!~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$' then
    raise exception 'connected release preview begin contract is invalid'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(
    '00000000-0000-4000-8000-000000000069'::uuid);
  select * into ceremony
  from connected_readiness_private.release_preview_ceremony
  where invocation_id=p_invocation_id for update;
  if not found or ceremony.status<>'running' or ceremony.expires_at<=reference
     or ceremony.deployment_id<>p_deployment_id
     or ceremony.commit_sha<>p_commit_sha
     or ceremony.host_configuration_ciphertext_sha256<>
        p_host_configuration_ciphertext_sha256 then
    raise exception 'connected release preview ceremony is not current'
      using errcode='55000';
  end if;
  if not exists(
    select 1
    from connected_oauth_code_private.release_bootstrap_dedicated_attestations
      as attestation
    where attestation.owner_id=ceremony.owner_id
      and attestation.descriptor_matrix_sha256=p_descriptor_matrix_sha256
      and attestation.dedicated_account_attestation_sha256=
        p_dedicated_account_attestation_sha256
  ) then
    raise exception 'connected release preview dedicated-account attestation is absent'
      using errcode='55000';
  end if;
  select pg_catalog.count(*),pg_catalog.count(distinct effect_id),
    pg_catalog.count(distinct(provider,account_kind,resource))
    into effect_count,distinct_count,matrix_count
  from pg_catalog.jsonb_to_recordset(p_effects)
    as effect(effect_id uuid,provider text,account_kind text,
              resource text,marker_sha256 text)
  where effect.effect_id is not null
    and effect.provider in ('google','microsoft')
    and effect.account_kind in ('personal','work_school')
    and effect.resource in ('mail','calendar')
    and effect.marker_sha256~'^[0-9a-f]{64}$';
  if effect_count<>6 or distinct_count<>6 or matrix_count<>6
     or not exists(
       select 1 from pg_catalog.jsonb_to_recordset(p_effects)
         as effect(provider text,account_kind text,resource text)
       where effect.provider='google'
         and effect.account_kind=p_google_account_kind
         and effect.resource='mail')
     or not exists(
       select 1 from pg_catalog.jsonb_to_recordset(p_effects)
         as effect(provider text,account_kind text,resource text)
       where effect.provider='google'
         and effect.account_kind=p_google_account_kind
         and effect.resource='calendar')
     or (select pg_catalog.count(*) from pg_catalog.jsonb_to_recordset(p_effects)
         as effect(provider text,account_kind text,resource text)
         where effect.provider='microsoft'
           and effect.account_kind in ('personal','work_school')
           and effect.resource in ('mail','calendar'))<>4 then
    raise exception 'connected release preview effect matrix is invalid'
      using errcode='22023';
  end if;
  select * into existing
  from connected_readiness_private.release_preview_invocation
  where invocation_id=p_invocation_id for update;
  if not found then
    insert into connected_readiness_private.release_preview_invocation(
      invocation_id,composition_manifest_sha256,database_contract_sha256,
      database_target_fingerprint,provider_contract_sha256,deployment_id,
      commit_sha,host_configuration_ciphertext_sha256,root_key_id,
      release_preview_contract_sha256,descriptor_matrix_sha256,
      dedicated_account_attestation_sha256,effect_manifest_sha256,
      google_account_kind,status,created_at)
    values(
      p_invocation_id,p_composition_manifest_sha256,p_database_contract_sha256,
      p_database_target_fingerprint,p_provider_contract_sha256,p_deployment_id,
      p_commit_sha,p_host_configuration_ciphertext_sha256,p_root_key_id,
      p_release_preview_contract_sha256,p_descriptor_matrix_sha256,
      p_dedicated_account_attestation_sha256,p_effect_manifest_sha256,
      p_google_account_kind,'running',reference);
    insert into connected_readiness_private.release_preview_effect(
      effect_id,invocation_id,provider,account_kind,resource,marker_sha256,
      phase,revision,artifact_id_sha256,created_at,updated_at)
    select effect.effect_id,p_invocation_id,effect.provider,effect.account_kind,
      effect.resource,effect.marker_sha256,'pending',0,null,reference,reference
    from pg_catalog.jsonb_to_recordset(p_effects)
      as effect(effect_id uuid,provider text,account_kind text,
                resource text,marker_sha256 text);
    insert into connected_readiness_private.release_preview_authority(
      invocation_id,provider,account_kind,phase,revision,
      provider_receipt_sha256,created_at,updated_at)
    values
      (p_invocation_id,'google',p_google_account_kind,'pending',0,
       null,reference,reference),
      (p_invocation_id,'microsoft','personal','pending',0,
       null,reference,reference),
      (p_invocation_id,'microsoft','work_school','pending',0,
       null,reference,reference);
  else
    if existing.composition_manifest_sha256<>p_composition_manifest_sha256
       or existing.database_contract_sha256<>p_database_contract_sha256
       or existing.database_target_fingerprint<>p_database_target_fingerprint
       or existing.provider_contract_sha256<>p_provider_contract_sha256
       or existing.deployment_id<>p_deployment_id
       or existing.commit_sha<>p_commit_sha
       or existing.host_configuration_ciphertext_sha256<>
          p_host_configuration_ciphertext_sha256
       or existing.root_key_id<>p_root_key_id
       or existing.release_preview_contract_sha256<>
          p_release_preview_contract_sha256
       or existing.descriptor_matrix_sha256<>p_descriptor_matrix_sha256
       or existing.dedicated_account_attestation_sha256<>
          p_dedicated_account_attestation_sha256
       or existing.effect_manifest_sha256<>p_effect_manifest_sha256
       or existing.google_account_kind<>p_google_account_kind
       or existing.status not in ('running','settled') then
      raise exception 'connected release preview invocation replay drifted'
        using errcode='55000';
    end if;
  end if;
  if (select pg_catalog.count(*)
      from connected_readiness_private.release_preview_effect
      where invocation_id=p_invocation_id)<>6
     or (select pg_catalog.count(*)
         from connected_readiness_private.release_preview_authority
         where invocation_id=p_invocation_id)<>3 then
    raise exception 'connected release preview durable rows are incomplete'
      using errcode='55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'invocation_id',p_invocation_id,
    'effect_manifest_sha256',p_effect_manifest_sha256,
    'effects',6);
end;
$fn$;
comment on function public.connected_app_release_preview_begin_v1(
  uuid,text,text,text,text,text,jsonb,text,text,text,text,text,text,text,text) is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_BEGIN_V1_EXACT_SIX_EFFECTS';

create or replace function public.connected_app_release_preview_status_v1(
  p_invocation_id uuid
)
returns table(
  effect_id uuid,invocation_id uuid,provider text,account_kind text,
  resource text,marker_sha256 text,phase text,revision bigint,
  artifact_id_sha256 text
)
language sql stable security definer set search_path='' as $fn$
  select effect.effect_id,effect.invocation_id,effect.provider,
    effect.account_kind,effect.resource,effect.marker_sha256,effect.phase,
    effect.revision,effect.artifact_id_sha256
  from connected_readiness_private.release_preview_effect as effect
  join connected_readiness_private.release_preview_ceremony as ceremony
    on ceremony.invocation_id=effect.invocation_id
  where effect.invocation_id=p_invocation_id
    and ceremony.status='running'
    and ceremony.expires_at>pg_catalog.statement_timestamp()
  order by effect.provider,effect.account_kind,effect.resource
$fn$;
comment on function public.connected_app_release_preview_status_v1(uuid) is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_STATUS_V1_CONTENT_FREE_ACTIVE_LEASE';

create or replace function public.connected_app_release_preview_authority_status_v1(
  p_invocation_id uuid
)
returns table(
  invocation_id uuid,provider text,account_kind text,phase text,
  revision bigint,provider_receipt_sha256 text
)
language sql stable security definer set search_path='' as $fn$
  select authority.invocation_id,authority.provider,authority.account_kind,
    authority.phase,authority.revision,authority.provider_receipt_sha256
  from connected_readiness_private.release_preview_authority as authority
  join connected_readiness_private.release_preview_ceremony as ceremony
    on ceremony.invocation_id=authority.invocation_id
  where authority.invocation_id=p_invocation_id
    and ceremony.status='running'
    and ceremony.expires_at>pg_catalog.statement_timestamp()
  order by authority.provider,authority.account_kind
$fn$;
comment on function public.connected_app_release_preview_authority_status_v1(uuid) is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_AUTHORITY_STATUS_V1_ACTIVE_LEASE';

create or replace function public.connected_app_release_preview_authority_v1(
  p_invocation_id uuid,
  p_provider text,
  p_account_kind text,
  p_expected_revision bigint,
  p_expected_phase text,
  p_next_phase text,
  p_provider_receipt_sha256 text
)
returns jsonb
language plpgsql volatile security definer set search_path='' as $fn$
declare
  reference timestamptz:=pg_catalog.statement_timestamp();
  authority connected_readiness_private.release_preview_authority%rowtype;
  ceremony connected_readiness_private.release_preview_ceremony%rowtype;
  effective_receipt text;
begin
  if p_invocation_id is null
     or p_provider not in ('google','microsoft')
     or p_account_kind not in ('personal','work_school')
     or p_expected_revision<0
     or p_expected_phase not in (
       'pending','revocation_dispatched','revocation_attested','local_retired')
     or p_next_phase not in (
       'revocation_dispatched','revocation_attested','local_retired')
     or (p_provider_receipt_sha256 is not null
         and p_provider_receipt_sha256!~'^[0-9a-f]{64}$') then
    raise exception 'connected release preview authority transition is invalid'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(
    '00000000-0000-4000-8000-000000000069'::uuid);
  select * into ceremony
  from connected_readiness_private.release_preview_ceremony
  where invocation_id=p_invocation_id for update;
  if not found or ceremony.status<>'running' or ceremony.expires_at<=reference then
    raise exception 'connected release preview authority lease is absent'
      using errcode='55000';
  end if;
  select * into authority
  from connected_readiness_private.release_preview_authority
  where invocation_id=p_invocation_id and provider=p_provider
    and account_kind=p_account_kind for update;
  if not found then
    raise exception 'connected release preview authority is absent'
      using errcode='55000';
  end if;
  effective_receipt:=coalesce(
    p_provider_receipt_sha256,authority.provider_receipt_sha256);
  if authority.revision=p_expected_revision+1
     and authority.phase=p_next_phase
     and authority.provider_receipt_sha256 is not distinct from effective_receipt then
    return pg_catalog.to_jsonb(authority);
  end if;
  if authority.revision<>p_expected_revision
     or authority.phase<>p_expected_phase then
    raise exception 'connected release preview authority transition drifted'
      using errcode='55000';
  end if;
  if not (
    (p_provider='google' and (
      (authority.phase='pending' and p_next_phase='revocation_dispatched'
       and effective_receipt is null)
      or (authority.phase='revocation_dispatched'
          and p_next_phase='revocation_attested'
          and effective_receipt is not null)
      or (authority.phase='revocation_attested'
          and p_next_phase='local_retired'
          and effective_receipt is not null)))
    or (p_provider='microsoft' and authority.phase='pending'
        and p_next_phase='local_retired' and effective_receipt is null)
  ) then
    raise exception 'connected release preview authority transition is forbidden'
      using errcode='55000';
  end if;
  update connected_readiness_private.release_preview_authority
  set phase=p_next_phase,revision=revision+1,
      provider_receipt_sha256=effective_receipt,updated_at=reference
  where invocation_id=p_invocation_id and provider=p_provider
    and account_kind=p_account_kind
  returning * into authority;
  return pg_catalog.to_jsonb(authority);
end;
$fn$;
comment on function public.connected_app_release_preview_authority_v1(
  uuid,text,text,bigint,text,text,text) is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_AUTHORITY_V1_EXACT_REVOCATION_RETIREMENT_STATE_MACHINE';

create or replace function public.connected_app_release_preview_effect_v1(
  p_invocation_id uuid,
  p_effect_id uuid,
  p_expected_revision bigint,
  p_expected_phase text,
  p_next_phase text,
  p_artifact_id_sha256 text
)
returns jsonb
language plpgsql volatile security definer set search_path='' as $fn$
declare
  reference timestamptz:=pg_catalog.statement_timestamp();
  effect connected_readiness_private.release_preview_effect%rowtype;
  ceremony connected_readiness_private.release_preview_ceremony%rowtype;
  effective_artifact text;
begin
  if p_invocation_id is null or p_effect_id is null
     or p_expected_revision<0
     or p_expected_phase not in (
       'pending','dispatched','observed','cleanup','clean',
       'retained_test_artifact','effect_unknown')
     or p_next_phase not in (
       'dispatched','observed','cleanup','clean',
       'retained_test_artifact','effect_unknown')
     or (p_artifact_id_sha256 is not null
         and p_artifact_id_sha256!~'^[0-9a-f]{64}$') then
    raise exception 'connected release preview effect transition is invalid'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(
    '00000000-0000-4000-8000-000000000069'::uuid);
  select * into ceremony
  from connected_readiness_private.release_preview_ceremony
  where invocation_id=p_invocation_id for update;
  if not found or ceremony.status<>'running' or ceremony.expires_at<=reference then
    raise exception 'connected release preview effect lease is absent'
      using errcode='55000';
  end if;
  select * into effect
  from connected_readiness_private.release_preview_effect
  where invocation_id=p_invocation_id and effect_id=p_effect_id for update;
  if not found then
    raise exception 'connected release preview effect is absent'
      using errcode='55000';
  end if;
  effective_artifact:=coalesce(
    p_artifact_id_sha256,effect.artifact_id_sha256);
  if effect.revision=p_expected_revision+1 and effect.phase=p_next_phase
     and effect.artifact_id_sha256 is not distinct from effective_artifact then
    return pg_catalog.to_jsonb(effect);
  end if;
  if effect.revision<>p_expected_revision or effect.phase<>p_expected_phase then
    raise exception 'connected release preview effect transition drifted'
      using errcode='55000';
  end if;
  if not (
    (effect.phase='pending' and p_next_phase='dispatched')
    or (effect.phase='dispatched' and p_next_phase in ('observed','effect_unknown'))
    or (effect.phase='observed' and p_next_phase in ('cleanup','effect_unknown'))
    or (effect.phase='cleanup' and p_next_phase in (
      'clean','retained_test_artifact','effect_unknown'))
  ) then
    raise exception 'connected release preview effect transition is forbidden'
      using errcode='55000';
  end if;
  if p_next_phase in ('observed','retained_test_artifact')
     and effective_artifact is null then
    raise exception 'connected release preview effect artifact proof is absent'
      using errcode='22023';
  end if;
  if effect.resource='calendar' and p_next_phase='retained_test_artifact'
     or effect.resource='mail' and p_next_phase='clean' then
    raise exception 'connected release preview effect terminal truth is invalid'
      using errcode='55000';
  end if;
  update connected_readiness_private.release_preview_effect
  set phase=p_next_phase,revision=revision+1,
      artifact_id_sha256=effective_artifact,updated_at=reference
  where invocation_id=p_invocation_id and effect_id=p_effect_id
  returning * into effect;
  return pg_catalog.to_jsonb(effect);
end;
$fn$;
comment on function public.connected_app_release_preview_effect_v1(
  uuid,uuid,bigint,text,text,text) is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_EFFECT_V1_EXACT_STATE_MACHINE';

create or replace function public.connected_app_release_preview_finalize_v1(
  p_invocation_id uuid
)
returns jsonb
language plpgsql volatile security definer set search_path='' as $fn$
declare
  reference timestamptz:=pg_catalog.statement_timestamp();
  ceremony connected_readiness_private.release_preview_ceremony%rowtype;
begin
  perform connected_app_private.owner_lock_v1(
    '00000000-0000-4000-8000-000000000069'::uuid);
  select * into ceremony
  from connected_readiness_private.release_preview_ceremony
  where invocation_id=p_invocation_id for update;
  if not found or ceremony.status<>'running' or ceremony.expires_at<=reference then
    raise exception 'connected release preview finalize lease is absent'
      using errcode='55000';
  end if;
  if (select pg_catalog.count(*)
      from connected_readiness_private.release_preview_effect
      where invocation_id=p_invocation_id)<>6
     or (select pg_catalog.count(*)
         from connected_readiness_private.release_preview_effect
         where invocation_id=p_invocation_id and resource='calendar'
           and phase='clean')<>3
     or (select pg_catalog.count(*)
         from connected_readiness_private.release_preview_effect
         where invocation_id=p_invocation_id and resource='mail'
           and phase='retained_test_artifact')<>3 then
    raise exception 'connected release preview effects are unsettled'
      using errcode='55000';
  end if;
  if (select pg_catalog.count(*)
      from connected_readiness_private.release_preview_authority
      where invocation_id=p_invocation_id)<>3
     or (select pg_catalog.count(*)
         from connected_readiness_private.release_preview_authority
         where invocation_id=p_invocation_id
           and phase='local_retired')<>3
     or not exists(
       select 1
       from connected_readiness_private.release_preview_authority
       where invocation_id=p_invocation_id and provider='google'
         and phase='local_retired'
         and provider_receipt_sha256 is not null)
     or exists(
       select 1
       from connected_readiness_private.release_preview_authority
       where invocation_id=p_invocation_id and provider='microsoft'
         and provider_receipt_sha256 is not null) then
    raise exception 'connected release preview authorities are unsettled'
      using errcode='55000';
  end if;
  update connected_readiness_private.release_preview_invocation
  set status='settled',settled_at=coalesce(settled_at,reference)
  where invocation_id=p_invocation_id and status in ('running','settled');
  return pg_catalog.jsonb_build_object(
    'invocation_id',p_invocation_id,'status','clean','unsettled_effects',0);
end;
$fn$;
comment on function public.connected_app_release_preview_finalize_v1(uuid) is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_FINALIZE_V1_ZERO_UNSETTLED_EFFECTS';

create or replace function public.connected_app_release_preview_fail_v1(
  p_invocation_id uuid
)
returns jsonb
language plpgsql volatile security definer set search_path='' as $fn$
declare
  reference timestamptz:=pg_catalog.statement_timestamp();
  ceremony connected_readiness_private.release_preview_ceremony%rowtype;
  invocation connected_readiness_private.release_preview_invocation%rowtype;
  unknown_count integer;
begin
  if p_invocation_id is null then
    raise exception 'connected release preview failure binding is invalid'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(
    '00000000-0000-4000-8000-000000000069'::uuid);
  select * into ceremony
  from connected_readiness_private.release_preview_ceremony
  where invocation_id=p_invocation_id for update;
  if not found then
    raise exception 'connected release preview ceremony is absent'
      using errcode='55000';
  end if;
  select * into invocation
  from connected_readiness_private.release_preview_invocation
  where invocation_id=p_invocation_id for update;
  if not found then
    raise exception 'connected release preview invocation is absent'
      using errcode='55000';
  end if;
  if ceremony.status='failed' and invocation.status='failed' then
    select pg_catalog.count(*) into unknown_count
    from connected_readiness_private.release_preview_effect
    where invocation_id=p_invocation_id and phase='effect_unknown';
    return pg_catalog.jsonb_build_object(
      'invocation_id',p_invocation_id,'status','failed',
      'unknown_effects',unknown_count);
  end if;
  if ceremony.status<>'running' or invocation.status<>'running' then
    raise exception 'connected release preview failure state is not current'
      using errcode='55000';
  end if;
  if (select pg_catalog.count(*)
      from connected_readiness_private.release_preview_authority
      where invocation_id=p_invocation_id)<>3
     or (select pg_catalog.count(*)
         from connected_readiness_private.release_preview_authority
         where invocation_id=p_invocation_id and phase='local_retired')<>3 then
    raise exception 'connected release preview failure authorities are unsettled'
      using errcode='55000';
  end if;
  if exists(
    select 1 from connected_readiness_private.release_preview_effect
    where invocation_id=p_invocation_id and phase in ('observed','cleanup')
  ) then
    raise exception 'connected release preview failure artifacts are unsettled'
      using errcode='55000';
  end if;
  update connected_readiness_private.release_preview_effect
  set phase='effect_unknown',revision=revision+1,updated_at=reference
  where invocation_id=p_invocation_id
    and phase in ('pending','dispatched');
  select pg_catalog.count(*) into unknown_count
  from connected_readiness_private.release_preview_effect
  where invocation_id=p_invocation_id and phase='effect_unknown';
  update connected_readiness_private.release_preview_invocation
  set status='failed',settled_at=coalesce(settled_at,reference)
  where invocation_id=p_invocation_id and status='running';
  if not found then
    raise exception 'connected release preview invocation failure raced'
      using errcode='55000';
  end if;
  update connected_readiness_private.release_preview_ceremony
  set status='failed',completed_at=reference
  where invocation_id=p_invocation_id and status='running';
  if not found then
    raise exception 'connected release preview ceremony failure raced'
      using errcode='55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'invocation_id',p_invocation_id,'status','failed',
    'unknown_effects',unknown_count);
end;
$fn$;
comment on function public.connected_app_release_preview_fail_v1(uuid) is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_FAIL_V1_RETIRED_AUTHORITIES_NO_UNSETTLED_ARTIFACTS';

create or replace function
  public.connected_app_release_preview_retire_connection_v1(
    p_owner_id uuid,
    p_connection_id uuid,
    p_connection_incarnation_id uuid,
    p_expected_authorization_revision bigint,
    p_current_flow_nonce_sha256 text,
    p_authorization_snapshot_sha256 text,
    p_credential_ref_sha256 text,
    p_retirement_id uuid,
    p_retirement_binding_sha256 text
  )
returns jsonb
language plpgsql volatile security definer set search_path='' as $fn$
declare
  connection_row connected_app_private.connections%rowtype;
  reference timestamptz:=pg_catalog.statement_timestamp();
  credential_erased boolean;
begin
  if p_owner_id is null or p_connection_id is null
     or p_connection_incarnation_id is null or p_retirement_id is null
     or p_expected_authorization_revision<1
     or p_current_flow_nonce_sha256!~'^[0-9a-f]{64}$'
     or p_authorization_snapshot_sha256!~'^[0-9a-f]{64}$'
     or p_credential_ref_sha256!~'^[0-9a-f]{64}$'
     or p_retirement_binding_sha256!~'^[0-9a-f]{64}$' then
    raise exception 'connected release preview retirement binding is invalid'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select connection.* into connection_row
  from connected_app_private.connections as connection
  where connection.owner_id=p_owner_id and connection.id=p_connection_id
  for update;
  if not found then
    raise exception 'connected release preview connection is absent'
      using errcode='55000';
  end if;
  if connection_row.authorization_state='active' then
    if connection_row.connection_incarnation_id<>p_connection_incarnation_id
       or connection_row.authorization_revision<>
          p_expected_authorization_revision
       or connection_row.current_flow_nonce_sha256<>
          p_current_flow_nonce_sha256
       or connection_row.authorization_snapshot_sha256<>
          p_authorization_snapshot_sha256
       or connection_row.credential_ref_sha256<>p_credential_ref_sha256
       or connection_row.broker_credential_ref is null
       or connection_row.revoked_at is not null then
      raise exception 'connected release preview retirement authority changed'
        using errcode='55000';
    end if;
    update connected_app_private.connections as connection
    set authorization_revision=connection.authorization_revision+1,
        authorization_state='revoked',broker_credential_ref=null,
        credential_ref_sha256=null,current_flow_nonce_sha256=null,
        authorization_expires_at=null,revoked_at=reference,updated_at=reference
    where connection.owner_id=p_owner_id and connection.id=p_connection_id
    returning * into connection_row;
    update connected_app_private.oauth_flows as flow
    set status='invalidated',updated_at=reference
    where flow.owner_id=p_owner_id and flow.connection_id=p_connection_id
      and flow.status not in ('completed','invalidated');
  elsif connection_row.authorization_state='revoked' then
    if connection_row.connection_incarnation_id<>p_connection_incarnation_id
       or connection_row.authorization_revision<>
          p_expected_authorization_revision+1
       or connection_row.authorization_snapshot_sha256<>
          p_authorization_snapshot_sha256
       or connection_row.broker_credential_ref is not null
       or connection_row.credential_ref_sha256 is not null
       or connection_row.current_flow_nonce_sha256 is not null
       or connection_row.authorization_expires_at is not null
       or connection_row.revoked_at is null then
      raise exception 'connected release preview retirement replay drifted'
        using errcode='55000';
    end if;
  else
    raise exception 'connected release preview retirement state is invalid'
      using errcode='55000';
  end if;
  select exists(
    select 1
    from connected_app_private.credential_secret_tombstones as tombstone
    where tombstone.credential_handle_sha256=p_credential_ref_sha256
  ) and not exists(
    select 1
    from connected_app_private.credential_envelopes as envelope
    where envelope.credential_handle_sha256=p_credential_ref_sha256
  ) into credential_erased;
  if credential_erased is not true then
    raise exception 'connected release preview credential erasure was not observed'
      using errcode='55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'retired',true,'retirement_id',p_retirement_id,
    'retirement_binding_sha256',p_retirement_binding_sha256,
    'connection_id',connection_row.id,
    'authorization_revision',connection_row.authorization_revision,
    'revoked_at',connection_row.revoked_at,'credential_erased',true
  );
end;
$fn$;
comment on function
  public.connected_app_release_preview_retire_connection_v1(
    uuid,uuid,uuid,bigint,text,text,text,uuid,text
  ) is
  'ASK_CRUMP_CONNECTED_RELEASE_PREVIEW_RETIRE_V1_LOCAL_AUTHORITY_AND_CREDENTIAL_ERASURE';

create or replace function public.connected_app_issue_provider_smoke_challenge_v1(
  p_composition_manifest_sha256 text,
  p_database_contract_sha256 text,
  p_database_target_fingerprint text,
  p_provider_contract_sha256 text,
  p_deployment_id text,
  p_commit_sha text,
  p_host_configuration_ciphertext_sha256 text,
  p_root_key_id text,
  p_release_preview_contract_sha256 text,
  p_release_preview_descriptor_matrix_sha256 text,
  p_release_preview_dedicated_account_attestation_sha256 text,
  p_release_preview_invocation_id uuid,
  p_release_preview_effect_manifest_sha256 text
)
returns table(
  challenge_id uuid,
  composition_manifest_sha256 text,
  database_contract_sha256 text,
  database_target_fingerprint text,
  provider_contract_sha256 text,
  deployment_id text,
  commit_sha text,
  host_configuration_ciphertext_sha256 text,
  root_key_id text,
  release_preview_contract_sha256 text,
  release_preview_descriptor_matrix_sha256 text,
  release_preview_dedicated_account_attestation_sha256 text,
  release_preview_invocation_id uuid,
  release_preview_effect_manifest_sha256 text,
  challenge_issued_at timestamptz,
  challenge_expires_at timestamptz
)
language plpgsql volatile security definer set search_path='' as $fn$
declare
  reference timestamptz:=pg_catalog.statement_timestamp();
  issued_challenge_id uuid:=pg_catalog.gen_random_uuid();
begin
  if p_composition_manifest_sha256 is null
     or p_composition_manifest_sha256!~'^[0-9a-f]{64}$'
     or p_database_contract_sha256<>
       '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a'
     or p_database_target_fingerprint!~'^[0-9a-f]{32}$'
     or p_provider_contract_sha256<>
       'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6'
     or p_deployment_id is null
     or p_deployment_id!~'^dpl_[A-Za-z0-9]{8,}$'
     or p_commit_sha is null or p_commit_sha!~'^[0-9a-f]{40}$'
     or p_host_configuration_ciphertext_sha256 is null
     or p_host_configuration_ciphertext_sha256!~'^[0-9a-f]{64}$'
     or p_root_key_id is null
     or p_root_key_id!~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$'
     or p_release_preview_contract_sha256<>
       '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f'
     or p_release_preview_descriptor_matrix_sha256!~'^[0-9a-f]{64}$'
     or p_release_preview_dedicated_account_attestation_sha256!~'^[0-9a-f]{64}$'
     or p_release_preview_invocation_id is null
     or p_release_preview_effect_manifest_sha256!~'^[0-9a-f]{64}$' then
    raise exception 'connected provider smoke challenge contract is invalid'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(
    '00000000-0000-4000-8000-000000000069'::uuid);
  if not exists(
    select 1
    from connected_readiness_private.release_preview_invocation as invocation
    join connected_readiness_private.release_preview_ceremony as ceremony
      on ceremony.invocation_id=invocation.invocation_id
    where invocation.invocation_id=p_release_preview_invocation_id
      and invocation.status='settled'
      and ceremony.status='running' and ceremony.expires_at>reference
      and invocation.composition_manifest_sha256=p_composition_manifest_sha256
      and invocation.database_contract_sha256=p_database_contract_sha256
      and invocation.database_target_fingerprint=p_database_target_fingerprint
      and invocation.provider_contract_sha256=p_provider_contract_sha256
      and invocation.deployment_id=p_deployment_id
      and invocation.commit_sha=p_commit_sha
      and invocation.host_configuration_ciphertext_sha256=
        p_host_configuration_ciphertext_sha256
      and invocation.root_key_id=p_root_key_id
      and invocation.release_preview_contract_sha256=
        p_release_preview_contract_sha256
      and invocation.descriptor_matrix_sha256=
        p_release_preview_descriptor_matrix_sha256
      and invocation.dedicated_account_attestation_sha256=
        p_release_preview_dedicated_account_attestation_sha256
      and invocation.effect_manifest_sha256=
        p_release_preview_effect_manifest_sha256
  ) then
    raise exception 'connected provider smoke effects are not settled'
      using errcode='55000';
  end if;
  insert into connected_readiness_private.provider_smoke_challenge(
    singleton,challenge_id,composition_manifest_sha256,
    database_contract_sha256,database_target_fingerprint,
    provider_contract_sha256,deployment_id,commit_sha,
    host_configuration_ciphertext_sha256,root_key_id,
    release_preview_contract_sha256,
    release_preview_descriptor_matrix_sha256,
    release_preview_dedicated_account_attestation_sha256,
    release_preview_invocation_id,release_preview_effect_manifest_sha256,
    issued_at,expires_at)
  values(
    true,issued_challenge_id,p_composition_manifest_sha256,
    p_database_contract_sha256,p_database_target_fingerprint,
    p_provider_contract_sha256,p_deployment_id,p_commit_sha,
    p_host_configuration_ciphertext_sha256,p_root_key_id,
    p_release_preview_contract_sha256,
    p_release_preview_descriptor_matrix_sha256,
    p_release_preview_dedicated_account_attestation_sha256,
    p_release_preview_invocation_id,p_release_preview_effect_manifest_sha256,
    reference,reference+interval '15 minutes')
  on conflict(singleton) do update set
    challenge_id=excluded.challenge_id,
    composition_manifest_sha256=excluded.composition_manifest_sha256,
    database_contract_sha256=excluded.database_contract_sha256,
    database_target_fingerprint=excluded.database_target_fingerprint,
    provider_contract_sha256=excluded.provider_contract_sha256,
    deployment_id=excluded.deployment_id,
    commit_sha=excluded.commit_sha,
    host_configuration_ciphertext_sha256=
      excluded.host_configuration_ciphertext_sha256,
    root_key_id=excluded.root_key_id,
    release_preview_contract_sha256=excluded.release_preview_contract_sha256,
    release_preview_descriptor_matrix_sha256=
      excluded.release_preview_descriptor_matrix_sha256,
    release_preview_dedicated_account_attestation_sha256=
      excluded.release_preview_dedicated_account_attestation_sha256,
    release_preview_invocation_id=excluded.release_preview_invocation_id,
    release_preview_effect_manifest_sha256=
      excluded.release_preview_effect_manifest_sha256,
    issued_at=excluded.issued_at,
    expires_at=excluded.expires_at;
  return query select
    challenge.challenge_id,challenge.composition_manifest_sha256,
    challenge.database_contract_sha256,challenge.database_target_fingerprint,
    challenge.provider_contract_sha256,challenge.deployment_id,
    challenge.commit_sha,challenge.host_configuration_ciphertext_sha256,
    challenge.root_key_id,challenge.release_preview_contract_sha256,
    challenge.release_preview_descriptor_matrix_sha256,
    challenge.release_preview_dedicated_account_attestation_sha256,
    challenge.release_preview_invocation_id,
    challenge.release_preview_effect_manifest_sha256,
    challenge.issued_at,challenge.expires_at
  from connected_readiness_private.provider_smoke_challenge as challenge
  where challenge.singleton;
end;
$fn$;
comment on function public.connected_app_issue_provider_smoke_challenge_v1(
  text,text,text,text,text,text,text,text,text,text,text,uuid,text
) is 'ASK_CRUMP_CONNECTED_PROVIDER_SMOKE_CHALLENGE_V1_SERVICE_ROLE_ONE_USE';

create or replace function public.connected_app_record_provider_smoke_v1(
  p_composition_manifest_sha256 text,
  p_database_contract_sha256 text,
  p_database_target_fingerprint text,
  p_provider_contract_sha256 text,
  p_deployment_id text,
  p_commit_sha text,
  p_host_configuration_ciphertext_sha256 text,
  p_root_key_id text,
  p_release_preview_contract_sha256 text,
  p_release_preview_descriptor_matrix_sha256 text,
  p_release_preview_dedicated_account_attestation_sha256 text,
  p_release_preview_invocation_id uuid,
  p_release_preview_effect_manifest_sha256 text,
  p_challenge_id uuid,
  p_provider_smoke_attestation_sha256 text
)
returns table(
  composition_manifest_sha256 text,
  database_contract_sha256 text,
  database_target_fingerprint text,
  provider_contract_sha256 text,
  deployment_id text,
  commit_sha text,
  host_configuration_ciphertext_sha256 text,
  root_key_id text,
  release_preview_contract_sha256 text,
  release_preview_descriptor_matrix_sha256 text,
  release_preview_dedicated_account_attestation_sha256 text,
  release_preview_invocation_id uuid,
  release_preview_effect_manifest_sha256 text,
  provider_smoke_checked_at timestamptz
)
language plpgsql volatile security definer set search_path='' as $fn$
declare
  reference timestamptz:=pg_catalog.statement_timestamp();
  challenge connected_readiness_private.provider_smoke_challenge%rowtype;
begin
  if p_challenge_id is null
     or p_provider_smoke_attestation_sha256 is null
     or p_provider_smoke_attestation_sha256!~'^[0-9a-f]{64}$' then
    raise exception 'connected provider smoke receipt is invalid'
      using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(
    '00000000-0000-4000-8000-000000000069'::uuid);
  select * into challenge
  from connected_readiness_private.provider_smoke_challenge as challenge_row
  where challenge_row.singleton
    and challenge_row.challenge_id=p_challenge_id
    and challenge_row.composition_manifest_sha256=p_composition_manifest_sha256
    and challenge_row.database_contract_sha256=p_database_contract_sha256
    and challenge_row.database_target_fingerprint=p_database_target_fingerprint
    and challenge_row.provider_contract_sha256=p_provider_contract_sha256
    and challenge_row.deployment_id=p_deployment_id
    and challenge_row.commit_sha=p_commit_sha
    and challenge_row.host_configuration_ciphertext_sha256=
      p_host_configuration_ciphertext_sha256
    and challenge_row.root_key_id=p_root_key_id
    and challenge_row.release_preview_contract_sha256=
      p_release_preview_contract_sha256
    and challenge_row.release_preview_descriptor_matrix_sha256=
      p_release_preview_descriptor_matrix_sha256
    and challenge_row.release_preview_dedicated_account_attestation_sha256=
      p_release_preview_dedicated_account_attestation_sha256
    and challenge_row.release_preview_invocation_id=
      p_release_preview_invocation_id
    and challenge_row.release_preview_effect_manifest_sha256=
      p_release_preview_effect_manifest_sha256
    and challenge_row.expires_at>reference
  for update;
  if not found then
    raise exception 'connected provider smoke challenge is absent or consumed'
      using errcode='55000';
  end if;
  insert into connected_readiness_private.provider_smoke(
    singleton,challenge_id,challenge_issued_at,composition_manifest_sha256,
    database_contract_sha256,database_target_fingerprint,
    provider_contract_sha256,deployment_id,commit_sha,
    host_configuration_ciphertext_sha256,root_key_id,
    release_preview_contract_sha256,
    release_preview_descriptor_matrix_sha256,
    release_preview_dedicated_account_attestation_sha256,
    release_preview_invocation_id,release_preview_effect_manifest_sha256,
    provider_smoke_attestation_sha256,checked_at)
  values(
    true,challenge.challenge_id,challenge.issued_at,
    challenge.composition_manifest_sha256,challenge.database_contract_sha256,
    challenge.database_target_fingerprint,challenge.provider_contract_sha256,
    challenge.deployment_id,challenge.commit_sha,
    challenge.host_configuration_ciphertext_sha256,challenge.root_key_id,
    challenge.release_preview_contract_sha256,
    challenge.release_preview_descriptor_matrix_sha256,
    challenge.release_preview_dedicated_account_attestation_sha256,
    challenge.release_preview_invocation_id,
    challenge.release_preview_effect_manifest_sha256,
    p_provider_smoke_attestation_sha256,reference)
  on conflict(singleton) do update set
    challenge_id=excluded.challenge_id,
    challenge_issued_at=excluded.challenge_issued_at,
    composition_manifest_sha256=excluded.composition_manifest_sha256,
    database_contract_sha256=excluded.database_contract_sha256,
    database_target_fingerprint=excluded.database_target_fingerprint,
    provider_contract_sha256=excluded.provider_contract_sha256,
    deployment_id=excluded.deployment_id,
    commit_sha=excluded.commit_sha,
    host_configuration_ciphertext_sha256=
      excluded.host_configuration_ciphertext_sha256,
    root_key_id=excluded.root_key_id,
    release_preview_contract_sha256=excluded.release_preview_contract_sha256,
    release_preview_descriptor_matrix_sha256=
      excluded.release_preview_descriptor_matrix_sha256,
    release_preview_dedicated_account_attestation_sha256=
      excluded.release_preview_dedicated_account_attestation_sha256,
    release_preview_invocation_id=excluded.release_preview_invocation_id,
    release_preview_effect_manifest_sha256=
      excluded.release_preview_effect_manifest_sha256,
    provider_smoke_attestation_sha256=excluded.provider_smoke_attestation_sha256,
    checked_at=excluded.checked_at;
  update connected_readiness_private.release_preview_invocation
  set status='attested',attested_at=reference
  where invocation_id=p_release_preview_invocation_id and status='settled';
  if not found then
    raise exception 'connected release preview invocation is not settled'
      using errcode='55000';
  end if;
  update connected_readiness_private.release_preview_ceremony
  set status='succeeded',completed_at=reference
  where invocation_id=p_release_preview_invocation_id
    and status='running';
  if not found then
    raise exception 'connected release preview ceremony is not active'
      using errcode='55000';
  end if;
  delete from connected_readiness_private.provider_smoke_challenge
  where provider_smoke_challenge.singleton
    and provider_smoke_challenge.challenge_id=p_challenge_id;
  return query
  select smoke.composition_manifest_sha256,smoke.database_contract_sha256,
    smoke.database_target_fingerprint,smoke.provider_contract_sha256,
    smoke.deployment_id,smoke.commit_sha,
    smoke.host_configuration_ciphertext_sha256,smoke.root_key_id,
    smoke.release_preview_contract_sha256,
    smoke.release_preview_descriptor_matrix_sha256,
    smoke.release_preview_dedicated_account_attestation_sha256,
    smoke.release_preview_invocation_id,
    smoke.release_preview_effect_manifest_sha256,
    smoke.checked_at
  from connected_readiness_private.provider_smoke as smoke
  where smoke.singleton;
end;
$fn$;
comment on function public.connected_app_record_provider_smoke_v1(
  text,text,text,text,text,text,text,text,text,text,text,uuid,text,uuid,text
) is 'ASK_CRUMP_CONNECTED_PROVIDER_SMOKE_RECORD_V1_KMS_HMAC_ONE_USE_CHALLENGE';

create or replace function public.connected_app_runtime_readiness_v1(
  p_expected_manifest_sha256 text,
  p_expected_database_contract_sha256 text,
  p_expected_database_target_fingerprint text,
  p_expected_provider_contract_sha256 text,
  p_expected_deployment_id text,
  p_expected_commit_sha text,
  p_expected_host_configuration_ciphertext_sha256 text,
  p_expected_root_key_id text,
  p_expected_release_preview_contract_sha256 text
)
returns table(
  composition_manifest_sha256 text,
  database_contract_sha256 text,
  database_target_fingerprint text,
  provider_contract_sha256 text,
  deployment_id text,
  commit_sha text,
  host_configuration_ciphertext_sha256 text,
  root_key_id text,
  release_preview_contract_sha256 text,
  release_preview_descriptor_matrix_sha256 text,
  release_preview_dedicated_account_attestation_sha256 text,
  release_preview_invocation_id uuid,
  release_preview_effect_manifest_sha256 text,
  checked_at timestamptz,
  expires_at timestamptz,
  provider_smoke_checked_at timestamptz,
  provider_smoke_challenge_id uuid,
  provider_smoke_challenge_issued_at timestamptz,
  provider_smoke_attestation_sha256 text
)
language plpgsql stable security definer set search_path='' as $fn$
declare
  reference timestamptz:=pg_catalog.statement_timestamp();
  observed_target text;
  smoke connected_readiness_private.provider_smoke%rowtype;
begin
  if p_expected_manifest_sha256 is null
     or p_expected_manifest_sha256!~'^[0-9a-f]{64}$'
     or p_expected_database_contract_sha256<>
       '4a1b678715584712f96f1ca224f3c3311bc7b62f63fdd0fde7c8fa937786226a'
     or p_expected_database_target_fingerprint!~'^[0-9a-f]{32}$'
     or p_expected_provider_contract_sha256<>
       'aed6387ef7b1e401b9a126138c47efa5ff9313af78b55fd1b43bbda66bd684d6'
     or p_expected_deployment_id is null
     or p_expected_deployment_id!~'^dpl_[A-Za-z0-9]{8,}$'
     or p_expected_commit_sha is null
     or p_expected_commit_sha!~'^[0-9a-f]{40}$'
     or p_expected_host_configuration_ciphertext_sha256 is null
     or p_expected_host_configuration_ciphertext_sha256!~'^[0-9a-f]{64}$'
     or p_expected_root_key_id is null
     or p_expected_root_key_id!~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,30}$'
     or p_expected_release_preview_contract_sha256<>
       '8f69d8bdf2d137c42af93179dc887e66d0073d7bb1444a860f5a211f0f172d0f' then
    raise exception 'connected runtime readiness contract is invalid'
      using errcode='22023';
  end if;
  select connected_readiness_private.runtime_readiness_target_fingerprint_v1()
    into observed_target;
  if observed_target<>p_expected_database_target_fingerprint then
    raise exception 'connected runtime readiness catalog drifted: %',observed_target
      using errcode='55000';
  end if;
  select * into smoke
  from connected_readiness_private.provider_smoke as smoke_row
  where smoke_row.singleton
    and smoke_row.composition_manifest_sha256=p_expected_manifest_sha256
    and smoke_row.database_contract_sha256=p_expected_database_contract_sha256
    and smoke_row.database_target_fingerprint=p_expected_database_target_fingerprint
    and smoke_row.provider_contract_sha256=p_expected_provider_contract_sha256
    and smoke_row.deployment_id=p_expected_deployment_id
    and smoke_row.commit_sha=p_expected_commit_sha
    and smoke_row.host_configuration_ciphertext_sha256=
      p_expected_host_configuration_ciphertext_sha256
    and smoke_row.root_key_id=p_expected_root_key_id
    and smoke_row.release_preview_contract_sha256=
      p_expected_release_preview_contract_sha256
    and smoke_row.checked_at<=reference+interval '5 seconds';
  if not found then
    raise exception 'connected runtime readiness provider smoke is absent or mismatched'
      using errcode='55000';
  end if;
  return query select
    smoke.composition_manifest_sha256,smoke.database_contract_sha256,
    smoke.database_target_fingerprint,smoke.provider_contract_sha256,
    smoke.deployment_id,smoke.commit_sha,
    smoke.host_configuration_ciphertext_sha256,smoke.root_key_id,
    smoke.release_preview_contract_sha256,
    smoke.release_preview_descriptor_matrix_sha256,
    smoke.release_preview_dedicated_account_attestation_sha256,
    smoke.release_preview_invocation_id,
    smoke.release_preview_effect_manifest_sha256,
    reference,reference+interval '15 minutes',smoke.checked_at,
    smoke.challenge_id,smoke.challenge_issued_at,
    smoke.provider_smoke_attestation_sha256;
end;
$fn$;
comment on function public.connected_app_runtime_readiness_v1(
  text,text,text,text,text,text,text,text,text
) is 'ASK_CRUMP_CONNECTED_RUNTIME_READINESS_V1_LIVE_CATALOG_DURABLE_KMS_HMAC_SMOKE';

alter function public.connected_app_claim_release_preview_ceremony_v1(
  uuid,uuid,text,text,text,text,text) owner to postgres;
alter function public.connected_app_read_release_preview_ceremony_v1(
  uuid,uuid,text,text,text,text,text) owner to postgres;
alter function public.connected_app_release_preview_begin_v1(
  uuid,text,text,text,text,text,jsonb,text,text,text,text,text,text,text,text)
  owner to postgres;
alter function public.connected_app_release_preview_status_v1(uuid)
  owner to postgres;
alter function public.connected_app_release_preview_authority_status_v1(uuid)
  owner to postgres;
alter function public.connected_app_release_preview_authority_v1(
  uuid,text,text,bigint,text,text,text) owner to postgres;
alter function public.connected_app_release_preview_effect_v1(
  uuid,uuid,bigint,text,text,text) owner to postgres;
alter function public.connected_app_release_preview_finalize_v1(uuid)
  owner to postgres;
alter function public.connected_app_release_preview_fail_v1(uuid)
  owner to postgres;
alter function public.connected_app_issue_provider_smoke_challenge_v1(
  text,text,text,text,text,text,text,text,text,text,text,uuid,text)
  owner to postgres;
alter function public.connected_app_record_provider_smoke_v1(
  text,text,text,text,text,text,text,text,text,text,text,uuid,text,uuid,text)
  owner to postgres;
alter function public.connected_app_runtime_readiness_v1(
  text,text,text,text,text,text,text,text,text) owner to postgres;
alter function public.connected_app_release_preview_retire_connection_v1(
  uuid,uuid,uuid,bigint,text,text,text,uuid,text) owner to postgres;
revoke all on function public.connected_app_claim_release_preview_ceremony_v1(
  uuid,uuid,text,text,text,text,text)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_read_release_preview_ceremony_v1(
  uuid,uuid,text,text,text,text,text)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_release_preview_begin_v1(
  uuid,text,text,text,text,text,jsonb,text,text,text,text,text,text,text,text)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_release_preview_status_v1(uuid)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_release_preview_authority_status_v1(uuid)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_release_preview_authority_v1(
  uuid,text,text,bigint,text,text,text)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_release_preview_effect_v1(
  uuid,uuid,bigint,text,text,text)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_release_preview_finalize_v1(uuid)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_release_preview_fail_v1(uuid)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_issue_provider_smoke_challenge_v1(
  text,text,text,text,text,text,text,text,text,text,text,uuid,text)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_record_provider_smoke_v1(
  text,text,text,text,text,text,text,text,text,text,text,uuid,text,uuid,text)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_runtime_readiness_v1(
  text,text,text,text,text,text,text,text,text)
  from public,anon,authenticated,service_role;
revoke all on function public.connected_app_release_preview_retire_connection_v1(
  uuid,uuid,uuid,bigint,text,text,text,uuid,text)
  from public,anon,authenticated,service_role;
grant execute on function public.connected_app_claim_release_preview_ceremony_v1(
  uuid,uuid,text,text,text,text,text) to service_role;
grant execute on function public.connected_app_read_release_preview_ceremony_v1(
  uuid,uuid,text,text,text,text,text) to service_role;
grant execute on function public.connected_app_release_preview_begin_v1(
  uuid,text,text,text,text,text,jsonb,text,text,text,text,text,text,text,text)
  to service_role;
grant execute on function public.connected_app_release_preview_status_v1(uuid)
  to service_role;
grant execute on function public.connected_app_release_preview_authority_status_v1(uuid)
  to service_role;
grant execute on function public.connected_app_release_preview_authority_v1(
  uuid,text,text,bigint,text,text,text) to service_role;
grant execute on function public.connected_app_release_preview_effect_v1(
  uuid,uuid,bigint,text,text,text) to service_role;
grant execute on function public.connected_app_release_preview_finalize_v1(uuid)
  to service_role;
grant execute on function public.connected_app_release_preview_fail_v1(uuid)
  to service_role;
grant execute on function public.connected_app_issue_provider_smoke_challenge_v1(
  text,text,text,text,text,text,text,text,text,text,text,uuid,text)
  to service_role;
grant execute on function public.connected_app_record_provider_smoke_v1(
  text,text,text,text,text,text,text,text,text,text,text,uuid,text,uuid,text)
  to service_role;
grant execute on function public.connected_app_runtime_readiness_v1(
  text,text,text,text,text,text,text,text,text) to service_role;
grant execute on function public.connected_app_release_preview_retire_connection_v1(
  uuid,uuid,uuid,bigint,text,text,text,uuid,text) to service_role;

create or replace function
  connected_readiness_private.runtime_readiness_target_fingerprint_v1()
returns text language sql stable security definer set search_path='' as $fingerprint$
  select pg_catalog.md5(pg_catalog.string_agg(item::text,E'\n' order by item::text))
  from (
    select pg_catalog.jsonb_build_array(
      'schema',namespace_row.nspname,
      pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text,''),
      coalesce(pg_catalog.obj_description(namespace_row.oid,'pg_namespace'),'')) as item
    from pg_catalog.pg_namespace as namespace_row
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'relation',namespace_row.nspname,class_row.relname,class_row.relkind,
      class_row.relpersistence,class_row.relam,class_row.reltablespace,
      class_row.relrowsecurity,class_row.relforcerowsecurity,
      class_row.relreplident,class_row.relispopulated,class_row.relispartition,
      pg_catalog.pg_get_userbyid(class_row.relowner),
      coalesce(class_row.relacl::text,''),coalesce(class_row.reloptions::text,''),
      case when class_row.relkind in ('v','m')
        then pg_catalog.pg_get_viewdef(class_row.oid,true) else null end,
      coalesce(pg_catalog.obj_description(class_row.oid,'pg_class'),''))
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
      and class_row.relkind in ('r','p','S','v','m','f')
    union all
    select pg_catalog.jsonb_build_array(
      'inheritance',child_namespace.nspname,child_class.relname,
      parent_namespace.nspname,parent_class.relname,
      inheritance.inhseqno,inheritance.inhdetachpending)
    from pg_catalog.pg_inherits as inheritance
    join pg_catalog.pg_class as child_class on child_class.oid=inheritance.inhrelid
    join pg_catalog.pg_namespace as child_namespace
      on child_namespace.oid=child_class.relnamespace
    join pg_catalog.pg_class as parent_class on parent_class.oid=inheritance.inhparent
    join pg_catalog.pg_namespace as parent_namespace
      on parent_namespace.oid=parent_class.relnamespace
    where child_namespace.nspname like 'connected\_%\_private' escape '\'
       or parent_namespace.nspname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'sequence',namespace_row.nspname,class_row.relname,
      sequence_row.seqtypid::pg_catalog.regtype::text,
      sequence_row.seqstart,sequence_row.seqincrement,sequence_row.seqmax,
      sequence_row.seqmin,sequence_row.seqcache,sequence_row.seqcycle,
      coalesce(dependency_row.deptype::text,''),
      coalesce(dependency_namespace.nspname,''),
      coalesce(dependency_table.relname,''),
      coalesce(dependency_attribute.attname,''))
    from pg_catalog.pg_sequence as sequence_row
    join pg_catalog.pg_class as class_row on class_row.oid=sequence_row.seqrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_depend as dependency_row
      on dependency_row.classid='pg_catalog.pg_class'::pg_catalog.regclass
      and dependency_row.objid=class_row.oid
      and dependency_row.deptype in ('a','i')
    left join pg_catalog.pg_class as dependency_table
      on dependency_table.oid=dependency_row.refobjid
    left join pg_catalog.pg_namespace as dependency_namespace
      on dependency_namespace.oid=dependency_table.relnamespace
    left join pg_catalog.pg_attribute as dependency_attribute
      on dependency_attribute.attrelid=dependency_row.refobjid
      and dependency_attribute.attnum=dependency_row.refobjsubid
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'domain_constraint',namespace_row.nspname,type_row.typname,
      constraint_row.conname,constraint_row.contype,
      constraint_row.condeferrable,constraint_row.condeferred,
      constraint_row.convalidated,constraint_row.connoinherit,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    join pg_catalog.pg_type as type_row on type_row.oid=constraint_row.contypid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=type_row.typnamespace
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'column',namespace_row.nspname,class_row.relname,attribute_row.attnum,
      attribute_row.attname,
      pg_catalog.format_type(attribute_row.atttypid,attribute_row.atttypmod),
      attribute_row.attnotnull,attribute_row.attidentity,attribute_row.attgenerated,
      attribute_row.attstorage,attribute_row.attcompression,
      attribute_row.attstattarget,attribute_row.atthasmissing,
      coalesce(attribute_row.attmissingval::text,''),
      attribute_row.attinhcount,attribute_row.attislocal,
      attribute_row.attcollation,
      coalesce(attribute_row.attoptions::text,''),
      coalesce(pg_catalog.pg_get_expr(default_row.adbin,default_row.adrelid),''),
      coalesce(attribute_row.attacl::text,''),
      coalesce(pg_catalog.col_description(class_row.oid,attribute_row.attnum),''))
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row on class_row.oid=attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_attrdef as default_row
      on default_row.adrelid=attribute_row.attrelid
      and default_row.adnum=attribute_row.attnum
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
      and attribute_row.attnum>0 and not attribute_row.attisdropped
    union all
    select pg_catalog.jsonb_build_array(
      'constraint',namespace_row.nspname,class_row.relname,constraint_row.conname,
      constraint_row.contype,constraint_row.condeferrable,constraint_row.condeferred,
      constraint_row.convalidated,constraint_row.connoinherit,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    join pg_catalog.pg_class as class_row on class_row.oid=constraint_row.conrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'index',namespace_row.nspname,class_row.relname,index_class.relname,
      index_class.relpersistence,index_class.relam,index_class.reltablespace,
      coalesce(index_class.reloptions::text,''),
      pg_catalog.pg_get_userbyid(index_class.relowner),
      coalesce(index_class.relacl::text,''),
      coalesce(pg_catalog.obj_description(index_class.oid,'pg_class'),''),
      index_row.indisunique,index_row.indisprimary,index_row.indisexclusion,
      index_row.indimmediate,index_row.indisclustered,index_row.indisvalid,
      index_row.indcheckxmin,index_row.indisready,index_row.indislive,
      index_row.indisreplident,index_row.indnkeyatts,index_row.indnatts,
      index_row.indnullsnotdistinct,index_row.indkey::text,
      index_row.indcollation::text,index_row.indclass::text,
      index_row.indoption::text,
      pg_catalog.pg_get_indexdef(index_row.indexrelid))
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as class_row on class_row.oid=index_row.indrelid
    join pg_catalog.pg_class as index_class on index_class.oid=index_row.indexrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'trigger',namespace_row.nspname,class_row.relname,trigger_row.tgname,
      trigger_row.tgenabled,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid=trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
      and not trigger_row.tgisinternal
    union all
    select pg_catalog.jsonb_build_array(
      'constraint_trigger',namespace_row.nspname,class_row.relname,
      constraint_row.conname,trigger_row.tgtype,trigger_row.tgenabled,
      trigger_row.tgdeferrable,trigger_row.tginitdeferred)
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid=trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    join pg_catalog.pg_constraint as constraint_row
      on constraint_row.oid=trigger_row.tgconstraint
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
      and trigger_row.tgisinternal and trigger_row.tgconstraint<>0
    union all
    select pg_catalog.jsonb_build_array(
      'rule',namespace_row.nspname,class_row.relname,rewrite_row.rulename,
      rewrite_row.ev_enabled,rewrite_row.is_instead,
      pg_catalog.pg_get_ruledef(rewrite_row.oid,true))
    from pg_catalog.pg_rewrite as rewrite_row
    join pg_catalog.pg_class as class_row on class_row.oid=rewrite_row.ev_class
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
      and rewrite_row.rulename<>'_RETURN'
    union all
    select pg_catalog.jsonb_build_array(
      'type',namespace_row.nspname,type_row.typname,type_row.typtype,
      type_row.typcategory,type_row.typispreferred,type_row.typnotnull,
      type_row.typbasetype,type_row.typtypmod,type_row.typcollation,
      coalesce(type_row.typdefaultbin::text,''),coalesce(type_row.typdefault,''),
      pg_catalog.pg_get_userbyid(type_row.typowner),
      coalesce(type_row.typacl::text,''),
      coalesce(pg_catalog.obj_description(type_row.oid,'pg_type'),''))
    from pg_catalog.pg_type as type_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=type_row.typnamespace
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'enum_label',namespace_row.nspname,type_row.typname,
      enum_row.enumsortorder,enum_row.enumlabel)
    from pg_catalog.pg_enum as enum_row
    join pg_catalog.pg_type as type_row on type_row.oid=enum_row.enumtypid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=type_row.typnamespace
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'policy',policy_row.schemaname,policy_row.tablename,
      policy_row.policyname,policy_row.permissive,policy_row.roles::text,
      policy_row.cmd,coalesce(policy_row.qual,''),
      coalesce(policy_row.with_check,''))
    from pg_catalog.pg_policies as policy_row
    where policy_row.schemaname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'default_acl',namespace_row.nspname,
      pg_catalog.pg_get_userbyid(default_acl.defaclrole),
      default_acl.defaclobjtype,coalesce(default_acl.defaclacl::text,''))
    from pg_catalog.pg_default_acl as default_acl
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=default_acl.defaclnamespace
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'role',role_row.rolname,role_row.rolsuper,role_row.rolinherit,
      role_row.rolcreaterole,role_row.rolcreatedb,role_row.rolcanlogin,
      role_row.rolreplication,role_row.rolbypassrls,role_row.rolconnlimit,
      coalesce(role_row.rolconfig::text,''))
    from pg_catalog.pg_roles as role_row
    where role_row.rolname in (
      'postgres','service_role','authenticated','anon','authenticator')
    union all
    select pg_catalog.jsonb_build_array(
      'role_membership',pg_catalog.pg_get_userbyid(membership.roleid),
      pg_catalog.pg_get_userbyid(membership.member),
      pg_catalog.pg_get_userbyid(membership.grantor),
      membership.admin_option,membership.inherit_option,membership.set_option)
    from pg_catalog.pg_auth_members as membership
    where pg_catalog.pg_get_userbyid(membership.roleid) in (
            'postgres','service_role','authenticated','anon','authenticator')
       or pg_catalog.pg_get_userbyid(membership.member) in (
            'postgres','service_role','authenticated','anon','authenticator')
    union all
    select pg_catalog.jsonb_build_array(
      'function',namespace_row.nspname,proc_row.proname,
      pg_catalog.pg_get_function_identity_arguments(proc_row.oid),
      case when namespace_row.nspname='public'
              and proc_row.proname='connected_app_runtime_readiness_v1'
        then pg_catalog.regexp_replace(
          pg_catalog.pg_get_functiondef(proc_row.oid),
          'observed_target[[:space:]]*<>[[:space:]]*''[0-9a-f]{32}''',
          'observed_target<>''<TARGET_FINGERPRINT>''','g')
        else pg_catalog.pg_get_functiondef(proc_row.oid) end,
      pg_catalog.pg_get_userbyid(proc_row.proowner),proc_row.prosecdef,
      proc_row.proleakproof,proc_row.proisstrict,proc_row.proretset,
      proc_row.prokind,proc_row.provolatile,proc_row.proparallel,
      proc_row.procost,proc_row.prorows,
      language_row.lanname,coalesce(proc_row.proconfig::text,''),
      coalesce(proc_row.proacl::text,''),
      coalesce(pg_catalog.obj_description(proc_row.oid,'pg_proc'),''))
    from pg_catalog.pg_proc as proc_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=proc_row.pronamespace
    join pg_catalog.pg_language as language_row on language_row.oid=proc_row.prolang
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
       or (namespace_row.nspname='public'
         and (
           proc_row.proname like 'connected\_%' escape '\'
           or proc_row.proname in (
             'apply_guest_chat_sync_v2',
             'persist_guest_chat_reply_v1',
             'consume_password_reset_v1',
             'verify_registered_and_create_session_v1',
             'verify_guest_and_create_session_v1',
             'finalize_password_login_v1',
             'complete_initial_password_setup_v1',
             'delete_user_account',
             'claim_ai_gateway_cost_receipt',
             'settle_ai_gateway_cost_receipt'
           )
         ))
    union all
    select pg_catalog.jsonb_build_array(
      'publication',publication_row.pubname,publication_row.puballtables,
      publication_row.pubinsert,publication_row.pubupdate,
      publication_row.pubdelete,publication_row.pubtruncate,
      publication_row.pubviaroot,
      coalesce(namespace_row.nspname,''),coalesce(class_row.relname,''),
      coalesce(publication_relation.prattrs::text,''),
      coalesce(pg_catalog.pg_get_expr(
        publication_relation.prqual,publication_relation.prrelid),''))
    from pg_catalog.pg_publication as publication_row
    left join pg_catalog.pg_publication_rel as publication_relation
      on publication_relation.prpubid=publication_row.oid
    left join pg_catalog.pg_class as class_row
      on class_row.oid=publication_relation.prrelid
    left join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where publication_row.puballtables
       or namespace_row.nspname like 'connected\_%\_private' escape '\'
    union all
    select pg_catalog.jsonb_build_array(
      'publication_schema',publication_row.pubname,namespace_row.nspname)
    from pg_catalog.pg_publication_namespace as publication_schema
    join pg_catalog.pg_publication as publication_row
      on publication_row.oid=publication_schema.pnpubid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=publication_schema.pnnspid
    where namespace_row.nspname like 'connected\_%\_private' escape '\'
  ) as manifest(item)
$fingerprint$;
comment on function
  connected_readiness_private.runtime_readiness_target_fingerprint_v1() is
  'ASK_CRUMP_CONNECTED_RUNTIME_READINESS_TARGET_FINGERPRINT_V1_FULL_STACK';
alter function
  connected_readiness_private.runtime_readiness_target_fingerprint_v1()
  owner to postgres;
revoke all on function
  connected_readiness_private.runtime_readiness_target_fingerprint_v1()
  from public,anon,authenticated,service_role;

do $postflight$
declare
  target_fingerprint text;
begin
  select connected_readiness_private.runtime_readiness_target_fingerprint_v1()
    into target_fingerprint;
  if target_fingerprint<>'59714dce4c61f8140eddc1a2c8606b70' then
    raise exception 'connected runtime readiness postflight drifted: %',
      target_fingerprint using errcode='55000';
  end if;
  if pg_catalog.has_schema_privilege(
       'service_role','connected_readiness_private','usage')
     or pg_catalog.has_table_privilege(
       'service_role','connected_readiness_private.provider_smoke','select')
     or pg_catalog.has_table_privilege(
       'service_role','connected_readiness_private.provider_smoke_challenge','select')
     or pg_catalog.has_table_privilege(
       'service_role','connected_readiness_private.release_preview_ceremony','select')
     or pg_catalog.has_table_privilege(
       'service_role','connected_readiness_private.release_preview_invocation','select')
     or pg_catalog.has_table_privilege(
       'service_role','connected_readiness_private.release_preview_effect','select')
     or pg_catalog.has_table_privilege(
       'service_role','connected_readiness_private.release_preview_authority','select')
     or pg_catalog.has_function_privilege(
       'public',
       'public.connected_app_runtime_readiness_v1(text,text,text,text,text,text,text,text,text)',
       'execute')
     or pg_catalog.has_function_privilege(
       'anon',
       'public.connected_app_issue_provider_smoke_challenge_v1(text,text,text,text,text,text,text,text,text,text,text,uuid,text)',
       'execute')
     or pg_catalog.has_function_privilege(
       'authenticated',
       'public.connected_app_record_provider_smoke_v1(text,text,text,text,text,text,text,text,text,text,text,uuid,text,uuid,text)',
       'execute')
     or pg_catalog.has_function_privilege(
       'public',
       'public.connected_app_release_preview_fail_v1(uuid)',
       'execute')
     or not pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_runtime_readiness_v1(text,text,text,text,text,text,text,text,text)',
       'execute')
     or not pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_issue_provider_smoke_challenge_v1(text,text,text,text,text,text,text,text,text,text,text,uuid,text)',
       'execute')
     or not pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_record_provider_smoke_v1(text,text,text,text,text,text,text,text,text,text,text,uuid,text,uuid,text)',
       'execute')
     or not pg_catalog.has_function_privilege(
       'service_role',
       'public.connected_app_release_preview_fail_v1(uuid)',
       'execute')
     or exists(select 1 from pg_catalog.pg_publication where puballtables)
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
    raise exception 'connected runtime readiness authority or privacy failed'
      using errcode='55000';
  end if;
end;
$postflight$;

commit;
