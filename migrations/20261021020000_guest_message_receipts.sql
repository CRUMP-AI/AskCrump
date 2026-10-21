-- Guest allowance receipts: bind one allowance unit to one message so a
-- retry of the same accepted message (after a failed generation, an
-- expired claim, or a reclaimed claim) reuses its original reservation
-- instead of consuming another slot. The counter alone cannot express
-- "once per message"; the receipt is the durable proof.
create table if not exists public.guest_message_receipts (
    user_id uuid not null references public.users (id) on delete cascade,
    message_id text not null,
    created_at timestamptz not null default now(),
    primary key (user_id, message_id)
);

alter table public.guest_message_receipts enable row level security;

-- Atomic guest reservation. Serializes on the guest's own user row, so
-- concurrent fresh messages cannot both take the last slot, and a retry
-- carrying an existing receipt is answered 'reused' without touching the
-- counter. Returns 'reserved' | 'reused' | 'exhausted'.
create or replace function public.reserve_guest_message(
    p_user_id uuid,
    p_message_id text,
    p_limit integer
)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
    v_count integer;
begin
    perform 1 from public.users where id = p_user_id for update;
    if not found then
        return 'exhausted';
    end if;

    if exists (
        select 1 from public.guest_message_receipts
        where user_id = p_user_id and message_id = p_message_id
    ) then
        return 'reused';
    end if;

    select guest_message_count into v_count from public.users where id = p_user_id;
    if coalesce(v_count, 0) >= p_limit then
        return 'exhausted';
    end if;

    insert into public.guest_message_receipts (user_id, message_id)
    values (p_user_id, p_message_id);

    update public.users
    set guest_message_count = coalesce(v_count, 0) + 1,
        updated_at = now()
    where id = p_user_id;

    return 'reserved';
end;
$$;
