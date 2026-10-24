-- Behavioral, security, denial-side-effect, and concurrency proof for the
-- paired guest-admission limiter. All values are synthetic.

\set ON_ERROR_STOP on

create or replace function pg_temp.assert_true(condition boolean, message text)
returns void
language plpgsql
as $$
begin
  if condition is not true then
    raise exception 'assertion failed: %', message;
  end if;
end;
$$;

select pg_temp.assert_true(
  (
    select function_row.prosecdef
       and function_row.proconfig = array['search_path=""']::text[]
      from pg_catalog.pg_proc as function_row
     where function_row.oid =
       'public.consume_guest_admission_rate_limit_v1(text,text,integer,integer,integer)'::regprocedure
  ),
  'paired limiter must be SECURITY DEFINER with an empty search_path'
);

select pg_temp.assert_true(
  (select count(*) = 1
     from pg_catalog.pg_proc as function_row
     join pg_catalog.pg_namespace as namespace_row
       on namespace_row.oid = function_row.pronamespace
    where namespace_row.nspname = 'public'
      and function_row.proname = 'consume_guest_admission_rate_limit_v1'),
  'paired limiter must not have PostgREST-ambiguous overloads'
);

select pg_temp.assert_true(
  not pg_catalog.has_function_privilege(
    'anon',
    'public.consume_guest_admission_rate_limit_v1(text,text,integer,integer,integer)',
    'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated',
    'public.consume_guest_admission_rate_limit_v1(text,text,integer,integer,integer)',
    'EXECUTE'
  )
  and pg_catalog.has_function_privilege(
    'service_role',
    'public.consume_guest_admission_rate_limit_v1(text,text,integer,integer,integer)',
    'EXECUTE'
  ),
  'paired limiter execution must be service-only'
);

select pg_temp.assert_true(
  (select relrowsecurity from pg_catalog.pg_class where oid = 'public.rate_limit_events'::regclass)
  and not pg_catalog.has_table_privilege('anon', 'public.rate_limit_events', 'SELECT')
  and not pg_catalog.has_table_privilege('authenticated', 'public.rate_limit_events', 'SELECT'),
  'rate-limit event storage must remain RLS protected from browser roles'
);

set role service_role;

create temporary table first_admission as
select * from public.consume_guest_admission_rate_limit_v1(
  repeat('1', 64), repeat('a', 64), 3, 20, 3600
);
reset role;
select pg_temp.assert_true(
  (select allowed and identity_used = 1 and ip_used = 1 from first_admission)
  and (select count(*) = 2 from public.rate_limit_events),
  'fresh admission must insert exactly one identity and one IP event'
);

truncate public.rate_limit_events;
select * from public.consume_guest_admission_rate_limit_v1(
  repeat('2', 64), repeat('b', 64), 1, 20, 3600
);
create temporary table identity_denied as
select * from public.consume_guest_admission_rate_limit_v1(
  repeat('2', 64), repeat('c', 64), 1, 20, 3600
);
select pg_temp.assert_true(
  (select not allowed and identity_limited and not ip_limited from identity_denied)
  and not exists (
    select 1 from public.rate_limit_events
     where scope = 'auth:guest:ip' and key_hash = repeat('c', 64)
  )
  and (select count(*) = 2 from public.rate_limit_events),
  'identity denial must not consume a new shared-IP event'
);

truncate public.rate_limit_events;
select * from public.consume_guest_admission_rate_limit_v1(
  repeat('3', 64), repeat('d', 64), 3, 1, 3600
);
do $rotated_installations$
declare
  digit text;
  result record;
begin
  foreach digit in array array['4','5','6','7','8','9','a','b','c','d'] loop
    select * into result
      from public.consume_guest_admission_rate_limit_v1(
        repeat(digit, 64), repeat('d', 64), 3, 1, 3600
      );
    if result.allowed or not result.ip_limited then
      raise exception 'rotated installation unexpectedly bypassed shared IP';
    end if;
  end loop;
end;
$rotated_installations$;
select pg_temp.assert_true(
  (select count(*) = 2 from public.rate_limit_events)
  and (select count(distinct key_hash) = 1
         from public.rate_limit_events where scope = 'auth:guest:identity'),
  'IP denial with rotated installation IDs must not grow the event table'
);

