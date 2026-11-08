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
       'connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()'
     ) is not null then
    select connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()
      into target_fingerprint;
    if target_fingerprint<>'5e4480837c5ebb316da85be988a6561f' then
      raise exception 'connected OAuth code-custody target drifted: %',
        target_fingerprint using errcode='55000';
    end if;
    return;
  end if;
  if pg_catalog.to_regprocedure(
       'connected_oauth_binding_private.oauth_binding_target_fingerprint_v1()'
     ) is null then
    raise exception 'connected OAuth code-custody predecessor is absent'
      using errcode='55000';
  end if;
  select connected_oauth_binding_private.oauth_binding_target_fingerprint_v1()
    into predecessor_fingerprint;
  if predecessor_fingerprint<>'74257db1f45f1f755d1ea5c1389599b7' then
    raise exception 'connected OAuth code-custody predecessor drifted: %',
      predecessor_fingerprint using errcode='55000';
  end if;
  if pg_catalog.to_regclass('public.sessions') is null
     or pg_catalog.to_regclass('public.users') is null
     or pg_catalog.to_regclass('connected_app_private.oauth_flows') is null
     or pg_catalog.to_regclass(
       'connected_app_private.oauth_callback_requests'
     ) is null
     or pg_catalog.to_regclass(
       'connected_app_private.oauth_exchange_permits'
     ) is null
     or pg_catalog.to_regclass(
       'connected_app_private.oauth_secret_custody'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_accept_oauth_callback_v1(text,text,text,timestamp with time zone,uuid,uuid,uuid,uuid,bigint,text,text,text,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'connected_app_private.owner_lock_v1(uuid)'
     ) is null then
    raise exception 'connected OAuth code-custody predecessor is incomplete'
      using errcode='55000';
  end if;
  if pg_catalog.to_regnamespace('connected_oauth_code_private') is not null
     or pg_catalog.to_regprocedure(
       'public.connected_app_operator_accept_oauth_callback_v2(uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,text,text,text,timestamp with time zone,timestamp with time zone,bigint,text,text,text,text)'
     ) is not null then
    raise exception 'connected OAuth code-custody target is partial'
      using errcode='55000';
  end if;
  if exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace
       where pnnspid in (
         pg_catalog.to_regnamespace('connected_app_private'),
         pg_catalog.to_regnamespace('connected_oauth_binding_private'),
         pg_catalog.to_regnamespace('connected_oauth_code_private')
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
         'connected_app_private','connected_oauth_binding_private',
         'connected_oauth_code_private'
       )
     ) then
    raise exception 'connected OAuth code-custody publication exposure refused'
      using errcode='55000';
  end if;
end;
$preflight$;

create schema if not exists connected_oauth_code_private authorization postgres;
comment on schema connected_oauth_code_private is
  'ASK_CRUMP_CONNECTED_OAUTH_AUTHORIZATION_CODE_CUSTODY_V1_PRIVATE';
revoke all on schema connected_oauth_code_private
  from public,anon,authenticated,service_role;

create table if not exists connected_oauth_code_private.authorization_code_custody(
  flow_id uuid primary key
    references connected_app_private.oauth_flows(flow_id) on delete cascade,
  owner_id uuid not null references public.users(id) on delete cascade,
  session_binding_sha256 text not null
    check (session_binding_sha256 ~ '^[0-9a-f]{64}$'),
  provider text not null check (provider in ('google','microsoft')),
  consumption_id uuid not null unique,
  exchange_id uuid not null unique,
  connection_id uuid not null,
  connection_incarnation_id uuid not null,
  current_flow_nonce_sha256 text not null
    check (current_flow_nonce_sha256 ~ '^[0-9a-f]{64}$'),
  state_sha256 text not null check (state_sha256 ~ '^[0-9a-f]{64}$'),
  callback_binding_sha256 text not null unique
    check (callback_binding_sha256 ~ '^[0-9a-f]{64}$'),
  flow_binding_sha256 text not null
    check (flow_binding_sha256 ~ '^[0-9a-f]{64}$'),
  consume_binding_sha256 text not null
    check (consume_binding_sha256 ~ '^[0-9a-f]{64}$'),
  exchange_binding_sha256 text not null
    check (exchange_binding_sha256 ~ '^[0-9a-f]{64}$'),
  pkce_challenge_sha256 text not null
    check (pkce_challenge_sha256 ~ '^[0-9a-f]{64}$'),
  redirect_uri_sha256 text not null
    check (redirect_uri_sha256 ~ '^[0-9a-f]{64}$'),
  authorization_code_sha256 text not null
    check (authorization_code_sha256 ~ '^[0-9a-f]{64}$'),
  code_authority_binding_sha256 text not null unique
    check (code_authority_binding_sha256 ~ '^[0-9a-f]{64}$'),
  code_key_id text check (
    code_key_id is null
    or code_key_id ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'
  ),
  code_nonce text check (
    code_nonce is null or code_nonce ~ '^[A-Za-z0-9_-]{16}$'
  ),
  code_ciphertext text check (
    code_ciphertext is null
    or (pg_catalog.length(code_ciphertext) between 23 and 8192
        and code_ciphertext ~ '^[A-Za-z0-9_-]+$')
  ),
  code_record_binding_sha256 text check (
    code_record_binding_sha256 is null
    or code_record_binding_sha256 ~ '^[0-9a-f]{64}$'
  ),
  status text not null default 'available'
    check (status in ('available','retired')),
  received_at timestamptz not null,
  expires_at timestamptz not null,
  claimed_at timestamptz,
  retired_at timestamptz,
  retired_reason text check (
    retired_reason is null
    or retired_reason in ('terminal','ambiguous','deadline','safe_restart')
  ),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  constraint oauth_code_owner_connection_fk
    foreign key(owner_id,connection_id)
    references connected_app_private.connections(owner_id,id) on delete cascade,
  constraint oauth_code_bounded_lifetime check (
    expires_at>received_at and expires_at<=received_at+interval '2 minutes'
  ),
  constraint oauth_code_status_shape check (
    (status='available' and code_key_id is not null and code_nonce is not null
      and code_ciphertext is not null and code_record_binding_sha256 is not null
      and retired_at is null and retired_reason is null)
    or
    (status='retired' and code_key_id is null and code_nonce is null
      and code_ciphertext is null and code_record_binding_sha256 is null
      and retired_at is not null and retired_reason is not null)
  )
);
alter table connected_oauth_code_private.authorization_code_custody
  owner to postgres;
