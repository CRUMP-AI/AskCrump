-- Server-authoritative guest conversation sync.
--
-- Guest sync used to reserve a caller-reported byte count and then apply the
-- chat through a second RPC. That split was both race-prone and incapable of
-- measuring the row produced by merge_chat_messages. The replacement below
-- serializes every guest sync for an owner, applies one candidate inside a
-- PL/pgSQL exception block (an inner subtransaction), measures the stored
-- jsonb in UTF-8 bytes, and rolls the candidate back when it exceeds a fixed
-- database-owned ceiling.
--
-- The migration runner owns the surrounding transaction. Do not add BEGIN or
-- COMMIT here; doing so can leave schema and migration history out of sync.

create or replace function public.apply_guest_chat_sync_v2(
    p_user_id uuid,
    p_chat_id uuid,
    p_title text,
    p_messages jsonb,
    p_created_at timestamptz,
    p_updated_at timestamptz,
    p_deleted_at timestamptz,
    p_revision bigint
)
returns table(
    accepted boolean,
    resulting_revision bigint,
    outcome text,
    stored_chat_count integer,
    stored_bytes bigint,
    chat_bytes bigint
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_is_guest boolean;
    v_guest_mode_enabled boolean := false;
    v_existed boolean := false;
    v_before_revision bigint := 0;
    v_before_chat_bytes bigint := 0;
    v_before_count integer := 0;
    v_before_total bigint := 0;
    v_applied boolean := false;
    v_after_revision bigint := 0;
    v_after_chat_bytes bigint := 0;
    v_after_count integer := 0;
    v_after_total bigint := 0;
    v_within_caps boolean := false;
    v_safe_reduction boolean := false;
begin
    -- Acquire the shared side of the global guest-write barrier before the
    -- owner row. Disable uses the exclusive side of the same lock, so once it
    -- commits no waiting or newly-started guest sync can persist afterward.
    v_guest_mode_enabled := public.lock_guest_mode_control_v1();

    -- This row lock is the per-owner serialization point. It is acquired
    -- before reading footprint totals and held through the inner apply/check.
    select candidate.is_guest
      into v_is_guest
      from public.users as candidate
     where candidate.id = p_user_id
     for update;

    if not found then
        return query
        select false, 0::bigint, 'user_not_found'::text, 0, 0::bigint, 0::bigint;
        return;
    end if;

    if not coalesce(v_is_guest, false) then
        return query
        select false, 0::bigint, 'not_guest'::text, 0, 0::bigint, 0::bigint;
        return;
    end if;

    if v_guest_mode_enabled is not true then
        return query
        select false, 0::bigint, 'guest_mode_disabled'::text, 0, 0::bigint, 0::bigint;
        return;
    end if;

    select true,
           candidate.revision,
           pg_catalog.octet_length(candidate.messages::text)::bigint
      into v_existed, v_before_revision, v_before_chat_bytes
      from public.user_chats as candidate
     where candidate.user_id = p_user_id
       and candidate.chat_id = p_chat_id;

    v_existed := coalesce(v_existed, false);
    v_before_revision := coalesce(v_before_revision, 0);
    v_before_chat_bytes := coalesce(v_before_chat_bytes, 0);

    select count(*)::integer,
           coalesce(
               sum(pg_catalog.octet_length(candidate.messages::text)::bigint),
               0::bigint
           )
      into v_before_count, v_before_total
      from public.user_chats as candidate
     where candidate.user_id = p_user_id;

    -- A tombstone may only shrink/close a conversation already owned by the
    -- user. Never manufacture rows from arbitrary unknown deletion ids.
    if p_deleted_at is not null and not v_existed then
        return query
        select false,
               0::bigint,
               'unknown_tombstone'::text,
               v_before_count,
               v_before_total,
               0::bigint;
        return;
    end if;

    begin
        select applied.accepted, applied.resulting_revision
          into v_applied, v_after_revision
          from public.apply_chat_sync(
              p_user_id,
              p_chat_id,
              p_title,
              p_messages,
              p_created_at,
              p_updated_at,
              p_deleted_at,
              p_revision
          ) as applied;

        if not coalesce(v_applied, false) then
            return query
            select false,
                   coalesce(v_after_revision, v_before_revision),
                   'stale'::text,
                   v_before_count,
                   v_before_total,
                   v_before_chat_bytes;
            return;
        end if;

        select candidate.revision,
               pg_catalog.octet_length(candidate.messages::text)::bigint
          into v_after_revision, v_after_chat_bytes
          from public.user_chats as candidate
         where candidate.user_id = p_user_id
           and candidate.chat_id = p_chat_id;

        select count(*)::integer,
               coalesce(
                   sum(pg_catalog.octet_length(candidate.messages::text)::bigint),
                   0::bigint
               )
          into v_after_count, v_after_total
          from public.user_chats as candidate
         where candidate.user_id = p_user_id;

        -- These are product limits, not caller inputs.
        v_within_caps := v_after_count <= 50
            and v_after_chat_bytes <= 200000
            and v_after_total <= 2000000;

        -- Existing data that predates these ceilings must remain cleanable.
        -- A known tombstone or a strict byte reduction may proceed even while
        -- the account is still above a ceiling, provided it cannot increase
        -- row count, chat bytes, or the owner's total bytes.
        v_safe_reduction := v_existed
            and v_after_count <= v_before_count
            and v_after_chat_bytes <= v_before_chat_bytes
            and v_after_total <= v_before_total
            and (
                p_deleted_at is not null
                or v_after_chat_bytes < v_before_chat_bytes
                or v_after_total < v_before_total
            );

        if not v_within_caps and not v_safe_reduction then
            raise exception using
                errcode = 'GX001',
                message = 'guest sync storage quota exceeded';
        end if;
    exception
        when sqlstate 'GX001' then
            -- Entering this handler rolls back only the inner block, including
            -- apply_chat_sync. Re-read the durable pre-candidate state.
            select count(*)::integer,
                   coalesce(
                       sum(pg_catalog.octet_length(candidate.messages::text)::bigint),
                       0::bigint
                   )
              into v_after_count, v_after_total
              from public.user_chats as candidate
             where candidate.user_id = p_user_id;

            select candidate.revision,
                   pg_catalog.octet_length(candidate.messages::text)::bigint
              into v_after_revision, v_after_chat_bytes
              from public.user_chats as candidate
             where candidate.user_id = p_user_id
               and candidate.chat_id = p_chat_id;

            return query
            select false,
                   coalesce(v_after_revision, v_before_revision),
                   'quota_exceeded'::text,
                   v_after_count,
                   v_after_total,
                   coalesce(v_after_chat_bytes, 0::bigint);
            return;
    end;

    return query
    select true,
           v_after_revision,
           'accepted'::text,
           v_after_count,
           v_after_total,
           v_after_chat_bytes;
end;
$$;

comment on function public.apply_guest_chat_sync_v2(
    uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint
) is
'Atomically applies one guest chat sync and enforces fixed post-merge UTF-8 storage caps.';

-- SECURITY DEFINER functions default to PUBLIC execution. This RPC is a
-- backend-only capability and must never be reachable through anon or an end
-- user's authenticated PostgREST session.
revoke all on function public.apply_guest_chat_sync_v2(
    uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint
) from public, anon, authenticated, service_role;
grant execute on function public.apply_guest_chat_sync_v2(
    uuid, uuid, text, jsonb, timestamptz, timestamptz, timestamptz, bigint
) to service_role;

-- Normal /api/chat replies must cross the same guest storage boundary as a
-- later browser sync. The legacy persistence RPC predates guest mode and does
-- not lock the owner or measure the post-merge row, so wrap it in a serialized
-- inner subtransaction and roll back only the candidate reply when it would
-- exceed a database-owned cap.
create or replace function public.persist_guest_chat_reply_v1(
    p_user_id uuid,
    p_chat_id uuid,
    p_title text,
    p_user_message jsonb,
    p_assistant_message jsonb
)
returns table(
    accepted boolean,
    outcome text,
    resulting_revision bigint,
    resulting_updated_at timestamptz,
    stored_chat_count integer,
    stored_bytes bigint,
    chat_bytes bigint
)
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_is_guest boolean;
    v_guest_mode_enabled boolean := false;
    v_before_count integer := 0;
    v_before_total bigint := 0;
    v_before_chat_bytes bigint := 0;
    v_after_count integer := 0;
    v_after_total bigint := 0;
    v_after_chat_bytes bigint := 0;
    v_revision bigint;
    v_updated_at timestamptz;
begin
    -- Keep the same global control -> owner lock order as reservation and
    -- browser sync. The shared control lock remains held through persistence.
    v_guest_mode_enabled := public.lock_guest_mode_control_v1();

    select candidate.is_guest
      into v_is_guest
      from public.users as candidate
     where candidate.id = p_user_id
     for update;

    if not found then
        return query select false, 'user_not_found'::text, 0::bigint, null::timestamptz, 0, 0::bigint, 0::bigint;
        return;
    end if;
    if not coalesce(v_is_guest, false) then
        return query select false, 'not_guest'::text, 0::bigint, null::timestamptz, 0, 0::bigint, 0::bigint;
        return;
    end if;
    if v_guest_mode_enabled is not true then
        return query select false, 'guest_mode_disabled'::text, 0::bigint, null::timestamptz, 0, 0::bigint, 0::bigint;
        return;
    end if;

    select count(*)::integer,
           coalesce(sum(pg_catalog.octet_length(candidate.messages::text)::bigint), 0::bigint)
      into v_before_count, v_before_total
      from public.user_chats as candidate
     where candidate.user_id = p_user_id;

    select coalesce(pg_catalog.octet_length(candidate.messages::text)::bigint, 0::bigint)
      into v_before_chat_bytes
      from public.user_chats as candidate
     where candidate.user_id = p_user_id
       and candidate.chat_id = p_chat_id;
    v_before_chat_bytes := coalesce(v_before_chat_bytes, 0::bigint);

    begin
        select persisted.resulting_revision, persisted.resulting_updated_at
          into v_revision, v_updated_at
          from public.persist_chat_reply(
              p_user_id,
              p_chat_id,
              p_title,
              p_user_message,
              p_assistant_message
          ) as persisted;

        select count(*)::integer,
               coalesce(sum(pg_catalog.octet_length(candidate.messages::text)::bigint), 0::bigint)
          into v_after_count, v_after_total
          from public.user_chats as candidate
         where candidate.user_id = p_user_id;

        select coalesce(pg_catalog.octet_length(candidate.messages::text)::bigint, 0::bigint)
          into v_after_chat_bytes
          from public.user_chats as candidate
         where candidate.user_id = p_user_id
           and candidate.chat_id = p_chat_id;
        v_after_chat_bytes := coalesce(v_after_chat_bytes, 0::bigint);

        if not (
            v_after_count <= 50
            and v_after_chat_bytes <= 200000
            and v_after_total <= 2000000
        ) and not (
            v_after_count <= v_before_count
            and v_after_chat_bytes <= v_before_chat_bytes
            and v_after_total <= v_before_total
        ) then
            raise exception using
                errcode = 'GX001',
                message = 'guest reply storage quota exceeded';
        end if;
    exception
        when sqlstate 'GX001' then
            return query select
                false,
                'quota_exceeded'::text,
                0::bigint,
                null::timestamptz,
                v_before_count,
                v_before_total,
                v_before_chat_bytes;
            return;
    end;

    return query select
        true,
        'accepted'::text,
        v_revision,
        v_updated_at,
        v_after_count,
        v_after_total,
        v_after_chat_bytes;
end;
$$;

comment on function public.persist_guest_chat_reply_v1(uuid, uuid, text, jsonb, jsonb) is
'Atomically persists one guest chat reply while enforcing fixed post-merge UTF-8 storage caps.';

revoke all on function public.persist_guest_chat_reply_v1(uuid, uuid, text, jsonb, jsonb)
from public, anon, authenticated, service_role;
grant execute on function public.persist_guest_chat_reply_v1(uuid, uuid, text, jsonb, jsonb)
to service_role;

-- A deployment that briefly installed the old two-step admission RPC keeps
-- its data untouched, but the unsafe capability is retired for every API role.
do $retire_guest_admission$
begin
    if pg_catalog.to_regprocedure(
        'public.admit_guest_sync_chats(uuid,uuid[],integer[],integer,bigint)'
    ) is not null then
        execute
            'revoke all on function public.admit_guest_sync_chats(uuid, uuid[], integer[], integer, bigint) '
            'from public, anon, authenticated, service_role';
    end if;
end;
$retire_guest_admission$;
