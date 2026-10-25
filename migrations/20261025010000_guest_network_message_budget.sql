-- Privacy-minimized shared-network budget for guest text messages.
--
-- The existing account receipt remains authoritative for every Free account.
-- Guests additionally attach a short-lived, one-way network-key receipt so
-- many disposable guest accounts on one network cannot each mint five more
-- messages. Registered Free accounts never enter the network budget.
--
-- The migration runner owns the transaction. Do not embed BEGIN/COMMIT here.

set local lock_timeout = '5s';
set local statement_timeout = '30s';

do $preflight$
declare
  expected_reservation constant text :=
    'public.reserve_free_message_v2(uuid,uuid,text,text)';
  expected_refund constant text :=
    'public.refund_usage_event_v2(uuid,uuid)';
  expected_purge constant text :=
    'public.purge_guest_network_message_events_v1()';
begin
  if pg_catalog.to_regclass('public.users') is null
     or pg_catalog.to_regclass('public.usage_events') is null
     or pg_catalog.to_regclass('cron.job') is null
     or pg_catalog.to_regprocedure(
       'cron.schedule(text,text,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.reserve_free_message_v1(uuid,uuid,text)'
     ) is null
     or pg_catalog.to_regprocedure(
       'public.lock_guest_mode_control_v1()'
     ) is null
     or pg_catalog.to_regprocedure('pg_catalog.gen_random_uuid()') is null then
    raise exception
      'Guest network message-budget prerequisites are missing.'
      using errcode = '55000';
  end if;

  if (
    select count(*)
      from cron.job
     where jobname = 'askcrump_guest_network_retention_v1'
  ) > 1
     or exists (
       select 1
         from cron.job
        where jobname = 'askcrump_guest_network_retention_v1'
          and (
            schedule <> '*/15 * * * *'
            or command <>
              'select * from public.purge_guest_network_message_events_v1();'
            or database <> current_database()
            or username <> current_user
            or nodename <> 'localhost'
            or nodeport <> pg_catalog.inet_server_port()
            or active is not true
          )
     ) then
    raise exception
      'Conflicting guest network retention schedule; refusing migration.'
      using errcode = '55000';
  end if;

  if not exists (
       select 1 from pg_catalog.pg_roles where rolname = 'service_role'
     )
     or not exists (
       select 1 from pg_catalog.pg_roles where rolname = 'anon'
     )
     or not exists (
       select 1 from pg_catalog.pg_roles where rolname = 'authenticated'
     ) then
    raise exception
      'Guest network message-budget database roles are missing.'
      using errcode = '55000';
  end if;

  if (
    select count(*)
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'users'
       and column_name = 'is_guest'
       and data_type = 'boolean'
       and is_nullable = 'NO'
  ) <> 1
     or (
       select count(*)
         from information_schema.columns
        where table_schema = 'public'
          and table_name = 'usage_events'
          and (
            (column_name = 'id' and data_type = 'uuid' and is_nullable = 'NO')
            or (column_name = 'user_id' and data_type = 'uuid' and is_nullable = 'NO')
            or (column_name = 'event_type' and data_type = 'text' and is_nullable = 'NO')
            or (column_name = 'idempotency_key' and data_type = 'text')
            or (
              column_name = 'created_at'
              and data_type = 'timestamp with time zone'
              and is_nullable = 'NO'
            )
          )
     ) <> 5 then
    raise exception
      'Unexpected guest message-budget prerequisite schema.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname = 'reserve_free_message_v2'
       and function_row.oid <> coalesce(
         pg_catalog.to_regprocedure(expected_reservation),
         0::oid
       )
  ) or exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname = 'refund_usage_event_v2'
       and function_row.oid <> coalesce(
         pg_catalog.to_regprocedure(expected_refund),
         0::oid
       )
  ) or exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname = 'purge_guest_network_message_events_v1'
       and function_row.oid <> coalesce(
         pg_catalog.to_regprocedure(expected_purge),
         0::oid
       )
  ) then
    raise exception
      'Unexpected guest network message-budget function overload.'
      using errcode = '55000';
  end if;
end;
$preflight$;