alter table connected_oauth_code_private.authorization_code_custody
  enable row level security;
alter table connected_oauth_code_private.authorization_code_custody
  force row level security;
revoke all on table connected_oauth_code_private.authorization_code_custody
  from public,anon,authenticated,service_role;
comment on table connected_oauth_code_private.authorization_code_custody is
  'ASK_CRUMP_SHORT_TTL_AES_GCM_AUTHORIZATION_CODE_CUSTODY_V1_SERVICE_RPC_ONLY';

create index if not exists oauth_code_custody_owner_idx
  on connected_oauth_code_private.authorization_code_custody(
    owner_id,connection_id,flow_id
  );
create index if not exists oauth_code_custody_expiry_idx
  on connected_oauth_code_private.authorization_code_custody(expires_at,flow_id)
  where status='available';

create table if not exists connected_oauth_code_private.release_bootstrap_dedicated_attestations(
  ceremony_id uuid primary key,
  owner_id uuid not null references public.users(id) on delete cascade,
  session_id uuid not null references public.sessions(id) on delete cascade,
  descriptor_matrix_sha256 text not null unique
    check (descriptor_matrix_sha256 ~ '^[0-9a-f]{64}$'),
  dedicated_account_attestation_sha256 text not null unique
    check (dedicated_account_attestation_sha256 ~ '^[0-9a-f]{64}$'),
  confirmed_at timestamptz not null default pg_catalog.clock_timestamp()
);
alter table connected_oauth_code_private.release_bootstrap_dedicated_attestations
  owner to postgres;
alter table connected_oauth_code_private.release_bootstrap_dedicated_attestations
  enable row level security;
alter table connected_oauth_code_private.release_bootstrap_dedicated_attestations
  force row level security;
revoke all on table connected_oauth_code_private.release_bootstrap_dedicated_attestations
  from public,anon,authenticated,service_role;
comment on table connected_oauth_code_private.release_bootstrap_dedicated_attestations is
  'ASK_CRUMP_RELEASE_PREVIEW_EXPLICIT_DEDICATED_NON_CUSTOMER_ACCOUNT_ATTESTATION_V1';

create index if not exists release_bootstrap_attestation_owner_idx
  on connected_oauth_code_private.release_bootstrap_dedicated_attestations(
    owner_id,confirmed_at,ceremony_id
  );

