\set ON_ERROR_STOP on

create extension if not exists dblink;

create or replace function pg_temp.assert_true(
  condition boolean,
  failure_message text
)
returns void
language plpgsql
as $$
begin
  if condition is not true then
    raise exception 'PostgreSQL guest-sync gate failed: %', failure_message;
  end if;
end;
$$;

select pg_temp.assert_true(
  pg_catalog.has_function_privilege(
    'service_role',
    'public.apply_guest_chat_sync_v2(uuid,uuid,text,jsonb,timestamptz,timestamptz,timestamptz,bigint)',
    'EXECUTE'
  ),
  'service_role cannot execute the atomic guest-sync RPC'
);
select pg_temp.assert_true(
  not pg_catalog.has_function_privilege(
    'anon',
    'public.apply_guest_chat_sync_v2(uuid,uuid,text,jsonb,timestamptz,timestamptz,timestamptz,bigint)',
    'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated',
    'public.apply_guest_chat_sync_v2(uuid,uuid,text,jsonb,timestamptz,timestamptz,timestamptz,bigint)',
    'EXECUTE'
  ),
  'the definer RPC is exposed to a browser API role'
);
select pg_temp.assert_true(
  pg_catalog.has_function_privilege(
    'service_role',
    'public.persist_guest_chat_reply_v1(uuid,uuid,text,jsonb,jsonb)',
    'EXECUTE'
  ),
  'service_role cannot execute the guest reply persistence RPC'
);
select pg_temp.assert_true(
  not pg_catalog.has_function_privilege(
    'anon',
    'public.persist_guest_chat_reply_v1(uuid,uuid,text,jsonb,jsonb)',
    'EXECUTE'
  )
  and not pg_catalog.has_function_privilege(
    'authenticated',
    'public.persist_guest_chat_reply_v1(uuid,uuid,text,jsonb,jsonb)',
    'EXECUTE'
  ),
  'the guest reply persistence RPC is exposed to a browser API role'
);
select pg_temp.assert_true(
  not pg_catalog.has_function_privilege(
    'service_role',
    'public.admit_guest_sync_chats(uuid,uuid[],integer[],integer,bigint)',
    'EXECUTE'
  ),
  'the legacy caller-sized admission RPC remains executable'
);

-- The release singleton is intentionally installed disabled. This disposable
-- fixture enables it directly as the migration owner so bounded guest writes
-- can be exercised before the later service-role operator RPC is installed.
update public.guest_mode_control
   set enabled = true,
       updated_at = pg_catalog.clock_timestamp()
 where singleton is true;

insert into public.users (id, is_guest)
values
  ('10000000-0000-4000-8000-000000000001', true),
  ('20000000-0000-4000-8000-000000000001', true),
  ('30000000-0000-4000-8000-000000000001', true),
  ('40000000-0000-4000-8000-000000000001', true),
  ('50000000-0000-4000-8000-000000000001', true),
  ('60000000-0000-4000-8000-000000000001', false);

set role service_role;

-- Unknown tombstones are no-ops and never create a row.
create temporary table unknown_tombstone_result as
select *
from public.apply_guest_chat_sync_v2(
  '10000000-0000-4000-8000-000000000001',
  '11000000-0000-4000-8000-000000000001',
  'Unknown',
  '[]'::jsonb,
  now(),
  now(),
  now(),
  1
);
select pg_temp.assert_true(
  (select not accepted and outcome = 'unknown_tombstone' from unknown_tombstone_result),
  'an unknown tombstone was not rejected explicitly'
);
select pg_temp.assert_true(
  not exists (
    select 1 from public.user_chats
     where user_id = '10000000-0000-4000-8000-000000000001'
  ),
  'an unknown tombstone created a conversation row'
);

