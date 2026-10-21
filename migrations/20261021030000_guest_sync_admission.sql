-- Atomic admission for guest sync growth.
--
-- The guest conversation ceiling (count and bytes) cannot be enforced
-- with a read-count-then-write check: two concurrent pushes with fresh
-- conversation ids would both pass. This function serializes admission
-- on the guest's own user row and records each admission durably — as a
-- placeholder conversation — inside the same transaction, so the next
-- admission always counts what a concurrent one already took.
--
-- The placeholder is revision 0 at the epoch; apply_chat_sync's
-- compare-and-apply accepts any real client payload over it, so a
-- legitimate first save always wins over its own placeholder.
create or replace function public.admit_guest_sync_chats(
    p_user_id uuid,
    p_chat_ids uuid[],
    p_sizes integer[],
    p_max_chats integer,
    p_max_bytes bigint
)
returns uuid[]
language plpgsql
security definer
set search_path = public
as $$
declare
    v_admitted uuid[] := '{}';
    v_count integer;
    v_bytes bigint;
    v_id uuid;
    v_size integer;
begin
    -- Never trust the caller's bounds unboundedly.
    p_max_chats := least(greatest(coalesce(p_max_chats, 0), 0), 200);
    p_max_bytes := least(greatest(coalesce(p_max_bytes, 0), 0), 50000000);

    perform 1 from public.users where id = p_user_id for update;
    if not found then
        return v_admitted;
    end if;

    select count(*), coalesce(sum(length(messages::text)), 0)
    into v_count, v_bytes
    from public.user_chats
    where user_id = p_user_id;

    for i in 1..coalesce(array_length(p_chat_ids, 1), 0) loop
        v_id := p_chat_ids[i];
        v_size := coalesce(p_sizes[i], 0);
        if v_id = any(v_admitted) then
            continue;
        end if;
        if exists (
            select 1 from public.user_chats
            where user_id = p_user_id and chat_id = v_id
        ) then
            -- Updates to conversations the server already owns always
            -- pass: continuity is never rationed.
            v_admitted := v_admitted || v_id;
            continue;
        end if;
        if v_count >= p_max_chats or v_bytes + v_size > p_max_bytes then
            continue;
        end if;
        insert into public.user_chats (
            user_id, chat_id, title, messages, created_at, updated_at, deleted_at, revision
        ) values (
            p_user_id, v_id, 'New conversation', '[]'::jsonb,
            'epoch'::timestamptz, 'epoch'::timestamptz, null, 0
        );
        v_count := v_count + 1;
        v_bytes := v_bytes + v_size;
        v_admitted := v_admitted || v_id;
    end loop;

    return v_admitted;
end;
$$;

-- Same lockdown as the other definer functions: no default PUBLIC
-- EXECUTE for anon/authenticated through PostgREST.
revoke all on function public.admit_guest_sync_chats(uuid, uuid[], integer[], integer, bigint) from public, anon, authenticated;
grant execute on function public.admit_guest_sync_chats(uuid, uuid[], integer[], integer, bigint) to service_role;