create or replace function public.connected_app_operator_accept_oauth_callback_v2(
  p_owner_id uuid,
  p_session_binding_sha256 text,
  p_provider text,
  p_flow_id uuid,
  p_consumption_id uuid,
  p_exchange_id uuid,
  p_connection_id uuid,
  p_connection_incarnation_id uuid,
  p_current_flow_nonce_sha256 text,
  p_state_sha256 text,
  p_callback_binding_sha256 text,
  p_flow_binding_sha256 text,
  p_consume_binding_sha256 text,
  p_exchange_binding_sha256 text,
  p_pkce_challenge_sha256 text,
  p_redirect_uri_sha256 text,
  p_authorization_code_sha256 text,
  p_code_authority_binding_sha256 text,
  p_received_at timestamptz,
  p_code_expires_at timestamptz,
  p_expected_base_revision bigint,
  p_code_key_id text,
  p_code_nonce text,
  p_code_ciphertext text,
  p_code_record_binding_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $fn$
declare
  result jsonb;
  flow_row connected_app_private.oauth_flows%rowtype;
  callback_row connected_app_private.oauth_callback_requests%rowtype;
  secret_row connected_app_private.oauth_secret_custody%rowtype;
  code_row connected_oauth_code_private.authorization_code_custody%rowtype;
  expected_expiry timestamptz;
begin
  if p_owner_id is null or p_flow_id is null or p_consumption_id is null
     or p_exchange_id is null or p_connection_id is null
     or p_connection_incarnation_id is null
     or p_provider not in ('google','microsoft')
     or p_expected_base_revision<0
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_current_flow_nonce_sha256 !~ '^[0-9a-f]{64}$'
     or p_state_sha256 !~ '^[0-9a-f]{64}$'
     or p_callback_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_flow_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_consume_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_exchange_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_pkce_challenge_sha256 !~ '^[0-9a-f]{64}$'
     or p_redirect_uri_sha256 !~ '^[0-9a-f]{64}$'
     or p_authorization_code_sha256 !~ '^[0-9a-f]{64}$'
     or p_code_authority_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_code_key_id !~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$'
     or p_code_nonce !~ '^[A-Za-z0-9_-]{16}$'
     or pg_catalog.length(p_code_ciphertext) not between 23 and 8192
     or p_code_ciphertext !~ '^[A-Za-z0-9_-]+$'
     or p_code_record_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_received_at is null or p_code_expires_at is null then
    raise exception 'invalid connected OAuth code custody acceptance'
      using errcode='22023';
  end if;
  if p_consumption_id<>p_flow_id or p_exchange_id<>p_consumption_id then
    raise exception 'OAuth code custody identity drifted' using errcode='55000';
  end if;

  result:=public.connected_app_operator_accept_oauth_callback_v1(
    p_provider,p_state_sha256,p_callback_binding_sha256,p_received_at,
    p_consumption_id,p_owner_id,p_connection_id,
    p_connection_incarnation_id,p_expected_base_revision,
    p_current_flow_nonce_sha256,p_session_binding_sha256,
    p_flow_binding_sha256,p_consume_binding_sha256
  );

  perform connected_app_private.owner_lock_v1(p_owner_id);
  select flow.* into flow_row
  from connected_app_private.oauth_flows as flow
  where flow.flow_id=p_flow_id for update;
  select callback.* into callback_row
  from connected_app_private.oauth_callback_requests as callback
  where callback.provider=p_provider and callback.state_sha256=p_state_sha256
  for update;
  select secret.* into secret_row
  from connected_app_private.oauth_secret_custody as secret
  where secret.flow_id=p_flow_id for update;
  select code.* into code_row
  from connected_oauth_code_private.authorization_code_custody as code
  where code.flow_id=p_flow_id for update;

  expected_expiry:=least(
    flow_row.expires_at,callback_row.received_at+interval '2 minutes'
  );
  if flow_row.flow_id is null or callback_row.flow_id is null
     or secret_row.flow_id is null
     or flow_row.owner_id<>p_owner_id
     or flow_row.session_binding_sha256<>p_session_binding_sha256
     or flow_row.provider<>p_provider or flow_row.state_sha256<>p_state_sha256
     or flow_row.connection_id<>p_connection_id
     or flow_row.connection_incarnation_id<>p_connection_incarnation_id
     or flow_row.expected_base_revision<>p_expected_base_revision
     or flow_row.current_flow_nonce_sha256<>p_current_flow_nonce_sha256
     or flow_row.flow_binding_sha256<>p_flow_binding_sha256
     or flow_row.redirect_uri_sha256<>p_redirect_uri_sha256
     or p_pkce_challenge_sha256<>pg_catalog.encode(
       pg_catalog.sha256(
         pg_catalog.convert_to(flow_row.pkce_challenge,'UTF8')
       ),'hex'
     )
     or flow_row.status<>'consumed'
     or flow_row.consumption_id<>p_consumption_id
     or flow_row.consume_binding_sha256<>p_consume_binding_sha256
     or flow_row.consumed_at<>callback_row.received_at
     or callback_row.callback_binding_sha256<>p_callback_binding_sha256
     or secret_row.owner_id<>p_owner_id
     or secret_row.session_binding_sha256<>p_session_binding_sha256
     or secret_row.flow_binding_sha256<>p_flow_binding_sha256
     or secret_row.status<>'pending' or secret_row.exchange_id is not null
     or p_code_expires_at<>expected_expiry then
    raise exception 'OAuth code custody live authority changed'
      using errcode='55000';
  end if;

  if code_row.flow_id is not null then
    if code_row.owner_id<>p_owner_id
       or code_row.session_binding_sha256<>p_session_binding_sha256
       or code_row.provider<>p_provider
       or code_row.consumption_id<>p_consumption_id
       or code_row.exchange_id<>p_exchange_id
       or code_row.connection_id<>p_connection_id
       or code_row.connection_incarnation_id<>p_connection_incarnation_id
       or code_row.current_flow_nonce_sha256<>p_current_flow_nonce_sha256
       or code_row.state_sha256<>p_state_sha256
       or code_row.callback_binding_sha256<>p_callback_binding_sha256
       or code_row.flow_binding_sha256<>p_flow_binding_sha256
       or code_row.consume_binding_sha256<>p_consume_binding_sha256
       or code_row.exchange_binding_sha256<>p_exchange_binding_sha256
       or code_row.pkce_challenge_sha256<>p_pkce_challenge_sha256
       or code_row.redirect_uri_sha256<>p_redirect_uri_sha256
       or code_row.authorization_code_sha256<>p_authorization_code_sha256
       or code_row.code_authority_binding_sha256<>
          p_code_authority_binding_sha256
       or code_row.code_key_id<>p_code_key_id
       or code_row.code_nonce<>p_code_nonce
       or code_row.code_ciphertext<>p_code_ciphertext
       or code_row.code_record_binding_sha256<>p_code_record_binding_sha256
       or code_row.received_at<>callback_row.received_at
       or code_row.expires_at<>p_code_expires_at
       or code_row.status<>'available' then
      raise exception 'OAuth code custody replay drifted' using errcode='55000';
    end if;
    return result;
  end if;

  insert into connected_oauth_code_private.authorization_code_custody(
    flow_id,owner_id,session_binding_sha256,provider,consumption_id,exchange_id,
    connection_id,connection_incarnation_id,current_flow_nonce_sha256,
    state_sha256,callback_binding_sha256,flow_binding_sha256,
    consume_binding_sha256,exchange_binding_sha256,pkce_challenge_sha256,
    redirect_uri_sha256,authorization_code_sha256,
    code_authority_binding_sha256,code_key_id,code_nonce,code_ciphertext,
    code_record_binding_sha256,received_at,expires_at
  ) values (
    p_flow_id,p_owner_id,p_session_binding_sha256,p_provider,p_consumption_id,
    p_exchange_id,p_connection_id,p_connection_incarnation_id,
    p_current_flow_nonce_sha256,p_state_sha256,p_callback_binding_sha256,
    p_flow_binding_sha256,p_consume_binding_sha256,p_exchange_binding_sha256,
    p_pkce_challenge_sha256,p_redirect_uri_sha256,p_authorization_code_sha256,
    p_code_authority_binding_sha256,p_code_key_id,p_code_nonce,
    p_code_ciphertext,p_code_record_binding_sha256,callback_row.received_at,
    p_code_expires_at
  );
  return result;
end;
$fn$;
comment on function public.connected_app_operator_accept_oauth_callback_v2(
  uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,text,
  text,text,timestamptz,timestamptz,bigint,text,text,text,text
) is 'ASK_CRUMP_OAUTH_CALLBACK_V2_ATOMIC_CONSUMPTION_AND_ENCRYPTED_CODE_CUSTODY';

create or replace function public.connected_app_oauth_code_read_v1(
  p_owner_id uuid,p_session_binding_sha256 text,p_provider text,p_flow_id uuid,
  p_consumption_id uuid,p_exchange_id uuid,p_connection_id uuid,
  p_connection_incarnation_id uuid,p_current_flow_nonce_sha256 text,
  p_state_sha256 text,p_callback_binding_sha256 text,p_flow_binding_sha256 text,
  p_consume_binding_sha256 text,p_exchange_binding_sha256 text,
  p_pkce_challenge_sha256 text,p_redirect_uri_sha256 text,
  p_authorization_code_sha256 text,p_code_authority_binding_sha256 text,
  p_received_at timestamptz,p_code_expires_at timestamptz
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $fn$
declare
  code_row connected_oauth_code_private.authorization_code_custody%rowtype;
begin
  if p_owner_id is null or p_flow_id is null or p_exchange_id is null then
    raise exception 'invalid OAuth code custody read' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select code.* into code_row
  from connected_oauth_code_private.authorization_code_custody as code
  where code.flow_id=p_flow_id for update;
  if not found then return null; end if;
  if code_row.owner_id<>p_owner_id
     or code_row.session_binding_sha256<>p_session_binding_sha256
     or code_row.provider<>p_provider
     or code_row.consumption_id<>p_consumption_id
     or code_row.exchange_id<>p_exchange_id
     or code_row.connection_id<>p_connection_id
     or code_row.connection_incarnation_id<>p_connection_incarnation_id
     or code_row.current_flow_nonce_sha256<>p_current_flow_nonce_sha256
     or code_row.state_sha256<>p_state_sha256
     or code_row.callback_binding_sha256<>p_callback_binding_sha256
     or code_row.flow_binding_sha256<>p_flow_binding_sha256
     or code_row.consume_binding_sha256<>p_consume_binding_sha256
     or code_row.exchange_binding_sha256<>p_exchange_binding_sha256
     or code_row.pkce_challenge_sha256<>p_pkce_challenge_sha256
     or code_row.redirect_uri_sha256<>p_redirect_uri_sha256
     or code_row.authorization_code_sha256<>p_authorization_code_sha256
     or code_row.code_authority_binding_sha256<>
        p_code_authority_binding_sha256
     or code_row.received_at<>p_received_at
     or code_row.expires_at<>p_code_expires_at then
    raise exception 'OAuth code custody read binding drifted' using errcode='55000';
  end if;
  return pg_catalog.jsonb_build_object(
    'status',code_row.status,
    'code_authority_binding_sha256',code_row.code_authority_binding_sha256,
    'code_key_id',code_row.code_key_id,
    'code_nonce',code_row.code_nonce,
    'code_ciphertext',code_row.code_ciphertext,
    'code_record_binding_sha256',code_row.code_record_binding_sha256,
    'claimed_at',code_row.claimed_at,
    'retired_at',code_row.retired_at
  );
end;
$fn$;
comment on function public.connected_app_oauth_code_read_v1(
  uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,text,
  text,text,timestamptz,timestamptz
) is 'ASK_CRUMP_OAUTH_CODE_CUSTODY_READ_V1_EXACT_RESPONSE_LOSS_READBACK';

create or replace function public.connected_app_oauth_code_claim_v1(
  p_owner_id uuid,p_session_binding_sha256 text,p_provider text,p_flow_id uuid,
  p_consumption_id uuid,p_exchange_id uuid,p_exchange_binding_sha256 text,
  p_state_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $fn$
declare
  code_row connected_oauth_code_private.authorization_code_custody%rowtype;
  flow_row connected_app_private.oauth_flows%rowtype;
  secret_row connected_app_private.oauth_secret_custody%rowtype;
  permit_row connected_app_private.oauth_exchange_permits%rowtype;
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  if p_owner_id is null or p_flow_id is null or p_consumption_id is null
     or p_exchange_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_provider not in ('google','microsoft')
     or p_exchange_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_state_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid OAuth code custody claim' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select flow.* into flow_row from connected_app_private.oauth_flows as flow
  where flow.flow_id=p_flow_id for update;
  select secret.* into secret_row
  from connected_app_private.oauth_secret_custody as secret
  where secret.flow_id=p_flow_id for update;
  select permit.* into permit_row
  from connected_app_private.oauth_exchange_permits as permit
  where permit.exchange_id=p_exchange_id for update;
  select code.* into code_row
  from connected_oauth_code_private.authorization_code_custody as code
  where code.flow_id=p_flow_id for update;
  if code_row.flow_id is null or flow_row.flow_id is null
     or secret_row.flow_id is null
     or code_row.status<>'available' or now_at>=code_row.expires_at
     or code_row.owner_id<>p_owner_id
     or code_row.session_binding_sha256<>p_session_binding_sha256
     or code_row.provider<>p_provider
     or code_row.consumption_id<>p_consumption_id
     or code_row.exchange_id<>p_exchange_id
     or code_row.exchange_binding_sha256<>p_exchange_binding_sha256
     or code_row.state_sha256<>p_state_sha256
     or flow_row.owner_id<>p_owner_id or flow_row.status<>'consumed'
     or flow_row.consumption_id<>p_consumption_id
     or secret_row.status<>'pending' or secret_row.exchange_id is not null
     or (permit_row.permit_id is not null
         and (permit_row.status<>'issued' or permit_row.consumed_at is not null))
     or exists(
       select 1 from connected_app_private.oauth_provisional_credentials as p
       where p.flow_id=p_flow_id and p.exchange_id=p_exchange_id
     ) then
    raise exception 'OAuth code custody is unavailable after dispatch authority'
      using errcode='55000';
  end if;
  update connected_oauth_code_private.authorization_code_custody as code
  set claimed_at=coalesce(code.claimed_at,now_at)
  where code.flow_id=p_flow_id returning * into code_row;
  return pg_catalog.jsonb_build_object(
    'status',code_row.status,
    'callback_binding_sha256',code_row.callback_binding_sha256,
    'authorization_code_sha256',code_row.authorization_code_sha256,
    'code_authority_binding_sha256',code_row.code_authority_binding_sha256,
    'code_key_id',code_row.code_key_id,'code_nonce',code_row.code_nonce,
    'code_ciphertext',code_row.code_ciphertext,
    'code_record_binding_sha256',code_row.code_record_binding_sha256,
    'claimed_at',code_row.claimed_at,'retired_at',code_row.retired_at
  );
end;
$fn$;
comment on function public.connected_app_oauth_code_claim_v1(
  uuid,text,text,uuid,uuid,uuid,text,text
) is 'ASK_CRUMP_OAUTH_CODE_CUSTODY_CLAIM_V1_ONLY_BEFORE_EXCHANGE_FENCE';

create or replace function public.connected_app_oauth_code_retire_v1(
  p_owner_id uuid,p_session_binding_sha256 text,p_provider text,p_flow_id uuid,
  p_consumption_id uuid,p_exchange_id uuid,p_exchange_binding_sha256 text,
  p_state_sha256 text,p_reason text
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $fn$
declare
  code_row connected_oauth_code_private.authorization_code_custody%rowtype;
  secret_row connected_app_private.oauth_secret_custody%rowtype;
  permit_row connected_app_private.oauth_exchange_permits%rowtype;
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  if p_owner_id is null or p_flow_id is null or p_consumption_id is null
     or p_exchange_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_provider not in ('google','microsoft')
     or p_exchange_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_state_sha256 !~ '^[0-9a-f]{64}$'
     or p_reason not in ('terminal','ambiguous','deadline','safe_restart') then
    raise exception 'invalid OAuth code custody retirement' using errcode='22023';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select secret.* into secret_row
  from connected_app_private.oauth_secret_custody as secret
  where secret.flow_id=p_flow_id for update;
  select permit.* into permit_row
  from connected_app_private.oauth_exchange_permits as permit
  where permit.exchange_id=p_exchange_id for update;
  select code.* into code_row
  from connected_oauth_code_private.authorization_code_custody as code
  where code.flow_id=p_flow_id for update;
  if code_row.flow_id is null
     or code_row.owner_id<>p_owner_id
     or code_row.session_binding_sha256<>p_session_binding_sha256
     or code_row.provider<>p_provider
     or code_row.consumption_id<>p_consumption_id
     or code_row.exchange_id<>p_exchange_id
     or code_row.exchange_binding_sha256<>p_exchange_binding_sha256
     or code_row.state_sha256<>p_state_sha256 then
    raise exception 'OAuth code custody retirement binding drifted'
      using errcode='55000';
  end if;
  if code_row.status='retired' then
    if code_row.retired_reason<>p_reason then
      raise exception 'OAuth code custody retirement replay drifted'
        using errcode='55000';
    end if;
    return pg_catalog.jsonb_build_object(
      'retired',true,'retired_at',code_row.retired_at
    );
  end if;
  if (p_reason='terminal' and not (
        secret_row.status='granted' or permit_row.status='terminal'
      ))
     or (p_reason='ambiguous' and secret_row.status not in (
        'attempt_fenced','ambiguous'
      ))
     or (p_reason='deadline' and secret_row.status not in (
        'deadline_expired','attempt_fenced'
      ))
     or (p_reason='safe_restart' and not (
        now_at>=code_row.expires_at and secret_row.status='pending'
        and secret_row.exchange_id is null
        and (permit_row.permit_id is null
             or (permit_row.status='issued' and permit_row.consumed_at is null))
      )) then
    raise exception 'OAuth code custody retirement authority is absent'
      using errcode='55000';
  end if;
  update connected_oauth_code_private.authorization_code_custody as code
  set status='retired',code_key_id=null,code_nonce=null,code_ciphertext=null,
      code_record_binding_sha256=null,retired_at=now_at,
      retired_reason=p_reason
  where code.flow_id=p_flow_id returning * into code_row;
  return pg_catalog.jsonb_build_object(
    'retired',true,'retired_at',code_row.retired_at
  );
end;
$fn$;
comment on function public.connected_app_oauth_code_retire_v1(
  uuid,text,text,uuid,uuid,uuid,text,text,text
) is 'ASK_CRUMP_OAUTH_CODE_CUSTODY_RETIRE_V1_ERASE_AFTER_TERMINAL_OR_SAFE_EXPIRY';

create or replace function public.connected_app_release_bootstrap_authenticate_v1(
  p_session_token_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $fn$
declare
  candidate_owner_id uuid;
  session_row public.sessions%rowtype;
  user_row public.users%rowtype;
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  if p_session_token_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid release-bootstrap session authority'
      using errcode='22023';
  end if;
  select session.user_id into candidate_owner_id
  from public.sessions as session
  where session.token_hash=p_session_token_sha256;
  if candidate_owner_id is null then
    return pg_catalog.jsonb_build_object(
      'authenticated',false,'owner_id',null,'session_id',null
    );
  end if;
  perform connected_app_private.owner_lock_v1(candidate_owner_id);
  select users.* into user_row from public.users as users
  where users.id=candidate_owner_id for share;
  select session.* into session_row
  from public.sessions as session
  where session.token_hash=p_session_token_sha256
    and session.user_id=candidate_owner_id for share;
  if session_row.id is null or user_row.id is null
     or session_row.revoked_at is not null or session_row.expires_at<=now_at
     or user_row.is_verified is not true then
    return pg_catalog.jsonb_build_object(
      'authenticated',false,'owner_id',null,'session_id',null
    );
  end if;
  return pg_catalog.jsonb_build_object(
    'authenticated',true,'owner_id',user_row.id,'session_id',session_row.id
  );
end;
$fn$;
comment on function public.connected_app_release_bootstrap_authenticate_v1(text)
  is 'ASK_CRUMP_RELEASE_BOOTSTRAP_CURRENT_REGISTERED_SESSION_AUTHORITY_V1';

create or replace function connected_oauth_code_private.dedicated_attestation_sha256_v1(
  p_ceremony_id uuid,p_owner_id uuid,p_descriptor_matrix_sha256 text
)
returns text
language sql
immutable
security definer
set search_path=''
as $fn$
  select pg_catalog.encode(
    pg_catalog.sha256(
      pg_catalog.convert_to(
        'askcrump-release-preview-dedicated-account-attestation-v1','UTF8'
      ) || pg_catalog.decode('00','hex') ||
      pg_catalog.convert_to(p_ceremony_id::text,'UTF8') ||
      pg_catalog.decode('00','hex') ||
      pg_catalog.convert_to(p_owner_id::text,'UTF8') ||
      pg_catalog.decode('00','hex') ||
      pg_catalog.convert_to(p_descriptor_matrix_sha256,'UTF8') ||
      pg_catalog.decode('00','hex') ||
      pg_catalog.convert_to('three_dedicated_non_customer_accounts','UTF8')
    ),
    'hex'
  )
$fn$;
comment on function connected_oauth_code_private.dedicated_attestation_sha256_v1(
  uuid,uuid,text
) is 'ASK_CRUMP_RELEASE_PREVIEW_DEDICATED_ACCOUNT_ATTESTATION_DIGEST_V1';

create or replace function public.connected_app_release_bootstrap_attest_dedicated_v1(
  p_ceremony_id uuid,p_owner_id uuid,p_session_id uuid,
  p_session_binding_sha256 text,p_descriptor_matrix_sha256 text,
  p_dedicated_account_attestation_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $fn$
declare
  user_row public.users%rowtype;
  session_row public.sessions%rowtype;
  receipt connected_oauth_code_private.release_bootstrap_dedicated_attestations%rowtype;
  expected_attestation text;
  now_at timestamptz:=pg_catalog.clock_timestamp();
begin
  if p_ceremony_id is null or p_owner_id is null or p_session_id is null
     or p_session_binding_sha256 !~ '^[0-9a-f]{64}$'
     or p_descriptor_matrix_sha256 !~ '^[0-9a-f]{64}$'
     or p_dedicated_account_attestation_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid dedicated-account attestation authority'
      using errcode='22023';
  end if;
  expected_attestation:=
    connected_oauth_code_private.dedicated_attestation_sha256_v1(
      p_ceremony_id,p_owner_id,p_descriptor_matrix_sha256
    );
  if p_dedicated_account_attestation_sha256<>expected_attestation
     or p_session_binding_sha256<>pg_catalog.encode(
       pg_catalog.sha256(pg_catalog.convert_to(p_session_id::text,'UTF8')),'hex'
     ) then
    raise exception 'dedicated-account attestation binding drifted'
      using errcode='55000';
  end if;
  perform connected_app_private.owner_lock_v1(p_owner_id);
  select users.* into user_row from public.users as users
  where users.id=p_owner_id for share;
  select session.* into session_row from public.sessions as session
  where session.id=p_session_id and session.user_id=p_owner_id for share;
  if user_row.id is null or user_row.is_verified is not true
     or session_row.id is null or session_row.revoked_at is not null
     or session_row.expires_at<=now_at then
    raise exception 'dedicated-account attestation session is not current'
      using errcode='55000';
  end if;
  insert into connected_oauth_code_private.release_bootstrap_dedicated_attestations(
    ceremony_id,owner_id,session_id,descriptor_matrix_sha256,
    dedicated_account_attestation_sha256,confirmed_at
  ) values (
    p_ceremony_id,p_owner_id,p_session_id,p_descriptor_matrix_sha256,
    p_dedicated_account_attestation_sha256,now_at
  ) returning * into receipt;
  return pg_catalog.jsonb_build_object(
    'ceremony_id',receipt.ceremony_id,'owner_id',receipt.owner_id,
    'session_id',receipt.session_id,
    'descriptor_matrix_sha256',receipt.descriptor_matrix_sha256,
    'dedicated_account_attestation_sha256',
      receipt.dedicated_account_attestation_sha256,
    'confirmed_at',receipt.confirmed_at
  );
end;
$fn$;
comment on function public.connected_app_release_bootstrap_attest_dedicated_v1(
  uuid,uuid,uuid,text,text,text
) is 'ASK_CRUMP_RELEASE_PREVIEW_ONE_USE_ACTION_TIME_DEDICATED_ACCOUNT_ATTESTATION_V1';

create or replace function public.connected_app_release_bootstrap_read_dedicated_v1(
  p_dedicated_account_attestation_sha256 text
)
returns jsonb
language plpgsql
security definer
set search_path=''
as $fn$
declare
  candidate_owner_id uuid;
  receipt connected_oauth_code_private.release_bootstrap_dedicated_attestations%rowtype;
begin
  if p_dedicated_account_attestation_sha256 !~ '^[0-9a-f]{64}$' then
    raise exception 'invalid dedicated-account attestation read'
      using errcode='22023';
  end if;
  select row_value.owner_id into candidate_owner_id
  from connected_oauth_code_private.release_bootstrap_dedicated_attestations as row_value
  where row_value.dedicated_account_attestation_sha256=
    p_dedicated_account_attestation_sha256;
  if candidate_owner_id is null then return null; end if;
  perform connected_app_private.owner_lock_v1(candidate_owner_id);
  select row_value.* into receipt
  from connected_oauth_code_private.release_bootstrap_dedicated_attestations as row_value
  where row_value.dedicated_account_attestation_sha256=
    p_dedicated_account_attestation_sha256 for share;
  if receipt.ceremony_id is null then return null; end if;
  return pg_catalog.jsonb_build_object(
    'ceremony_id',receipt.ceremony_id,'owner_id',receipt.owner_id,
    'session_id',receipt.session_id,
    'descriptor_matrix_sha256',receipt.descriptor_matrix_sha256,
    'dedicated_account_attestation_sha256',
      receipt.dedicated_account_attestation_sha256,
    'confirmed_at',receipt.confirmed_at
  );
end;
$fn$;
comment on function public.connected_app_release_bootstrap_read_dedicated_v1(text)
  is 'ASK_CRUMP_RELEASE_PREVIEW_DEDICATED_ACCOUNT_ATTESTATION_EXACT_READBACK_V1';

alter function public.connected_app_operator_accept_oauth_callback_v2(
  uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,text,
  text,text,timestamptz,timestamptz,bigint,text,text,text,text
) owner to postgres;
alter function public.connected_app_oauth_code_read_v1(
  uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,text,
  text,text,timestamptz,timestamptz
) owner to postgres;
alter function public.connected_app_oauth_code_claim_v1(
  uuid,text,text,uuid,uuid,uuid,text,text
) owner to postgres;
alter function public.connected_app_oauth_code_retire_v1(
  uuid,text,text,uuid,uuid,uuid,text,text,text
) owner to postgres;
alter function public.connected_app_release_bootstrap_authenticate_v1(text)
  owner to postgres;
alter function connected_oauth_code_private.dedicated_attestation_sha256_v1(
  uuid,uuid,text
) owner to postgres;
alter function public.connected_app_release_bootstrap_attest_dedicated_v1(
  uuid,uuid,uuid,text,text,text
) owner to postgres;
alter function public.connected_app_release_bootstrap_read_dedicated_v1(text)
  owner to postgres;

revoke all on function public.connected_app_operator_accept_oauth_callback_v1(
  text,text,text,timestamptz,uuid,uuid,uuid,uuid,bigint,text,text,text,text
) from service_role;
revoke all on function public.connected_app_operator_accept_oauth_callback_v2(
  uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,text,
  text,text,timestamptz,timestamptz,bigint,text,text,text,text
) from public,anon,authenticated;
revoke all on function public.connected_app_oauth_code_read_v1(
  uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,text,
  text,text,timestamptz,timestamptz
) from public,anon,authenticated;
revoke all on function public.connected_app_oauth_code_claim_v1(
  uuid,text,text,uuid,uuid,uuid,text,text
) from public,anon,authenticated;
revoke all on function public.connected_app_oauth_code_retire_v1(
  uuid,text,text,uuid,uuid,uuid,text,text,text
) from public,anon,authenticated;
revoke all on function public.connected_app_release_bootstrap_authenticate_v1(text)
  from public,anon,authenticated;
revoke all on function connected_oauth_code_private.dedicated_attestation_sha256_v1(
  uuid,uuid,text
) from public,anon,authenticated,service_role;
revoke all on function public.connected_app_release_bootstrap_attest_dedicated_v1(
  uuid,uuid,uuid,text,text,text
) from public,anon,authenticated;
revoke all on function public.connected_app_release_bootstrap_read_dedicated_v1(text)
  from public,anon,authenticated;
grant execute on function public.connected_app_operator_accept_oauth_callback_v2(
  uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,text,
  text,text,timestamptz,timestamptz,bigint,text,text,text,text
) to service_role;
grant execute on function public.connected_app_oauth_code_read_v1(
  uuid,text,text,uuid,uuid,uuid,uuid,uuid,text,text,text,text,text,text,text,text,
  text,text,timestamptz,timestamptz
) to service_role;
grant execute on function public.connected_app_oauth_code_claim_v1(
  uuid,text,text,uuid,uuid,uuid,text,text
) to service_role;
grant execute on function public.connected_app_oauth_code_retire_v1(
  uuid,text,text,uuid,uuid,uuid,text,text,text
) to service_role;
grant execute on function public.connected_app_release_bootstrap_authenticate_v1(text)
  to service_role;
grant execute on function public.connected_app_release_bootstrap_attest_dedicated_v1(
  uuid,uuid,uuid,text,text,text
) to service_role;
grant execute on function public.connected_app_release_bootstrap_read_dedicated_v1(text)
  to service_role;

create or replace function connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()
returns text language sql stable security definer set search_path='' as $fingerprint$
  select pg_catalog.md5(pg_catalog.string_agg(
    item, E'\n' order by item collate pg_catalog."C"
  ))
  from (
    select pg_catalog.concat_ws('|','predecessor',
      connected_oauth_binding_private.oauth_binding_target_fingerprint_v1()) item
    union all
    select pg_catalog.concat_ws('|','schema',namespace_row.nspname,
      pg_catalog.pg_get_userbyid(namespace_row.nspowner),
      coalesce(namespace_row.nspacl::text,''),
      coalesce(description.description,''))
    from pg_catalog.pg_namespace as namespace_row
    left join pg_catalog.pg_description as description
      on description.objoid=namespace_row.oid and description.objsubid=0
    where namespace_row.nspname='connected_oauth_code_private'
    union all
    select pg_catalog.concat_ws('|','relation',class_row.relname,
      class_row.relkind,class_row.relrowsecurity,class_row.relforcerowsecurity,
      pg_catalog.pg_get_userbyid(class_row.relowner),
      coalesce(class_row.relacl::text,''),
      coalesce(description.description,''))
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_description as description
      on description.objoid=class_row.oid and description.objsubid=0
    where namespace_row.nspname='connected_oauth_code_private'
      and class_row.relname in (
        'authorization_code_custody',
        'release_bootstrap_dedicated_attestations'
      )
    union all
    select pg_catalog.concat_ws('|','column',class_row.relname,
      attribute_row.attnum,
      attribute_row.attname,
      pg_catalog.format_type(attribute_row.atttypid,attribute_row.atttypmod),
      attribute_row.attnotnull,coalesce(attribute_row.attacl::text,''),
      coalesce(pg_catalog.pg_get_expr(
        default_row.adbin,default_row.adrelid),''))
    from pg_catalog.pg_attribute as attribute_row
    join pg_catalog.pg_class as class_row
      on class_row.oid=attribute_row.attrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_attrdef as default_row
      on default_row.adrelid=attribute_row.attrelid
     and default_row.adnum=attribute_row.attnum
    where namespace_row.nspname='connected_oauth_code_private'
      and class_row.relname in (
        'authorization_code_custody',
        'release_bootstrap_dedicated_attestations'
      )
      and attribute_row.attnum>0 and not attribute_row.attisdropped
    union all
    select pg_catalog.concat_ws('|','policy_set',class_row.relname,
      pg_catalog.count(policy_row.oid),
      coalesce(pg_catalog.md5(pg_catalog.string_agg(
        pg_catalog.concat_ws('|',policy_row.polname,policy_row.polcmd,
          policy_row.polpermissive,
          (
            select pg_catalog.array_agg(
              case when policy_role.role_oid = 0 then 'public'::text
                else pg_catalog.pg_get_userbyid(policy_role.role_oid)::text end
              order by (case when policy_role.role_oid = 0 then 'public'::text
                else pg_catalog.pg_get_userbyid(policy_role.role_oid)::text end)
                collate pg_catalog."C"
            )::text
            from pg_catalog.unnest(policy_row.polroles)
              as policy_role(role_oid)
          ),
          coalesce(pg_catalog.pg_get_expr(
            policy_row.polqual,policy_row.polrelid),''),
          coalesce(pg_catalog.pg_get_expr(
            policy_row.polwithcheck,policy_row.polrelid),'')),
        E'\n' order by policy_row.polname collate pg_catalog."C")),''))
    from pg_catalog.pg_class as class_row
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    left join pg_catalog.pg_policy as policy_row
      on policy_row.polrelid=class_row.oid
    where namespace_row.nspname='connected_oauth_code_private'
      and class_row.relname in (
        'authorization_code_custody',
        'release_bootstrap_dedicated_attestations'
      )
    group by class_row.relname
    union all
    select pg_catalog.concat_ws('|','constraint',class_row.relname,
      constraint_row.conname,
      constraint_row.contype,
      pg_catalog.pg_get_constraintdef(constraint_row.oid,true))
    from pg_catalog.pg_constraint as constraint_row
    join pg_catalog.pg_class as class_row
      on class_row.oid=constraint_row.conrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where namespace_row.nspname='connected_oauth_code_private'
      and class_row.relname in (
        'authorization_code_custody',
        'release_bootstrap_dedicated_attestations'
      )
    union all
    select pg_catalog.concat_ws('|','index',indexed_class.relname,
      index_class.relname,
      pg_catalog.pg_get_indexdef(index_class.oid),
      coalesce(pg_catalog.obj_description(
        index_class.oid,'pg_class'),''))
    from pg_catalog.pg_index as index_row
    join pg_catalog.pg_class as index_class
      on index_class.oid=index_row.indexrelid
    join pg_catalog.pg_class as indexed_class
      on indexed_class.oid=index_row.indrelid
    join pg_catalog.pg_namespace as indexed_namespace
      on indexed_namespace.oid=indexed_class.relnamespace
    where indexed_namespace.nspname='connected_oauth_code_private'
      and indexed_class.relname in (
        'authorization_code_custody',
        'release_bootstrap_dedicated_attestations'
      )
    union all
    select pg_catalog.concat_ws('|','function',
      procedure.oid::pg_catalog.regprocedure::text,
      pg_catalog.pg_get_userbyid(procedure.proowner),procedure.prosecdef,
      procedure.provolatile,coalesce(procedure.proconfig::text,''),
      coalesce(procedure.proacl::text,''),
      coalesce(description.description,''),
      pg_catalog.md5(pg_catalog.pg_get_functiondef(procedure.oid)))
    from pg_catalog.pg_proc as procedure
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=procedure.pronamespace
    left join pg_catalog.pg_description as description
      on description.objoid=procedure.oid and description.objsubid=0
    where (namespace_row.nspname,procedure.proname) in (
      ('public','connected_app_operator_accept_oauth_callback_v2'),
      ('public','connected_app_oauth_code_read_v1'),
      ('public','connected_app_oauth_code_claim_v1'),
      ('public','connected_app_oauth_code_retire_v1'),
      ('public','connected_app_release_bootstrap_authenticate_v1'),
      ('connected_oauth_code_private','dedicated_attestation_sha256_v1'),
      ('public','connected_app_release_bootstrap_attest_dedicated_v1'),
      ('public','connected_app_release_bootstrap_read_dedicated_v1'))
    union all
    select pg_catalog.concat_ws('|','hidden_trigger',trigger_row.tgname,
      pg_catalog.pg_get_triggerdef(trigger_row.oid,true))
    from pg_catalog.pg_trigger as trigger_row
    join pg_catalog.pg_class as class_row on class_row.oid=trigger_row.tgrelid
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where not trigger_row.tgisinternal
      and namespace_row.nspname='connected_oauth_code_private'
      and class_row.relname in (
        'authorization_code_custody',
        'release_bootstrap_dedicated_attestations'
      )
    union all
    select pg_catalog.concat_ws('|','hidden_rule',rewrite_row.rulename,
      pg_catalog.pg_get_ruledef(rewrite_row.oid,true))
    from pg_catalog.pg_rewrite as rewrite_row
    join pg_catalog.pg_class as class_row on class_row.oid=rewrite_row.ev_class
    join pg_catalog.pg_namespace as namespace_row
      on namespace_row.oid=class_row.relnamespace
    where rewrite_row.rulename<>'_RETURN'
      and namespace_row.nspname='connected_oauth_code_private'
      and class_row.relname in (
        'authorization_code_custody',
        'release_bootstrap_dedicated_attestations'
      )
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
       or namespace_row.nspname='connected_oauth_code_private'
  ) as manifest(item)
$fingerprint$;
comment on function connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()
  is 'ASK_CRUMP_CONNECTED_OAUTH_CODE_CUSTODY_TARGET_FINGERPRINT_V1';
alter function connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()
  owner to postgres;
revoke all on function connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()
  from public,anon,authenticated,service_role;

do $postflight$
declare
  target_fingerprint text;
begin
  select connected_oauth_code_private.oauth_code_custody_target_fingerprint_v1()
    into target_fingerprint;
  if target_fingerprint<>'5e4480837c5ebb316da85be988a6561f' then
    raise exception 'connected OAuth code-custody postflight drifted: %',
      target_fingerprint using errcode='55000';
  end if;
  if pg_catalog.has_function_privilege(
       'service_role','public.connected_app_operator_accept_oauth_callback_v1(text,text,text,timestamp with time zone,uuid,uuid,uuid,uuid,bigint,text,text,text,text)','execute')
     or pg_catalog.has_schema_privilege(
       'service_role','connected_oauth_code_private','usage')
     or pg_catalog.has_table_privilege(
       'service_role','connected_oauth_code_private.authorization_code_custody','select')
     or pg_catalog.has_table_privilege(
       'service_role','connected_oauth_code_private.release_bootstrap_dedicated_attestations','select')
     or exists(
       select 1
       from pg_catalog.pg_attribute as attribute_row
       join pg_catalog.pg_class as class_row
         on class_row.oid=attribute_row.attrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname='connected_oauth_code_private'
         and class_row.relname in (
           'authorization_code_custody',
           'release_bootstrap_dedicated_attestations'
         )
         and attribute_row.attnum>0
         and not attribute_row.attisdropped
         and attribute_row.attacl is not null
     )
     or exists(
       select 1
       from pg_catalog.pg_policy as policy_row
       join pg_catalog.pg_class as class_row
         on class_row.oid=policy_row.polrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname='connected_oauth_code_private'
         and class_row.relname in (
           'authorization_code_custody',
           'release_bootstrap_dedicated_attestations'
         )
     )
     or pg_catalog.has_function_privilege(
       'public','public.connected_app_oauth_code_claim_v1(uuid,text,text,uuid,uuid,uuid,text,text)','execute')
     or pg_catalog.has_function_privilege(
       'public','public.connected_app_release_bootstrap_attest_dedicated_v1(uuid,uuid,uuid,text,text,text)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_oauth_code_claim_v1(uuid,text,text,uuid,uuid,uuid,text,text)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_release_bootstrap_authenticate_v1(text)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_release_bootstrap_attest_dedicated_v1(uuid,uuid,uuid,text,text,text)','execute')
     or not pg_catalog.has_function_privilege(
       'service_role','public.connected_app_release_bootstrap_read_dedicated_v1(text)','execute')
     or exists(select 1 from pg_catalog.pg_publication where puballtables)
     or exists(
       select 1 from pg_catalog.pg_publication_namespace
       where pnnspid=pg_catalog.to_regnamespace('connected_oauth_code_private')
     )
     or exists(
       select 1 from pg_catalog.pg_publication_rel as publication_relation
       join pg_catalog.pg_class as class_row
         on class_row.oid=publication_relation.prrelid
       join pg_catalog.pg_namespace as namespace_row
         on namespace_row.oid=class_row.relnamespace
       where namespace_row.nspname='connected_oauth_code_private'
     ) then
    raise exception 'connected OAuth code-custody authority drifted'
      using errcode='55000';
  end if;
end;
$postflight$;

commit;