-- A normal guest reply persists both messages through the bounded wrapper.
create temporary table guest_reply_success_result as
select *
from public.persist_guest_chat_reply_v1(
  '10000000-0000-4000-8000-000000000001',
  '12000000-0000-4000-8000-000000000001',
  'Reply success',
  pg_catalog.jsonb_build_object(
    'id', 'reply-success-user',
    'role', 'user',
    'content', 'Hello'
  ),
  pg_catalog.jsonb_build_object(
    'id', 'reply-success-assistant',
    'role', 'assistant',
    'inReplyTo', 'reply-success-user',
    'content', 'Hi'
  )
);
select pg_temp.assert_true(
  (
    select accepted
       and outcome = 'accepted'
       and resulting_revision = 2
       and resulting_updated_at is not null
       and stored_chat_count = 1
       and chat_bytes > 0
      from guest_reply_success_result
  ),
  'a normal guest reply was not persisted'
);
select pg_temp.assert_true(
  (
    select pg_catalog.jsonb_array_length(messages) = 2
      from public.user_chats
     where user_id = '10000000-0000-4000-8000-000000000001'
       and chat_id = '12000000-0000-4000-8000-000000000001'
  ),
  'the normal guest reply did not persist both messages'
);

create temporary table guest_reply_success_snapshot as
select messages, revision, updated_at
from public.user_chats
where user_id = '10000000-0000-4000-8000-000000000001'
  and chat_id = '12000000-0000-4000-8000-000000000001';

-- A post-merge UTF-8 payload above 200k bytes must leave the existing row
-- byte-for-byte and revision-for-revision unchanged.
create temporary table oversized_guest_reply_result as
select *
from public.persist_guest_chat_reply_v1(
  '10000000-0000-4000-8000-000000000001',
  '12000000-0000-4000-8000-000000000001',
  'Reply success',
  pg_catalog.jsonb_build_object(
    'id', 'reply-oversized-user',
    'role', 'user',
    'content', pg_catalog.repeat('é', 60000)
  ),
  pg_catalog.jsonb_build_object(
    'id', 'reply-oversized-assistant',
    'role', 'assistant',
    'inReplyTo', 'reply-oversized-user',
    'content', pg_catalog.repeat('é', 60000)
  )
);
select pg_temp.assert_true(
  (
    select not accepted and outcome = 'quota_exceeded'
      from oversized_guest_reply_result
  ),
  'an oversized post-merge guest reply was not rejected'
);
select pg_temp.assert_true(
  (
    select candidate.messages = snapshot.messages
       and candidate.revision = snapshot.revision
       and candidate.updated_at = snapshot.updated_at
      from public.user_chats as candidate
      cross join guest_reply_success_snapshot as snapshot
     where candidate.user_id = '10000000-0000-4000-8000-000000000001'
       and candidate.chat_id = '12000000-0000-4000-8000-000000000001'
  ),
  'the oversized guest reply was not fully rolled back'
);

-- Character count is not a byte count: a multibyte payload below 200k
-- characters but above 200k UTF-8 bytes must roll back completely.
create temporary table multibyte_result as
select *
from public.apply_guest_chat_sync_v2(
  '20000000-0000-4000-8000-000000000001',
  '21000000-0000-4000-8000-000000000001',
  'Multibyte',
  pg_catalog.jsonb_build_array(
    pg_catalog.jsonb_build_object('role', 'user', 'content', repeat('é', 100000))
  ),
  now(),
  now(),
  null,
  1
);
select pg_temp.assert_true(
  (select not accepted and outcome = 'quota_exceeded' from multibyte_result),
  'the per-chat cap did not use UTF-8 bytes'
);
select pg_temp.assert_true(
  not exists (
    select 1 from public.user_chats
     where user_id = '20000000-0000-4000-8000-000000000001'
  ),
  'the inner subtransaction did not roll back an oversized insert'
);