create table if not exists public.guest_network_message_events (
  receipt_id uuid primary key default pg_catalog.gen_random_uuid(),
  usage_event_id uuid unique
    references public.usage_events(id) on delete set null,
  network_key_hash text not null,
  created_at timestamptz not null,
  constraint guest_network_message_events_network_key_hash_check
    check (network_key_hash ~ '^[0-9a-f]{64}$')
);

do $table_guard$
declare
  receipt_attribute smallint;
  usage_event_attribute smallint;
  network_key_hash_attribute smallint;
  usage_event_target_attribute smallint;
  expected_constraints constant text[] := array[
    'guest_network_message_events_network_key_hash_check:c',
    'guest_network_message_events_pkey:p',
    'guest_network_message_events_usage_event_id_fkey:f',
    'guest_network_message_events_usage_event_id_key:u'
  ];
begin
  if (
    select count(*)
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'guest_network_message_events'
  ) <> 4
     or (
       select count(*)
         from information_schema.columns
        where table_schema = 'public'
          and table_name = 'guest_network_message_events'
          and (
            (
              column_name = 'receipt_id'
              and data_type = 'uuid'
              and is_nullable = 'NO'
              and column_default = 'gen_random_uuid()'
            )
            or
            (
              column_name = 'usage_event_id'
              and data_type = 'uuid'
              and is_nullable = 'YES'
            )
            or (
              column_name = 'network_key_hash'
              and data_type = 'text'
              and is_nullable = 'NO'
            )
            or (
              column_name = 'created_at'
              and data_type = 'timestamp with time zone'
              and is_nullable = 'NO'
            )
          )
     ) <> 4 then
    raise exception
      'Unexpected public.guest_network_message_events definition.'
      using errcode = '55000';
  end if;

  select attribute.attnum
    into receipt_attribute
    from pg_catalog.pg_attribute as attribute
   where attribute.attrelid = 'public.guest_network_message_events'::regclass
     and attribute.attname = 'receipt_id'
     and not attribute.attisdropped;

  select attribute.attnum
    into usage_event_attribute
    from pg_catalog.pg_attribute as attribute
   where attribute.attrelid = 'public.guest_network_message_events'::regclass
     and attribute.attname = 'usage_event_id'
     and not attribute.attisdropped;

  select attribute.attnum
    into network_key_hash_attribute
    from pg_catalog.pg_attribute as attribute
   where attribute.attrelid = 'public.guest_network_message_events'::regclass
     and attribute.attname = 'network_key_hash'
     and not attribute.attisdropped;

  select attribute.attnum
    into usage_event_target_attribute
    from pg_catalog.pg_attribute as attribute
   where attribute.attrelid = 'public.usage_events'::regclass
     and attribute.attname = 'id'
     and not attribute.attisdropped;

  if not exists (
       select 1
         from pg_catalog.pg_constraint as constraint_row
         join pg_catalog.pg_index as index_row
           on index_row.indexrelid = constraint_row.conindid
         join pg_catalog.pg_class as index_relation
           on index_relation.oid = index_row.indexrelid
         join pg_catalog.pg_am as access_method
           on access_method.oid = index_relation.relam
         join pg_catalog.pg_opclass as operator_class
           on operator_class.oid = index_row.indclass[0]
        where constraint_row.conrelid =
              'public.guest_network_message_events'::regclass
          and constraint_row.conname =
              'guest_network_message_events_pkey'
          and constraint_row.contype = 'p'
          and constraint_row.conkey = array[receipt_attribute]
          and index_row.indrelid = constraint_row.conrelid
          and index_row.indisunique
          and index_row.indisprimary
          and index_row.indisvalid
          and index_row.indisready
          and index_row.indislive
          and index_row.indimmediate
          and not index_row.indnullsnotdistinct
          and not index_row.indisexclusion
          and not index_row.indisreplident
          and index_row.indpred is null
          and index_row.indexprs is null
          and index_row.indnkeyatts = 1
          and index_row.indnatts = 1
          and index_row.indkey[0] = receipt_attribute
          and access_method.amname = 'btree'
          and operator_class.opcname = 'uuid_ops'
          and operator_class.opcintype = 'uuid'::regtype
          and operator_class.opcdefault
          and index_row.indcollation[0] = 0
          and index_row.indoption[0] = 0
     )
     or not exists (
       select 1
         from pg_catalog.pg_constraint as constraint_row
        where constraint_row.conrelid =
              'public.guest_network_message_events'::regclass
          and constraint_row.conname =
              'guest_network_message_events_usage_event_id_fkey'
          and constraint_row.contype = 'f'
          and constraint_row.confrelid = 'public.usage_events'::regclass
          and constraint_row.confdeltype = 'n'
          and constraint_row.confupdtype = 'a'
          and constraint_row.confmatchtype = 's'
          and constraint_row.conkey = array[usage_event_attribute]
          and constraint_row.confkey = array[usage_event_target_attribute]
          and constraint_row.confdelsetcols is null
     )
     or not exists (
       select 1
         from pg_catalog.pg_constraint as constraint_row
         join pg_catalog.pg_index as index_row
           on index_row.indexrelid = constraint_row.conindid
         join pg_catalog.pg_class as index_relation
           on index_relation.oid = index_row.indexrelid
         join pg_catalog.pg_am as access_method
           on access_method.oid = index_relation.relam
         join pg_catalog.pg_opclass as operator_class
           on operator_class.oid = index_row.indclass[0]
        where constraint_row.conrelid =
              'public.guest_network_message_events'::regclass
          and constraint_row.conname =
              'guest_network_message_events_usage_event_id_key'
          and constraint_row.contype = 'u'
          and constraint_row.conkey = array[usage_event_attribute]
          and index_row.indrelid = constraint_row.conrelid
          and index_row.indisunique
          and not index_row.indisprimary
          and index_row.indisvalid
          and index_row.indisready
          and index_row.indislive
          and index_row.indimmediate
          and not index_row.indnullsnotdistinct
          and not index_row.indisexclusion
          and not index_row.indisreplident
          and index_row.indpred is null
          and index_row.indexprs is null
          and index_row.indnkeyatts = 1
          and index_row.indnatts = 1
          and index_row.indkey[0] = usage_event_attribute
          and access_method.amname = 'btree'
          and operator_class.opcname = 'uuid_ops'
          and operator_class.opcintype = 'uuid'::regtype
          and operator_class.opcdefault
          and index_row.indcollation[0] = 0
          and index_row.indoption[0] = 0
     )
     or not exists (
       select 1
         from pg_catalog.pg_constraint as constraint_row
        where constraint_row.conrelid =
              'public.guest_network_message_events'::regclass
          and constraint_row.conname =
              'guest_network_message_events_network_key_hash_check'
          and constraint_row.contype = 'c'
          and constraint_row.conkey = array[network_key_hash_attribute]
          and not constraint_row.connoinherit
          and pg_catalog.pg_get_constraintdef(constraint_row.oid, false) =
              'CHECK ((network_key_hash ~ ''^[0-9a-f]{64}$''::text))'
     ) then
    raise exception
      'Unexpected public.guest_network_message_events constraints.'
      using errcode = '55000';
  end if;

  if (
       select pg_catalog.array_agg(
         constraint_row.conname || ':' || constraint_row.contype::text
         order by constraint_row.conname
       )
         from pg_catalog.pg_constraint as constraint_row
        where constraint_row.conrelid =
              'public.guest_network_message_events'::regclass
     ) is distinct from expected_constraints
     or exists (
       select 1
         from pg_catalog.pg_constraint as constraint_row
        where constraint_row.conrelid =
              'public.guest_network_message_events'::regclass
          and (
            not constraint_row.convalidated
            or constraint_row.condeferrable
            or constraint_row.condeferred
            or not constraint_row.conislocal
            or constraint_row.coninhcount <> 0
            or constraint_row.conparentid <> 0
          )
     ) then
    raise exception
      'Unexpected public.guest_network_message_events constraint shape.'
      using errcode = '55000';
  end if;