truncate public.rate_limit_events;
insert into public.rate_limit_events(scope, key_hash, created_at)
values
  ('auth:guest:identity', repeat('e', 64), pg_catalog.clock_timestamp() - interval '50 seconds'),
  ('auth:guest:ip', repeat('f', 64), pg_catalog.clock_timestamp() - interval '20 seconds');
create temporary table both_denied as
select * from public.consume_guest_admission_rate_limit_v1(
  repeat('e', 64), repeat('f', 64), 1, 1, 60
);
select pg_temp.assert_true(
  (select not allowed and identity_limited and ip_limited
          and retry_after between 35 and 45 from both_denied)
  and (select count(*) = 2 from public.rate_limit_events),
  'dual denial must return the later expiry and insert nothing'
);

truncate public.rate_limit_events;
insert into public.rate_limit_events(scope, key_hash, created_at)
values
  ('auth:guest:identity', repeat('1', 64), pg_catalog.clock_timestamp() - interval '130 seconds'),
  ('auth:guest:ip', repeat('2', 64), pg_catalog.clock_timestamp() - interval '130 seconds');
create temporary table after_stale as
select * from public.consume_guest_admission_rate_limit_v1(
  repeat('1', 64), repeat('2', 64), 1, 1, 60
);
select pg_temp.assert_true(
  (select allowed and identity_used = 1 and ip_used = 1 from after_stale)
  and (select count(*) = 2 from public.rate_limit_events),
  'expired events must be pruned and capacity restored'
);

do $invalid_inputs$
begin
  begin
    perform * from public.consume_guest_admission_rate_limit_v1(
      'raw-installation-id', repeat('a', 64), 1, 1, 60
    );
    raise exception 'raw identity key unexpectedly accepted';
  exception when sqlstate '22023' then null;
  end;
  begin
    perform * from public.consume_guest_admission_rate_limit_v1(
      repeat('a', 64), repeat('b', 64), 0, 1, 60
    );
    raise exception 'zero identity limit unexpectedly accepted';
  exception when sqlstate '22023' then null;
  end;
end;
$invalid_inputs$;

truncate public.rate_limit_events;

select public.dblink_connect(
  'guest_pair_a',
  pg_catalog.format(
    'host=%L port=%L dbname=%L user=%L application_name=%L',
    '127.0.0.1', current_setting('port'), current_database(), current_user, 'guest-pair-a'
  )
);
select public.dblink_connect(
  'guest_pair_b',
  pg_catalog.format(
    'host=%L port=%L dbname=%L user=%L application_name=%L',
    '127.0.0.1', current_setting('port'), current_database(), current_user, 'guest-pair-b'
  )
);
select public.dblink_exec('guest_pair_a', 'set role service_role');
select public.dblink_exec('guest_pair_b', 'set role service_role');
select public.dblink_send_query(
  'guest_pair_a',
  $$select * from public.consume_guest_admission_rate_limit_v1(
      repeat('7', 64), repeat('8', 64), 1, 1, 3600
    )$$
);
select public.dblink_send_query(
  'guest_pair_b',
  $$select * from public.consume_guest_admission_rate_limit_v1(
      repeat('7', 64), repeat('8', 64), 1, 1, 3600
    )$$
);

create temporary table concurrent_results (
  caller text,
  identity_used integer,
  ip_used integer,
  allowed boolean,
  identity_limited boolean,
  ip_limited boolean,
  retry_after integer
);
insert into concurrent_results
select 'a', result.*
  from public.dblink_get_result('guest_pair_a') as result(
    identity_used integer, ip_used integer, allowed boolean,
    identity_limited boolean, ip_limited boolean, retry_after integer
  );
insert into concurrent_results
select 'b', result.*
  from public.dblink_get_result('guest_pair_b') as result(
    identity_used integer, ip_used integer, allowed boolean,
    identity_limited boolean, ip_limited boolean, retry_after integer
  );
select pg_temp.assert_true(
  (select count(*) = 1 from concurrent_results where allowed)
  and (select count(*) = 1 from concurrent_results where not allowed)
  and (select count(*) = 2 from public.rate_limit_events),
  'concurrent calls at limit one must admit exactly one paired event set'
);

select public.dblink_disconnect('guest_pair_a');
select public.dblink_disconnect('guest_pair_b');

select 'atomic guest admission rate-limit tests passed' as result;