reset role;
-- Existing rows still update at the 50-row ceiling; row 51 does not appear.
insert into public.user_chats (
  user_id, chat_id, title, messages, created_at, updated_at, revision
)
select
  '30000000-0000-4000-8000-000000000001',
  ('30000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  'Stored',
  '[]'::jsonb,
  now() - interval '1 hour',
  now() - interval '1 hour',
  1
from pg_catalog.generate_series(1, 50) as series;

set role service_role;
create temporary table at_count_update_result as
select *
from public.apply_guest_chat_sync_v2(
  '30000000-0000-4000-8000-000000000001',
  '30000000-0000-4000-8000-000000000001',
  'Updated safely',
  pg_catalog.jsonb_build_array(pg_catalog.jsonb_build_object('content', 'kept')),
  now() - interval '1 hour',
  now(),
  null,
  2
);
create temporary table over_count_result as
select *
from public.apply_guest_chat_sync_v2(
  '30000000-0000-4000-8000-000000000001',
  '31000000-0000-4000-8000-000000000001',
  'Row 51',
  '[]'::jsonb,
  now(),
  now(),
  null,
  1
);
select pg_temp.assert_true(
  (select accepted from at_count_update_result),
  'an existing conversation could not update at the row ceiling'
);
select pg_temp.assert_true(
  (select not accepted and outcome = 'quota_exceeded' from over_count_result),
  'the 51st conversation was not rejected'
);
select pg_temp.assert_true(
  (select count(*) = 50 from public.user_chats
    where user_id = '30000000-0000-4000-8000-000000000001'),
  'the rejected 51st row was not rolled back'
);
create temporary table reply_over_count_result as
select *
from public.persist_guest_chat_reply_v1(
  '30000000-0000-4000-8000-000000000001',
  '32000000-0000-4000-8000-000000000001',
  'Reply row 51',
  pg_catalog.jsonb_build_object(
    'id', 'row-51-user',
    'role', 'user',
    'content', 'Hello'
  ),
  pg_catalog.jsonb_build_object(
    'id', 'row-51-assistant',
    'role', 'assistant',
    'inReplyTo', 'row-51-user',
    'content', 'Hi'
  )
);
select pg_temp.assert_true(
  (
    select not accepted
       and outcome = 'quota_exceeded'
       and stored_chat_count = 50
      from reply_over_count_result
  ),
  'the reply wrapper did not reject conversation row 51'
);
select pg_temp.assert_true(
  not exists (
    select 1
      from public.user_chats
     where user_id = '30000000-0000-4000-8000-000000000001'
       and chat_id = '32000000-0000-4000-8000-000000000001'
  )
  and (
    select count(*) = 50
      from public.user_chats
     where user_id = '30000000-0000-4000-8000-000000000001'
  ),
  'the rejected reply-created row 51 was not rolled back'
);
reset role;
-- Legacy over-cap data stays cleanable: a known tombstone may reduce its
-- actual footprint even when the account cannot become compliant in one step.
insert into public.user_chats (
  user_id, chat_id, title, messages, created_at, updated_at, revision
)
select
  '40000000-0000-4000-8000-000000000001',
  ('40000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  'Legacy oversized',
  pg_catalog.jsonb_build_array(
    pg_catalog.jsonb_build_object('role', 'user', 'content', repeat('x', 190000))
  ),
  now() - interval '1 hour',
  now() - interval '1 hour',
  1
from pg_catalog.generate_series(1, 11) as series;

set role service_role;
create temporary table safe_tombstone_result as
select *
from public.apply_guest_chat_sync_v2(
  '40000000-0000-4000-8000-000000000001',
  '40000000-0000-4000-8000-000000000001',
  'Deleted',
  '[]'::jsonb,
  now() - interval '1 hour',
  now(),
  now(),
  2
);
select pg_temp.assert_true(
  (select accepted and outcome = 'accepted' from safe_tombstone_result),
  'a known tombstone could not shrink legacy over-cap state'
);
select pg_temp.assert_true(
  (
    select deleted_at is not null and messages = '[]'::jsonb
      from public.user_chats
     where user_id = '40000000-0000-4000-8000-000000000001'
       and chat_id = '40000000-0000-4000-8000-000000000001'
  ),
  'the accepted tombstone did not durably shrink the row'
);
reset role;

-- Two individually admissible writes that exceed the total only together are
-- started concurrently. The owner-row lock must authorize exactly one.
insert into public.user_chats (
  user_id, chat_id, title, messages, created_at, updated_at, revision
)
select
  '50000000-0000-4000-8000-000000000001',
  ('50000000-0000-4000-8000-' || pg_catalog.lpad(series::text, 12, '0'))::uuid,
  'Near total cap',
  pg_catalog.jsonb_build_array(
    pg_catalog.jsonb_build_object('role', 'user', 'content', repeat('x', 198000))
  ),
  now() - interval '1 hour',
  now() - interval '1 hour',
  1
from pg_catalog.generate_series(1, 10) as series;

select public.dblink_connect(
  'guest_sync_a',
  pg_catalog.format('dbname=%L user=%L', current_database(), current_user)
);
select public.dblink_connect(
  'guest_sync_b',
  pg_catalog.format('dbname=%L user=%L', current_database(), current_user)
);
select public.dblink_exec('guest_sync_a', 'set role service_role');
select public.dblink_exec('guest_sync_b', 'set role service_role');
select public.dblink_send_query(
  'guest_sync_a',
  $query$
    select * from public.apply_guest_chat_sync_v2(
      '50000000-0000-4000-8000-000000000001',
      '51000000-0000-4000-8000-000000000001',
      'Concurrent A',
      jsonb_build_array(jsonb_build_object('content', repeat('a', 15000))),
      now(), now(), null, 1
    )
  $query$
);
select public.dblink_send_query(
  'guest_sync_b',
  $query$
    select * from public.apply_guest_chat_sync_v2(
      '50000000-0000-4000-8000-000000000001',
      '51000000-0000-4000-8000-000000000002',
      'Concurrent B',
      jsonb_build_array(jsonb_build_object('content', repeat('b', 15000))),
      now(), now(), null, 1
    )
  $query$
);

create temporary table concurrent_results (
  accepted boolean,
  resulting_revision bigint,
  outcome text,
  stored_chat_count integer,
  stored_bytes bigint,
  chat_bytes bigint
);
insert into concurrent_results
select * from public.dblink_get_result('guest_sync_a') as result(
  accepted boolean,
  resulting_revision bigint,
  outcome text,
  stored_chat_count integer,
  stored_bytes bigint,
  chat_bytes bigint
);
insert into concurrent_results
select * from public.dblink_get_result('guest_sync_b') as result(
  accepted boolean,
  resulting_revision bigint,
  outcome text,
  stored_chat_count integer,
  stored_bytes bigint,
  chat_bytes bigint
);
select pg_temp.assert_true(
  (select count(*) = 1 from concurrent_results where accepted),
  'concurrent calls did not authorize exactly one candidate'
);
select pg_temp.assert_true(
  (select count(*) = 1 from concurrent_results where outcome = 'quota_exceeded'),
  'concurrent calls did not reject exactly one over-total candidate'
);
select pg_temp.assert_true(
  (
    select coalesce(
      sum(pg_catalog.octet_length(messages::text)::bigint), 0
    ) <= 2000000
    from public.user_chats
    where user_id = '50000000-0000-4000-8000-000000000001'
  ),
  'concurrent guest sync exceeded the fixed total-byte cap'
);
select public.dblink_disconnect('guest_sync_a');
select public.dblink_disconnect('guest_sync_b');

-- The guest-only RPC fails closed for a non-guest account.
set role service_role;
create temporary table registered_result as
select *
from public.apply_guest_chat_sync_v2(
  '60000000-0000-4000-8000-000000000001',
  '61000000-0000-4000-8000-000000000001',
  'Wrong path',
  '[]'::jsonb,
  now(), now(), null, 1
);
select pg_temp.assert_true(
  (select not accepted and outcome = 'not_guest' from registered_result),
  'the guest-only RPC accepted a registered account'
);
create temporary table registered_reply_result as
select *
from public.persist_guest_chat_reply_v1(
  '60000000-0000-4000-8000-000000000001',
  '62000000-0000-4000-8000-000000000001',
  'Wrong reply path',
  pg_catalog.jsonb_build_object(
    'id', 'registered-user',
    'role', 'user',
    'content', 'Hello'
  ),
  pg_catalog.jsonb_build_object(
    'id', 'registered-assistant',
    'role', 'assistant',
    'inReplyTo', 'registered-user',
    'content', 'Hi'
  )
);
select pg_temp.assert_true(
  (
    select not accepted and outcome = 'not_guest'
      from registered_reply_result
  ),
  'the guest reply RPC accepted a registered account'
);
select pg_temp.assert_true(
  not exists (
    select 1
      from public.user_chats
     where user_id = '60000000-0000-4000-8000-000000000001'
       and chat_id = '62000000-0000-4000-8000-000000000001'
  ),
  'the rejected registered-account reply created a conversation'
);
reset role; -- Return to the migration-test owner.