end;
$table_guard$;

create index if not exists guest_network_message_events_network_window_idx
  on public.guest_network_message_events(
    network_key_hash,
    created_at,
    receipt_id
  );

-- The leading timestamp supports the global privacy-retention sweep. The
-- network-leading quota index above cannot efficiently serve that operation.
create index if not exists guest_network_message_events_retention_idx
  on public.guest_network_message_events(created_at, receipt_id);

do $index_guard$
begin
  if not exists (
       select 1
         from pg_catalog.pg_index as index_row
         join pg_catalog.pg_class as index_relation
           on index_relation.oid = index_row.indexrelid
         join pg_catalog.pg_am as access_method
           on access_method.oid = index_relation.relam
        where index_row.indexrelid =
              pg_catalog.to_regclass(
                'public.guest_network_message_events_network_window_idx'
              )
          and index_row.indrelid =
              'public.guest_network_message_events'::regclass
          and index_row.indisvalid
          and index_row.indisready
          and not index_row.indisunique
          and index_row.indpred is null
          and index_row.indexprs is null
          and index_row.indnkeyatts = 3
          and index_row.indnatts = 3
          and access_method.amname = 'btree'
          and pg_catalog.pg_get_indexdef(index_row.indexrelid, 1, true) =
              'network_key_hash'
          and pg_catalog.pg_get_indexdef(index_row.indexrelid, 2, true) =
              'created_at'
          and pg_catalog.pg_get_indexdef(index_row.indexrelid, 3, true) =
              'receipt_id'
     )
     or not exists (
       select 1
         from pg_catalog.pg_index as index_row
         join pg_catalog.pg_class as index_relation
           on index_relation.oid = index_row.indexrelid
         join pg_catalog.pg_am as access_method
           on access_method.oid = index_relation.relam
        where index_row.indexrelid =
              pg_catalog.to_regclass(
                'public.guest_network_message_events_retention_idx'
              )
          and index_row.indrelid =
              'public.guest_network_message_events'::regclass
          and index_row.indisvalid
          and index_row.indisready
          and not index_row.indisunique
          and index_row.indpred is null
          and index_row.indexprs is null
          and index_row.indnkeyatts = 2
          and index_row.indnatts = 2
          and access_method.amname = 'btree'
          and pg_catalog.pg_get_indexdef(index_row.indexrelid, 1, true) =
              'created_at'
          and pg_catalog.pg_get_indexdef(index_row.indexrelid, 2, true) =
              'receipt_id'
     ) then
    raise exception
      'Unexpected guest network message-budget index definition.'
      using errcode = '55000';
  end if;
