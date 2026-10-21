-- Guest allowance receipts: bind one allowance unit to one message so a
-- retry of the same accepted message (after a failed generation, an
-- expired claim, or a reclaimed claim) reuses its original reservation
-- instead of consuming another slot. The counter alone cannot express
-- "once per message"; the receipt is the durable proof.
--
-- The receipt also carries a fingerprint of the send (chat + message
-- text). A message id recycled with different content is a different
-- send: it gets its own receipt and pays its own slot, so one id can
-- never carry unlimited distinct prompts on a single reservation.
create table if not exists public.guest_message_receipts (
    user_id uuid not null references public.users (id) on delete cascade,
    message_id text not null,
    fingerprint text not null default '',
    created_at timestamptz not null default now(),
    primary key (user_id, message_id, fingerprint)
);

alter table public.guest_message_receipts enable row level security;

-- Atomic guest reservation. Serializes on the guest's own user row, so
-- concurrent fresh messages cannot both take the last slot, and a retry
-- carrying an existing receipt is answered 'reused' without touching the
-- counter. Returns 'reserved' | 'reused' | 'exhausted'.
create or replace function public.reserve_guest_message(
    p_user_id uuid,
    p_message_id text,
    p_fingerprint text,
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
    -- Never trust the caller's bound: the allowance is a small number,
    -- and a definer function must not honor an absurd limit.
    p_limit := least(greatest(coalesce(p_limit, 0), 0), 100);

    perform 1 from public.users where id = p_user_id for update;
    if not found then
        return 'exhausted';
    end if;

    if exists (
        select 1 from public.guest_message_receipts
        where user_id = p_user_id
          and message_id = p_message_id
          and fingerprint = coalesce(p_fingerprint, '')
    ) then
        return 'reused';
    end if;

    select guest_message_count into v_count from public.users where id = p_user_id;
    if coalesce(v_count, 0) >= p_limit then
        return 'exhausted';
    end if;

    insert into public.guest_message_receipts (user_id, message_id, fingerprint)
    values (p_user_id, p_message_id, coalesce(p_fingerprint, ''));

    update public.users
    set guest_message_count = coalesce(v_count, 0) + 1,
        updated_at = now()
    where id = p_user_id;

    return 'reserved';
end;
$$;

-- A SECURITY DEFINER function inherits PostgreSQL's default PUBLIC
-- EXECUTE, which would let the anon key call it directly through
-- PostgREST and move any guest's counter. Lock it to the backend's
-- service role only, matching the other definer functions.
revoke all on function public.reserve_guest_message(uuid, text, text, integer) from public, anon, authenticated;
grant execute on function public.reserve_guest_message(uuid, text, text, integer) to service_role;
