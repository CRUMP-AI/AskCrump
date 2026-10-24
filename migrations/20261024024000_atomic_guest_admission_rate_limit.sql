-- Admit guest previews against installation and shared-IP ceilings atomically.
-- The production migration runner owns the transaction boundary.

do $preflight$
declare
  expected_signature constant text :=
    'public.consume_guest_admission_rate_limit_v1(text,text,integer,integer,integer)';
begin
  if pg_catalog.to_regclass('public.rate_limit_events') is null
     or pg_catalog.to_regprocedure(
       'public.consume_rate_limit_event(text,text,integer,integer)'
     ) is null then
    raise exception
      'Guest admission rate-limit prerequisites are missing.'
      using errcode = '55000';
  end if;

  if (
    select count(*)
      from information_schema.columns
     where table_schema = 'public'
       and table_name = 'rate_limit_events'
       and (
         (column_name = 'scope' and data_type = 'text')
         or (column_name = 'key_hash' and data_type = 'text')
         or (column_name = 'created_at' and data_type = 'timestamp with time zone')
       )
  ) <> 3 then
    raise exception
      'Unexpected public.rate_limit_events definition; refusing guest admission migration.'
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
      'Guest admission database roles are missing.'
      using errcode = '55000';
  end if;

  if exists (
    select 1
      from pg_catalog.pg_proc as function_row
      join pg_catalog.pg_namespace as namespace_row
        on namespace_row.oid = function_row.pronamespace
     where namespace_row.nspname = 'public'
       and function_row.proname = 'consume_guest_admission_rate_limit_v1'
       and function_row.oid <> coalesce(
         pg_catalog.to_regprocedure(expected_signature),
         0::oid
       )
  ) then
    raise exception
      'Unexpected consume_guest_admission_rate_limit_v1 overload; refusing migration.'
      using errcode = '55000';
  end if;
end;
$preflight$;

create or replace function public.consume_guest_admission_rate_limit_v1(
  p_identity_key_hash text,
  p_ip_key_hash text,
  p_identity_limit integer,
  p_ip_limit integer,
  p_window_seconds integer
)
returns table(
  identity_used integer,
  ip_used integer,
  allowed boolean,
  identity_limited boolean,
  ip_limited boolean,
  retry_after integer
)
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_identity_scope constant text := 'auth:guest:identity';
  v_ip_scope constant text := 'auth:guest:ip';
  v_identity_lock bigint;
  v_ip_lock bigint;
  v_now timestamptz;
  v_window interval;
  v_identity_used integer;
  v_ip_used integer;
  v_identity_oldest timestamptz;
  v_ip_oldest timestamptz;
  v_identity_limited boolean;
  v_ip_limited boolean;
  v_retry_after integer := 0;
begin
  if p_identity_key_hash is null
     or p_identity_key_hash !~ '^[0-9a-f]{64}$'
     or p_ip_key_hash is null
     or p_ip_key_hash !~ '^[0-9a-f]{64}$'
     or p_identity_limit is null
     or p_identity_limit < 1
     or p_identity_limit > 1000000
     or p_ip_limit is null
     or p_ip_limit < 1
     or p_ip_limit > 1000000
     or p_window_seconds is null
     or p_window_seconds < 1
     or p_window_seconds > 2592000 then
    raise exception 'Invalid guest admission rate-limit configuration.'
      using errcode = '22023';
  end if;

  -- Match the legacy single-bucket namespace so migration-first rollout and
  -- rollback callers serialize with this paired writer. Global numeric order
  -- prevents two paired calls from deadlocking when one key is shared.
  v_identity_lock := pg_catalog.hashtextextended(
    v_identity_scope || ':' || p_identity_key_hash,
    0
  );
  v_ip_lock := pg_catalog.hashtextextended(
    v_ip_scope || ':' || p_ip_key_hash,
    0
  );

  if v_identity_lock < v_ip_lock then
    perform pg_catalog.pg_advisory_xact_lock(v_identity_lock);
    perform pg_catalog.pg_advisory_xact_lock(v_ip_lock);
  elsif v_ip_lock < v_identity_lock then
    perform pg_catalog.pg_advisory_xact_lock(v_ip_lock);
    perform pg_catalog.pg_advisory_xact_lock(v_identity_lock);
  else
    perform pg_catalog.pg_advisory_xact_lock(v_identity_lock);
  end if;

  -- clock_timestamp() is sampled only after lock acquisition. now() would be
  -- transaction-start time and could be stale after waiting behind a writer.
  v_now := pg_catalog.clock_timestamp();
  v_window := pg_catalog.make_interval(secs => p_window_seconds);

  delete from public.rate_limit_events
   where (
       (
         scope = v_identity_scope
         and key_hash = p_identity_key_hash
       ) or (
         scope = v_ip_scope
         and key_hash = p_ip_key_hash
       )
     )
     and created_at < v_now - (v_window * 2);

  select count(*)::integer, min(created_at)
    into v_identity_used, v_identity_oldest
    from public.rate_limit_events
   where scope = v_identity_scope
     and key_hash = p_identity_key_hash
     and created_at >= v_now - v_window;

  select count(*)::integer, min(created_at)
    into v_ip_used, v_ip_oldest
    from public.rate_limit_events
   where scope = v_ip_scope
     and key_hash = p_ip_key_hash
     and created_at >= v_now - v_window;

  v_identity_limited := v_identity_used >= p_identity_limit;
  v_ip_limited := v_ip_used >= p_ip_limit;

  if v_identity_limited then
    v_retry_after := greatest(
      v_retry_after,
      greatest(
        1,
        pg_catalog.ceil(
          pg_catalog.date_part(
            'epoch',
            (v_identity_oldest + v_window) - v_now
          )
        )::integer
      )
    );
  end if;

  if v_ip_limited then
    v_retry_after := greatest(
      v_retry_after,
      greatest(
        1,
        pg_catalog.ceil(
          pg_catalog.date_part('epoch', (v_ip_oldest + v_window) - v_now)
        )::integer
      )
    );
  end if;

  if v_identity_limited or v_ip_limited then
    return query select
      v_identity_used,
      v_ip_used,
      false,
      v_identity_limited,
      v_ip_limited,
      v_retry_after;
    return;
  end if;

  insert into public.rate_limit_events (scope, key_hash, created_at)
  values
    (v_identity_scope, p_identity_key_hash, v_now),
    (v_ip_scope, p_ip_key_hash, v_now);

  return query select
    v_identity_used + 1,
    v_ip_used + 1,
    true,
    false,
    false,
    0;
end;
$function$;

alter table public.rate_limit_events enable row level security;
revoke all on table public.rate_limit_events from public, anon, authenticated;

revoke all on function public.consume_guest_admission_rate_limit_v1(
  text,
  text,
  integer,
  integer,
  integer
) from public, anon, authenticated, service_role;

grant execute on function public.consume_guest_admission_rate_limit_v1(
  text,
  text,
  integer,
  integer,
  integer
) to service_role;

comment on function public.consume_guest_admission_rate_limit_v1(
  text,
  text,
  integer,
  integer,
  integer
) is
  'Atomically admits a guest installation and shared IP or consumes neither rate-limit bucket.';