end;
$index_guard$;

alter table public.guest_network_message_events enable row level security;
alter table public.guest_network_message_events owner to postgres;

revoke all on table public.guest_network_message_events
  from public, anon, authenticated, service_role;

comment on table public.guest_network_message_events is
  'Short-lived one-way network keys for the guest rolling message budget; never raw IP addresses.';
comment on column public.guest_network_message_events.receipt_id is
  'Independent opaque receipt identity; never derived from an account or usage receipt.';
comment on column public.guest_network_message_events.usage_event_id is
  'Nullable refundable account receipt link; account deletion clears the link but preserves the de-identified network receipt until retention purge.';
comment on column public.guest_network_message_events.network_key_hash is
  'Server-keyed lowercase SHA-256 digest of the canonical guest network key; targeted for deletion after 25 hours.';

do $table_security_guard$
declare
  relation_oid constant oid :=
    'public.guest_network_message_events'::regclass;
begin
  if not exists (
       select 1
         from pg_catalog.pg_class as relation_row
        where relation_row.oid = relation_oid
          and relation_row.relkind = 'r'
          and relation_row.relpersistence = 'p'
          and pg_catalog.pg_get_userbyid(relation_row.relowner) = 'postgres'
          and relation_row.relrowsecurity
          and not relation_row.relforcerowsecurity
     )
     or exists (
       select 1
         from pg_catalog.pg_attribute as attribute_row
        where attribute_row.attrelid = relation_oid
          and attribute_row.attnum > 0
          and not attribute_row.attisdropped
          and attribute_row.attacl is not null
     )
     or exists (
       select 1
         from pg_catalog.pg_policy as policy_row
        where policy_row.polrelid = relation_oid
     )
     or (
       select pg_catalog.count(*) <> 4
          or pg_catalog.count(*) filter (
            where trigger_row.tgenabled <> 'O'
               or not trigger_row.tgisinternal
          ) <> 0
         from pg_catalog.pg_trigger as trigger_row
         join pg_catalog.pg_constraint as constraint_row
           on constraint_row.oid = trigger_row.tgconstraint
        where constraint_row.conrelid = relation_oid
          and constraint_row.conname =
              'guest_network_message_events_usage_event_id_fkey'
          and constraint_row.contype = 'f'
     )
     or (
       select pg_catalog.count(*) <> 2
          or pg_catalog.count(*) filter (
            where trigger_row.tgenabled <> 'O'
               or not trigger_row.tgisinternal
               or constraint_row.conname <>
                  'guest_network_message_events_usage_event_id_fkey'
               or constraint_row.contype <> 'f'
          ) <> 0
         from pg_catalog.pg_trigger as trigger_row
         left join pg_catalog.pg_constraint as constraint_row
           on constraint_row.oid = trigger_row.tgconstraint
        where trigger_row.tgrelid = relation_oid
     )
     or exists (
       select 1
         from pg_catalog.pg_rewrite as rewrite_row
        where rewrite_row.ev_class = relation_oid
     )
     or not exists (
       select 1
         from pg_catalog.pg_class as relation_row
         cross join lateral (
           select pg_catalog.count(*) = 8
              and pg_catalog.bool_and(
                grantee_role.rolname = 'postgres'
                and grantor_role.rolname = 'postgres'
                and not acl_row.is_grantable
              ) as is_exact
             from pg_catalog.aclexplode(
               coalesce(
                 relation_row.relacl,
                 pg_catalog.acldefault('r', relation_row.relowner)
               )
             ) as acl_row
             left join pg_catalog.pg_roles as grantee_role
               on grantee_role.oid = acl_row.grantee
             left join pg_catalog.pg_roles as grantor_role
               on grantor_role.oid = acl_row.grantor
         ) as acl_contract
        where relation_row.oid = relation_oid
          and acl_contract.is_exact
     ) then
    raise exception
      'Unexpected guest network message-budget table security contract.'
      using errcode = '55000';
  end if;
end;
$table_security_guard$;

create or replace function public.reserve_free_message_v2(
  p_user_id uuid,
  p_message_id uuid,
  p_fingerprint text,
  p_network_key_hash text
)
returns table(
  outcome text,
  event_id uuid,
  used integer,
  remaining integer,
  next_available_at timestamptz,
  network_used integer,
  network_remaining integer,
  network_next_available_at timestamptz
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_account_limit constant integer := 5;
  v_network_limit constant integer := 25;
  v_window constant interval := interval '24 hours';
  v_now timestamptz;
  v_key text;
  v_existing uuid;
  v_used integer;
  v_oldest timestamptz;
  v_next_available timestamptz;
  v_network_used integer;
  v_network_oldest timestamptz;
  v_network_next_available timestamptz;
  v_inserted uuid;
  v_is_guest boolean := false;
  v_guest_mode_enabled boolean := false;
begin
  if p_user_id is null or p_message_id is null then
    raise exception using
      errcode = '22023',
      message = 'Free message identity is required.';
  end if;
  if coalesce(p_fingerprint, '') !~ '^[0-9a-f]{64}$' then
    raise exception using
      errcode = '22023',
      message = 'Free message fingerprint is invalid.';
  end if;

  v_key := p_message_id::text || ':' || p_fingerprint;

  -- Preserve the established guest-write barrier and account lock order. A
  -- conversion or disable transaction cannot change authority mid-reservation.
  v_guest_mode_enabled := public.lock_guest_mode_control_v1();

  select coalesce(account.is_guest, false)
    into v_is_guest
    from public.users as account
   where account.id = p_user_id
   for share;

  if not found then
    raise exception using
      errcode = '23503',
      message = 'Free message account does not exist.';
  end if;

  if v_is_guest and v_guest_mode_enabled is not true then
    return query select
      'guest_mode_disabled'::text,
      null::uuid,
      0,
      0,
      null::timestamptz,
      null::integer,
      null::integer,
      null::timestamptz;
    return;
  end if;

  -- Registered Free callers deliberately bypass the network identifier. A
  -- guest must provide the privacy-minimized server digest and fails closed.
  if v_is_guest
     and coalesce(p_network_key_hash, '') !~ '^[0-9a-f]{64}$' then
    raise exception using
      errcode = '22023',
      message = 'Guest network key hash is invalid.';
  end if;

  -- This is the same namespace used by reserve_free_message_v1 and the legacy
  -- message consumer. Every path therefore serializes the five-message cap.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      'usage:' || p_user_id::text || ':messages',
      0
    )
  );

  -- Every v2 call locks account first, then network. Calls sharing only one
  -- side of the budget cannot form an account/network lock-order cycle.
  if v_is_guest then
    perform pg_catalog.pg_advisory_xact_lock(
      pg_catalog.hashtextextended(
        'usage:guest-network:' || p_network_key_hash || ':messages',
        0
      )
    );
  end if;

  -- Transaction and statement timestamps can predate either lock wait.
  v_now := pg_catalog.clock_timestamp();

  -- Discover the exact replay before considering either quota. It remains
  -- allowed at both caps and never exposes a refundable event id.
  select event.id
    into v_existing
    from public.usage_events as event
   where event.user_id = p_user_id
     and event.event_type = 'messages'
     and event.idempotency_key = v_key;

  select count(*)::integer, min(event.created_at)
    into v_used, v_oldest
    from public.usage_events as event
   where event.user_id = p_user_id
     and event.event_type = 'messages'
     and event.created_at > v_now - v_window;

  if v_used >= v_account_limit then
    select event.created_at + v_window
      into v_next_available
      from public.usage_events as event
     where event.user_id = p_user_id
       and event.event_type = 'messages'
       and event.created_at > v_now - v_window
     order by event.created_at asc, event.id asc
     offset greatest(v_used - v_account_limit, 0)
     limit 1;
  end if;

  if v_is_guest then
    select count(*)::integer, min(network_event.created_at)
      into v_network_used, v_network_oldest
      from public.guest_network_message_events as network_event
     where network_event.network_key_hash = p_network_key_hash
       and network_event.created_at > v_now - v_window;

    if v_network_used >= v_network_limit then
      select network_event.created_at + v_window
        into v_network_next_available
        from public.guest_network_message_events as network_event
       where network_event.network_key_hash = p_network_key_hash
         and network_event.created_at > v_now - v_window
       order by network_event.created_at asc, network_event.receipt_id asc
       offset greatest(v_network_used - v_network_limit, 0)
       limit 1;
    end if;
  end if;

  if v_existing is not null then
    return query select
      'reused'::text,
      null::uuid,
      v_used,
      greatest(v_account_limit - v_used, 0),
      case
        when v_used >= v_account_limit then v_next_available
        else null
      end,
      v_network_used,
      case
        when v_is_guest then
          greatest(v_network_limit - v_network_used, 0)
        else null
      end,
      case
        when v_is_guest and v_network_used >= v_network_limit then
          v_network_next_available
        else null
      end;
    return;
  end if;

  if v_used >= v_account_limit then
    return query select
      'exhausted'::text,
      null::uuid,
      v_used,
      0,
      v_next_available,
      v_network_used,
      case
        when v_is_guest then
          greatest(v_network_limit - v_network_used, 0)
        else null
      end,
      case
        when v_is_guest and v_network_used >= v_network_limit then
          v_network_next_available
        else null
      end;
    return;
  end if;

  if v_is_guest and v_network_used >= v_network_limit then
    return query select
      'network_exhausted'::text,
      null::uuid,
      v_used,
      greatest(v_account_limit - v_used, 0),
      null::timestamptz,
      v_network_used,
      0,
      v_network_next_available;
    return;
  end if;

  insert into public.usage_events (
    user_id,
    event_type,
    idempotency_key,
    metadata,
    created_at
  ) values (
    p_user_id,
    'messages',
    v_key,
    pg_catalog.jsonb_build_object(
      'source', 'free_message_allowance',
      'messageId', p_message_id::text
    ),
    v_now
  )
  returning id into v_inserted;

  if v_is_guest then
    insert into public.guest_network_message_events (
      usage_event_id,
      network_key_hash,
      created_at
    ) values (
      v_inserted,
      p_network_key_hash,
      v_now
    );
  end if;

  v_used := v_used + 1;
  if v_oldest is null then
    v_oldest := v_now;
  end if;
  if v_used >= v_account_limit then
    v_next_available := v_oldest + v_window;
  end if;

  if v_is_guest then
    v_network_used := v_network_used + 1;
    if v_network_oldest is null then
      v_network_oldest := v_now;
    end if;
    if v_network_used >= v_network_limit then
      v_network_next_available := v_network_oldest + v_window;
    end if;
  end if;

  return query select
    'reserved'::text,
    v_inserted,
    v_used,
    greatest(v_account_limit - v_used, 0),
    case
      when v_used >= v_account_limit then v_next_available
      else null
    end,
    v_network_used,
    case
      when v_is_guest then
        greatest(v_network_limit - v_network_used, 0)
      else null
    end,
    case
      when v_is_guest and v_network_used >= v_network_limit then
        v_network_next_available
      else null
    end;
end;
$function$;

alter function public.reserve_free_message_v2(uuid, uuid, text, text)
  owner to postgres;
revoke all on function public.reserve_free_message_v2(uuid, uuid, text, text)
  from public, anon, authenticated, service_role;
grant execute on function public.reserve_free_message_v2(uuid, uuid, text, text)
  to service_role;

comment on function public.reserve_free_message_v2(uuid, uuid, text, text) is
  'Atomically reserves the five-per-account Free allowance and, for guests only, a 25-per-network rolling-24-hour allowance.';

create or replace function public.refund_usage_event_v2(
  p_user_id uuid,
  p_event_id uuid
)
returns table(refunded boolean)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_owned_event uuid;
  v_event_type text;
  v_network_receipt_id uuid;
  v_has_network_receipt boolean := false;
  v_deleted integer := 0;
begin
  if p_user_id is null or p_event_id is null then
    raise exception using
      errcode = '22023',
      message = 'Usage refund identity is required.';
  end if;

  -- Only an explicitly owned live account receipt can authorize removal of
  -- its short-lived network receipt. Deliberately avoid quota advisories here:
  -- account deletion does not join that protocol, and concurrent removal can
  -- only make a reservation conservatively underfill or false-deny, never
  -- overfill either rolling window.
  select usage_event.id, usage_event.event_type
    into v_owned_event, v_event_type
    from public.usage_events as usage_event
   where usage_event.id = p_event_id
     and usage_event.user_id = p_user_id
   for update;

  if not found then
    return query select false;
    return;
  end if;

  select network_event.receipt_id
    into v_network_receipt_id
    from public.guest_network_message_events as network_event
   where network_event.usage_event_id = p_event_id
   for update;
  v_has_network_receipt := found;

  if v_has_network_receipt then
    if v_event_type <> 'messages' then
      raise exception
        'Guest network receipt is not attached to a message usage event.'
        using errcode = '55000';
    end if;

  end if;

  -- Parent first matches account deletion and the FK action's lock order. The
  -- SET NULL action de-identifies the child before an explicit refund removes
  -- that exact captured receipt. Both writes remain one transaction.
  delete from public.usage_events as usage_event
   where usage_event.id = p_event_id
     and usage_event.user_id = p_user_id;
  get diagnostics v_deleted = row_count;

  if v_deleted = 1 and v_has_network_receipt then
    delete from public.guest_network_message_events as network_event
     where network_event.receipt_id = v_network_receipt_id;
  end if;

  return query select v_deleted = 1;
end;
$function$;

alter function public.refund_usage_event_v2(uuid, uuid)
  owner to postgres;
revoke all on function public.refund_usage_event_v2(uuid, uuid)
  from public, anon, authenticated, service_role;
grant execute on function public.refund_usage_event_v2(uuid, uuid)
  to service_role;

comment on function public.refund_usage_event_v2(uuid, uuid) is
  'Row-locks and refunds one exactly owned usage receipt and its linked guest-network receipt; account deletion cannot invoke this orphan-removal path.';

create or replace function public.purge_guest_network_message_events_v1()
returns table(deleted_count integer, has_more boolean)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_batch_limit constant integer := 10000;
  v_cutoff timestamptz :=
    pg_catalog.clock_timestamp() - interval '25 hours';
  v_batch_deleted integer;
  v_deleted integer := 0;
  v_has_more boolean;
begin
  -- Delete only the privacy-sensitive child receipt. usage_events remains the
  -- durable account ledger and can still identify an exact replay.
  loop
    with expired as (
      select network_event.receipt_id
        from public.guest_network_message_events as network_event
       where network_event.created_at <= v_cutoff
       order by network_event.created_at asc, network_event.receipt_id asc
       limit v_batch_limit
       for update skip locked
    ), removed as (
      delete from public.guest_network_message_events as network_event
      using expired
       where network_event.receipt_id = expired.receipt_id
      returning network_event.receipt_id
    )
    select count(*)::integer
      into v_batch_deleted
      from removed;

    v_deleted := v_deleted + v_batch_deleted;
    exit when v_batch_deleted = 0;
  end loop;

  select exists (
    select 1
      from public.guest_network_message_events as network_event
     where network_event.created_at <= v_cutoff
  ) into v_has_more;

  return query select v_deleted, v_has_more;
end;
$function$;

alter function public.purge_guest_network_message_events_v1()
  owner to postgres;
revoke all on function public.purge_guest_network_message_events_v1()
  from public, anon, authenticated, service_role;
grant execute on function public.purge_guest_network_message_events_v1()
  to service_role;

comment on function public.purge_guest_network_message_events_v1() is
  'Drains unlocked guest network-key receipts older than 25 hours; service role only.';

do $function_security_guard$
begin
  if not exists (
       select 1
         from (
           select pg_catalog.count(*) = 3
              and pg_catalog.bool_and(
                pg_catalog.pg_get_userbyid(function_row.proowner) = 'postgres'
                and language_row.lanname = 'plpgsql'
                and function_row.prokind = 'f'
                and function_row.prosecdef
                and not function_row.proleakproof
                and function_row.provolatile = 'v'
                and function_row.proparallel = 'u'
                and function_row.proretset
                and function_row.proconfig = array['search_path=""']::text[]
                and acl_contract.is_exact
              ) as is_exact
             from (
               values
                 ('public.reserve_free_message_v2(uuid,uuid,text,text)'),
                 ('public.refund_usage_event_v2(uuid,uuid)'),
                 ('public.purge_guest_network_message_events_v1()')
             ) as expected(signature)
             join pg_catalog.pg_proc as function_row
               on function_row.oid =
                  pg_catalog.to_regprocedure(expected.signature)
             join pg_catalog.pg_language as language_row
               on language_row.oid = function_row.prolang
             cross join lateral (
               select pg_catalog.count(*) = 2
                  and pg_catalog.count(*) filter (
                    where grantee_role.rolname = 'postgres'
                      and grantor_role.rolname = 'postgres'
                      and acl_row.privilege_type = 'EXECUTE'
                      and not acl_row.is_grantable
                  ) = 1
                  and pg_catalog.count(*) filter (
                    where grantee_role.rolname = 'service_role'
                      and grantor_role.rolname = 'postgres'
                      and acl_row.privilege_type = 'EXECUTE'
                      and not acl_row.is_grantable
                  ) = 1 as is_exact
                 from pg_catalog.aclexplode(
                   coalesce(
                     function_row.proacl,
                     pg_catalog.acldefault('f', function_row.proowner)
                   )
                 ) as acl_row
                 left join pg_catalog.pg_roles as grantee_role
                   on grantee_role.oid = acl_row.grantee
                 left join pg_catalog.pg_roles as grantor_role
                   on grantor_role.oid = acl_row.grantor
             ) as acl_contract
         ) as function_contract
        where function_contract.is_exact
     ) then
    raise exception
      'Unexpected guest network message-budget function security contract.'
      using errcode = '55000';
  end if;
end;
$function_security_guard$;

do $retention_schedule$
declare
  scheduled_job_id bigint;
begin
  select cron.schedule(
    'askcrump_guest_network_retention_v1',
    '*/15 * * * *',
    'select * from public.purge_guest_network_message_events_v1();'
  ) into scheduled_job_id;

  if scheduled_job_id is null then
    raise exception
      'Guest network retention schedule was not created.'
      using errcode = '55000';
  end if;
end;
$retention_schedule$;

do $retention_schedule_guard$
begin
  if (
    select count(*)
      from cron.job
     where jobname = 'askcrump_guest_network_retention_v1'
       and schedule = '*/15 * * * *'
       and command =
         'select * from public.purge_guest_network_message_events_v1();'
       and database = current_database()
       and username = current_user
       and nodename = 'localhost'
       and nodeport = pg_catalog.inet_server_port()
       and active is true
  ) <> 1 then
    raise exception
      'Guest network retention schedule postflight failed.'
      using errcode = '55000';
  end if;
end;
$retention_schedule_guard$;
